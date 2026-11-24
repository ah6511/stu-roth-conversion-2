"""2026 MFJ ordinary income tax, inverse tax, capital gains, NIIT, RMD, and IRMAA functions."""

from __future__ import annotations

from backend.constants import (
    CAP_GAIN_BRACKETS_MFJ,
    IRMAA_BRACKETS_2026,
    NIIT_RATE,
    NIIT_THRESHOLD_MFJ,
    NIIT_THRESHOLD_SINGLE,
    ORDINARY_TAX_BRACKETS_MFJ,
    RMD_DIVISORS_1960_PLUS,
    RMD_DIVISORS_PRE_1960,
    RMD_DIVISORS_PRE_1960_EXCEL,
    STD_DEDUCTION_MFJ,
)


def _lookup_ordinary_bracket(taxable_income: float) -> tuple[float, float | None, float, float]:
    chosen = ORDINARY_TAX_BRACKETS_MFJ[0]
    for bracket in ORDINARY_TAX_BRACKETS_MFJ:
        if taxable_income >= bracket[0]:
            chosen = bracket
        else:
            break
    return chosen


def ordinary_income_tax(income: float, apply_std_deduction: bool = True) -> float:
    """Forward 2026 MFJ ordinary income tax."""
    ti = max(0.0, income - STD_DEDUCTION_MFJ) if apply_std_deduction else max(0.0, income)
    low, _, rate, base = _lookup_ordinary_bracket(ti)
    return base + (ti - low) * rate


def ordinary_marginal_rate(income: float, apply_std_deduction: bool = True) -> float:
    """Marginal ordinary income tax rate for a given income."""
    if apply_std_deduction and income <= STD_DEDUCTION_MFJ:
        return 0.0
    ti = max(0.0, income - STD_DEDUCTION_MFJ) if apply_std_deduction else max(0.0, income)
    return _lookup_ordinary_bracket(ti)[2]


def ordinary_marginal_rate_model3(gross_income: float) -> float:
    """Marginal rate matching model3!GN (looks up gross_income directly when > $32,200)."""
    if gross_income <= STD_DEDUCTION_MFJ:
        return 0.0
    return _lookup_ordinary_bracket(gross_income)[2]


def inverse_income_from_sum(
    income_plus_tax: float,
    apply_std_deduction: bool = True,
) -> tuple[float, float, float]:
    """Scenario A: given (Income + Tax), return (income, tax, marginal_rate)."""
    ded = STD_DEDUCTION_MFJ if apply_std_deduction else 0.0
    adj = max(0.0, income_plus_tax - ded)
    chosen = ORDINARY_TAX_BRACKETS_MFJ[0]
    for bracket in ORDINARY_TAX_BRACKETS_MFJ:
        low, _, _, base = bracket
        base_sum = low + base
        if adj >= base_sum:
            chosen = bracket
        else:
            break
    low, _, rate, base = chosen
    base_sum = low + base
    income = low + (adj - base_sum) / (1.0 + rate) + ded
    tax = max(0.0, income_plus_tax - income)
    return income, tax, rate


def inverse_income_from_tax(
    total_tax: float,
    apply_std_deduction: bool = True,
) -> tuple[float, float]:
    """Scenario B: given Total Federal Tax, return (income, marginal_rate)."""
    ded = STD_DEDUCTION_MFJ if apply_std_deduction else 0.0
    chosen = ORDINARY_TAX_BRACKETS_MFJ[0]
    for bracket in ORDINARY_TAX_BRACKETS_MFJ:
        if total_tax >= bracket[3]:
            chosen = bracket
        else:
            break
    low, _, rate, base = chosen
    income = low + (total_tax - base) / rate + ded
    return income, rate


def solve_recursive_tax(base_b: float, clamp_min_std_ded: bool = True) -> float:
    """Formula 1: solve X = F(X + B) in closed form for progressive MFJ brackets."""
    val = max(base_b, STD_DEDUCTION_MFJ) if clamp_min_std_ded else base_b
    chosen = ORDINARY_TAX_BRACKETS_MFJ[0]
    for bracket in ORDINARY_TAX_BRACKETS_MFJ:
        low, _, _, base = bracket
        g_at_low = low + STD_DEDUCTION_MFJ - base
        if val >= g_at_low:
            chosen = bracket
        else:
            break
    low, _, rate, base = chosen
    y = low + (base_b - (low + STD_DEDUCTION_MFJ - base)) / (1.0 - rate)
    return max(0.0, base + (y - low) * rate)


def capital_gain_rate(gross_income: float, apply_std_deduction: bool = True) -> float:
    """Look up 2026 MFJ long-term capital gains tax rate (0%, 15%, 20%)."""
    ti = max(0.0, gross_income - STD_DEDUCTION_MFJ) if apply_std_deduction else max(0.0, gross_income)
    rate = 0.0
    for low, _, r in CAP_GAIN_BRACKETS_MFJ:
        if ti >= low:
            rate = r
        else:
            break
    return rate


def solve_recursive_cgr(inc_plus_to_gain: float, dwd: float, cgp: float) -> float:
    """Formula 2: determine LTCG tax rate when brokerage withdrawal is grossed up for tax.

    Thresholds derive from CAP_GAIN_BRACKETS_MFJ (taxable-income breakpoints + standard deduction).
    """
    top_0 = int(CAP_GAIN_BRACKETS_MFJ[1][0] - 1 + STD_DEDUCTION_MFJ)  # 131,100
    top_15 = int(CAP_GAIN_BRACKETS_MFJ[2][0] - 1 + STD_DEDUCTION_MFJ)  # 645,900
    r15 = CAP_GAIN_BRACKETS_MFJ[1][2]
    r20 = CAP_GAIN_BRACKETS_MFJ[2][2]
    y0 = int(inc_plus_to_gain + dwd * cgp)
    if 0 <= y0 <= top_0:
        return CAP_GAIN_BRACKETS_MFJ[0][2]
    y15 = int(inc_plus_to_gain + (dwd * cgp) / (1.0 - cgp * r15))
    if top_0 + 1 <= y15 <= top_15:
        return r15
    y20 = int(inc_plus_to_gain + (dwd * cgp) / (1.0 - cgp * r20))
    if y20 >= top_15 + 1:
        return r20
    return r15


def niit_taxable_gain(
    gross_income: float,
    capital_gain: float,
    threshold: float = NIIT_THRESHOLD_MFJ,
) -> float:
    """Portion of capital gain subject to the 3.8% Net Investment Income Tax."""
    return min(max(gross_income - threshold, 0.0), max(0.0, capital_gain))


def niit_tax(
    gross_income: float,
    capital_gain: float,
    threshold: float = NIIT_THRESHOLD_MFJ,
) -> float:
    """Direct 3.8% NIIT on investment income above threshold."""
    return niit_taxable_gain(gross_income, capital_gain, threshold) * NIIT_RATE


def rmd_divisor(age: int, birth_year: int, legacy_excel: bool = False) -> float:
    """IRS Uniform Lifetime Table divisor given current age and birth year.

    legacy_excel=True reproduces the workbook's (shifted) 1951-1959 table.
    """
    if birth_year < 1960:
        table = RMD_DIVISORS_PRE_1960_EXCEL if legacy_excel else RMD_DIVISORS_PRE_1960
        return table.get(age, 0.0)
    return RMD_DIVISORS_1960_PLUS.get(age, 0.0)


def irmaa_surcharge(
    magi: float,
    filing_status: str = "MFJ",
    num_enrolled: int = 2,
) -> dict[str, float | int | str]:
    """2026 Medicare IRMAA Part B + Part D surcharge lookup."""
    min_key = "mfj_min" if filing_status == "MFJ" else "single_min"
    max_key = "mfj_max" if filing_status == "MFJ" else "single_max"
    chosen = IRMAA_BRACKETS_2026[0]
    for tier in IRMAA_BRACKETS_2026:
        if magi > float(tier[min_key]) - 1.0:  # tier mins are "$X,001" style; > previous max
            chosen = tier
    part_b = float(chosen["part_b_monthly"])  # type: ignore[arg-type]
    part_d = float(chosen["part_d_monthly"])  # type: ignore[arg-type]
    monthly_per_person = part_b + part_d
    annual_total = monthly_per_person * 12.0 * max(0, num_enrolled)
    return {
        "tier": int(chosen["tier"]),  # type: ignore[arg-type]
        "label": str(chosen["label"]),
        "part_b_monthly": part_b,
        "part_d_monthly": part_d,
        "monthly_per_person": monthly_per_person,
        "annual_total": annual_total,
    }


__all__ = [
    "NIIT_RATE",
    "NIIT_THRESHOLD_MFJ",
    "NIIT_THRESHOLD_SINGLE",
    "capital_gain_rate",
    "inverse_income_from_sum",
    "inverse_income_from_tax",
    "irmaa_surcharge",
    "niit_tax",
    "niit_taxable_gain",
    "ordinary_income_tax",
    "ordinary_marginal_rate",
    "ordinary_marginal_rate_model3",
    "rmd_divisor",
    "solve_recursive_cgr",
    "solve_recursive_tax",
]
