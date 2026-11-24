# Code Review: Retirement Planner & Roth Conversion App

Scope: backend (`engine.py`, `tax.py`, `constants.py`, `schemas.py`, `main.py`, `optimizer.py`), tests, and the tax/RMD/IRMAA sheets of `retirement-planner-v3.xlsx`. The frontend JS was reviewed only where it builds request payloads.

## Summary

The Python engine reproduces the workbook's cached values exactly (`model3` for all 80 years and all 608 `DataPage2` sweep points, within $0.01). The main problems are errors in the workbook itself that the code copied, plus a few modeling limitations.

## Findings

### Errors copied from the workbook

1. **RMD table for people born 1951–1959 is shifted two years.** The workbook ("Tax Rates" sheet) and the code started at divisor 24.6 at age 73. The IRS Uniform Lifetime Table gives 26.5 at 73, 25.5 at 74 and 24.6 at 75. RMDs were overstated for this cohort. The 1960+ table was correct.
2. **IRMAA data labeled 2026 was actually 2024.** Thresholds (MFJ $206k/$258k/$322k/$386k/$750k) and surcharges (Part B $69.90 to $419.30) were 2024 values.
3. **IRMAA is approximated.** It uses current-year gross income (not MAGI with the 2-year lookback) and unindexed thresholds. It is reported only and never reduces spending or net worth.

### Modeling limitations

- No inflation: spending, Social Security, brackets and thresholds were flat for 80 years.
- Hard-coded Excel quirks: `yr <= 11` (brokerage debit) and `yr == 1` (NIIT and conversion formulas).
- Hard-coded `BASE_YEAR = 2025` (tax tables are 2026) drives birth years and RMD start ages.
- `avg_rate` is an unweighted mean of the three account returns, used to compound the accumulated-tax figures.
- Single-filer and surviving-spouse years are not modeled (the engine is MFJ-only).

### Code issues

- `solve_recursive_cgr` used literal thresholds (131100 / 645900) instead of the bracket table.
- `eval_age` allowed up to 140 but was silently clamped to the 80-year horizon.
- `irmaa_surcharge` had a confusing overlapping fallback in its tier lookup.
- A stale test comment hid that the app's optimizer beats the workbook's `DataPage2` optimum ($293k DTB vs $300k).
- Minor, not changed: unused `apply_std_deduction` in some paths, float dictionary keys in the sweep, Starlette `httpx` deprecation warning.

## Fixes applied

| Area | Change |
| --- | --- |
| RMD | `constants.py` now holds the IRS table. The workbook's old table is kept as `RMD_DIVISORS_PRE_1960_EXCEL`, selected with `legacy_excel_rmd=True`. |
| IRMAA | Updated to 2026 thresholds and surcharges (MFJ tier 2 starts at $218k). **Entered from memory of the CMS announcement. Verify against the current CMS notice.** |
| Capital gains | `solve_recursive_cgr` derives its thresholds from `CAP_GAIN_BRACKETS_MFJ` and `STD_DEDUCTION_MFJ`. |
| Inflation | New `inflation_rate` request field (default 0, which gives identical results). It indexes spending, the conversion target (DTB), income, brackets, standard deduction and IRMAA thresholds. NIIT threshold stays fixed. API only; no frontend input yet. |
| Base year | New `base_year` field (default 2025). |
| Validation | `eval_age > primary_age + 80` is now rejected. |
| IRMAA lookup | Tier lookup simplified. |
| Quirks | The `yr <= 11` cutoff is now the named constant `LEGACY_BRKG_WITHDRAW_YEARS`. Both quirks are otherwise retained for workbook parity. |
| Presets | Both built-in presets set `legacy_excel_rmd: true`. `app.js` stores the flag when a preset is applied and sends it with every request. |
| Tests | Parity tests pass `legacy_excel_rmd`. `test_api.py` and `test_tax.py` were updated for the new RMD and IRMAA values. New `tests/test_fixes.py` covers the RMD table, IRMAA tiers, capital-gains thresholds, inflation and the `eval_age` validation. |
| Docs | README has a "Differences from retirement-planner-v3.xlsx" section. |

Result: 20 tests pass (15 original, 5 new).

## Behavior to be aware of

- The API default (no flag) uses the corrected IRS RMD table. The presets, and the UI after a preset is applied, use the workbook table. The flag is not visible on the form.
- A request with default settings will not match the workbook for anyone born 1951–1959, including the default scenario (primary age 66, born 1959).

## Not done / suggested follow-ups

- Correct the RMD and IRMAA tables in the workbook itself.
- Add inflation and RMD-table controls to the frontend form.
- Decide whether to keep or remove the `yr <= 11` and `yr == 1` quirks. Their intended behavior is unknown.
- Weight `avg_rate` by account balances.
- Model single-filer years after a spouse's death.
- Clean up the minor items listed above.
