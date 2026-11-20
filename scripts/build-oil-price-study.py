"""Screen monthly Brent declines and capture official US and euro-area measurements.

Build against the published cycle panels' vintage. Save the source responses with
--save-inputs; use --input-dir for an exact offline rebuild. Requires lxml.
"""
import argparse
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lxml import html

DATA = Path(__file__).resolve().parents[1] / "dist/data"
EIA = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=RBRTE&f=M"
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr"
BLS = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def shift(month, steps):
    year, m = map(int, month.split("-"))
    y, n = divmod(year*12 + m - 1 + steps, 12)
    return f"{y}-{n+1:02}"


def screen(prices, threshold):
    kept = []
    def meets(m):
        return 100 * prices[m] <= (100 - threshold) * prices[shift(m,-6)]
    for m in sorted(prices):
        if m < "2000-01" or not all(shift(m, n) in prices for n in (-1,-6,-7)):
            continue
        if meets(m) and not meets(shift(m,-1)) and (not kept or m > shift(kept[-1],12)):
            kept.append(m)
    return kept


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir",type=Path)
    parser.add_argument("--save-inputs",type=Path)
    parser.add_argument("--output",type=Path,default=DATA/"oil-price-study.json")
    args = parser.parse_args()
    files = {"US":"cycle-context.json","EA":"euro-cycle-context.json"}
    panels = {k:json.loads((DATA/f).read_bytes()) for k,f in files.items()}
    vintage = date.fromisoformat(panels["US"]["asOf"])
    assert panels["EA"]["asOf"] == vintage.isoformat()
    end = (vintage.replace(day=1)-timedelta(days=1)).strftime("%Y-%m")
    receipts = {}
    def fetch(key,url):
        if args.input_dir: body = (args.input_dir/key).read_bytes()
        else:
            with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=60) as resp: body=resp.read()
        if args.save_inputs:
            args.save_inputs.mkdir(exist_ok=True,parents=True); (args.save_inputs/key).write_bytes(body)
        receipts[key] = {"url":url,"sha256":hashlib.sha256(body).hexdigest()}
        return body

    oil_page = html.fromstring(fetch("brent",EIA))
    assert "Europe Brent Spot Price FOB" in oil_page.xpath("string(//title)")
    release = re.search(r"(?<!Next )Release Date:\s*(\d+/\d+/\d+)",oil_page.text_content())
    assert release and datetime.strptime(release[1],"%m/%d/%Y").date() <= vintage
    oil = {}
    for tr in oil_page.xpath("//tr"):
        cells = [c.text_content().strip() for c in tr.xpath("./th|./td")]
        if len(cells)==13 and cells[0].isdigit():
            for i,val in enumerate(cells[1:],1):
                month=f"{cells[0]}-{i:02}"
                if val and month<=end: oil[month]=Decimal(val)
    assert max(oil)==end, "Brent monthly series is not current to the chosen vintage"

    annual = {"US":{},"EA":{}}
    for label,series in [("energy","CUUR0000SA0E"),("core","CUUR0000SA0L1E")]:
        values = {}
        for start,stop in [(1998,2006)]+[(y,min(y+9,vintage.year)) for y in range(2007,vintage.year+1,10)]:
            key=f"{series}-{start}"
            doc=json.loads(fetch(key,BLS+series+"?"+urlencode({"startyear":start,"endyear":stop})))
            assert doc["status"]=="REQUEST_SUCCEEDED" and doc["Results"]["series"][0]["seriesID"]==series
            for r in doc["Results"]["series"][0]["data"]:
                if r["period"].startswith("M") and r["period"]!="M13" and r["value"] not in ("-",".",""):
                    values[r["year"]+"-"+r["period"][1:]]=Decimal(r["value"])
        annual["US"][label] = {m:float(round(100*(v/values[shift(m,-12)]-1),3)) for m,v in values.items() if shift(m,-12) in values}
    flags={}
    for label,code in [("energy","NRG"),("core","TOT_X_NRG_FOOD")]:
        keys={"lang":"en","freq":"M","geo":"EA21","coicop18":code,"unit":"RCH_A","sinceTimePeriod":"1998-01","untilTimePeriod":end}
        doc=json.loads(fetch(code+"-annual",EUROSTAT+"?"+urlencode(keys)))
        assert doc["source"]=="ESTAT" and doc["updated"][:10]<=vintage.isoformat()
        for dim in ("freq","geo","coicop18","unit"): assert doc["dimension"][dim]["category"]["index"]=={keys[dim]:0}
        assert doc["id"][-1]=="time"
        months=doc["dimension"]["time"]["category"]["index"]
        annual["EA"][label]={m:doc["value"][str(i)] for m,i in months.items() if str(i) in doc["value"] and "f" not in doc.get("status",{}).get(str(i),"").split()}
        flags[label]={m:doc["status"][str(i)] for m,i in months.items() if str(i) in doc.get("status",{})}
    indexes={k:{r["month"]:r["industrialProduction"] for r in p["rows"]}for k,p in panels.items()}
    flags["output"]=panels["EA"]["statusByMonth"].get("industrialProduction",{})
    historical=json.loads((DATA/"historical-series.json").read_bytes()); origin=date.fromisoformat(historical["start"])
    rates={k:next(s for s in historical["series"] if s["metric"]=="rates" and s["id"]==code) for k,code in [("US","US"),("EA","XM")]}
    def month_end_policy(area,month):
        y,m=map(int,month.split("-"));day=(date(y,m,monthrange(y,m)[1])-origin).days
        return next((r[2] for r in rates[area]["observations"] if r[0]<=day<r[0]+r[1]),None)
    events={str(n):screen(oil,n) for n in (25,30,35)}
    anchors=sorted({m for dates in events.values() for m in dates})
    months=sorted({shift(a,k) for a in anchors for k in range(-6,13) if shift(a,k)<=end})
    obs={m:{"brent":float(oil[m]),**{k:{"energy":annual[k]["energy"].get(m),"core":annual[k]["core"].get(m),"output":indexes[k].get(m)}for k in annual}}for m in months}
    policies={m:{k:month_end_policy(k,m) for k in rates} for m in anchors}
    assert all(isinstance(v,(float,int)) for rates_at_month in policies.values() for v in rates_at_month.values())
    out={"asOf":vintage.isoformat(),"through":end,"events":events,"policies":policies,"observations":obs,"flags":{k:{m:v for m,v in series.items() if m in obs}for k,series in flags.items()},"sources":receipts}
    for name in [*files.values(),"historical-series.json"]: out["sources"][name]={"file":name,"sha256":hashlib.sha256((DATA/name).read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(out,separators=(",",":"))+"\n")


if __name__=="__main__":
    main()
