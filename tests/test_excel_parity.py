"""Verify exact numerical parity against retirement-planner-v3.xlsx cached values."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from backend.constants import SCENARIO_PRESETS
from backend.engine import run_simulation
from backend.optimizer import (
    run_dsb_vs_rate,
    run_per_year_dtb_optimization,
    run_strategy_sweep,
)
from backend.schemas import (
    DsbVsRateRequest,
    PerYearOptimizeRequest,
    SimulationRequest,
    SweepRequest,
)

XLSX_PATH = Path(__file__).resolve().parent.parent / "retirement-planner-v3.xlsx"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _load_sheet_values(sheet_name: str) -> dict[int, dict[str, str]]:
    with zipfile.ZipFile(XLSX_PATH) as zf:
        sst = [
            "".join(t.text or "" for t in si.findall(".//m:t", NS))
            for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall("m:si", NS)
        ]
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        target = None
        for sheet in wb.findall(".//m:sheet", NS):
            if sheet.attrib["name"] == sheet_name:
                rid = sheet.attrib[
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                ]
                target = "xl/" + rmap[rid]
                break
        assert target is not None, f"Sheet {sheet_name} not found"
        root = ET.fromstring(zf.read(target))
        rows: dict[int, dict[str, str]] = {}
        for row in root.findall(".//m:sheetData/m:row", NS):
            rnum = int(row.attrib["r"])
            rc: dict[str, str] = {}
            for cell in row.findall("m:c", NS):
                col = re.match(r"^([A-Z]+)", cell.attrib["r"]).group(1)  # type: ignore[union-attr]
                t = cell.attrib.get("t", "")
                v = cell.find("m:v", NS)
                if v is not None and v.text is not None:
                    rc[col] = sst[int(v.text)] if t == "s" else v.text
            if rc:
                rows[rnum] = rc
        return rows


def test_model3_80_year_exact_parity() -> None:
    """Every year 0..80 in model3 matches our Python engine within $0.01."""
    m3 = _load_sheet_values("model3")
    req = SimulationRequest(**{**SCENARIO_PRESETS["model3_default"]["params"], "inflation_rate": 0.0, "legacy_excel_rmd": True})  # type: ignore[arg-type]
    res = run_simulation(req)

    assert len(res.projections) == 81
    assert res.summary.net_worth_year0 == pytest.approx(3000000.0, abs=0.01)
    assert res.summary.net_worth_at_eval == pytest.approx(float(m3[3]["U"]), abs=0.01)
    assert res.summary.acc_tax_tv_at_eval == pytest.approx(float(m3[3]["V"]), abs=0.01)
    assert res.summary.acc_cg_tax_tv_at_eval == pytest.approx(float(m3[3]["W"]), abs=0.01)
    assert res.summary.shortfall_age == int(float(m3[3]["X"]))
    assert res.summary.depletion_age == int(float(m3[3]["AA"]))

    for row in res.projections:
        excel_row = 20 + row.year_index
        xl = m3[excel_row]
        assert row.brkg_balance == pytest.approx(float(xl["G"]), abs=0.01)
        assert row.k401_balance == pytest.approx(float(xl["L"]), abs=0.01)
        assert row.roth_balance == pytest.approx(float(xl["O"]), abs=0.01)
        assert row.net_worth == pytest.approx(float(xl["P"]), abs=0.01)
        if row.year_index >= 1:
            assert row.actual_spending == pytest.approx(float(xl["Q"]), abs=0.01)
            assert row.total_tax == pytest.approx(float(xl["AM"]), abs=0.01)
            assert row.acc_tax_tv == pytest.approx(float(xl["AQ"]), abs=0.01)
            assert row.acc_cg_tax_tv == pytest.approx(float(xl["AS"]), abs=0.01)


def test_datapage2_608_sweeps_exact_parity() -> None:
    """All 608 sweep points in DataPage2 match our Python engine within $0.01."""
    dp2 = _load_sheet_values("DataPage2")
    base_params = {**SCENARIO_PRESETS["datapage2_5m"]["params"], "inflation_rate": 0.0, "legacy_excel_rmd": True}  # type: ignore[arg-type]

    checked = 0
    for r in range(54, 680):
        row = dp2.get(r)
        if not row:
            continue
        wo = row.get("A")
        if wo not in (
            "BRKG-ROTH-401K",
            "BRKG-401K-ROTH",
            "401K-BRKG-ROTH",
            "401K-ROTH-BRKG",
            "ROTH-BRKG-401K",
            "ROTH-401K-BRKG",
        ):
            continue
        dtb = float(row["C"])
        xl_nw = float(row["D"])
        xl_aq = float(row["E"])

        req = SimulationRequest(**{**base_params, "withdraw_order": wo, "dtb": dtb})
        sim = run_simulation(req)
        assert sim.summary.net_worth_at_eval == pytest.approx(xl_nw, abs=0.01)
        assert sim.summary.acc_tax_tv_at_eval == pytest.approx(xl_aq, abs=0.01)
        checked += 1

    assert checked == 608


def test_strategy_sweep_matches_datapage2_rankings() -> None:
    """3-stage sweep matches DataPage2 rankings and finds equal or higher Net Worth per order."""
    dp2 = _load_sheet_values("DataPage2")
    base_params = {**SCENARIO_PRESETS["datapage2_5m"]["params"], "inflation_rate": 0.0, "legacy_excel_rmd": True}  # type: ignore[arg-type]
    sweep_req = SweepRequest(**base_params)
    sweep_res = run_strategy_sweep(sweep_req)

    assert sweep_res.elapsed_ms < 3000.0
    assert len(sweep_res.summaries) == 6
    assert sweep_res.summaries[0].withdraw_order == "ROTH-BRKG-401K"
    # NOTE: intentional divergence from the workbook - widening stage 2 below min(top3) finds a $293k DTB
    # ($1,877,759.04) that beats DataPage2's $300k ($1,802,782.60); the app optimum is better than the sheet's.
    assert sweep_res.summaries[0].best_dtb == pytest.approx(293000.0)
    assert sweep_res.summaries[0].net_worth_at_eval == pytest.approx(1877759.04, abs=0.05)

    by_order = {s.withdraw_order: s for s in sweep_res.summaries}
    for r in range(6, 12):
        wo = dp2[r]["A"]
        xl_best_dtb = float(dp2[r]["B"])
        xl_nw = float(dp2[r]["C"])
        xl_rank = int(float(dp2[r]["E"]))
        assert by_order[wo].rank == xl_rank
        assert by_order[wo].net_worth_at_eval >= xl_nw - 0.05
        # Verify the exact DataPage2 point is in the curve when evaluated
        exact_sim = run_simulation(
            SimulationRequest(**{**base_params, "withdraw_order": wo, "dtb": xl_best_dtb})
        )
        assert exact_sim.summary.net_worth_at_eval == pytest.approx(xl_nw, abs=0.05)


def test_per_year_optimizer_and_dsb_vs_rate_performance() -> None:
    """Verify prompt2 per-year optimizer improves Net Worth and DSB-vs-rate runs quickly."""
    base_params = {**SCENARIO_PRESETS["model3_default"]["params"], "inflation_rate": 0.0, "legacy_excel_rmd": True}  # type: ignore[arg-type]
    per_yr_res = run_per_year_dtb_optimization(PerYearOptimizeRequest(**base_params))
    assert per_yr_res.elapsed_ms < 3000.0
    assert per_yr_res.optimized_net_worth >= per_yr_res.baseline_net_worth

    dsb_res = run_dsb_vs_rate(DsbVsRateRequest(**base_params))
    assert dsb_res.elapsed_ms < 3000.0
    assert len(dsb_res.points) == 21
    for i in range(1, len(dsb_res.points)):
        assert dsb_res.points[i].max_dsb >= dsb_res.points[i - 1].max_dsb
