"""Build the monthly yearbook against the same vintage as both local cycle panels.

Run the existing US and euro-area cycle builders first. Use --save-inputs to retain
the additional source responses. Use --input-dir for an exact offline rebuild.
The ONS labour table requires openpyxl. No months are interpolated.
"""
import argparse
import calendar
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from openpyxl import load_workbook

DATA = Path(__file__).resolve().parents[1] / "dist/data"
ONS = "https://www.ons.gov.uk"
UK_CPI = ONS + "/economy/inflationandpriceindices/timeseries/d7g7/mm23"
UK_IP = ONS + "/economy/economicoutputandproductivity/output/timeseries/k222/diop"
UK_JOB = ONS + "/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/datasets/labourforcesurveysinglemonthestimatesx01"
START = "1999-12"


def annual_change(data, month, digits):
    prior = data.get(str(int(month[:4]) - 1) + month[4:])
    current = data.get(month)
    if not prior or current is None:
        return None
    return float(round(100 * (Decimal(str(current)) / Decimal(str(prior)) - 1), digits))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--save-inputs", type=Path)
    parser.add_argument("--output", type=Path, default=DATA / "macro-yearbook.json")
    args = parser.parse_args()
    us, ea = [json.loads((DATA / name).read_text()) for name in ("cycle-context.json","euro-cycle-context.json")]
    vintage = date.fromisoformat(us["asOf"])
    if ea["asOf"] != vintage.isoformat():
        raise ValueError("The two cycle panels must use the same observation vintage")
    last = (vintage.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    receipts = {}

    def fetch(key, url):
        if args.input_dir:
            body = (args.input_dir / key).read_bytes()
        else:
            with urlopen(Request(url, headers={"User-Agent":"Mozilla/5.0"}), timeout=60) as response:
                body = response.read()
        if args.save_inputs:
            args.save_inputs.mkdir(exist_ok=True, parents=True)
            (args.save_inputs / key).write_bytes(body)
        receipts[key] = {"url": url, "sha256": hashlib.sha256(body).hexdigest()}
        return body

    query = urlencode({"id":"CPIAUCNS", "cosd":"1998-12-01", "coed":(vintage.replace(day=1) - timedelta(days=1)).isoformat(), "vintage_date":vintage.isoformat()})
    csv_data = csv.DictReader(io.StringIO(fetch("us-cpi.csv","https://alfred.stlouisfed.org/graph/alfredgraph.csv?" + query).decode()))
    col = "CPIAUCNS_" + vintage.strftime("%Y%m%d")
    if csv_data.fieldnames != ["observation_date", col]:
        raise ValueError("Unexpected US CPI source vintage")
    us_cpi = {r["observation_date"][:7]:Decimal(r[col]) for r in csv_data if r[col] not in ("",".")}

    def ons_months(key, url, code):
        doc = json.loads(fetch(key, url + "/data"))
        if doc["description"]["cdid"].upper() != code or doc["description"]["releaseDate"][:10] > vintage.isoformat():
            raise ValueError("Unexpected ONS series or release date: " + code)
        month_numbers = {name.upper(): str(i).zfill(2) for i, name in enumerate(calendar.month_abbr) if name}
        return {r["date"][:4]+"-"+month_numbers[r["date"][-3:]]:float(r["value"]) for r in doc["months"] if r["value"] not in (":","", "..")}

    uk_cpi = ons_months("ukcpi", UK_CPI, "D7G7")
    uk_ip = ons_months("ukip", UK_IP, "K222")
    page = fetch("uklab", UK_JOB).decode()
    file_link = re.search(r'href="(/file\?uri=[^"]+/current/x01([a-z]{3})(\d{4})\.xlsx)"', page, re.I)
    release = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page)
    if not file_link or not release or release[1][:10] > vintage.isoformat():
        raise ValueError("Unexpected ONS X01 edition")
    sheet = load_workbook(io.BytesIO(fetch("x01.xlsx", urljoin(ONS,file_link[1]))),read_only=True,data_only=True)["X01 SM Estimates"]
    matrix = list(sheet.values)
    if matrix[2][24].strip() != "UK 16+ Unemployment Rates (SA)" or [matrix[n][27] for n in (4,5)] != ["Single","Month Rate"]:
        raise ValueError("Unexpected X01 single-month unemployment columns")
    uk_job = {r[24].strftime("%Y-%m"):round(r[27],3) for r in matrix[6:] if isinstance(r[24],datetime) and isinstance(r[27],(int,float))}

    params = {"lang":"en","freq":"M","geo":"EA21","sinceTimePeriod":"1998-12","untilTimePeriod":"2000-12","indic_bt":"PRD","s_adj":"SCA","nace_r2":"B-D","unit":"I21"}
    ip = json.loads(fetch("eaip","https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_inpr_m?" + urlencode(params)))
    if ip["updated"][:10] > vintage.isoformat() or ip["dimension"]["geo"]["category"]["index"] != {"EA21": 0}:
        raise ValueError("Unexpected euro-area production vintage or geography")
    times = ip["dimension"]["time"]["category"]["index"]
    euro_ip = {m:ip["value"].get(str(i)) for m,i in times.items()}
    panels = {}
    for name, panel in [("US",us),("EA",ea)]:
        panels[name] = {r["month"]:{"prices":annual_change(us_cpi,r["month"],1) if name=="US" else r["cpiYoY"], "jobless":r["unemployment"], "industry":r["industrialProductionYoY"], "output":r["industrialProduction"]} for r in panel["rows"] if START <= r["month"] <= last}
    panels["EA"][START] = {"prices":None,"jobless":None,"industry":annual_change(euro_ip,START,3),"output":euro_ip[START]}
    panels["UK"] = {m:{"prices":uk_cpi.get(m),"jobless":uk_job.get(m),"industry":annual_change(uk_ip,m,3),"output":uk_ip.get(m)} for m in sorted(set(uk_cpi) | set(uk_job) | set(uk_ip)) if START <= m <= last}
    for code, panel in panels.items():
        if not all(any(r[key] is not None for r in panel.values()) for key in ("prices","jobless","industry","output")):
            raise ValueError("Empty yearbook series for " + code)
    flags = dict(ea["statusByMonth"].get("industrialProductionYoY",{}))
    base_flags = {flag for m in ("1998-12",START) for flag in ip.get("status",{}).get(str(times[m]),"").split()}
    if base_flags:
        flags[START] = " ".join(sorted(base_flags))
    out = {"asOf":vintage.isoformat(),"panels":panels,"supplementSources":receipts,"euroProductionFlags":flags}
    args.output.write_text(json.dumps(out,separators=(",",":"))+"\n")


if __name__ == "__main__":
    main()
