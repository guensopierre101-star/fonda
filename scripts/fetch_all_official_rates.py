#!/usr/bin/env python3
"""Official central-bank policy rates. Never guess values when a source cannot be parsed."""
import csv, io, json, os, urllib.request
from datetime import datetime, timezone

SOURCES = [
 {"currency":"USD","bank":"Federal Reserve","indicator":"Federal funds target range upper bound","kind":"csv","url":"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU","source":"https://www.federalreserve.gov/monetarypolicy.htm","date":"observation_date","value":"DFEDTARU"},
 {"currency":"EUR","bank":"European Central Bank","indicator":"Main refinancing operations rate","kind":"csv","url":"https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.MRR_FR.LEV?format=csvdata&lastNObservations=1","source":"https://www.ecb.europa.eu/press/govcdec/mopo/html/index.en.html","date":"TIME_PERIOD","value":"OBS_VALUE"},
 {"currency":"GBP","bank":"Bank of England","indicator":"Official Bank Rate","kind":"html","url":"https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp","source":"https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp","pattern":r"Current official Bank Rate\s*([0-9]+(?:\.[0-9]+)?)\s*%","date_pattern":r"(\d{2} [A-Z][a-z]{2} \d{2})\s*\|\s*[0-9]+(?:\.[0-9]+)?"},
 {"currency":"JPY","bank":"Bank of Japan","indicator":"Policy interest rate","kind":"unavailable","url":"https://www.boj.or.jp/en/mopo/","source":"https://www.boj.or.jp/en/mopo/"},
 {"currency":"CAD","bank":"Bank of Canada","indicator":"Target for the overnight rate","kind":"csv","url":"https://www.bankofcanada.ca/valet/observations/V39079/json?recent=1","source":"https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/","json_series":"V39079"},
 {"currency":"AUD","bank":"Reserve Bank of Australia","indicator":"Cash rate target","kind":"html","url":"https://www.rba.gov.au/statistics/cash-rate/","source":"https://www.rba.gov.au/statistics/cash-rate/","pattern":r"Cash rate target\s*%?\s*</[^>]+>\s*<[^>]+>\s*([0-9]+(?:\.[0-9]+)?)","date_pattern":r"(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})"},
 {"currency":"NZD","bank":"Reserve Bank of New Zealand","indicator":"Official Cash Rate","kind":"html","url":"https://www.rbnz.govt.nz/monetary-policy/about-monetary-policy/the-official-cash-rate","source":"https://www.rbnz.govt.nz/monetary-policy/about-monetary-policy/the-official-cash-rate","pattern":r"Official Cash Rate\s*([0-9]+(?:\.[0-9]+)?)\s*%","date_pattern":r"Updated:?\s*([0-9]{1,2}\s+[A-Z][a-z]+\s+\d{4})"},
 {"currency":"CHF","bank":"Swiss National Bank","indicator":"SNB policy rate","kind":"csv","url":"https://data.snb.ch/api/cube/snboffzisa/data/csv/en","source":"https://data.snb.ch/en/topics/snb/cube/snboffzisa","snb":true},
]

def collect(s):
    req = urllib.request.Request(s["url"], headers={"User-Agent":"FundamentalFXDesk/1.0", "Accept":"text/csv, application/json, text/html"})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read().decode("utf-8-sig", errors="replace")
    if s["kind"] == "unavailable":
        raise RuntimeError("No validated adapter for this official source.")
    if s["kind"] == "html":
        import re
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text)
        match = re.search(s["pattern"], text, re.I)
        if not match:
            raise ValueError("Could not validate the official rate on the source page")
        number = float(match.group(1))
        date_match = re.search(s["date_pattern"], text, re.I)
        if not date_match:
            raise ValueError("Could not validate an observation date on the source page")
        date = date_match.group(1)
        return {"currency":s["currency"],"central_bank":s["bank"],"indicator":s["indicator"],"value_percent":number,"observation_date":date,"source_url":s["source"],"api_url":s["url"],"status":"verified"}
    if s.get("json_series"):
        payload = json.loads(raw)
        observations = payload.get("observations", [])
        for obs in reversed(observations):
            value = obs.get(s["json_series"], {}).get("v")
            date = obs.get("d")
            if value is not None and date:
                number = float(value)
                if -2 <= number <= 30:
                    return {"currency":s["currency"],"central_bank":s["bank"],"indicator":s["indicator"],"value_percent":number,"observation_date":date,"source_url":s["source"],"api_url":s["url"],"status":"verified"}
        raise ValueError("No valid dated observation in official JSON")
    if s.get("snb"):
        rows = list(csv.reader(io.StringIO(raw)))
        # Require a row explicitly identified as the policy-rate series and a real date; never guess a numeric cell.
        for row in reversed(rows):
            joined = " ".join(row)
            if ("policy rate" in joined.lower() or "policy-rate" in joined.lower()) and len(row) >= 2:
                for cell in reversed(row):
                    try:
                        number = float(cell.replace(",", "."))
                        if -2 <= number <= 30 and row[0] and any(ch.isdigit() for ch in row[0]):
                            return {"currency":s["currency"],"central_bank":s["bank"],"indicator":s["indicator"],"value_percent":number,"observation_date":row[0],"source_url":s["source"],"api_url":s["url"],"status":"verified"}
                    except ValueError:
                        continue
        raise ValueError("Could not identify the SNB policy-rate series in CSV")
    if s["kind"] != "csv":
        raise RuntimeError("No validated adapter for this official source.")
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
