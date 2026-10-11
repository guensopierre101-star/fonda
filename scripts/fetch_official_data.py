#!/usr/bin/env python3
"""Fetch verified official policy-rate observations; never fabricate fallback values."""
import csv
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

OUT = "data/official-rates.json"
SOURCES = [
    {
        "currency": "EUR",
        "central_bank": "European Central Bank",
        "indicator": "Main refinancing operations rate",
        "series_key": "FM.D.U2.EUR.4F.KR.MRR_FR.LEV",
        "url": "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.MRR_FR.LEV?format=csvdata&lastNObservations=1",
        "source_page": "https://www.ecb.europa.eu/press/govcdec/mopo/html/index.en.html",
    }
]

def fetch_csv(item):
    request = urllib.request.Request(
        item["url"],
        headers={"User-Agent": "FundamentalFXDesk/1.0 (official-source data pipeline)", "Accept": "text/csv"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        raise ValueError("The official API returned no observations")
    row = rows[-1]
    # ECB CSV fields normally include TIME_PERIOD and OBS_VALUE.
    date = row.get("TIME_PERIOD") or row.get("TIME_PERIOD_LABEL")
    value = row.get("OBS_VALUE")
    if not date or value in (None, ""):
        raise ValueError("Expected date/value fields were missing")
    number = float(value)
    if not (-1 <= number <= 30):
        raise ValueError("Observation outside plausibility bounds")
    return {
        "currency": item["currency"],
        "central_bank": item["central_bank"],
        "indicator": item["indicator"],
        "value_percent": number,
        "observation_date": date,
        "source_url": item["source_page"],
        "api_url": item["url"],
        "status": "verified",
    }

def main():
    os.makedirs("data", exist_ok=True)
    result = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Only values successfully retrieved from the named official API are included. Missing values are not guessed. This partial feed is not sufficient on its own to generate FX trade signals.",
        "coverage": {"verified": 0, "unavailable": 0, "planned": ["USD", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF", "XAU/USD", "CFTC COT"]},
        "rates": [],
        "source_errors": [],
    }
    for item in SOURCES:
        try:
            result["rates"].append(fetch_csv(item))
            result["coverage"]["verified"] += 1
        except Exception as exc:
            result["coverage"]["unavailable"] += 1
            result["source_errors"].append({
                "currency": item["currency"],
                "source_url": item["source_page"],
                "error": str(exc)[:300],
            })
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Saved {OUT}: {result['coverage']['verified']} verified, {result['coverage']['unavailable']} unavailable")
    # Do not fail the workflow on a temporary source outage: status JSON records it honestly.

if __name__ == "__main__":
    main()
