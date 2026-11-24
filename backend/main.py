"""FastAPI application exposing Roth conversion simulation, optimization, and tax tools."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.constants import (
    CAP_GAIN_BRACKETS_MFJ,
    HISTORIC_RETURNS,
    IRMAA_BRACKETS_2026,
    ORDINARY_TAX_BRACKETS_MFJ,
    SCENARIO_PRESETS,
    SS_PROFILES,
    STD_DEDUCTION_MFJ,
    WITHDRAW_ORDERS,
)
from backend.engine import run_simulation
from backend.optimizer import (
    run_dsb_vs_rate,
    run_per_year_dtb_optimization,
    run_strategy_sweep,
)
from backend.schemas import (
    CapGainCalcRequest,
    CapGainCalcResponse,
    DsbVsRateRequest,
    DsbVsRateResponse,
    IncomeTaxCalcRequest,
    IncomeTaxCalcResponse,
    PerYearOptimizeRequest,
    PerYearOptimizeResponse,
    SimulationRequest,
    SimulationResponse,
    SweepRequest,
    SweepResponse,
)
from backend.tax import (
    capital_gain_rate,
    inverse_income_from_sum,
    inverse_income_from_tax,
    irmaa_surcharge,
    niit_tax,
    niit_taxable_gain,
    ordinary_income_tax,
    ordinary_marginal_rate,
    solve_recursive_cgr,
    solve_recursive_tax,
)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title="Roth Conversion & Retirement Strategy Planner",
    description="80-year retirement cash-flow, tax-bracket Roth conversion, and optimization API.",
    version="3.0.0",
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def _build_historic_stats() -> dict[str, object]:
    """Compute cumulative growth and 10y/20y/30y CAGRs from 1996-2025 historic returns."""
    n = len(HISTORIC_RETURNS)

    def cagr(key: str, last_k: int) -> float:
        factor = 1.0
        for row in HISTORIC_RETURNS[n - last_k :]:
            factor *= 1.0 + float(row[key])
        return factor ** (1.0 / last_k) - 1.0

    return {
        "rows": list(HISTORIC_RETURNS),
        "cagr": {
            "10y": {k: cagr(k, 10) for k in ("sp500", "djia", "nasdaq100")},
            "20y": {k: cagr(k, 20) for k in ("sp500", "djia", "nasdaq100")},
            "30y": {k: cagr(k, 30) for k in ("sp500", "djia", "nasdaq100")},
        },
    }


@app.get("/", include_in_schema=False)
def read_index() -> FileResponse:
    """Serve the single-page frontend application."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness health check."""
    return {"status": "ok", "version": "3.0.0"}


@app.get("/api/config")
def get_config() -> dict[str, object]:
    """Return presets, withdrawal orders, SS profiles, 2026 tax/IRMAA schedules, and historic rates."""
    return {
        "standard_deduction_mfj": STD_DEDUCTION_MFJ,
        "withdraw_orders": list(WITHDRAW_ORDERS),
        "presets": SCENARIO_PRESETS,
        "ss_profiles": {
            name: {
                "label": info["label"],
                "description": info["description"],
            }
            for name, info in SS_PROFILES.items()
        },
        "ordinary_brackets_mfj": [
            {
                "lower": b[0],
                "upper": b[1],
                "rate": b[2],
                "base_tax": b[3],
            }
            for b in ORDINARY_TAX_BRACKETS_MFJ
        ],
        "cap_gain_brackets_mfj": [
            {"lower": b[0], "upper": b[1], "rate": b[2]} for b in CAP_GAIN_BRACKETS_MFJ
        ],
        "irmaa_brackets_2026": list(IRMAA_BRACKETS_2026),
        "historic_returns": _build_historic_stats(),
    }


@app.post("/api/simulate", response_model=SimulationResponse)
def simulate(req: SimulationRequest) -> SimulationResponse:
    """Run an 80-year retirement projection and Roth conversion strategy."""
    return run_simulation(req)


@app.post("/api/optimize/sweep", response_model=SweepResponse)
def optimize_sweep(req: SweepRequest) -> SweepResponse:
    """Run 3-stage (100k -> 10k -> 1k) DTB sweep across withdrawal orders."""
    return run_strategy_sweep(req)


@app.post("/api/optimize/per-year-dtb", response_model=PerYearOptimizeResponse)
def optimize_per_year_dtb(req: PerYearOptimizeRequest) -> PerYearOptimizeResponse:
    """Optimize each year's DTB independently until 401(k) balance depletes."""
    return run_per_year_dtb_optimization(req)


@app.post("/api/optimize/dsb-vs-rate", response_model=DsbVsRateResponse)
def optimize_dsb_vs_rate(req: DsbVsRateRequest) -> DsbVsRateResponse:
    """Find max sustainable spending budget (DSB) across return rates 0%-10%."""
    return run_dsb_vs_rate(req)


@app.post("/api/calculators/income-tax", response_model=IncomeTaxCalcResponse)
def calc_income_tax(req: IncomeTaxCalcRequest) -> IncomeTaxCalcResponse:
    """Forward, inverse, and recursive federal ordinary income tax calculator."""
    ded = STD_DEDUCTION_MFJ if req.apply_std_deduction else 0.0

    if req.mode == "forward":
        gross = req.amount
        tax = ordinary_income_tax(gross, apply_std_deduction=req.apply_std_deduction)
        marginal = ordinary_marginal_rate(gross, apply_std_deduction=req.apply_std_deduction)
        income_plus_tax = gross + tax
    elif req.mode == "inverse_sum":
        income_plus_tax = req.amount
        gross, tax, marginal = inverse_income_from_sum(
            income_plus_tax, apply_std_deduction=req.apply_std_deduction
        )
    elif req.mode == "inverse_tax":
        tax = req.amount
        gross, marginal = inverse_income_from_tax(
            tax, apply_std_deduction=req.apply_std_deduction
        )
        income_plus_tax = gross + tax
    else:  # recursive_formula1
        tax = solve_recursive_tax(req.amount, clamp_min_std_ded=True)
        gross = req.amount + tax
        marginal = ordinary_marginal_rate(gross, apply_std_deduction=True)
        income_plus_tax = gross

    taxable = max(0.0, gross - ded)
    eff = (tax / gross) if gross > 0.0 else 0.0
    irmaa = irmaa_surcharge(gross, "MFJ", num_enrolled=req.num_enrolled_medicare)

    return IncomeTaxCalcResponse(
        mode=req.mode,
        gross_income=gross,
        taxable_income=taxable,
        federal_tax=tax,
        income_plus_tax=income_plus_tax,
        effective_rate=eff,
        marginal_rate=marginal,
        irmaa_tier=int(irmaa["tier"]),
        irmaa_label=str(irmaa["label"]),
        irmaa_annual_surcharge=float(irmaa["annual_total"]),
    )


@app.post("/api/calculators/capital-gains", response_model=CapGainCalcResponse)
def calc_capital_gains(req: CapGainCalcRequest) -> CapGainCalcResponse:
    """Capital gains + 3.8% NIIT calculator with optional recursive withdrawal gross-up."""
    ded = STD_DEDUCTION_MFJ if req.apply_std_deduction else 0.0

    if req.solve_recursive:
        cgr = solve_recursive_cgr(req.ordinary_income, req.desired_withdrawal, req.cgp)
        grossed_up = req.desired_withdrawal / (1.0 - req.cgp * cgr)
        cap_gain = req.capital_gain + grossed_up * req.cgp
        gross = req.ordinary_income + cap_gain
        niit_taxable = niit_taxable_gain(gross, cap_gain)
        niit = niit_taxable * 0.038 / (1.0 - req.cgp * cgr)
        cg_tax = cap_gain * cgr
    else:
        grossed_up = None
        cap_gain = req.capital_gain
        gross = req.ordinary_income + cap_gain
        cgr = capital_gain_rate(gross, apply_std_deduction=req.apply_std_deduction)
        cg_tax = cap_gain * cgr
        niit_taxable = niit_taxable_gain(gross, cap_gain)
        niit = niit_tax(gross, cap_gain)

    return CapGainCalcResponse(
        ordinary_income=req.ordinary_income,
        capital_gain=cap_gain,
        gross_income=gross,
        taxable_income=max(0.0, gross - ded),
        cap_gain_tax_rate=cgr,
        cap_gain_tax=cg_tax,
        niit_taxable_gain=niit_taxable,
        niit_tax=niit,
        total_cap_gain_and_niit_tax=cg_tax + niit,
        grossed_up_withdrawal=grossed_up,
    )
