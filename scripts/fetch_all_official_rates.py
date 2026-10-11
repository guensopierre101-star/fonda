#!/usr/bin/env python3
"""Official central-bank policy rates. Never guess values when a source cannot be parsed."""
import csv, io, json, os, urllib.request
from datetime import datetime, timezone

SOURCES = [
 {"currency":"USD","bank":"Federal Reserve","indicator":"Federal funds target range upper bound","kind":"csv","url":"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU","source":"https://www.federalreserve.gov/monetarypolicy.htm","date":"observation_date","value":"DFEDTARU"},
 {"currency":"EUR","bank":"European Central Bank","indicator":"Main refinancing operations rate","kind":"csv","url":"https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.MRR_FR.LEV?format=csvdata&lastNObservations=1","source":"https://www.ecb.europa.eu/press/govcdec/mopo/html/index.en.html","date":"TIME_PERIOD","value":"OBS_VALUE"},
 {"currency":"GBP","bank":"Bank of England","indicator":"Official Bank Rate","kind":"unavailable","url":"https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp","source":"https://www.bankofengland.co.uk/monetary-policy"},
 {"currency":"JPY","bank":"Bank of Japan","indicator":"Policy interest rate","kind":"unavailable","url":"https://www.boj.or.jp/en/mopo/","source":"https://www.boj.or.jp/en/mopo/"},
 {"currency":"CAD","bank":"Bank of Canada","indicator":"Target for the overnight rate","kind":"unavailable","url":"https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/","source":"https://www.bankofcanada.ca/core-functions/monetary-policy/"},
 {"currency":"AUD","bank":"Reserve Bank of Australia","indicator":"Cash rate target","kind":"unavailable","url":"https://www.rba.gov.au/statistics/cash-rate/","source":"https://www.rba.gov.au/monetary-policy/"},
 {"currency":"NZD","bank":"Reserve Bank of New Zealand","indicator":"Official Cash Rate","kind":"unavailable","url":"https://www.rbnz.govt.nz/monetary-policy/about-monetary-policy/the-official-cash-rate","source":"https://www.rbnz.govt.nz/monetary-policy"},
 {"currency":"CHF","bank":"Swiss National Bank","indicator":"SNB policy rate","kind":"unavailable","url":"https://www.snb.ch/en/the-snb/mandates-goals/monetary-policy","source":"https://www.snb.ch/en/the-snb/mandates-goals/monetary-policy"},
]

def collect(s):
    if s["kind"] != "csv":
        raise RuntimeError("Official source identified, but a reliable machine-readable adapter has not yet been validated.")
    req = urllib.request.Request(s["url"], headers={"User-Agent":"FundamentalFXDesk/1.0", "Accept":"text/csv"})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(raw)))
    for row in reversed(rows):
        date, value = row.get(s["date"]), row.get(s["value"])
        if not date or value in (None, "", "."): continue
        try: number = float(value)
        except ValueError: continue
        if not -2 <= number <= 30: continue
        return {"currency":s["currency"],"central_bank":s["bank"],"indicator":s["indicator"],"value_percent":number,"observation_date":date,"source_url":s["source"],"api_url":s["url"],"status":"verified"}
    raise ValueError("No valid date/rate observation in official response")

def main():
    os.makedirs("data", exist_ok=True)
    out={"schema_version":1,"generated_at_utc":datetime.now(timezone.utc).isoformat(),"note":"Coverage lists all eight central banks. Only successfully parsed official machine-readable observations appear as verified rates. Unavailable adapters are not replaced by estimates. Do not derive trading signals from partial coverage.","coverage":{"total_currencies":8,"verified":0,"unavailable":0},"rates":[],"source_errors":[]}
    for s in SOURCES:
        try:
            out["rates"].append(collect(s)); out["coverage"]["verified"] += 1
        except Exception as e:
            out["coverage"]["unavailable"] += 1
            out["source_errors"].append({"currency":s["currency"],"central_bank":s["bank"],"source_url":s["source"],"official_data_url":s["url"],"status":"unavailable","error":str(e)[:220]})
    with open("data/official-rates.json","w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=2); f.write("\n")
    print("Official central-bank rates:",out["coverage"]["verified"],"verified / 8 currencies; unavailable:",out["coverage"]["unavailable"])

if __name__ == "__main__": main()
