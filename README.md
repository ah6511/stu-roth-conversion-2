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

## Docker Containerization

The repository includes containerization and deployment configuration across `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and `deployment.md`.

### Docker Compose (Recommended for Local Container Run)

```bash
docker compose up --build -d
docker compose logs -f
docker compose down
```

- **Port binding & environment overrides** (`docker-compose.yml`):
  - `HOST_BIND` (default `127.0.0.1`): host interface to bind; set `HOST_BIND=0.0.0.0` to expose externally.
  - `HOST_PORT` (default `8000`): host port mapped to container port `8000`.
- **Container hardening & runtime setup**:
  - Runs as a non-root system user (`app`, UID/GID `10001`).
  - Uses a read-only root filesystem (`read_only: true`) with an ephemeral `/tmp` tmpfs mount.
  - Drops all Linux capabilities (`cap_drop: [ALL]`) and enforces `no-new-privileges:true`.
  - Uses a stateless single-service bridge network (`app-net`) with no external database or cache required.
  - Includes a built-in HTTP `healthcheck` (30s interval, 5s timeout, 3 retries, 10s start period).

### Standalone Docker Build & Run

`Dockerfile` uses a multi-stage `python:3.14-slim` build (`builder` stage installs Python dependencies into `/opt/venv`; `runtime` stage copies only the venv and application assets under the non-root `app` user and runs `uvicorn` on `0.0.0.0:8000` with an HTTP `HEALTHCHECK` against `/api/health`). `.dockerignore` excludes `.git`, `.venv`, caches, `.env` files, `tests`, and local artifacts from the Docker build context.

```bash
docker build -t stu-roth-conversion:latest .
docker run --rm -p 127.0.0.1:8000:8000 stu-roth-conversion:latest
```

### Cloud Deployment (AWS Fargate / ECR)

See [`deployment.md`](deployment.md) for AWS ECR login, image tagging, and push commands targeting AWS Fargate.

## Architecture

- **`backend/constants.py`**: 2026 MFJ ordinary & long-term capital gains brackets, `$32,200` standard deduction, `3.8%` NIIT (`$250,000` MFJ threshold), IRS Uniform Lifetime Table RMD divisors (Born 1951–1959 starting age 73; Born 1960+ starting age 75), 2026 Medicare IRMAA tiers (verify against the current CMS notice), Social Security profiles, and 1996–2025 historical equity returns.
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
- **`Dockerfile` / `docker-compose.yml` / `.dockerignore` / `deployment.md`**: Multi-stage container build, hardened Compose service configuration, build-context exclusions, and AWS ECR/Fargate deployment instructions.

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

## Differences from `retirement-planner-v3.xlsx`

- **RMD table (born 1951-1959):** the two built-in presets set `legacy_excel_rmd: true` (workbook behaviour); the API default is the corrected to the IRS table (73 = 26.5, 74 = 25.5, 75 = 24.6). The workbook starts at 24.6 at age 73. Send `legacy_excel_rmd: true` to reproduce the workbook; the parity tests do this.
- **IRMAA:** updated from 2024 to 2026 thresholds and surcharges.
- **New request fields (all optional):** `inflation_rate` (default 0 = workbook behaviour; indexes spending, DTB, income, brackets and IRMAA), `base_year` (default 2025), `legacy_excel_rmd`.
- `eval_age` may not exceed `primary_age + 80`.
- Workbook formula quirks (`yr <= 11` brokerage debit, `yr == 1` NIIT/conversion special cases) are retained for parity.
