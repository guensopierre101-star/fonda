#!/usr/bin/env python3
"""Collect official policy rates for the 8 major currencies.

Writes data/official-rates.json. Only values that were fetched AND passed
validation are published; everything else is listed under source_errors.
No fallback numbers are ever invented. Standard library only.
"""
import csv
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, date

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "official-rates.json")
UA = {"User-Agent": "fonda-fx-desk/1.0 (+https://github.com/guensopierre101-star/fonda)"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def last_csv_value(text, date_col, value_col):
    rows = list(csv.DictReader(io.StringIO(text)))
    for row in reversed(rows):
        v = (row.get(value_col) or "").strip()
        if v and v != ".":
            return row[date_col].strip(), float(v)
    raise ValueError("no numeric observation in CSV")


def fred(series):
    text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
    return last_csv_value(text, "observation_date", series) if "observation_date" in text.splitlines()[0] else last_csv_value(text, "DATE", series)


def ecb_dfr():
    url = ("https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
           "?lastNObservations=1&format=csvdata")
    return last_csv_value(get(url), "TIME_PERIOD", "OBS_VALUE")


def boc_target():
    d = json.loads(get("https://www.bankofcanada.ca/valet/observations/V39079/json?recent=1"))
    obs = d["observations"][-1]
    return obs["d"], float(obs["V39079"]["v"])


# currency, bank, indicator, official page, fetcher, max age (days), origin label
SOURCES = [
    ("USD", "Federal Reserve", "Fed funds target range (upper bound)",
     "https://www.federalreserve.gov/monetarypolicy.htm", lambda: fred("DFEDTARU"), 14, "FRED / Board of Governors"),
    ("EUR", "European Central Bank", "Deposit facility rate",
     "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html", ecb_dfr, 14, "ECB Data Portal"),
    ("CAD", "Bank of Canada", "Target for the overnight rate",
     "https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/", boc_target, 14, "Bank of Canada Valet API"),
    ("GBP", "Bank of England", "Central bank rate (OECD, monthly)",
     "https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate", lambda: fred("IRSTCB01GBM156N"), 120, "OECD via FRED (monthly, secondary source)"),
    ("JPY", "Bank of Japan", "Central bank rate (OECD, monthly)",
     "https://www.boj.or.jp/en/mopo/", lambda: fred("IRSTCB01JPM156N"), 120, "OECD via FRED (monthly, secondary source)"),
    ("AUD", "Reserve Bank of Australia", "Central bank rate (OECD, monthly)",
     "https://www.rba.gov.au/statistics/cash-rate/", lambda: fred("IRSTCB01AUM156N"), 120, "OECD via FRED (monthly, secondary source)"),
    ("NZD", "Reserve Bank of New Zealand", "Central bank rate (OECD, monthly)",
     "https://www.rbnz.govt.nz/monetary-policy/about-monetary-policy/the-official-cash-rate", lambda: fred("IRSTCB01NZM156N"), 120, "OECD via FRED (monthly, secondary source)"),
    ("CHF", "Swiss National Bank", "Central bank rate (OECD, monthly)",
     "https://www.snb.ch/en/the-snb/mandates-goals/monetary-policy/decisions", lambda: fred("IRSTCB01CHM156N"), 120, "OECD via FRED (monthly, secondary source)"),
]


def main():
    now = datetime.now(timezone.utc)
    rates, errors = [], []
    for ccy, bank, indicator, page, fetch, max_age, origin in SOURCES:
        try:
            obs_date, value = fetch()
            age = (now.date() - date.fromisoformat(obs_date[:10])).days
            if not (-1.0 <= value <= 25.0):
                raise ValueError(f"value out of plausible range: {value}")
            if age > max_age:
                raise ValueError(f"observation too old ({age} days, limit {max_age})")
            rates.append({
                "currency": ccy, "central_bank": bank, "indicator": indicator,
                "value_percent": value, "observation_date": obs_date[:10],
                "source_url": page, "origin": origin,
            })
        except Exception as e:  # noqa: BLE001 - report every failure, never guess
            errors.append({
                "currency": ccy, "central_bank": bank, "source_url": page,
                "status": "unavailable", "error": f"{type(e).__name__}: {e}",
            })
    out = {
        "schema_version": 1,
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "Only validated observations are listed. Missing currencies appear in source_errors.",
        "coverage": {"total_currencies": len(SOURCES), "verified": len(rates), "unavailable": len(errors)},
        "rates": rates,
        "source_errors": errors,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"verified={len(rates)} unavailable={len(errors)}")
    for e in errors:
        print(f"  {e['currency']}: {e['error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
