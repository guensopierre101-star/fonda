#!/usr/bin/env python3
"""Price momentum for the 8 currencies, from ECB daily euro reference rates (free, no key).

For each currency: % change of its value (in euro) over the last ~4 weeks (20 observations).
EUR is the reference (0 before centring); values are then centred on the 8-currency average,
so the number reads "stronger/weaker than the group". Writes data/momentum.json.
"""
import csv
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "momentum.json")
UA = {"User-Agent": "fonda-fx-desk/1.0 (+https://github.com/guensopierre101-star/fonda)"}
URL = ("https://data-api.ecb.europa.eu/service/data/EXR/D.USD+GBP+JPY+CAD+AUD+NZD+CHF.EUR.SP00.A"
       "?lastNObservations=30&format=csvdata")
LOOKBACK = 20  # observations (~4 trading weeks)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return r.read().decode("utf-8")


def build(text):
    """-> dict currency -> list[(date, foreign units per 1 EUR)] sorted."""
    series = {}
    for row in csv.DictReader(io.StringIO(text)):
        v = (row.get("OBS_VALUE") or "").strip()
        if not v:
            continue
        x = float(v)
        if x != x or x <= 0:
            continue
        series.setdefault(row["CURRENCY"], []).append((row["TIME_PERIOD"][:10], x))
    return {k: sorted(v) for k, v in series.items()}


def momentum(series):
    raw, dates, errors = {"EUR": 0.0}, [], []
    for ccy in ("USD", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF"):
        pts = series.get(ccy, [])
        if len(pts) <= LOOKBACK:
            errors.append({"currency": ccy, "status": "unavailable", "error": f"only {len(pts)} observations"})
            continue
        (d1, now), (d0, past) = pts[-1], pts[-1 - LOOKBACK]
        # value of 1 unit of the currency in EUR = 1/rate; change = past_rate/now_rate - 1
        chg = (past / now - 1) * 100
        if abs(chg) > 25:
            errors.append({"currency": ccy, "status": "unavailable", "error": f"implausible change {chg:.1f}%"})
            continue
        raw[ccy] = chg
        dates.append((d0, d1))
    return raw, dates, errors


def main():
    now = datetime.now(timezone.utc)
    raw, dates, errors = momentum(build(get(URL)))
    avg = sum(raw.values()) / len(raw) if raw else 0
    items = [{"currency": c, "change_pct_vs_eur": round(v, 3), "momentum": round(v - avg, 3)} for c, v in raw.items()]
    out = {
        "schema_version": 1,
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "ECB euro foreign exchange reference rates (daily)",
        "lookback_observations": LOOKBACK,
        "from_date": min((d[0] for d in dates), default=None),
        "to_date": max((d[1] for d in dates), default=None),
        "coverage": {"total": 8, "verified": len(items), "unavailable": len(errors) + (8 - len(items) - len(errors))},
        "items": items,
        "errors": errors,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"verified={len(items)} unavailable={len(errors)} {out['from_date']}..{out['to_date']}")
    for e in errors:
        print(f"  {e['currency']}: {e['error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
