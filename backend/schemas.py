"""Pydantic v2 request and response schemas for the Roth Conversion API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

WithdrawOrder = Literal[
    "BRKG-ROTH-401K",
    "BRKG-401K-ROTH",
    "401K-BRKG-ROTH",
    "401K-ROTH-BRKG",
    "ROTH-BRKG-401K",
    "ROTH-401K-BRKG",
]


class CustomIncomeRow(BaseModel):
    """Optional year-specific income components."""

    year_index: int = Field(..., ge=1, le=80)
    wage: float = Field(0.0, ge=0.0)
    deferred_comp_1: float = Field(0.0, ge=0.0)
    deferred_comp_2: float = Field(0.0, ge=0.0)
    ss_primary: float = Field(0.0, ge=0.0)
    ss_secondary: float = Field(0.0, ge=0.0)
    other_income: float = Field(0.0, ge=0.0)


class CustomSSConfig(BaseModel):
    """Simplified custom Social Security and wage schedule generator."""

    primary_start_age: int = Field(67, ge=62, le=75)
    primary_annual: float = Field(50000.0, ge=0.0)
    secondary_start_age: int = Field(67, ge=62, le=75)
    secondary_annual: float = Field(50000.0, ge=0.0)
    wage_annual: float = Field(0.0, ge=0.0)
    wage_end_age: int = Field(66, ge=40, le=90)


class SimulationRequest(BaseModel):
    """Input assumptions for an 80-year retirement and Roth conversion simulation."""

    primary_age: int = Field(66, ge=40, le=100)
    secondary_age: int = Field(65, ge=40, le=100)
    brkg_balance: float = Field(1000000.0, ge=0.0)
    brkg_rate: float = Field(0.035, ge=-0.5, le=0.5)
    brkg_gain_pct: float = Field(0.7, ge=0.0, le=1.0)
    brkg_turnover_rate: float = Field(0.3, ge=0.0, le=1.0)
    primary_401k_balance: float = Field(1200000.0, ge=0.0)
    secondary_401k_balance: float = Field(600000.0, ge=0.0)
    k401_rate: float = Field(0.035, ge=-0.5, le=0.5)
    roth_balance: float = Field(200000.0, ge=0.0)
    roth_rate: float = Field(0.035, ge=-0.5, le=0.5)
    dsb: float = Field(200000.0, ge=0.0)
    dtb: float = Field(177000.0, ge=0.0)
    withdraw_order: WithdrawOrder = "401K-ROTH-BRKG"
    eval_age: int = Field(96, ge=67, le=140)
    ss_profile: str = "Profile 1"
    custom_ss: Optional[CustomSSConfig] = None
    custom_incomes: Optional[list[CustomIncomeRow]] = None
    dtb_overrides: Optional[dict[int, float]] = None
    inflation_rate: float = Field(0.0, ge=0.0, le=0.2, description="Annual inflation applied to spending, DTB, income, brackets, IRMAA")
    base_year: int = Field(2025, ge=2025, le=2100, description="Calendar year of Year 0")
    legacy_excel_rmd: bool = Field(False, description="Use the workbook's shifted 1951-1959 RMD table")

    @model_validator(mode="after")
    def _check_eval_age(self) -> "SimulationRequest":
        if self.eval_age > self.primary_age + 80:
            raise ValueError("eval_age cannot exceed primary_age + 80 (simulation horizon)")
        return self


class YearProjection(BaseModel):
    """Single-year simulation output (Year 0 through Year 80)."""

    year_index: int
    year: int
    primary_age: int
    secondary_age: int
    earned_income: float
    dtb_applied: float
    brkg_cashflow: float
    brkg_balance: float
    brkg_cgp: float
    k401_total_wd: float
    k401_rmd: float
    k401_conv_wd: float
    k401_vol_wd: float
    k401_primary_balance: float
    k401_secondary_balance: float
    k401_balance: float
    k401_overdraft: float
    roth_conv_deposit: float
    roth_wd: float
    roth_balance: float
    net_worth: float
    actual_spending: float
    ordinary_income: float
    ordinary_tax: float
    ordinary_marginal_rate: float
    capital_gains: float
    gross_income: float
    cap_gain_tax_rate: float
    cap_gain_tax: float
    niit_tax: float
    total_tax: float
    effective_tax_rate: float
    acc_spending: float
    acc_tax: float
    acc_tax_tv: float
    acc_cg_tax: float
    acc_cg_tax_tv: float
    net_worth_change: float
    total_expense: float
    total_funding: float
    funding_diff: float
    irmaa_tier: int
    irmaa_annual_surcharge: float


class SimulationSummary(BaseModel):
    """Headline KPIs for an 80-year simulation."""

    net_worth_year0: float
    year0_return: float
    eval_age: int
    net_worth_at_eval: float
    acc_tax_at_eval: float
    acc_tax_tv_at_eval: float
    acc_cg_tax_tv_at_eval: float
    total_roth_converted: float
    shortfall_age: Optional[int]
    shortfall_year_index: Optional[int]
    depletion_age: Optional[int]
    peak_irmaa_tier: int
    total_irmaa_surcharge: float
    withdraw_order: str


class SimulationResponse(BaseModel):
    """Full response returned by POST /api/simulate."""

    summary: SimulationSummary
    quick_summary: list[YearProjection]
    projections: list[YearProjection]


class SweepRequest(SimulationRequest):
    """Multi-order 3-stage DTB sweep request."""

    dtb_min: float = Field(0.0, ge=0.0)
    dtb_max: float = Field(2000000.0, ge=0.0)
    coarse_step: float = Field(100000.0, gt=0.0)
    mid_step: float = Field(10000.0, gt=0.0)
    fine_step: float = Field(1000.0, gt=0.0)
    withdraw_orders: Optional[list[WithdrawOrder]] = None


class SweepPoint(BaseModel):
    """Single evaluated DTB point for one withdrawal order."""

    withdraw_order: str
    stage: Literal["Coarse", "10k", "1k"]
    dtb: float
    net_worth: float
    acc_tax_tv: float
    acc_cg_tax_tv: float
    total_roth_converted: float


class OrderSweepSummary(BaseModel):
    """Ranked best DTB outcome for a single withdrawal order."""

    rank: int
    withdraw_order: str
    best_dtb: float
    net_worth_at_eval: float
    acc_tax_tv: float
    acc_cg_tax_tv: float
    total_roth_converted: float


class SweepResponse(BaseModel):
    """Response for 3-stage multi-order sweep."""

    eval_age: int
    net_worth_year0: float
    total_evaluations: int
    elapsed_ms: float
    mean_ms_per_eval: float
    summaries: list[OrderSweepSummary]
    curves: dict[str, list[SweepPoint]]


class PerYearOptimizeRequest(SimulationRequest):
    """Per-year DTB coordinate ascent request (prompt2)."""

    delta: float = Field(50000.0, gt=0.0)
    step: float = Field(5000.0, gt=0.0)
    max_passes: int = Field(2, ge=1, le=5)


class PerYearOptimizeResponse(BaseModel):
    """Per-year DTB coordinate ascent response."""

    eval_age: int
    baseline_net_worth: float
    optimized_net_worth: float
    net_worth_gain: float
    total_evaluations: int
    elapsed_ms: float
    optimized_dtb_by_year: dict[int, float]
    optimized_simulation: SimulationResponse


class DsbVsRateRequest(SimulationRequest):
    """Sustainable DSB vs Uniform Return Rate sensitivity request."""

    rate_min: float = Field(0.0, ge=-0.1, le=0.25)
    rate_max: float = Field(0.10, ge=-0.1, le=0.25)
    rate_step: float = Field(0.005, gt=0.0)
    dsb_min: float = Field(100000.0, ge=0.0)
    dsb_max: float = Field(1500000.0, gt=0.0)
    dsb_step: float = Field(10000.0, gt=0.0)
    dtb_min: float = Field(0.0, ge=0.0)
    dtb_max: float = Field(800000.0, gt=0.0)
    dtb_step: float = Field(20000.0, gt=0.0)
    min_net_worth: float = Field(1000.0, ge=0.0)


class DsbVsRatePoint(BaseModel):
    """Maximum sustainable DSB at a given portfolio return rate."""

    return_rate: float
    max_dsb: float
    optimal_dtb: float
    net_worth_at_eval: float
    acc_tax_tv: float


class DsbVsRateResponse(BaseModel):
    """Response for DSB vs Return Rate sensitivity sweep."""

    eval_age: int
    withdraw_order: str
    total_evaluations: int
    elapsed_ms: float
    points: list[DsbVsRatePoint]


class IncomeTaxCalcRequest(BaseModel):
    """Input for Tax & Income Calculator tool."""

    mode: Literal["forward", "inverse_sum", "inverse_tax", "recursive_formula1"]
    amount: float = Field(..., ge=0.0)
    apply_std_deduction: bool = True
    num_enrolled_medicare: int = Field(2, ge=0, le=2)


class IncomeTaxCalcResponse(BaseModel):
    """Output from Tax & Income Calculator tool."""

    mode: str
    gross_income: float
    taxable_income: float
    federal_tax: float
    income_plus_tax: float
    effective_rate: float
    marginal_rate: float
    irmaa_tier: int
    irmaa_label: str
    irmaa_annual_surcharge: float


class CapGainCalcRequest(BaseModel):
    """Input for Capital Gain & NIIT Calculator tool."""

    ordinary_income: float = Field(..., ge=0.0)
    capital_gain: float = Field(0.0, ge=0.0)
    apply_std_deduction: bool = True
    solve_recursive: bool = False
    desired_withdrawal: float = Field(0.0, ge=0.0)
    cgp: float = Field(0.3, ge=0.0, le=1.0)


class CapGainCalcResponse(BaseModel):
    """Output from Capital Gain & NIIT Calculator tool."""

    ordinary_income: float
    capital_gain: float
    gross_income: float
    taxable_income: float
    cap_gain_tax_rate: float
    cap_gain_tax: float
    niit_taxable_gain: float
    niit_tax: float
    total_cap_gain_and_niit_tax: float
    grossed_up_withdrawal: Optional[float] = None
