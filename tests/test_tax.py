"""Unit tests for 2026 MFJ tax, inverse tax, capital gains, NIIT, RMD, and IRMAA rules."""

from __future__ import annotations

import pytest

from backend.tax import (
    capital_gain_rate,
    inverse_income_from_sum,
    inverse_income_from_tax,
    irmaa_surcharge,
    niit_tax,
    niit_taxable_gain,
    ordinary_income_tax,
    ordinary_marginal_rate,
    rmd_divisor,
    solve_recursive_cgr,
    solve_recursive_tax,
)


def test_ordinary_income_tax_forward_cases() -> None:
    assert ordinary_income_tax(0.0) == pytest.approx(0.0)
    assert ordinary_income_tax(32200.0) == pytest.approx(0.0)
    # Tax & Income Calculator Scenario C rows
    assert ordinary_income_tax(125000.0) == pytest.approx(10640.0)
    assert ordinary_income_tax(532200.0) == pytest.approx(112912.0)
    assert ordinary_income_tax(3210000.0) == pytest.approx(1097950.5)
    assert ordinary_marginal_rate(125000.0) == pytest.approx(0.12)
    assert ordinary_marginal_rate(532200.0) == pytest.approx(0.32)
    assert ordinary_marginal_rate(3210000.0) == pytest.approx(0.37)


def test_inverse_income_calculators() -> None:
    # Scenario A: Income + Tax -> Income, Tax
    inc, tax, m_rate = inverse_income_from_sum(645112.0, apply_std_deduction=True)
    assert inc == pytest.approx(532200.0, abs=1e-6)
    assert tax == pytest.approx(112912.0, abs=1e-6)
    assert m_rate == pytest.approx(0.32)

    inc2, tax2, _ = inverse_income_from_sum(3210000.0, apply_std_deduction=True)
    assert inc2 == pytest.approx(2408576.2773722624, abs=1e-6)
    assert tax2 == pytest.approx(801423.7226277376, abs=1e-6)

    # Scenario B: Total Federal Tax -> Income
    inc_b, m_b = inverse_income_from_tax(112912.0, apply_std_deduction=True)
    assert inc_b == pytest.approx(532200.0, abs=1e-6)
    assert m_b == pytest.approx(0.32)

    inc_b_nod, m_b_nod = inverse_income_from_tax(36448.39, apply_std_deduction=False)
    assert inc_b_nod == pytest.approx(213551.625, abs=1e-6)
    assert m_b_nod == pytest.approx(0.24)


def test_recursive_tax_formula1() -> None:
    # Tax & Income Calculator row 43: B = 100,000 -> X = 8681.81818181818
    x = solve_recursive_tax(100000.0)
    assert x == pytest.approx(8681.81818181818, abs=1e-6)
    assert ordinary_income_tax(100000.0 + x) == pytest.approx(x, abs=1e-6)


def test_capital_gains_and_niit() -> None:
    assert capital_gain_rate(131100.0) == pytest.approx(0.0)
    assert capital_gain_rate(131101.0) == pytest.approx(0.15)
    assert capital_gain_rate(260000.0) == pytest.approx(0.15)
    assert capital_gain_rate(645901.0) == pytest.approx(0.20)

    # Capital Gain Tax Calculator rows 24-27
    assert niit_taxable_gain(260000.0, 0.0) == pytest.approx(0.0)
    assert niit_tax(260000.0, 5000.0) == pytest.approx(190.0)
    assert niit_tax(260000.0, 10000.0) == pytest.approx(380.0)
    assert niit_tax(260000.0, 20000.0) == pytest.approx(380.0)

    # Formula 2 rows 34-40
    assert solve_recursive_cgr(0.0, 0.0, 0.3) == pytest.approx(0.0)
    assert solve_recursive_cgr(131090.0, 1.0, 0.3) == pytest.approx(0.0)
    assert solve_recursive_cgr(131091.0, 10.0 / 0.3, 0.3) == pytest.approx(0.15)
    assert solve_recursive_cgr(645898.9, 1.0, 0.3) == pytest.approx(0.15)
    assert solve_recursive_cgr(645901.0, 0.0, 0.3) == pytest.approx(0.20)


def test_rmd_and_irmaa() -> None:
    # Born 1959 -> starts at age 73 with IRS divisor 26.5 (workbook's table says 24.6)
    assert rmd_divisor(72, 1959) == 0.0
    assert rmd_divisor(73, 1959) == pytest.approx(26.5)
    assert rmd_divisor(73, 1959, legacy_excel=True) == pytest.approx(24.6)
    # Born 1960 -> starts at age 75 with divisor 24.6
    assert rmd_divisor(74, 1960) == 0.0
    assert rmd_divisor(75, 1960) == pytest.approx(24.6)

    t1 = irmaa_surcharge(218000.0, "MFJ", num_enrolled=2)
    assert t1["tier"] == 1
    assert t1["annual_total"] == pytest.approx(0.0)

    t2 = irmaa_surcharge(218001.0, "MFJ", num_enrolled=2)
    assert t2["tier"] == 2
    assert t2["monthly_per_person"] == pytest.approx(95.7)
    assert t2["annual_total"] == pytest.approx(95.7 * 24.0)

    t6 = irmaa_surcharge(800000.0, "MFJ", num_enrolled=2)
    assert t6["tier"] == 6
    assert t6["monthly_per_person"] == pytest.approx(578.0)
