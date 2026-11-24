"""Domain constants, 2026 MFJ tax schedules, RMD tables, IRMAA tiers, and presets."""

from __future__ import annotations

BASE_YEAR = 2025
SIMULATION_YEARS = 80

STD_DEDUCTION_MFJ = 32200.0
NIIT_THRESHOLD_MFJ = 250000.0
NIIT_THRESHOLD_SINGLE = 200000.0
NIIT_RATE = 0.038

# (lower_limit, upper_limit_or_None, rate, base_tax_at_lower)
ORDINARY_TAX_BRACKETS_MFJ: tuple[tuple[float, float | None, float, float], ...] = (
    (0.0, 24800.0, 0.10, 0.0),
    (24800.0, 100800.0, 0.12, 2480.0),
    (100800.0, 211400.0, 0.22, 11600.0),
    (211400.0, 403550.0, 0.24, 35932.0),
    (403550.0, 512450.0, 0.32, 82048.0),
    (512450.0, 768700.0, 0.35, 116896.0),
    (768700.0, None, 0.37, 206583.5),
)

# (lower_limit, upper_limit_or_None, rate)
CAP_GAIN_BRACKETS_MFJ: tuple[tuple[float, float | None, float], ...] = (
    (0.0, 98900.0, 0.0),
    (98901.0, 613700.0, 0.15),
    (613701.0, None, 0.20),
)

# IRS Uniform Lifetime Table divisors from Tax Rates sheet
_RMD_DIVISOR_SEQUENCE: tuple[float, ...] = (
    24.6, 23.7, 22.9, 22.0, 21.1, 20.2, 19.4, 18.5, 17.7, 16.8,
    16.0, 15.2, 14.4, 13.7, 12.9, 12.2, 11.5, 10.8, 10.1, 9.5,
    8.9, 8.4, 7.8, 7.3, 6.8, 6.4, 6.0, 5.6, 5.2, 4.9,
    4.6, 4.3, 4.1, 3.9, 3.7, 3.5, 3.4, 3.3, 3.1, 3.0,
    2.9, 2.8, 2.7, 2.5, 2.3, 2.0,
)

# Correct IRS Uniform Lifetime Table: age 73 = 26.5, 74 = 25.5, 75 = 24.6 ...
RMD_DIVISORS_PRE_1960: dict[int, float] = {
    73: 26.5,
    74: 25.5,
    **{75 + idx: (_RMD_DIVISOR_SEQUENCE[idx] if idx < len(_RMD_DIVISOR_SEQUENCE) else 2.0) for idx in range(80)},
}

RMD_DIVISORS_1960_PLUS: dict[int, float] = {
    75 + idx: (_RMD_DIVISOR_SEQUENCE[idx] if idx < len(_RMD_DIVISOR_SEQUENCE) else 2.0)
    for idx in range(80)
}

# Legacy table copied verbatim from retirement-planner-v3.xlsx "Tax Rates" (starts 24.6 at age 73,
# two years early). Only used when legacy_excel_rmd=True (workbook parity tests).
RMD_DIVISORS_PRE_1960_EXCEL: dict[int, float] = {
    73 + idx: (_RMD_DIVISOR_SEQUENCE[idx] if idx < len(_RMD_DIVISOR_SEQUENCE) else 2.0)
    for idx in range(80)
}

# Excel-formula quirks reproduced from model3 (kept as named constants for visibility)
LEGACY_BRKG_WITHDRAW_YEARS = 11  # model3 uses grossed-up brokerage debit only for years 1..11

# Medicare IRMAA 2026 monthly surcharges per enrolled beneficiary (CMS 2026 announcement;
# verify against the current CMS notice before relying on them).
IRMAA_BRACKETS_2026: tuple[dict[str, float | int | str | None], ...] = (
    {"tier": 1, "label": "Tier 1 (Standard)", "single_min": 0.0, "single_max": 109000.0,
     "mfj_min": 0.0, "mfj_max": 218000.0, "part_b_monthly": 0.0, "part_d_monthly": 0.0},
    {"tier": 2, "label": "Tier 2", "single_min": 109001.0, "single_max": 137000.0,
     "mfj_min": 218001.0, "mfj_max": 274000.0, "part_b_monthly": 81.2, "part_d_monthly": 14.5},
    {"tier": 3, "label": "Tier 3", "single_min": 137001.0, "single_max": 171000.0,
     "mfj_min": 274001.0, "mfj_max": 342000.0, "part_b_monthly": 202.9, "part_d_monthly": 37.5},
    {"tier": 4, "label": "Tier 4", "single_min": 171001.0, "single_max": 205000.0,
     "mfj_min": 342001.0, "mfj_max": 410000.0, "part_b_monthly": 324.6, "part_d_monthly": 60.4},
    {"tier": 5, "label": "Tier 5", "single_min": 205001.0, "single_max": 500000.0,
     "mfj_min": 410001.0, "mfj_max": 750000.0, "part_b_monthly": 446.3, "part_d_monthly": 83.3},
    {"tier": 6, "label": "Tier 6", "single_min": 500001.0, "single_max": None,
     "mfj_min": 750001.0, "mfj_max": None, "part_b_monthly": 487.0, "part_d_monthly": 91.0},
)

WITHDRAW_ORDERS: tuple[str, ...] = (
    "BRKG-ROTH-401K",
    "BRKG-401K-ROTH",
    "401K-BRKG-ROTH",
    "401K-ROTH-BRKG",
    "ROTH-BRKG-401K",
    "ROTH-401K-BRKG",
)


def _build_ss_profile_schedule(profile_name: str) -> list[tuple[float, float]]:
    """Build an 80-year list of (primary_ss, secondary_ss) for Years 1..80."""
    schedule: list[tuple[float, float]] = []
    if profile_name in ("Profile 1", "Profile Test"):
        for yr in range(1, SIMULATION_YEARS + 1):
            if yr == 1:
                schedule.append((0.0, 0.0))
            elif yr <= 5:
                schedule.append((50000.0, 0.0))
            else:
                schedule.append((50000.0, 50000.0))
    elif profile_name == "Profile 0":
        for yr in range(1, SIMULATION_YEARS + 1):
            if yr <= 9:
                schedule.append((0.0, 0.0))
            else:
                schedule.append((63396.0, 48540.0))
    elif profile_name == "Profile 2":
        for yr in range(1, SIMULATION_YEARS + 1):
            if yr <= 5:
                schedule.append((0.0, 0.0))
            elif yr == 6:
                schedule.append((42000.0, 21000.0))
            else:
                schedule.append((38220.0, 19110.0))
    else:
        schedule = [(0.0, 0.0)] * SIMULATION_YEARS
    return schedule


SS_PROFILES: dict[str, dict[str, object]] = {
    "Profile 1": {
        "label": "Profile 1 (Default: $50k yr 2+, +$50k spouse yr 6+)",
        "description": "Primary $50,000/yr starting Year 2 (2027); Secondary $50,000/yr starting Year 6 (2031).",
        "schedule": _build_ss_profile_schedule("Profile 1"),
    },
    "Profile 0": {
        "label": "Profile 0 (Delayed age 70: $63,396 + $48,540 yr 10+)",
        "description": "Both spouses delay Social Security until Year 10 (2035): $63,396 + $48,540/yr.",
        "schedule": _build_ss_profile_schedule("Profile 0"),
    },
    "Profile 2": {
        "label": "Profile 2 ($42k/$21k yr 6, then $38,220/$19,110 yr 7+)",
        "description": "Starts Year 6 (2031) at $42k + $21k, then $38,220 + $19,110/yr from Year 7 onward.",
        "schedule": _build_ss_profile_schedule("Profile 2"),
    },
    "Profile Test": {
        "label": "Profile Test (Matches Profile 1)",
        "description": "Test profile matching Profile 1 schedule.",
        "schedule": _build_ss_profile_schedule("Profile Test"),
    },
    "None": {
        "label": "No Social Security ($0/yr)",
        "description": "Zero Social Security income across all 80 years.",
        "schedule": _build_ss_profile_schedule("None"),
    },
}

# Historical annual total returns (1996-2025) from Historic Investment Rates sheet
HISTORIC_RETURNS: tuple[dict[str, float | int], ...] = (
    {"year": 1996, "sp500": 0.2296, "djia": 0.2601, "nasdaq100": 0.4254},
    {"year": 1997, "sp500": 0.3336, "djia": 0.2264, "nasdaq100": 0.2063},
    {"year": 1998, "sp500": 0.2858, "djia": 0.1610, "nasdaq100": 0.8530},
    {"year": 1999, "sp500": 0.2104, "djia": 0.2522, "nasdaq100": 1.0195},
    {"year": 2000, "sp500": -0.0910, "djia": -0.0617, "nasdaq100": -0.3684},
    {"year": 2001, "sp500": -0.1189, "djia": -0.0710, "nasdaq100": -0.3265},
    {"year": 2002, "sp500": -0.2210, "djia": -0.1676, "nasdaq100": -0.3758},
    {"year": 2003, "sp500": 0.2868, "djia": 0.2532, "nasdaq100": 0.4912},
    {"year": 2004, "sp500": 0.1088, "djia": 0.0315, "nasdaq100": 0.1043},
    {"year": 2005, "sp500": 0.0491, "djia": -0.0061, "nasdaq100": 0.0149},
    {"year": 2006, "sp500": 0.1579, "djia": 0.1629, "nasdaq100": 0.0679},
    {"year": 2007, "sp500": 0.0549, "djia": 0.0643, "nasdaq100": 0.1867},
    {"year": 2008, "sp500": -0.3700, "djia": -0.3384, "nasdaq100": -0.4189},
    {"year": 2009, "sp500": 0.2646, "djia": 0.1882, "nasdaq100": 0.5354},
    {"year": 2010, "sp500": 0.1506, "djia": 0.1102, "nasdaq100": 0.1922},
    {"year": 2011, "sp500": 0.0211, "djia": 0.0553, "nasdaq100": 0.0270},
    {"year": 2012, "sp500": 0.1600, "djia": 0.0726, "nasdaq100": 0.1682},
    {"year": 2013, "sp500": 0.3239, "djia": 0.2650, "nasdaq100": 0.3499},
    {"year": 2014, "sp500": 0.1369, "djia": 0.0752, "nasdaq100": 0.1794},
    {"year": 2015, "sp500": 0.0138, "djia": -0.0223, "nasdaq100": 0.0843},
    {"year": 2016, "sp500": 0.1196, "djia": 0.1342, "nasdaq100": 0.0589},
    {"year": 2017, "sp500": 0.2183, "djia": 0.2508, "nasdaq100": 0.3152},
    {"year": 2018, "sp500": -0.0438, "djia": -0.0563, "nasdaq100": -0.0104},
    {"year": 2019, "sp500": 0.3149, "djia": 0.2234, "nasdaq100": 0.3796},
    {"year": 2020, "sp500": 0.1840, "djia": 0.0725, "nasdaq100": 0.4758},
    {"year": 2021, "sp500": 0.2871, "djia": 0.1873, "nasdaq100": 0.2663},
    {"year": 2022, "sp500": -0.1811, "djia": -0.0878, "nasdaq100": -0.3297},
    {"year": 2023, "sp500": 0.2629, "djia": 0.1370, "nasdaq100": 0.5381},
    {"year": 2024, "sp500": 0.2502, "djia": 0.1288, "nasdaq100": 0.2488},
    {"year": 2025, "sp500": 0.1788, "djia": 0.1297, "nasdaq100": 0.2017},
)

SCENARIO_PRESETS: dict[str, dict[str, object]] = {
    "model3_default": {
        "name": "Model 3 Baseline ($3.0M @ 3.5%)",
        "description": "Primary $3.0M retirement baseline from model3 with 3.5% returns, $200k DSB, and $177k DTB.",
        "params": {
            "primary_age": 66,
            "secondary_age": 65,
            "brkg_balance": 1000000.0,
            "brkg_rate": 0.035,
            "brkg_gain_pct": 0.7,
            "brkg_turnover_rate": 0.3,
            "primary_401k_balance": 1200000.0,
            "secondary_401k_balance": 600000.0,
            "k401_rate": 0.035,
            "roth_balance": 200000.0,
            "roth_rate": 0.035,
            "dsb": 200000.0,
            "dtb": 177000.0,
            "withdraw_order": "401K-ROTH-BRKG",
            "eval_age": 96,
            "inflation_rate": 0.03,
            "legacy_excel_rmd": True,
            "ss_profile": "Profile 1",
        },
    },
    "datapage2_5m": {
        "name": "High-Growth Scenario ($5.0M @ 7.0%)",
        "description": "Optimization benchmark scenario ($5.0M starting assets, 7.0% returns, $400k DSB, $300k DTB).",
        "params": {
            "primary_age": 66,
            "secondary_age": 62,
            "brkg_balance": 1500000.0,
            "brkg_rate": 0.07,
            "brkg_gain_pct": 0.7,
            "brkg_turnover_rate": 0.3,
            "primary_401k_balance": 2000000.0,
            "secondary_401k_balance": 1000000.0,
            "k401_rate": 0.07,
            "roth_balance": 500000.0,
            "roth_rate": 0.07,
            "dsb": 400000.0,
            "dtb": 300000.0,
            "withdraw_order": "ROTH-BRKG-401K",
            "eval_age": 96,
            "inflation_rate": 0.03,
            "legacy_excel_rmd": True,
            "ss_profile": "Profile 1",
        },
    },
}
