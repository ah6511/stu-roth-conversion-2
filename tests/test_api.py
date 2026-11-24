"""FastAPI integration tests covering all endpoints and frontend static serving."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_root_and_health() -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "Roth Conversion" in res.text

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "3.0.0"}


def test_config_endpoint() -> None:
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert data["standard_deduction_mfj"] == 32200.0
    assert len(data["withdraw_orders"]) == 6
    assert "model3_default" in data["presets"]
    assert "datapage2_5m" in data["presets"]
    assert len(data["ordinary_brackets_mfj"]) == 7
    assert len(data["irmaa_brackets_2026"]) == 6
    assert len(data["historic_returns"]["rows"]) == 30


def test_simulate_endpoint_and_custom_ss() -> None:
    res = client.post("/api/simulate", json={"legacy_excel_rmd": True})
    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["net_worth_year0"] == 3000000.0
    assert body["summary"]["eval_age"] == 96
    assert abs(body["summary"]["net_worth_at_eval"] - 1104053.41) < 0.05
    assert len(body["projections"]) == 81

    # Custom SS schedule + string-keyed dtb_overrides (as sent by JS)
    custom = client.post(
        "/api/simulate",
        json={
            "ss_profile": "None",
            "custom_ss": {
                "primary_start_age": 68,
                "primary_annual": 45000,
                "secondary_start_age": 67,
                "secondary_annual": 35000,
                "wage_annual": 80000,
                "wage_end_age": 67,
            },
            "dtb_overrides": {"1": 250000, "2": 0},
        },
    )
    assert custom.status_code == 200
    assert custom.json()["projections"][1]["earned_income"] == 80000.0
    assert custom.json()["projections"][1]["dtb_applied"] == 250000.0
    assert custom.json()["projections"][2]["dtb_applied"] == 0.0


def test_simulate_validation_error() -> None:
    bad = client.post("/api/simulate", json={"primary_age": 150, "brkg_balance": -100})
    assert bad.status_code == 422


def test_optimize_endpoints() -> None:
    sweep = client.post(
        "/api/optimize/sweep",
        json={
            "brkg_balance": 1500000,
            "brkg_rate": 0.07,
            "primary_401k_balance": 2000000,
            "secondary_401k_balance": 1000000,
            "k401_rate": 0.07,
            "roth_balance": 500000,
            "roth_rate": 0.07,
            "secondary_age": 62,
            "dsb": 400000,
        },
    )
    assert sweep.status_code == 200
    s_data = sweep.json()
    assert len(s_data["summaries"]) == 6
    assert s_data["summaries"][0]["withdraw_order"] == "ROTH-BRKG-401K"

    per_yr = client.post("/api/optimize/per-year-dtb", json={"max_passes": 1})
    assert per_yr.status_code == 200
    p_data = per_yr.json()
    assert p_data["optimized_net_worth"] >= p_data["baseline_net_worth"]

    dsb_rate = client.post(
        "/api/optimize/dsb-vs-rate",
        json={"rate_step": 0.02, "dsb_step": 50000, "dtb_step": 100000},
    )
    assert dsb_rate.status_code == 200
    assert len(dsb_rate.json()["points"]) == 6


def test_calculator_endpoints() -> None:
    it_fwd = client.post(
        "/api/calculators/income-tax",
        json={"mode": "forward", "amount": 532200, "apply_std_deduction": True},
    )
    assert it_fwd.status_code == 200
    assert abs(it_fwd.json()["federal_tax"] - 112912.0) < 1e-4

    it_inv_sum = client.post(
        "/api/calculators/income-tax",
        json={"mode": "inverse_sum", "amount": 645112, "apply_std_deduction": True},
    )
    assert it_inv_sum.status_code == 200
    assert abs(it_inv_sum.json()["gross_income"] - 532200.0) < 1e-4

    it_inv_tax = client.post(
        "/api/calculators/income-tax",
        json={"mode": "inverse_tax", "amount": 112912, "apply_std_deduction": True},
    )
    assert it_inv_tax.status_code == 200
    assert abs(it_inv_tax.json()["gross_income"] - 532200.0) < 1e-4

    it_rec = client.post(
        "/api/calculators/income-tax",
        json={"mode": "recursive_formula1", "amount": 100000},
    )
    assert it_rec.status_code == 200
    assert abs(it_rec.json()["federal_tax"] - 8681.8181818) < 1e-4

    cg = client.post(
        "/api/calculators/capital-gains",
        json={"ordinary_income": 200000, "capital_gain": 80000},
    )
    assert cg.status_code == 200
    assert cg.json()["cap_gain_tax_rate"] == 0.15
    assert abs(cg.json()["cap_gain_tax"] - 12000.0) < 1e-4
    assert abs(cg.json()["niit_tax"] - 1140.0) < 1e-4

    cg_rec = client.post(
        "/api/calculators/capital-gains",
        json={
            "ordinary_income": 491000,
            "capital_gain": 0,
            "solve_recursive": True,
            "desired_withdrawal": 300000,
            "cgp": 0.27,
        },
    )
    assert cg_rec.status_code == 200
    assert cg_rec.json()["cap_gain_tax_rate"] == 0.15
