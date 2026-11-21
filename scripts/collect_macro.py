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
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "macro.json")
UA = {"User-Agent": "fonda-fx-desk/1.0 (+https://github.com/guensopierre101-star/fonda)"}
BASE_V2 = "https://www.imf.org/external/datamapper/api/v2/"
BASE_V1 = "https://www.imf.org/external/datamapper/api/v1/"

AREAS = {"USD": "USA", "EUR": "EURO", "GBP": "GBR", "JPY": "JPN",
         "CAD": "CAN", "AUD": "AUS", "NZD": "NZL", "CHF": "CHE"}
INDICATORS = {"inflation": "PCPIPCH", "gdp_growth": "NGDP_RPCH"}


def get_indicator(code):
    """IMF DataMapper: v2 is current (v1 now returns 404). Retry on 429 and tolerate small format changes."""
    countries = "/".join(AREAS.values())
    urls = [f"{BASE_V2}{code}/{countries}", f"{BASE_V1}{code}/{countries}", f"{BASE_V2}{code}"]
    last = None
    for url in urls:
        for wait in (0, 6, 20):
            if wait:
                time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=60) as r:
                    payload = json.loads(r.read().decode("utf-8"))
                values = payload.get("values", payload)
                series = values.get(code, values)
                if not isinstance(series, dict) or not any(k in series for k in AREAS.values()):
                    raise ValueError("unexpected response shape: " + json.dumps(payload)[:300])
                return series
            except urllib.error.HTTPError as e:
                last = e
                body = ""
                try:
                    body = e.read().decode("utf-8", "replace")[:160].replace("\n", " ")
                except Exception:  # noqa: BLE001
                    pass
                print(f"  IMF {url}: HTTP {e.code} {body}", file=sys.stderr)
                if e.code != 429:
                    break  # not rate limiting: try the next URL
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"  IMF {url}: {type(e).__name__}: {e}", file=sys.stderr)
                break
    raise last


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
    if not areas:
        # Do not replace the last good file with an empty one (IMF updates twice a year, so it stays valid).
        print("::warning::IMF data could not be refreshed (the IMF site is refusing requests); keeping the last published data/macro.json")
        for e in errors + [{"currency": "-", "error": x} for x in fetch_errors]:
            print(f"  {e['currency']}: {e['error']}", file=sys.stderr)
        return
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
