"""Match daily US market fixings to Chair speeches. Run the Fed event and speech builds first.
Requires exchange-calendars for the historical US equity sessions.
Optional --input-dir uses three cached downloads named fx, factor and vix.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from bisect import bisect_left
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import exchange_calendars

ROOT = Path(__file__).resolve().parents[1]
H10 = "https://www.federalreserve.gov/releases/h10/hist/"
FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_factors.html"
VIX = "https://www.cboe.com/tradable_products/vix/vix_historical_data/"
URLS = {
    "fx": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU,DEXJPUS&cosd=1999-12-15",
    "factor": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip",
    "vix": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
}
SPEECH_ROUTES = {
    "Greenspan": "Alan Greenspan", "Bernanke": "Ben S. Bernanke", "Yellen": "Janet L. Yellen",
    "Powell": "Jerome H. Powell", "Warsh": "Kevin Warsh",
}
ASSETS = [
    ("yield2y", "2-year US Treasury", "bp", "Rates", "US Treasury par yield, approximately 15:30 ET."),
    ("yield10y", "10-year US Treasury", "bp", "Rates", "US Treasury par yield, approximately 15:30 ET."),
    ("slope", "US 2s10s (10Y minus 2Y)", "bp", "Curve", "Positive means the Treasury curve steepened."),
    ("usEquityDaily", "US value-weighted equity market", "%", "Equity", "Daily total return across eligible NYSE, AMEX and Nasdaq stocks, from the Kenneth French Data Library. Market excess return plus the risk-free rate."),
    ("eurusd", "EUR/USD", "%", "FX", "Federal Reserve H.10 New York noon fixing, USD per EUR. Positive means the euro appreciated."),
    ("usdjpy", "USD/JPY", "%", "FX", "Federal Reserve H.10 New York noon fixing, JPY per USD. Positive means the dollar appreciated."),
    ("vixDaily", "Cboe VIX", "points", "Volatility", "Change in the closing level of S&P 500 option-implied 30-day volatility, in VIX index points."),
]


def read_input(name, folder):
    if folder:
        return (folder / name).read_bytes()
    with urlopen(Request(URLS[name], headers={"User-Agent": "CBI research data"}), timeout=60) as response:
        return response.read()


def read_series(folder):
    output = {key: {} for key in ["eurusd", "usdjpy", "vixDaily", "usEquityDaily"]}
    fx = csv.DictReader(io.StringIO(read_input("fx", folder).decode("utf-8-sig")))
    if fx.fieldnames != ["observation_date", "DEXUSEU", "DEXJPUS"]:
        raise ValueError("Unexpected H.10 series")
    for row in fx:
        for col, field in [("DEXUSEU", "eurusd"), ("DEXJPUS", "usdjpy")]:
            if row[col] not in ("", "."):
                output[field][row["observation_date"]] = float(row[col])
    vix = csv.DictReader(io.StringIO(read_input("vix", folder).decode("utf-8-sig")))
    for row in vix:
        day = datetime.strptime(row["DATE"], "%m/%d/%Y").date().isoformat()
        output["vixDaily"][day] = float(row["CLOSE"])
    with zipfile.ZipFile(io.BytesIO(read_input("factor", folder))) as archive:
        body = archive.read(next(n for n in archive.namelist() if n.lower().endswith(".csv"))).decode("utf-8-sig")
    start = body.index(",Mkt-RF,")
    for row in csv.DictReader(io.StringIO(body[start:])):
        if not re.fullmatch(r"[0-9]{8}", row[""]):
            continue
        excess, rf = float(row["Mkt-RF"]), float(row["RF"])
        if any(v < -90 or not math.isfinite(v) for v in (excess, rf)):
            continue
        day = datetime.strptime(row[""], "%Y%m%d").date().isoformat()
        output["usEquityDaily"][day] = round(excess + rf, 8)
    for k, values in output.items():
        if len(values) < 5000 or not all(math.isfinite(v) for v in values.values()):
            raise ValueError("Incomplete historical series: " + k)
    return output


def normal_time(value):
    if not value:
        return None
    if re.fullmatch(r"\d\d:\d\d", value):
        return value
    match = re.search(r"(\d{1,2}):(\d{2})\s*([ap])", value, re.I)
    if match:
        return f"{int(match[1]) % 12 + (12 if match[3].lower() == 'p' else 0):02d}:{match[2]}"
    return None


def clean_interval(day, time, start, end, start_clock, end_clock, conflicts, own):
    # To retain the return, the event must fall inside every permitted endpoint clock.
    if not start < end or not start <= day <= end:
        return False
    if day == start and (time is None or time <= start_clock[1]):
        return False
    if day == end and (time is None or time >= end_clock[0]):
        return False
    # Other releases must lie outside even the widest plausible interval.
    for otherday, othertime, identity in conflicts:
        if identity == own or not start <= otherday <= end:
            continue
        if otherday == start and othertime and othertime < start_clock[0]:
            continue
        if otherday == end and othertime and othertime > end_clock[1]:
            continue
        return False
    return True


def build(data, folder):
    def load(name):
        return json.loads((data / (name + ".json")).read_text())
    speeches = {r["sourceUrl"]: r for r in load("fed-leader-speeches")["records"]}
    markets = load("fed-speech-markets")
    intraday = load("fed-cross-asset-events")
    conflicts = [(r["date"], r["timeET"], r["url"]) for r in markets["records"]]
    statement_times = {r["date"]: normal_time(r.get("time")) for r in intraday["records"] if r["stage"] == "release"}
    for r in load("fed-statement-stance")["records"]:
        conflicts.append((r["date"], statement_times.get(r["date"]) or normal_time(r.get("publicationET")), "decision"))
    for r in intraday["records"]:
        if r["stage"] in ("minutes", "conference"):
            conflicts.append((r["date"], normal_time(r.get("time")), r["stage"]))
    series = read_series(folder)
    calendars = {k: sorted(values) for k, values in series.items()}
    ny = ZoneInfo("America/New_York")
    exchange = exchange_calendars.get_calendar("XNYS", start=min(r["date"] for r in markets["records"])[:4]+"-01-01", end=markets["through"])
    def clock(key, day):
        if key in ("eurusd", "usdjpy"):
            return ("12:00", "12:00")
        if not exchange.is_session(day):
            return None
        close = exchange.session_close(day).to_pydatetime().astimezone(ny)
        latest = close + timedelta(minutes=15) if key == "vixDaily" else close
        return close.strftime("%H:%M"), latest.strftime("%H:%M")
    rows = []
    for r in markets["records"]:
        if not r["eligible"]:
            continue
        day, time, url = r["date"], r["timeET"], r["url"]
        start, end = r["priorEnd"], r["closeDate"]
        if not clean_interval(day, time, start, end, ("15:30", "15:30"), ("15:30", "15:30"), conflicts, url):
            continue
        speech = speeches[url]
        values = {"yield2y": r["close2yBp"], "yield10y": r["close10yBp"], "slope": r["closeSlopeBp"]}
        for key, data_values in series.items():
            calendar = calendars[key]
            idx = bisect_left(calendar, start)
            if calendar[idx:idx+2] != [start, end]:
                continue
            left_clock, right_clock = clock(key, start), clock(key, end)
            if not left_clock or not right_clock or not clean_interval(day, time, start, end, left_clock, right_clock, conflicts, url):
                continue
            a, b = data_values[start], data_values[end]
            if key == "usEquityDaily":
                change = b
            elif key == "vixDaily":
                change = b - a
            else:
                change = 100 * (b / a - 1)
            values[key] = round(change, 6)
        row = dict(id="fed-speech-daily-"+hashlib.sha256(url.encode()).hexdigest()[:10],date=day,time=time,
                   timeZone="America/New_York",stage="speechDaily",type="speech",title=speech["title"],speaker=speech["speaker"],
                   leader=SPEECH_ROUTES.get(r["leader"],r["leader"]),documentUrl=url,sourceUrl=url,
                   score=speech["score"],evidence=speech.get("evidence"),groupEligible=True,values=values,
                   window=f"{start} to {end}, consecutive daily observations. Treasury yields are fixed around 15:30 ET, FX at noon ET, and equities and volatility at their session closes. Other news can contribute.",
                   startDate=start,endDate=end)
        rows.append(row)
    counts = Counter(k for row in rows for k in row["values"])
    return {"bank":"fed","timezone":"America/New_York","assets":[dict(zip(["id","label","unit","group","description"],a)) for a in ASSETS],
            "stages":{"speechDaily":{"label":"Chair speech · daily fixings","window":"Consecutive daily observations spanning a speech. Daily and intraday samples have different windows."}},
            "source":{"label":"US Treasury, Federal Reserve H.10, Kenneth French Data Library and Cboe","url":markets["sources"]["quotes"]},
            "sources":{"equities":FRENCH,"fx":H10,"volatility":VIX,"rates":markets["sources"]["method"]},
            "coverage":{"catalogue":len(speeches),"dailyIntervals":len(rows),"byAsset":dict(counts),"sourceThrough":{k:cal[-1] for k,cal in calendars.items()}},
            "method":["Each row uses a single documented Chair appearance in a Treasury fixing interval. Decisions, press conferences and releases of meeting minutes in the available FOMC files are checked for overlap.",
                      "For the other assets, both dates must be consecutive in that instrument’s own series and must strictly bracket the speech time. A speech exactly at a fixing is excluded for that asset.",
                      "Equities use the historical US exchange session close, including early closes. VIX endpoints allow the interval from the cash close through 15 minutes later. Ambiguously timed appearances and other Chair or archived FOMC releases at those boundaries are excluded. Other macroeconomic releases and news may still affect each daily change.",
                      "Source data extend to different dates. Missing marks and returns outside a source’s coverage are omitted."],
            "records":rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=ROOT / "dist/data")
    p.add_argument("--input-dir", type=Path)
    p.add_argument("--output", type=Path, default=ROOT / "dist/data/fed-speech-cross-asset-events.json")
    a = p.parse_args()
    result = build(a.data, a.input_dir)
    a.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"))+"\n")
    print(result["coverage"])
