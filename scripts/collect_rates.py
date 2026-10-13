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
from datetime import datetime, timezone, date, timedelta

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


_BIS = {}


def bis(area):
    """Policy rates from the BIS central bank policy rates dataset (one request, cached)."""
    if not _BIS:
        url = ("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/"
               "D.GB+JP+AU+NZ+CH?lastNObservations=1&format=csv")
        for row in csv.DictReader(io.StringIO(get(url))):
            _BIS[row["REF_AREA"]] = (row["TIME_PERIOD"], float(row["OBS_VALUE"]))
    if area not in _BIS:
        raise ValueError(f"no BIS observation for {area}")
    return _BIS[area]




_RBA = []


def rba_points():
    """Cash rate target from the RBA's own statistical table F1.1 (series FIRMMCRT)."""
    if not _RBA:
        raw = get("https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv")
        rows = list(csv.reader(io.StringIO(raw.lstrip("\ufeff"))))
        idx = None
        for row in rows:
            if row and row[0].strip().lower() == "series id":
                if "FIRMMCRT" not in row:
                    raise ValueError("series FIRMMCRT not found in RBA table F1.1")
                idx = row.index("FIRMMCRT")
                break
        if idx is None:
            raise ValueError("'Series ID' row not found in RBA table F1.1")
        for row in rows:
            if len(row) <= idx or not row[idx].strip():
                continue
            try:
                d = datetime.strptime(row[0].strip(), "%d-%b-%Y").date().isoformat()
                _RBA.append((d, float(row[idx])))
            except ValueError:
                continue  # header/metadata rows
        _RBA.sort()
        if not _RBA:
            sample = [[c[:25] for c in r[:3]] + (["..", r[idx][:12]] if len(r) > idx else []) for r in rows[8:14]]
            raise ValueError(f"no cash rate observations parsed from RBA table F1.1; idx={idx}; rows={len(rows)}; sample={sample}")
    return _RBA


def rba_latest():
    d, v = rba_points()[-1]
    return d, v


# ---- history (for the 6-month rate direction used as hawkish/dovish bias) ----
HIST_DAYS = 400          # window fetched
BIAS_DAYS = 180          # compare today's rate with the rate ~6 months ago
BIAS_STEP = 0.25         # one standard policy step; smaller moves count as neutral


def csv_points(text, date_col, value_col):
    pts = []
    for row in csv.DictReader(io.StringIO(text)):
        v = (row.get(value_col) or "").strip()
        if v and v != ".":
            pts.append((row[date_col].strip()[:10], float(v)))
    return sorted(pts)


def start_date():
    return (datetime.now(timezone.utc).date() - timedelta(days=HIST_DAYS)).isoformat()


def fred_hist(series):
    text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
    col = "observation_date" if "observation_date" in text.splitlines()[0] else "DATE"
    return csv_points(text, col, series)


def ecb_hist():
    url = ("https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
           f"?startPeriod={start_date()}&format=csvdata")
    return csv_points(get(url), "TIME_PERIOD", "OBS_VALUE")


def boc_hist():
    d = json.loads(get("https://www.bankofcanada.ca/valet/observations/V39079/json"
                       f"?start_date={start_date()}"))
    return sorted((o["d"], float(o["V39079"]["v"])) for o in d["observations"]
                  if o.get("V39079", {}).get("v") not in (None, ""))


_BIS_H = {}


def bis_hist(area):
    if not _BIS_H:
        url = ("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/"
               f"D.GB+JP+AU+NZ+CH?startPeriod={start_date()}&format=csv")
        for row in csv.DictReader(io.StringIO(get(url))):
            _BIS_H.setdefault(row["REF_AREA"], []).append(
                (row["TIME_PERIOD"][:10], float(row["OBS_VALUE"])))
        for k in _BIS_H:
            _BIS_H[k].sort()
    if area not in _BIS_H:
        raise ValueError(f"no BIS history for {area}")
    return _BIS_H[area]


HISTORY = {
    "USD": lambda: fred_hist("DFEDTARU"),
    "EUR": ecb_hist,
    "CAD": boc_hist,
    "GBP": lambda: bis_hist("GB"),
    "JPY": lambda: bis_hist("JP"),
    "AUD": rba_points,
    "NZD": lambda: bis_hist("NZ"),
    "CHF": lambda: bis_hist("CH"),
}


def value_at(points, target):
    """Rate in force on `target` (last observation on or before it); None if unknown."""
    prior = [v for d, v in points if d <= target]
    return prior[-1] if prior else None


def bias_from_change(change):
    if change is None:
        return None
    if change >= BIAS_STEP:
        return "hawkish"
    if change <= -BIAS_STEP:
        return "dovish"
    return "neutral"


# currency, bank, indicator, official page, fetcher, max age (days), origin label
SOURCES = [
    ("USD", "Federal Reserve", "Fed funds target range (upper bound)",
     "https://www.federalreserve.gov/monetarypolicy.htm", lambda: fred("DFEDTARU"), 14, "FRED / Board of Governors"),
    ("EUR", "European Central Bank", "Deposit facility rate",
     "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html", ecb_dfr, 14, "ECB Data Portal"),
    ("CAD", "Bank of Canada", "Target for the overnight rate",
     "https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/", boc_target, 14, "Bank of Canada Valet API"),
    ("GBP", "Bank of England", "Policy rate (BIS)",
     "https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate", lambda: bis("GB"), 14, "BIS central bank policy rates (secondary source)"),
    ("JPY", "Bank of Japan", "Policy rate (BIS)",
     "https://www.boj.or.jp/en/mopo/", lambda: bis("JP"), 14, "BIS central bank policy rates (secondary source)"),
    ("AUD", "Reserve Bank of Australia", "Cash rate target",
     "https://www.rba.gov.au/statistics/cash-rate/", rba_latest, 14, "RBA statistical table F1.1"),
    ("NZD", "Reserve Bank of New Zealand", "Policy rate (BIS)",
     "https://www.rbnz.govt.nz/monetary-policy/about-monetary-policy/the-official-cash-rate", lambda: bis("NZ"), 14, "BIS central bank policy rates (secondary source)"),
    ("CHF", "Swiss National Bank", "Policy rate (BIS)",
     "https://www.snb.ch/en/the-snb/mandates-goals/monetary-policy/decisions", lambda: bis("CH"), 14, "BIS central bank policy rates (secondary source)"),
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
            entry = {
                "currency": ccy, "central_bank": bank, "indicator": indicator,
                "value_percent": value, "observation_date": obs_date[:10],
                "source_url": page, "origin": origin,
                "value_6m_ago": None, "change_6m": None, "bias": None,
            }
            try:  # history is optional: if it fails the rate is still published, bias stays null
                target = (now.date() - timedelta(days=BIAS_DAYS)).isoformat()
                past = value_at(HISTORY[ccy](), target)
                if past is not None and -1.0 <= past <= 25.0:
                    entry["value_6m_ago"] = past
                    entry["change_6m"] = round(value - past, 4)
                    entry["bias"] = bias_from_change(entry["change_6m"])
            except Exception as e:  # noqa: BLE001
                entry["history_error"] = f"{type(e).__name__}: {e}"
            rates.append(entry)
        except Exception as e:  # noqa: BLE001 - report every failure, never guess
            errors.append({
                "currency": ccy, "central_bank": bank, "source_url": page,
                "status": "unavailable", "error": f"{type(e).__name__}: {e}",
            })
    out = {
        "schema_version": 1,
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "Only validated observations are listed. Missing currencies appear in source_errors. bias = direction of the policy rate over ~6 months (hawkish: +0.25 or more, dovish: -0.25 or less), not the tone of central bank statements.",
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
