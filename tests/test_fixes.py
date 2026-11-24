"""Tests for corrections beyond the workbook (RMD table, IRMAA, inflation, validation)."""

import pytest
from pydantic import ValidationError

from backend.constants import SCENARIO_PRESETS
from backend.engine import run_simulation
from backend.schemas import SimulationRequest
from backend.tax import irmaa_surcharge, rmd_divisor, solve_recursive_cgr


def _req(**kw):
    return SimulationRequest(**{**SCENARIO_PRESETS["model3_default"]["params"], **kw})


def test_irs_rmd_table_for_1951_1959_cohort() -> None:
    assert rmd_divisor(73, 1955) == 26.5
    assert rmd_divisor(74, 1955) == 25.5
    assert rmd_divisor(75, 1955) == 24.6
    assert rmd_divisor(73, 1955, legacy_excel=True) == 24.6
    assert rmd_divisor(75, 1960) == 24.6
    assert rmd_divisor(74, 1960) == 0.0


def test_irmaa_2026_tiers() -> None:
    assert irmaa_surcharge(218000.0)["tier"] == 1
    assert irmaa_surcharge(218001.0)["tier"] == 2
    assert irmaa_surcharge(900000.0)["tier"] == 6
    assert irmaa_surcharge(120000.0, "SINGLE")["tier"] == 2


def test_cgr_thresholds_from_bracket_table() -> None:
    assert solve_recursive_cgr(100000.0, 10000.0, 0.5) == 0.0
    assert solve_recursive_cgr(300000.0, 10000.0, 0.5) == 0.15
    assert solve_recursive_cgr(700000.0, 10000.0, 0.5) == 0.20


def test_zero_inflation_is_identity_and_inflation_changes_results() -> None:
    base = run_simulation(_req(legacy_excel_rmd=True))
    zero = run_simulation(_req(legacy_excel_rmd=True, inflation_rate=0.0))
    assert base.summary.net_worth_at_eval == zero.summary.net_worth_at_eval
    infl = run_simulation(_req(inflation_rate=0.03))
    assert infl.projections[10].year == 2035
    assert infl.summary.net_worth_at_eval != base.summary.net_worth_at_eval


def test_eval_age_beyond_horizon_rejected() -> None:
    with pytest.raises(ValidationError):
        _req(primary_age=66, eval_age=147)
