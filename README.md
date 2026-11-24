# Roth Conversion & Retirement Strategy Planner

Full-stack web application converting the retirement planning, tax-bracket Roth conversion, and optimization logic from `retirement-planner-v3.xlsx` (`model3`, `Tax & Income Calculator`, `Capital Gain Tax Calculator `, `Tax Rates`, `IRMAA Brackets`, `Incomes`, `Historic Investment Rates`, `Prompt1`, `prompt2`, `DataPage2`) into Python + FastAPI and vanilla HTML/CSS/JavaScript.

> The runtime backend (`backend/`) implements all financial formulas, tax schedules, RMD divisors, IRMAA tiers, and optimization algorithms directly in Python without loading `retirement-planner-v3.xlsx`.

## Quick Start

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

Open http://127.0.0.1:8000 in your browser (interactive OpenAPI docs at http://127.0.0.1:8000/docs).

## Architecture

- **`backend/constants.py`**: 2026 MFJ ordinary & long-term capital gains brackets, `$32,200` standard deduction, `3.8%` NIIT (`$250,000` MFJ threshold), IRS Uniform Lifetime Table RMD divisors (Born 1951–1959 starting age 73; Born 1960+ starting age 75), 2026 Medicare IRMAA tiers, Social Security profiles, and 1996–2025 historical equity returns.
- **`backend/tax.py`**: Forward and inverse federal tax calculators, closed-form recursive tax solver `X = F(X + B)` (`Formula 1`), recursive brokerage capital gain rate solver (`Formula 2`), NIIT, RMD, and IRMAA lookup functions.
- **`backend/engine.py`**: 80-year annual retirement cash-flow and Roth conversion engine:
  1. Computes primary and secondary 401(k) RMDs from beginning-of-year balances.
  2. Funds the Desired Spendable Budget (`DSB`) first from earned/SS/RMD income (`INC1`), deposits excess income into brokerage, or allocates remaining funding demand across `BRKG`, `401K`, and `ROTH` in the chosen withdrawal order.
  3. Fills remaining ordinary income headroom up to the Desired Tax Bracket (`DTB`) via Stage 1 / Stage 2 Roth conversions while paying conversion tax from the 401(k) (tracking unfunded overdrafts if 401(k) depletes).
  4. Models taxable brokerage annual portfolio turnover, unrealized capital gain ratio (`CGP`) dilution, grossed-up withdrawal taxes, and `3.8%` NIIT.
  5. Accumulates nominal and time-valued taxes and verifies total funding matches total expense every year.
- **`backend/optimizer.py`**:
  - `run_strategy_sweep`: 3-stage (`$100k -> $10k -> $1k`) DTB search across all 6 withdrawal orders.
  - `run_per_year_dtb_optimization`: Coordinate ascent fine-tuning each year's DTB until 401(k) depletion.
  - `run_dsb_vs_rate`: Binary-search max sustainable spending budget (`DSB`) across `0%–10%` portfolio return rates.
- **`backend/main.py`**: FastAPI service exposing REST endpoints and serving `frontend/`.
- **`frontend/`**: Accessible HTML5, modern CSS (`light-dark()`, container queries, scroll-driven tab fades), and modular ES modules (`api.js`, `charts.js`, `app.js`) with interactive SVG charts.

## API Endpoints

| Method | Path | Purpose |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Liveness health check |
| `GET` | `/api/config` | Presets, withdrawal orders, SS profiles, 2026 tax/IRMAA tables, 1996–2025 returns |
| `POST` | `/api/simulate` | Run 80-year projection and Roth conversion model |
| `POST` | `/api/optimize/sweep` | 3-stage DTB optimization across all 6 withdrawal orders |
| `POST` | `/api/optimize/per-year-dtb` | Fine-tune individual yearly DTBs until 401(k) depletes |
| `POST` | `/api/optimize/dsb-vs-rate` | Find maximum sustainable DSB across `0%–10%` return rates |
| `POST` | `/api/calculators/income-tax` | Forward, inverse, and recursive `X=F(X+B)` income tax calculator |
| `POST` | `/api/calculators/capital-gains` | LTCG + 3.8% NIIT calculator with optional recursive gross-up |

## Running Tests

```bash
.venv/bin/pytest -v
```
