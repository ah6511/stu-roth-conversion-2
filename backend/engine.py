"""Core 80-year retirement & Roth conversion simulation engine (model3 logic)."""

from __future__ import annotations

from typing import Optional

from backend.constants import (
    LEGACY_BRKG_WITHDRAW_YEARS,
    NIIT_RATE,
    SIMULATION_YEARS,
    SS_PROFILES,
)
from backend.schemas import (
    SimulationRequest,
    SimulationResponse,
    SimulationSummary,
    YearProjection,
)
from backend.tax import (
    capital_gain_rate as _capital_gain_rate,
    irmaa_surcharge,
    niit_taxable_gain,
    ordinary_income_tax as _ordinary_income_tax,
    ordinary_marginal_rate_model3,
    rmd_divisor,
    solve_recursive_cgr,
    solve_recursive_tax as _solve_recursive_tax,
)


def build_income_schedule(req: SimulationRequest) -> list[float]:
    """Build the 80-year earned + Social Security income schedule (Years 1..80)."""
    if req.custom_ss is not None:
        cfg = req.custom_ss
        schedule = []
        for yr in range(1, SIMULATION_YEARS + 1):
            p_age = req.primary_age + yr
            s_age = req.secondary_age + yr
            wage = cfg.wage_annual if p_age <= cfg.wage_end_age else 0.0
            ss1 = cfg.primary_annual if p_age >= cfg.primary_start_age else 0.0
            ss2 = cfg.secondary_annual if s_age >= cfg.secondary_start_age else 0.0
            schedule.append(wage + ss1 + ss2)
    else:
        profile = SS_PROFILES.get(req.ss_profile, SS_PROFILES["None"])
        ss_pairs: list[tuple[float, float]] = profile["schedule"]  # type: ignore[assignment]
        schedule = [p + s for p, s in ss_pairs]

    if req.custom_incomes:
        for row in req.custom_incomes:
            idx = row.year_index - 1
            if 0 <= idx < SIMULATION_YEARS:
                schedule[idx] = (
                    row.wage
                    + row.deferred_comp_1
                    + row.deferred_comp_2
                    + row.ss_primary
                    + row.ss_secondary
                    + row.other_income
                )
    return schedule


def _run_core(
    req: SimulationRequest,
    income_schedule: Optional[list[float]] = None,
    dtb_overrides: Optional[dict[int, float]] = None,
    collect_rows: bool = True,
) -> tuple[float, float, float, float, list[float], list[YearProjection]]:
    """Execute the 80-year simulation and return summary metrics + optional row projections.

    Returns:
        (net_worth_at_eval, acc_tax_tv_at_eval, acc_cg_tax_tv_at_eval,
         total_roth_converted, k401_end_by_year, rows)
    """
    if income_schedule is None:
        income_schedule = build_income_schedule(req)

    overrides = dtb_overrides if dtb_overrides is not None else (req.dtb_overrides or {})

    c4 = req.primary_age
    d4 = req.secondary_age
    base_year = req.base_year
    infl = req.inflation_rate
    legacy_rmd = req.legacy_excel_rmd
    p_birth_year = base_year - c4
    s_birth_year = base_year - d4

    e4 = req.brkg_balance
    f4 = req.brkg_rate
    g4 = req.brkg_gain_pct
    h4 = req.brkg_turnover_rate
    i4 = req.primary_401k_balance
    j4 = req.secondary_401k_balance
    k4 = req.k401_rate
    l4 = req.roth_balance
    m4 = req.roth_rate
    n4 = req.dsb
    o4 = req.dtb
    order = req.withdraw_order.split("-")
    o0, o1, o2 = order[0], order[1], order[2]

    eval_yr = max(0, min(SIMULATION_YEARS, req.eval_age - c4))

    # Year 0 (2025) initial balances
    fn_prev = i4
    fw_prev = j4
    ge_prev = i4 + j4
    gd_prev = 0.0

    hj20 = g4
    hz_prev = e4
    ib_prev = e4 * (1.0 - hj20)
    ic_prev = e4 * hj20
    id_prev = ib_prev + ic_prev

    iu_prev = l4
    nw_prev = id_prev + ge_prev + iu_prev

    aq_prev = 0.0
    as_prev = 0.0
    acc_spending = 0.0
    acc_tax = 0.0
    acc_cg_tax = 0.0
    total_roth_converted = 0.0

    avg_rate = (f4 + k4 + m4) / 3.0

    k401_end_by_year: list[float] = []
    rows: list[YearProjection] = []

    if collect_rows:
        rows.append(
            YearProjection(
                year_index=0,
                year=base_year,
                primary_age=c4,
                secondary_age=d4,
                earned_income=0.0,
                dtb_applied=o4,
                brkg_cashflow=0.0,
                brkg_balance=id_prev,
                brkg_cgp=g4,
                k401_total_wd=0.0,
                k401_rmd=0.0,
                k401_conv_wd=0.0,
                k401_vol_wd=0.0,
                k401_primary_balance=fn_prev,
                k401_secondary_balance=fw_prev,
                k401_balance=ge_prev,
                k401_overdraft=0.0,
                roth_conv_deposit=0.0,
                roth_wd=0.0,
                roth_balance=iu_prev,
                net_worth=nw_prev,
                actual_spending=0.0,
                ordinary_income=0.0,
                ordinary_tax=0.0,
                ordinary_marginal_rate=0.0,
                capital_gains=0.0,
                gross_income=0.0,
                cap_gain_tax_rate=0.0,
                cap_gain_tax=0.0,
                niit_tax=0.0,
                total_tax=0.0,
                effective_tax_rate=0.0,
                acc_spending=0.0,
                acc_tax=0.0,
                acc_tax_tv=0.0,
                acc_cg_tax=0.0,
                acc_cg_tax_tv=0.0,
                net_worth_change=0.0,
                total_expense=0.0,
                total_funding=0.0,
                funding_diff=0.0,
                irmaa_tier=1,
                irmaa_annual_surcharge=0.0,
            )
        )

    nw_eval = nw_prev
    aq_eval = 0.0
    as_eval = 0.0

    for yr in range(1, SIMULATION_YEARS + 1):
        p_age = c4 + yr
        s_age = d4 + yr
        k = (1.0 + infl) ** yr  # inflation index (1.0 when inflation_rate == 0)
        ba = income_schedule[yr - 1] * k

        def ordinary_income_tax(x: float) -> float:
            return k * _ordinary_income_tax(x / k)

        def solve_recursive_tax(x: float, clamp_min_std_ded: bool = True) -> float:
            return k * _solve_recursive_tax(x / k, clamp_min_std_ded)

        def capital_gain_rate(x: float) -> float:
            return _capital_gain_rate(x / k)


        # Step A: 401(k) BOY balances & RMD lookahead
        fg = max(fn_prev, 0.0)
        fi = fg * k4
        fj = rmd_divisor(p_age, p_birth_year, legacy_rmd)
        fk = 0.0 if fj == 0.0 else fg / fj

        fp = max(fw_prev, 0.0)
        fr = fp * k4
        fs = rmd_divisor(s_age, s_birth_year, legacy_rmd)
        ft = 0.0 if fs == 0.0 else fp / fs

        fy = fg + fp
        ga = fk + ft

        # Step B: Spending budget & withdrawal order allocation
        bc = ba + ga  # INC1 = EI + RMD
        bd = n4 * k   # DSB (inflated)
        bq = id_prev * (1.0 + f4)
        br = ge_prev * (1.0 + k4)
        bs = iu_prev * (1.0 + m4)
        be = bq + br + bs

        bf = ordinary_income_tax(bc)
        bg = min(be + bc - bf, bd)  # Actual Spending Budget (ASB)
        bi = gd_prev
        bh = min(be, max(bd - bc + bf, 0.0)) - bi  # Demand withdraw (DWD1)
        bl = max(bc - bd - bf, 0.0)  # Surplus income deposit to brokerage

        if o0 == "BRKG":
            bt, cap0 = bq, (min(1.0, bq / bh) if bh != 0.0 else 0.0)
        elif o0 == "401K":
            bt, cap0 = br, (min(1.0, br / bh) if bh != 0.0 else 0.0)
        else:
            bt, cap0 = bs, (min(1.0, bs / bh) if bh != 0.0 else 0.0)

        if o1 == "BRKG":
            bu, cap1 = bq, (min(1.0, bq / bh) if bh != 0.0 else 0.0)
        elif o1 == "401K":
            bu, cap1 = br, (min(1.0, br / bh) if bh != 0.0 else 0.0)
        else:
            bu, cap1 = bs, (min(1.0, bs / bh) if bh != 0.0 else 0.0)

        if o2 == "BRKG":
            bv, cap2 = bq, (min(1.0, bq / bh) if bh != 0.0 else 0.0)
        elif o2 == "401K":
            bv, cap2 = br, (min(1.0, br / bh) if bh != 0.0 else 0.0)
        else:
            bv, cap2 = bs, (min(1.0, bs / bh) if bh != 0.0 else 0.0)

        co = cap0
        if cap0 + cap1 >= 1.0:
            cp = 1.0 - cap0
            cq = 0.0
        else:
            cp = cap1
            cq = min(cap2, 1.0 - cap0 - cap1)

        cr = min(max(0.0, bh * co), max(0.0, bt))
        cs = min(max(0.0, bh * cp), max(0.0, bu))
        ct = min(max(0.0, bh * cq), max(0.0, bv))

        cu = -bl
        cv = 0.0
        cw = 0.0
        if o0 == "BRKG":
            cu += cr
        elif o0 == "401K":
            cv = cr
        else:
            cw = cr

        if o1 == "BRKG":
            cu += cs
        elif o1 == "401K":
            cv = cs
        else:
            cw = cs

        if o2 == "BRKG":
            cu += ct
        elif o2 == "401K":
            cv = ct
        else:
            cw = ct

        # Step C: Roth Conversion Bracket-Filling (Stage 0 -> Stage 1 -> Stage 2)
        da = bc + cv
        de = (overrides[yr] if yr in overrides else o4) * k
        dh = min(br, de)
        di = bd if cv > 0.0 else 0.0
        dl = bc - bf
        dn = max(0.0, dl - di)

        dr = da
        dq = ordinary_income_tax(dr)
        dt = solve_recursive_tax(dr, clamp_min_std_ded=True)
        du = (dr + dt) if cv > 0.0 else dr
        dw = cv != 0.0
        dy = dh > du

        if dy:
            dz = max(dr, dh)
            ea = ordinary_income_tax(dz)
            ec = dz - ea - dr + (dq if dn > 0.0 else 0.0)
        else:
            ec = 0.0

        ed = dr + ec
        ee = solve_recursive_tax(ed, clamp_min_std_ded=False)
        ef = ee - (0.0 if dw else dq)
        if yr == 1:
            ei = (ec + ee + du) if dy else du
        else:
            ei = (ec + ef + du) if dy else du

        fc = ei
        fd = ef
        fe = ec
        total_roth_converted += fe

        # Step D: 401(k) Dual-Account Update & Overdraft Tracking
        gb = fe
        gc_req = cv + fd - (bf if cv > 0.0 else 0.0)
        gc_avail = fy * (1.0 + k4) - ga
        gc = min(gc_avail, gc_req)
        gd = 0.0 if fy == 0.0 else min(0.0, gc_avail - gc_req)

        denom_conv = fg + fp
        fl = (gb * fg / denom_conv) if denom_conv != 0.0 else 0.0
        fu = (gb * fp / denom_conv) if denom_conv != 0.0 else 0.0

        num_p = fg + fi - fk
        num_s = fp + fr - ft
        denom_oth = num_p + num_s
        fm = (gc * num_p / denom_oth) if denom_oth != 0.0 else 0.0
        fv = (gc * num_s / denom_oth) if denom_oth != 0.0 else 0.0

        fn = max(0.0, fg + fi - fk - fl - fm)
        fw = max(0.0, fp + fr - ft - fu - fv)
        ge = fn + fw
        gf = ga + gb + gc
        k401_end_by_year.append(ge)

        # Step E: Ordinary Income Tax Finalization
        gm = ordinary_income_tax(fc)

        # Step F: Brokerage Turnover, Capital Gains & NIIT
        if id_prev > 0.0:
            hc = ib_prev
            hd = hz_prev * f4
            he = ic_prev + hd
        else:
            hc = 0.0
            hd = 0.0
            he = 0.0
        hf = hc + he
        hg = 0.0 if hf == 0.0 else he / hf
        hj = hg * (1.0 - h4)
        hm = hf * h4 * hg

        gs = fc
        gt = gs + hm
        gu = max(0.0, cu)
        gw = solve_recursive_cgr(gt / k, gu / k, hj)

        gx = cu
        gy = gu
        gz = gy / (1.0 - hj * gw)
        if yr <= LEGACY_BRKG_WITHDRAW_YEARS:
            ha = gz if gz < id_prev else id_prev
        else:
            ha = gx if gx < id_prev else id_prev

        hn = gz * hj
        ho = hm + hn
        hp = max(ho + gs, 0.0)
        hs = ho * gw
        ht = niit_taxable_gain(hp, ho)
        hu = ht * NIIT_RATE / (1.0 - hj * gw)
        hv = hs + hu

        hz = hf - ha - hu
        ia = hz - min(0.0, gx)
        ib = ia * (1.0 - hj)
        ic = ia * hj
        id_bal = 0.0 if ha < gx else (ib + ic)

        # Step G: Final Tax Totals & Roth Update
        ii = gs + ho
        ij = capital_gain_rate(ii)
        ik = ho * ij
        il = niit_taxable_gain(ii, ho)
        im = il * NIIT_RATE / (1.0 - hj * gw)

        ak = ik
        al = im if yr == 1 else hu
        am = gm + ak + al

        aq = aq_prev * (1.0 + avg_rate) + am
        as_val = as_prev * (1.0 + avg_rate) + ak + al

        ip = fe
        iq = 0.0 if iu_prev <= 0.0 else iu_prev
        is_ret = 0.0 if iq < 0.0 else iq * m4
        it = cw
        iu = ip + iq + is_ret - it

        iv = id_bal + ge + iu

        if yr == eval_yr:
            nw_eval = iv
            aq_eval = aq
            as_eval = as_val

        if collect_rows:
            acc_spending += bg
            acc_tax += am
            acc_cg_tax += ak + al

            gn = ordinary_marginal_rate_model3(fc / k)
            ie_debit = gx + hv
            total_exp = bg + am
            total_fund = ba + ie_debit + ga + gc + cw
            eff_rate = (am / (ii + ho)) if yr == 1 and (ii + ho) != 0.0 else ((am / ii) if ii != 0.0 else 0.0)

            num_enrolled = (1 if p_age >= 65 else 0) + (1 if s_age >= 65 else 0)
            irmaa = irmaa_surcharge(ii / k, "MFJ", num_enrolled=num_enrolled)

            rows.append(
                YearProjection(
                    year_index=yr,
                    year=base_year + yr,
                    primary_age=p_age,
                    secondary_age=s_age,
                    earned_income=ba,
                    dtb_applied=de,
                    brkg_cashflow=-ie_debit,
                    brkg_balance=id_bal,
                    brkg_cgp=hj,
                    k401_total_wd=-gf,
                    k401_rmd=-ga,
                    k401_conv_wd=-gb,
                    k401_vol_wd=-gc,
                    k401_primary_balance=fn,
                    k401_secondary_balance=fw,
                    k401_balance=ge,
                    k401_overdraft=gd,
                    roth_conv_deposit=ip,
                    roth_wd=-it,
                    roth_balance=iu,
                    net_worth=iv,
                    actual_spending=bg,
                    ordinary_income=gs,
                    ordinary_tax=gm,
                    ordinary_marginal_rate=gn,
                    capital_gains=ho,
                    gross_income=ii,
                    cap_gain_tax_rate=ij,
                    cap_gain_tax=ak,
                    niit_tax=al,
                    total_tax=am,
                    effective_tax_rate=eff_rate,
                    acc_spending=acc_spending,
                    acc_tax=acc_tax,
                    acc_tax_tv=aq,
                    acc_cg_tax=acc_cg_tax,
                    acc_cg_tax_tv=as_val,
                    net_worth_change=iv - nw_prev,
                    total_expense=total_exp,
                    total_funding=total_fund,
                    funding_diff=total_fund - total_exp,
                    irmaa_tier=int(irmaa["tier"]),
                    irmaa_annual_surcharge=float(irmaa["annual_total"]),
                )
            )

        fn_prev, fw_prev, ge_prev, gd_prev = fn, fw, ge, gd
        hz_prev, ib_prev, ic_prev, id_prev = hz, ib, ic, id_bal
        iu_prev = iu
        nw_prev = iv
        aq_prev, as_prev = aq, as_val

    return nw_eval, aq_eval, as_eval, total_roth_converted, k401_end_by_year, rows


def fast_evaluate(
    req: SimulationRequest,
    income_schedule: Optional[list[float]] = None,
    dtb_overrides: Optional[dict[int, float]] = None,
) -> tuple[float, float, float, float, list[float]]:
    """Lightweight simulation returning (nw_at_eval, acc_tax_tv, acc_cg_tax_tv, roth_conv, k401_bal)."""
    nw_eval, aq_eval, as_eval, roth_conv, k401_end, _ = _run_core(
        req,
        income_schedule=income_schedule,
        dtb_overrides=dtb_overrides,
        collect_rows=False,
    )
    return nw_eval, aq_eval, as_eval, roth_conv, k401_end


def run_simulation(req: SimulationRequest) -> SimulationResponse:
    """Run full 80-year retirement projection and return summary + milestone + yearly data."""
    income_schedule = build_income_schedule(req)
    nw_eval, aq_eval, as_eval, total_roth_converted, _, rows = _run_core(
        req,
        income_schedule=income_schedule,
        dtb_overrides=req.dtb_overrides,
        collect_rows=True,
    )

    eval_yr = max(0, min(SIMULATION_YEARS, req.eval_age - req.primary_age))
    eval_row = rows[eval_yr]

    shortfall_age: Optional[int] = None
    shortfall_yr: Optional[int] = None
    for row in rows[1:]:
        if row.actual_spending < req.dsb * (1.0 + req.inflation_rate) ** row.year_index - 1e-6:
            shortfall_age = row.primary_age
            shortfall_yr = row.year_index
            break

    depletion_age: Optional[int] = None
    for row in rows:
        if row.net_worth <= 1e-6:
            depletion_age = row.primary_age
            break

    peak_irmaa_tier = max(r.irmaa_tier for r in rows[1:]) if len(rows) > 1 else 1
    total_irmaa = sum(r.irmaa_annual_surcharge for r in rows[1:])

    year0_return = (
        req.brkg_balance * req.brkg_rate
        + (req.primary_401k_balance + req.secondary_401k_balance) * req.k401_rate
        + req.roth_balance * req.roth_rate
    )

    milestone_ages = sorted({67, 70, 75, 80, 85, 90, 95, req.eval_age, 100})
    quick_summary = [r for r in rows[1:] if r.primary_age in milestone_ages]

    summary = SimulationSummary(
        net_worth_year0=rows[0].net_worth,
        year0_return=year0_return,
        eval_age=req.eval_age,
        net_worth_at_eval=nw_eval,
        acc_tax_at_eval=eval_row.acc_tax,
        acc_tax_tv_at_eval=aq_eval,
        acc_cg_tax_tv_at_eval=as_eval,
        total_roth_converted=total_roth_converted,
        shortfall_age=shortfall_age,
        shortfall_year_index=shortfall_yr,
        depletion_age=depletion_age,
        peak_irmaa_tier=peak_irmaa_tier,
        total_irmaa_surcharge=total_irmaa,
        withdraw_order=req.withdraw_order,
    )

    return SimulationResponse(
        summary=summary,
        quick_summary=quick_summary,
        projections=rows,
    )
