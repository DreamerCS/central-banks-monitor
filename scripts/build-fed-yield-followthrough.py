"""Compare scheduled Fed statement-window yield moves with daily US Treasury fixes.

Rebuild from the pinned 2026-11-20 ALFRED vintage with:
  python scripts/build-fed-yield-followthrough.py --save-inputs /tmp/fed-yield-inputs
  python scripts/build-fed-yield-followthrough.py --input-dir /tmp/fed-yield-inputs --check
"""
import argparse
import csv
import importlib.util
import io
import json
import math
from bisect import bisect_left
from datetime import date, time
from pathlib import Path
from statistics import fmean, median

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "dist/data"
spec = importlib.util.spec_from_file_location("curve_input", HERE / "build-curve-timing.py")
curve_input = importlib.util.module_from_spec(spec)
spec.loader.exec_module(curve_input)
START, END = "2000-01-01", "2025-12-31"
THRESHOLDS = (1, 2, 5)
WINDOWS = {
    "priorToEvent": ("prior", "event"), "priorToNext": ("prior", "next"),
    "priorToFifth": ("prior", "fifth"), "eventToNext": ("event", "next"), "eventToFifth": ("event", "fifth"),
}
LABELS = {"yield2y":"US two-year Treasury yield","slope":"US 10-year minus two-year Treasury slope"}
METHOD = [
    "The frame comprises scheduled FOMC releases with an eligible statement window from 2000 through 2025. Each release enters once. The intraday move uses USMPD market quotes from ten minutes before to twenty minutes after the release. Dates are US Eastern.",
    "Daily H.15 two- and ten-year constant-maturity par yields are derived from indicative Treasury bid quotes at or near 3:30 p.m. Eastern. They are rounded to a basis point and may differ from the benchmark security quotes used intraday. The slope is the ten-year yield minus the two-year yield in both settings.",
    "Daily horizons use actual observed fixing dates, require the release date itself, and skip holidays and missing quotes. The fifth fixing after the meeting is five observed trading dates later. For the slope, a date requires both yields. Cumulative changes start at the previous fixing. Subsequent changes start at the meeting-day fixing and omit the announcement window.",
    "The primary sample requires an absolute intraday move strictly greater than 2 bp. The 1 bp and 5 bp thresholds use the same strict rule. Same-direction share divides strictly matching signs by all observations, including flat daily changes. Up and down groups refer to the sign of the intraday move.",
    "The magnitude ratio is the median of signed daily change divided by intraday change, computed separately at each horizon. A ratio of one means matching direction and size. A negative ratio means a reversal. Correlations use signed changes. The rows at different horizons share meetings and are descriptive.",
    "The previous-fixing-to-event change includes trading before the announcement. Later horizons can reflect the press conference, economic data and other news. Cumulative agreement can persist even when the market moves in the opposite direction after the event-day fixing.",
]


def round_or_none(x):
    return round(x, 7) if x is not None else None


def summaries(observations, delta):
    xy = [(r["intradayBp"],r[delta]) for r in observations if r[delta] is not None]
    n = len(xy)
    same = sum(x*y > 0 for x,y in xy)
    opp = sum(x*y < 0 for x,y in xy)
    rho = None
    if n > 1:
        xb,yb = fmean(x for x,_ in xy),fmean(y for _,y in xy)
        xx = math.fsum((x-xb)**2 for x,_ in xy)
        yy = math.fsum((y-yb)**2 for _,y in xy)
        if xx and yy:
            rho = math.fsum((x-xb)*(y-yb) for x,y in xy)/math.sqrt(xx*yy)
    return {"n":n, "sameDirection":same, "oppositeDirection":opp, "flat":n-same-opp,
            "sameShare":round_or_none(same/n if n else None),
            "medianAbsIntradayBp":round_or_none(median(abs(x) for x,_ in xy) if n else None),
            "medianAbsDailyMoveBp":round_or_none(median(abs(y) for _,y in xy) if n else None),
            "medianDailyOverIntraday":round_or_none(median(y/x for x,y in xy) if n else None),
            "correlation":round_or_none(rho)}


def event_rows(meetings, series):
    result = []
    days = {k:sorted(yields) for k,yields in series.items()}
    for meeting in meetings:
        for asset,yields in series.items():
            day = date.fromisoformat(meeting["date"])
            dates = days[asset]
            index = bisect_left(dates,day)
            anchors = dict.fromkeys(("prior","event","next","fifth"))
            if index < len(dates) and dates[index] == day:
                for name,offset in (("prior",-1),("event",0),("next",1),("fifth",5)):
                    if 0 <= index+offset < len(dates):
                        anchors[name] = dates[index+offset]
            r = {"date":str(day),"releaseTimeET":meeting["time"],"asset":asset,"intradayBp":meeting["values"].get(asset)}
            for name,anchor in anchors.items():
                r[name+"Date"] = str(anchor) if anchor else None
                r[name+"LevelBp"] = yields[anchor] if anchor else None
            for key,(a,b) in WINDOWS.items():
                r[key] = yields[anchors[b]]-yields[anchors[a]] if anchors[a] and anchors[b] else None
            r["officialSource"] = meeting["documentUrl"]
            result.append(r)
    return result


def build(data, args):
    market = json.loads((data/"fed-cross-asset-events.json").read_text())
    meetings = sorted((r for r in market["records"] if r["type"]=="decision" and r["stage"]=="release"
                       and r["groupEligible"] and r["scheduled"] and START<=r["date"]<=END), key=lambda r:r["date"])
    if len(meetings) != len({r["date"] for r in meetings}):
        raise ValueError("Duplicate release date.")
    for r in meetings:
        release = time.fromisoformat(r["time"])
        if release.hour*60 + release.minute + 20 >= 15*60 + 30:
            raise ValueError("A release window reaches the ordinary fixing.")
    two,meta2 = curve_input.load_series("DGS2",args)
    ten,meta10 = curve_input.load_series("DGS10",args)
    series = {"yield2y":two,"slope":{day:ten[day]-two[day] for day in two.keys() & ten.keys()}}
    rows = event_rows(meetings,series)
    assets = {}
    for key,label in LABELS.items():
        available = [r for r in rows if r["asset"]==key and r["intradayBp"] is not None]
        results = {}
        for threshold in THRESHOLDS:
            sample = [r for r in available if abs(r["intradayBp"]) > threshold]
            strata = {"all":sample,"up":[r for r in sample if r["intradayBp"]>0],"down":[r for r in sample if r["intradayBp"]<0]}
            results[str(threshold)] = {s:{w:summaries(group,w) for w in WINDOWS} for s,group in strata.items()}
        assets[key] = {"label":label,"intradayMeetings":len(available),
                       "matchedMeetings":sum(all(r[w] is not None for w in WINDOWS) for r in available),
                       "thresholds":results}
    sources = [{"label":market["source"]["label"],"url":market["source"]["url"]},
               {"label":"US Treasury · Daily Treasury par yield methodology","url":"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=yield"},
               {"label":"Federal Reserve H.15 · two-year constant maturity",**meta2},
               {"label":"Federal Reserve H.15 · ten-year constant maturity",**meta10}]
    summary = {"period":{"start":START,"end":END},"eligibleMeetings":len(meetings),"primaryThresholdBp":2,
               "thresholdsBp":THRESHOLDS,"assets":assets,"sources":sources,"method":METHOD}
    return summary,rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=DATA)
    parser.add_argument("--input-dir",type=Path)
    parser.add_argument("--save-inputs",type=Path)
    parser.add_argument("--check",action="store_true")
    args = parser.parse_args()
    args.as_of = curve_input.VINTAGE
    summary,rows = build(args.data,args)
    csv_out = io.StringIO(newline="")
    writer = csv.DictWriter(csv_out,fieldnames=rows[0],lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    outputs = {"json":json.dumps(summary,ensure_ascii=False,allow_nan=False,indent=2)+"\n","csv":csv_out.getvalue()}
    for ext,body in outputs.items():
        dest = args.data/("fed-yield-followthrough."+ext)
        if args.check:
            if not dest.exists() or dest.read_text()!=body:
                raise SystemExit("Regenerate "+str(dest))
        else:
            dest.write_text(body)
