# Official macro data pipeline

This repository is a static GitHub Pages app. GitHub Actions runs a scheduled collector and writes a public JSON snapshot to `data/official-rates.json`; the browser never needs a private API key.

## Current status
- Implemented first connector: ECB Data Portal series for the main refinancing operations rate.
- Scheduled on weekdays at 06:17 UTC; can also be started manually from Actions.
- Failed/empty API responses are recorded as unavailable, not replaced with guessed numbers.
- This first connector is intentionally partial. It does not produce pair or gold trade signals.
- Additional central-bank rates, macro releases, and CFTC COT data must be added with their own official endpoints, date checks, schema validation, and source attribution before signal calculations use them.

## Setup / verification
1. Open **Actions** and enable workflows if GitHub asks.
2. Run **Refresh official macro data** manually once.
3. Inspect the workflow log and `data/official-rates.json`.
4. Open `data.html` after GitHub Pages deploys the commit.

## Safety rules
- Never commit API secrets.
- Keep observation date separate from collection timestamp.
- Do not use failed or stale observations to generate signals.
- Do not label a signal live unless all required inputs passed freshness and validation checks.
