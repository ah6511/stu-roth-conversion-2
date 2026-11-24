"""Optimization engines for multi-order DTB sweeps, per-year DTB fine-tuning, and DSB vs Rate."""

from __future__ import annotations

import time

from backend.constants import SIMULATION_YEARS, WITHDRAW_ORDERS
from backend.engine import build_income_schedule, fast_evaluate, run_simulation
from backend.schemas import (
    DsbVsRatePoint,
    DsbVsRateRequest,
    DsbVsRateResponse,
    OrderSweepSummary,
    PerYearOptimizeRequest,
    PerYearOptimizeResponse,
    SimulationRequest,
    SweepPoint,
    SweepRequest,
    SweepResponse,
)


def _frange_inclusive(start: float, stop: float, step: float) -> list[float]:
    vals: list[float] = []
    cur = start
    while cur <= stop + 1e-9:
        vals.append(round(cur, 6))
        cur += step
    return vals


def run_strategy_sweep(req: SweepRequest) -> SweepResponse:
    """3-stage (Coarse -> 10k -> 1k) DTB sweep across withdrawal orders (Prompt1 / DataPage2)."""
    t0 = time.perf_counter()
    orders = list(req.withdraw_orders or WITHDRAW_ORDERS)
    income_schedule = build_income_schedule(req)

    # Clear per-year overrides when sweeping uniform DTB
    base_data = req.model_dump(
        exclude={
            "dtb_min",
            "dtb_max",
            "coarse_step",
            "mid_step",
            "fine_step",
            "withdraw_orders",
            "dtb_overrides",
        }
    )

    total_evals = 0
    curves: dict[str, list[SweepPoint]] = {}
    best_per_order: list[dict[str, float | str]] = []

    for wo in orders:
        sim_req = SimulationRequest(**{**base_data, "withdraw_order": wo})
        evaluated: dict[float, SweepPoint] = {}

        def eval_dtb(dtb_val: float, stage: str) -> SweepPoint:
            nonlocal total_evals
            key = round(dtb_val, 2)
            sim_req.dtb = key
            nw, aq, as_val, roth_conv, _ = fast_evaluate(
                sim_req,
                income_schedule=income_schedule,
                dtb_overrides={},
            )
            total_evals += 1
            pt = SweepPoint(
                withdraw_order=wo,
                stage=stage,  # type: ignore[arg-type]
                dtb=key,
                net_worth=nw,
                acc_tax_tv=aq,
                acc_cg_tax_tv=as_val,
                total_roth_converted=roth_conv,
            )
            evaluated[key] = pt
            return pt

        # Stage 1: Coarse grid
        coarse_pts = [eval_dtb(d, "Coarse") for d in _frange_inclusive(req.dtb_min, req.dtb_max, req.coarse_step)]
        top3 = sorted(coarse_pts, key=lambda p: p.net_worth, reverse=True)[:3]
        min_top3 = min(p.dtb for p in top3)
        max_top3 = max(p.dtb for p in top3)

        # Stage 2: 10k refinement around top-3 window
        s2_start = max(req.dtb_min, min_top3 - req.coarse_step)
        s2_end = min(req.dtb_max, max_top3 + req.coarse_step)
        for d in _frange_inclusive(s2_start, s2_end, req.mid_step):
            eval_dtb(d, "10k")

        # Stage 3: 1k fine search around overall best from Stages 1 & 2
        best_mid = max(evaluated.values(), key=lambda p: p.net_worth)
        s3_start = max(req.dtb_min, best_mid.dtb - req.mid_step)
        s3_end = min(req.dtb_max, best_mid.dtb + req.mid_step)
        for d in _frange_inclusive(s3_start, s3_end, req.fine_step):
            eval_dtb(d, "1k")

        ordered_pts = sorted(evaluated.values(), key=lambda p: p.dtb)
        curves[wo] = ordered_pts

        best_pt = max(ordered_pts, key=lambda p: p.net_worth)
        best_per_order.append(
            {
                "withdraw_order": wo,
                "best_dtb": best_pt.dtb,
                "net_worth_at_eval": best_pt.net_worth,
                "acc_tax_tv": best_pt.acc_tax_tv,
                "acc_cg_tax_tv": best_pt.acc_cg_tax_tv,
                "total_roth_converted": best_pt.total_roth_converted,
            }
        )

    ranked = sorted(best_per_order, key=lambda x: float(x["net_worth_at_eval"]), reverse=True)
    summaries = [
        OrderSweepSummary(
            rank=idx + 1,
            withdraw_order=str(item["withdraw_order"]),
            best_dtb=float(item["best_dtb"]),
            net_worth_at_eval=float(item["net_worth_at_eval"]),
            acc_tax_tv=float(item["acc_tax_tv"]),
            acc_cg_tax_tv=float(item["acc_cg_tax_tv"]),
            total_roth_converted=float(item["total_roth_converted"]),
        )
        for idx, item in enumerate(ranked)
    ]

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    nw_yr0 = (
        req.brkg_balance
        + req.primary_401k_balance
        + req.secondary_401k_balance
        + req.roth_balance
    )
    return SweepResponse(
        eval_age=req.eval_age,
        net_worth_year0=nw_yr0,
        total_evaluations=total_evals,
        elapsed_ms=elapsed_ms,
        mean_ms_per_eval=(elapsed_ms / total_evals) if total_evals else 0.0,
        summaries=summaries,
        curves=curves,
    )


def run_per_year_dtb_optimization(req: PerYearOptimizeRequest) -> PerYearOptimizeResponse:
    """Coordinate ascent optimizing each year's DTB until 401(k) balance depletes (prompt2)."""
    t0 = time.perf_counter()
    income_schedule = build_income_schedule(req)
    sim_data = req.model_dump(exclude={"delta", "step", "max_passes"})
    sim_req = SimulationRequest(**sim_data)

    base_overrides: dict[int, float] = {
        yr: (req.dtb_overrides[yr] if req.dtb_overrides and yr in req.dtb_overrides else req.dtb)
        for yr in range(1, SIMULATION_YEARS + 1)
    }

    best_nw, _, _, _, k401_end = fast_evaluate(
        sim_req,
        income_schedule=income_schedule,
        dtb_overrides=base_overrides,
    )
    baseline_nw = best_nw
    total_evals = 1

    overrides = dict(base_overrides)
    eval_yr = max(1, min(SIMULATION_YEARS, req.eval_age - req.primary_age))

    for _ in range(req.max_passes):
        improved = False
        for yr in range(1, eval_yr + 1):
            # Stop once 401(k) balance has already depleted prior to this year
            if yr > 1 and k401_end[yr - 2] <= 1e-6:
                break

            current_dtb = overrides[yr]
            low = max(0.0, current_dtb - req.delta)
            high = current_dtb + req.delta
            candidates = _frange_inclusive(low, high, req.step)
            if 0.0 not in candidates:
                candidates.insert(0, 0.0)

            best_yr_dtb = current_dtb
            best_yr_nw = best_nw
            best_yr_k401 = k401_end

            for cand in candidates:
                if abs(cand - current_dtb) < 1e-6:
                    continue
                overrides[yr] = cand
                nw, _, _, _, cand_k401 = fast_evaluate(
                    sim_req,
                    income_schedule=income_schedule,
                    dtb_overrides=overrides,
                )
                total_evals += 1
                if nw > best_yr_nw + 1e-6:
                    best_yr_nw = nw
                    best_yr_dtb = cand
                    best_yr_k401 = cand_k401
                    improved = True

            overrides[yr] = best_yr_dtb
            best_nw = best_yr_nw
            k401_end = best_yr_k401

        if not improved:
            break

    optimized_req = SimulationRequest(**{**sim_data, "dtb_overrides": overrides})
    optimized_sim = run_simulation(optimized_req)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return PerYearOptimizeResponse(
        eval_age=req.eval_age,
        baseline_net_worth=baseline_nw,
        optimized_net_worth=optimized_sim.summary.net_worth_at_eval,
        net_worth_gain=optimized_sim.summary.net_worth_at_eval - baseline_nw,
        total_evaluations=total_evals,
        elapsed_ms=elapsed_ms,
        optimized_dtb_by_year=overrides,
        optimized_simulation=optimized_sim,
    )


def run_dsb_vs_rate(req: DsbVsRateRequest) -> DsbVsRateResponse:
    """Find max sustainable DSB for each portfolio return rate (prompt2)."""
    t0 = time.perf_counter()
    income_schedule = build_income_schedule(req)
    base_data = req.model_dump(
        exclude={
            "rate_min",
            "rate_max",
            "rate_step",
            "dsb_min",
            "dsb_max",
            "dsb_step",
            "dtb_min",
            "dtb_max",
            "dtb_step",
            "min_net_worth",
            "dtb_overrides",
        }
    )

    rates = _frange_inclusive(req.rate_min, req.rate_max, req.rate_step)
    dsb_grid = _frange_inclusive(req.dsb_min, req.dsb_max, req.dsb_step)
    dtb_grid = _frange_inclusive(req.dtb_min, req.dtb_max, req.dtb_step)

    total_evals = 0
    points: list[DsbVsRatePoint] = []

    for rate in rates:
        sim_req = SimulationRequest(
            **{
                **base_data,
                "brkg_rate": rate,
                "k401_rate": rate,
                "roth_rate": rate,
                "dtb_overrides": None,
            }
        )

        def best_for_dsb(dsb_val: float, early_exit: bool) -> tuple[bool, float, float, float]:
            nonlocal total_evals
            sim_req.dsb = dsb_val
            best_nw = -1.0
            best_dtb = dtb_grid[0]
            best_aq = 0.0
            for dtb_val in dtb_grid:
                sim_req.dtb = dtb_val
                nw, aq, _, _, _ = fast_evaluate(
                    sim_req,
                    income_schedule=income_schedule,
                    dtb_overrides={},
                )
                total_evals += 1
                if nw > best_nw:
                    best_nw = nw
                    best_dtb = dtb_val
                    best_aq = aq
                if early_exit and nw > req.min_net_worth:
                    return True, best_dtb, best_nw, best_aq
            return (best_nw > req.min_net_worth), best_dtb, best_nw, best_aq

        lo, hi = 0, len(dsb_grid) - 1
        best_idx = -1
        while lo <= hi:
            mid = (lo + hi) // 2
            feasible, _, _, _ = best_for_dsb(dsb_grid[mid], early_exit=True)
            if feasible:
                best_idx = mid
                lo = mid + 1
            else:
                hi = mid - 1

        if best_idx >= 0:
            chosen_dsb = dsb_grid[best_idx]
            _, opt_dtb, opt_nw, opt_aq = best_for_dsb(chosen_dsb, early_exit=False)
        else:
            chosen_dsb = dsb_grid[0]
            _, opt_dtb, opt_nw, opt_aq = best_for_dsb(chosen_dsb, early_exit=False)

        points.append(
            DsbVsRatePoint(
                return_rate=rate,
                max_dsb=chosen_dsb,
                optimal_dtb=opt_dtb,
                net_worth_at_eval=opt_nw,
                acc_tax_tv=opt_aq,
            )
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return DsbVsRateResponse(
        eval_age=req.eval_age,
        withdraw_order=req.withdraw_order,
        total_evaluations=total_evals,
        elapsed_ms=elapsed_ms,
        points=points,
    )
