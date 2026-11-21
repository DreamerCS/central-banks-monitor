"""Refresh the World Development Indicators used in the historical yearbook."""
import argparse
import json
import math
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from yearbook_taiwan import read_annual

ROOT = Path(__file__).resolve().parents[1] / "dist" / "data"
COUNTRIES = dict(pair.split(":") for pair in (
    "US:USA XM:EMU GB:GBR SE:SWE NO:NOR CH:CHE CA:CAN AU:AUS NZ:NZL JP:JPN "
    "MX:MEX CO:COL BR:BRA AR:ARG PE:PER HU:HUN PL:POL CZ:CZE TR:TUR ZA:ZAF "
    "CN:CHN KR:KOR SG:SGP IN:IND ID:IDN MY:MYS PH:PHL TH:THA").split())
INDICATORS = {"gdp": "NY.GDP.MKTP.KD.ZG", "inflation": "FP.CPI.TOTL.ZG"}


def fetch_series(indicator, end):
    codes = ";".join(COUNTRIES.values())
    url = (f"https://api.worldbank.org/v2/country/{codes}/indicator/{indicator}"
           f"?source=2&date=1999:{end}&format=json&per_page=5000")
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "ThePolicyTape Yearbook"})
            with urlopen(request, timeout=45) as response:
                meta, rows = json.load(response)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    if meta["pages"] != 1 or len(rows) != int(meta["total"]):
        raise ValueError(f"Incomplete World Bank result for {indicator}")
    data = {}
    for row in rows:
        value = row["value"]
        if value is None:
            continue
        key = (row["countryiso3code"], int(row["date"]))
        if row["indicator"]["id"] != indicator or key in data or not math.isfinite(value):
            raise ValueError(f"Unexpected observation for {indicator}: {key}")
        data[key] = round(value, 3)
    if {code for code, _ in data} != set(COUNTRIES.values()):
        missing = set(COUNTRIES.values()) - {code for code, _ in data}
        if indicator == INDICATORS["gdp"] or len(missing) > 2:
            raise ValueError(f"Check missing economies for {indicator}: {missing}")
    return meta["lastupdated"], data


def build(end, taiwan_inputs=None):
    series = json.loads((ROOT / "historical-series.json").read_text())["series"]
    if set(COUNTRIES) != {item["id"] for item in series} - {"TW"}:
        raise ValueError("Map the new jurisdictions before rebuilding")
    values, vintages = {}, {}
    for key, code in INDICATORS.items():
        vintages[key], values[key] = fetch_series(code, end)
    # A row always means the reference year on that economy's own series.
    rows = []
    for economy in series:
        code = COUNTRIES.get(economy["id"])
        annual = {}
        for year in range(1999, end + 1):
            pair = [values[key].get((code, year)) for key in INDICATORS]
            if any(value is not None for value in pair):
                annual[year] = pair
        rows.append({"id": economy["id"], "name": economy["name"], "region": economy["region"],
                     "code": code, "years": annual})
    taiwan = read_annual(1999, end, taiwan_inputs)
    target = next(row for row in rows if row["id"] == "TW")
    target.update(years=taiwan["rows"], sources=taiwan["sourceUrls"],
                  note=taiwan["notes"] + " " + taiwan["vintage"])
    return {"through": end, "vintages": vintages, "indicators": INDICATORS, "economies": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", type=int, default=date.today().year - 1)
    parser.add_argument("--taiwan-inputs", type=Path, help="Local DGBAS gdp.ods, cpi.ods and cpi-levels.ods")
    args = parser.parse_args()
    if args.through >= date.today().year or args.through < 2000:
        parser.error("Use a completed year from 2000 onwards")
    data = build(args.through, args.taiwan_inputs)
    target = ROOT / "yearbook-economies.json"
    target.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
