#!/usr/bin/env python3
"""Collect CFTC Commitments of Traders (futures only) for the 8 currencies and gold.

Source: CFTC Public Reporting Environment (Socrata), free, no key.
 - Traders in Financial Futures (TFF), dataset gpe5-46if: currency futures,
   speculators = Leveraged Funds.
 - Disaggregated, dataset 72hh-3qpy: COMEX gold, speculators = Managed Money.
Writes data/cot.json. A market is published only if its contract name matches
what we expect; otherwise it goes to errors. Nothing is ever invented.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "cot.json")
BASE = "https://publicreporting.cftc.gov/resource/"
UA = {"User-Agent": "fonda-fx-desk/1.0 (+https://github.com/guensopierre101-star/fonda)"}

TFF = "gpe5-46if"
DISAGG = "72hh-3qpy"

# label, dataset, CFTC contract code, substring expected in contract_market_name,
# speculator group label, long field, short field, change-long field, change-short field
TFF_F = ("Leveraged Funds", "lev_money_positions_long", "lev_money_positions_short",
         "change_in_lev_money_long", "change_in_lev_money_short")
DIS_F = ("Managed Money", "m_money_positions_long_all", "m_money_positions_short_all",
         "change_in_m_money_long_all", "change_in_m_money_short_all")

MARKETS = [
    ("USD", "USD Index (ICE)", TFF, "098662", "U.S. DOLLAR INDEX", TFF_F),
    ("EUR", "Euro FX (CME)", TFF, "099741", "EURO FX", TFF_F),
    ("GBP", "British Pound (CME)", TFF, "096742", "BRITISH POUND", TFF_F),
    ("JPY", "Japanese Yen (CME)", TFF, "097741", "JAPANESE YEN", TFF_F),
    ("CAD", "Canadian Dollar (CME)", TFF, "090741", "CANADIAN DOLLAR", TFF_F),
    ("AUD", "Australian Dollar (CME)", TFF, "232741", "AUSTRALIAN DOLLAR", TFF_F),
    ("NZD", "New Zealand Dollar (CME)", TFF, "112741", "NZ DOLLAR", TFF_F),
    ("CHF", "Swiss Franc (CME)", TFF, "092741", "SWISS FRANC", TFF_F),
    ("XAU", "Gold (COMEX)", DISAGG, "088691", "GOLD", DIS_F),
]


def fetch_rows(dataset, code):
    q = urllib.parse.urlencode({
        "$where": f"cftc_contract_market_code='{code}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "2",
    })
    req = urllib.request.Request(f"{BASE}{dataset}.json?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def num(row, key):
    v = row.get(key)
    if v is None or v == "":
        raise ValueError(f"missing field {key}")
    return int(float(v))


def build(label, name, dataset, code, expect, fields):
    group, f_long, f_short, f_chg_long, f_chg_short = fields
    rows = fetch_rows(dataset, code)
    if not rows:
        raise ValueError("no rows returned")
    cur = rows[0]
    cname = (cur.get("contract_market_name") or "").upper()
    if expect not in cname:
        raise ValueError(f"unexpected contract '{cname}' for code {code}")
    long_, short = num(cur, f_long), num(cur, f_short)
    net = long_ - short
    net_change = num(cur, f_chg_long) - num(cur, f_chg_short)
    out = {
        "currency": label, "market": name, "group": group,
        "long": long_, "short": short, "net": net, "net_change": net_change,
        "open_interest": num(cur, "open_interest_all"),
        "nonreportable_net": num(cur, "nonrept_positions_long_all") - num(cur, "nonrept_positions_short_all"),
        "report_date": cur["report_date_as_yyyy_mm_dd"][:10],
        "contract_name": cur.get("contract_market_name"),
    }
    if len(rows) > 1:
        out["previous_report_date"] = rows[1]["report_date_as_yyyy_mm_dd"][:10]
    return out


def main():
    now = datetime.now(timezone.utc)
    markets, errors = [], []
    for label, name, dataset, code, expect, fields in MARKETS:
        try:
            markets.append(build(label, name, dataset, code, expect, fields))
        except Exception as e:  # noqa: BLE001
            errors.append({"currency": label, "market": name, "status": "unavailable",
                           "error": f"{type(e).__name__}: {e}"})
    report_date = max((m["report_date"] for m in markets), default=None)
    out = {
        "schema_version": 1,
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "CFTC Commitments of Traders, futures only (TFF for currencies, Disaggregated for gold)",
        "report_date": report_date,
        "coverage": {"total": len(MARKETS), "verified": len(markets), "unavailable": len(errors)},
        "markets": markets,
        "errors": errors,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"verified={len(markets)} unavailable={len(errors)} report_date={report_date}")
    for e in errors:
        print(f"  {e['currency']}: {e['error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
