# PolyScope Trader

Polymarket **prediction-market** research and **paper** trading stack. Profit is an objective, not a promise; **“no qualifying opportunities” is a successful result.**

## Features

- **RESEARCH** — public data only
- **PAPER** (default) — live market data, realistic simulated execution, no signed writes
- **LIVE** — disabled by default; requires explicit env limits, geoblock pass, credentials, and session arming

Single strategy: **wallet-following hypothesis signals** from leaderboard-derived cohorts (not verified copy-trading edge).

## Quick start

```bash
cd polyscope-trader
cp .env.example .env
# Set DASHBOARD_PASSWORD in .env
pip install -e ".[dev]"
export $(grep -v '^#' .env | xargs)
polyscope-worker &   # background worker
polyscope-api        # dashboard at http://127.0.0.1:8080
```

Docker:

```bash
cp .env.example .env
docker compose up --build
```

## Smoke test (real public APIs)

```bash
python scripts/smoke_public_data.py
```

Artifacts land in `evidence/smoke_*.json`.

## Tests

```bash
pytest -q
```

## Limitations

- No verified 90-day wallet study; leaderboard windows are API-labeled only
- Geoblock reflects **server IP**, not your personal eligibility
- Paper balances are simulated pUSD, not on-chain funds
- LIVE adapter remains fail-closed unless fully configured and armed

See [docs/SITREP.md](docs/SITREP.md) and [docs/live-readiness-checklist.md](docs/live-readiness-checklist.md).
