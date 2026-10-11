#!/usr/bin/env python3
"""Collect annual inflation and real GDP growth for the 8 currency areas.

Source: IMF DataMapper API (World Economic Outlook), free, no key.
 - PCPIPCH: inflation, average consumer prices, % change
 - NGDP_RPCH: real GDP growth, %
Figures are annual; the current year is an IMF estimate/projection and is
labelled as such. Writes data/macro.json. Missing data is reported, never invented.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "macro.json")
UA = {"User-Agent": "fonda-fx-desk/1.0 (+https://github.com/guensopierre101-star/fonda)"}
BASE = "https://www.imf.org/external/datamapper/api/v1/"

AREAS = {"USD": "USA", "EUR": "EURO", "GBP": "GBR", "JPY": "JPN",
         "CAD": "CAN", "AUD": "AUS", "NZD": "NZL", "CHF": "CHE"}
INDICATORS = {"inflation": "PCPIPCH", "gdp_growth": "NGDP_RPCH"}


def get_indicator(code):
    req = urllib.request.Request(f"{BASE}{code}", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))["values"][code]


def main():
    now = datetime.now(timezone.utc)
    year = now.year
    data = {}
    fetch_errors = []
    for key, code in INDICATORS.items():
        try:
            data[key] = get_indicator(code)
        except Exception as e:  # noqa: BLE001
            fetch_errors.append(f"{code}: {type(e).__name__}: {e}")
    areas, errors = [], []
    for ccy, iso in AREAS.items():
        try:
            entry = {"currency": ccy, "imf_code": iso}
            for key in INDICATORS:
                if key not in data:
                    raise ValueError(f"{INDICATORS[key]} not fetched")
                series = data[key].get(iso)
                if not series:
                    raise ValueError(f"no {INDICATORS[key]} series for {iso}")
                cur, prev = series.get(str(year)), series.get(str(year - 1))
                if cur is None or prev is None:
                    raise ValueError(f"{INDICATORS[key]} missing for {year - 1}/{year}")
                for v in (cur, prev):
                    if not -30 <= float(v) <= 60:
                        raise ValueError(f"implausible {INDICATORS[key]} value {v}")
                entry[key] = {"year": year, "value": float(cur),
                              "previous_year": year - 1, "previous_value": float(prev)}
            areas.append(entry)
        except Exception as e:  # noqa: BLE001
            errors.append({"currency": ccy, "status": "unavailable",
                           "error": f"{type(e).__name__}: {e}"})
    out = {
        "schema_version": 1,
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "IMF World Economic Outlook via DataMapper API (annual; current year = IMF estimate)",
        "year": year,
        "coverage": {"total": len(AREAS), "verified": len(areas), "unavailable": len(errors)},
        "areas": areas,
        "errors": errors,
        "fetch_errors": fetch_errors,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"verified={len(areas)} unavailable={len(errors)}")
    for e in errors + [{"currency": "-", "error": x} for x in fetch_errors]:
        print(f"  {e['currency']}: {e['error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
