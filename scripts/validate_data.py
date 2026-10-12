#!/usr/bin/env python3
"""Validate collected JSON before committing it to the public dashboard."""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODAY = datetime.now(timezone.utc).date()


def load(path):
    with (ROOT / path).open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"{path}: missing/unsupported schema_version")
    generated = datetime.fromisoformat(data["generated_at_utc"].replace("Z", "+00:00"))
    if generated.tzinfo is None:
        raise ValueError(f"{path}: generated_at_utc must include timezone")
    if (datetime.now(timezone.utc) - generated).total_seconds() > 24 * 3600:
        raise ValueError(f"{path}: generated_at_utc is over 24 hours old")
    return data


def coverage(data, key, minimum, label):
    actual = len(data.get(key, []))
    total = data.get("coverage", {}).get("total_currencies",
            data.get("coverage", {}).get("total", 0))
    if actual < minimum:
        raise ValueError(f"{label}: only {actual} entries; minimum required is {minimum}")
    if total and actual > total:
        raise ValueError(f"{label}: entry count exceeds declared total")
    return actual, total


def check_rates():
    d = load("data/official-rates.json")
    n, total = coverage(d, "rates", 6, "policy rates")
    seen = set()
    for x in d["rates"]:
        c = x["currency"]
        if c in seen:
            raise ValueError(f"policy rates: duplicate currency {c}")
        seen.add(c)
        value = float(x["value_percent"])
        if not -1 <= value <= 25:
            raise ValueError(f"policy rates: implausible value for {c}: {value}")
        obs = date.fromisoformat(x["observation_date"][:10])
        if obs > TODAY:
            raise ValueError(f"policy rates: future observation date for {c}")
        max_age = 45 if c in {"GBP", "JPY", "AUD", "NZD", "CHF"} else 14
        if (TODAY - obs).days > max_age:
            raise ValueError(f"policy rates: stale observation for {c}")
    return n, total


def check_cot():
    d = load("data/cot.json")
    n, total = coverage(d, "markets", 6, "COT")
    report = date.fromisoformat(d["report_date"][:10])
    if report > TODAY:
        raise ValueError("COT report date is in the future")
    if (TODAY - report).days > 21:
        raise ValueError("COT report is older than 21 days")
    seen = set()
    for x in d["markets"]:
        c = x["currency"]
        if c in seen:
            raise ValueError(f"COT: duplicate market currency {c}")
        seen.add(c)
        for field in ("long", "short", "net", "open_interest"):
            if not isinstance(x.get(field), (int, float)):
                raise ValueError(f"COT: missing/non-numeric {field} for {c}")
        if x["net"] != x["long"] - x["short"]:
            raise ValueError(f"COT: net does not match long-short for {c}")
        if x["long"] < 0 or x["short"] < 0 or x["open_interest"] <= 0:
            raise ValueError(f"COT: invalid position/open interest for {c}")
    return n, total


def check_macro():
    d = load("data/macro.json")
    n, total = coverage(d, "areas", 6, "macro data")
    year = int(d["year"])
    if year not in {TODAY.year, TODAY.year - 1}:
        raise ValueError(f"macro data year {year} is not current or previous year")
    seen = set()
    for x in d["areas"]:
        c = x["currency"]
        if c in seen:
            raise ValueError(f"macro data: duplicate currency {c}")
        seen.add(c)
        for field in ("inflation", "gdp_growth"):
            series = x.get(field, {})
            if int(series.get("year", -1)) != year or int(series.get("previous_year", -1)) != year - 1:
                raise ValueError(f"macro data: inconsistent year fields for {c}/{field}")
            for v in (series.get("value"), series.get("previous_value")):
                if not isinstance(v, (int, float)) or not -30 <= float(v) <= 60:
                    raise ValueError(f"macro data: missing/implausible {field} value for {c}")
    return n, total


def main():
    try:
        results = [("Rates", check_rates()), ("COT", check_cot()), ("Macro", check_macro())]
        for label, (n, total) in results:
            print(f"PASS {label}: {n} valid entries" + (f" / {total}" if total else ""))
    except Exception as e:
        print(f"DATA VALIDATION FAILED: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
