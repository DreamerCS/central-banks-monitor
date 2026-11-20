"""Join Board Chair speeches to Treasury fixings and independently sourced event windows.

python scripts/build-fed-speech-markets.py
The default inputs are the site's verified Chair catalogue, Treasury observations,
FOMC statement dates, published speech windows and Jackson Hole study.
"""
import argparse
import csv
import json
import re
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from io import BytesIO
from urllib.request import urlopen
from xml.etree import ElementTree
from zipfile import ZipFile
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dist/data"
TREASURY = "https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology"
PRICES = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve"


MPT = "https://www.atlantafed.org/en/research-and-data/data/market-probability-tracker"
MPT_FILE = "https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/research-and-data/data/market-probability-tracker/mpt_histdata.xlsx"
NBER = "https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions"


def load_option_priors(workbook):
    """Read the named statistics from the Atlanta Fed's published observation archive."""
    booksrc = workbook if workbook else BytesIO(urlopen(MPT_FILE, timeout=90).read())
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    fields = {"Rate: mean": "meanBp", "Prob: cut": "belowTargetPct", "Prob: hike": "aboveTargetPct"}
    by_day = defaultdict(lambda: defaultdict(dict))
    with ZipFile(booksrc) as book:
        strings = [item.findtext(ns+"t", "") for item in ElementTree.parse(book.open("xl/sharedStrings.xml")).getroot()]
        with book.open("xl/worksheets/sheet3.xml") as sheet:
            for _, row in ElementTree.iterparse(sheet):
                if row.tag != ns+"row":
                    continue
                cells = []
                for cell in row:
                    value = cell.findtext(ns+"v", "")
                    cells.append(strings[int(value)] if cell.get("t") == "s" else value)
                if len(cells) == 5 and cells[3] in fields:
                    day, serial, target, field, value = cells
                    start = (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()
                    if value.strip() not in {"", "NA", "NaN"}:
                        point = by_day[day][start]
                        point[fields[field]] = float(value)
                        point["targetRange"] = target
                row.clear()
    return sorted(by_day), by_day


def prior_distribution(day, dates, data):
    before = bisect_left(dates, day)-1
    if before < 4:
        return None
    end, first = dates[before], dates[before-4]
    if (date.fromisoformat(day)-date.fromisoformat(end)).days > 7:
        return None
    starts = [r for r in data[end] if r >= day and data[end][r].get("meanBp") is not None]
    if not starts:
        return None
    start = min(starts)
    last = data[end][start]
    prior = data[first].get(start, {}).get("meanBp")
    return {"asOf":end, "referenceStart":start, "meanBp":last["meanBp"], "fromDate":first,
            "changeBp":round(last["meanBp"] - prior, 2) if prior is not None else None,
            "belowTargetPct":last.get("belowTargetPct"), "aboveTargetPct":last.get("aboveTargetPct"),
            "targetRange":last["targetRange"], "source":MPT}


def cycle(day):
    month = day[:7]
    contractions = (("2001-04","2001-11"),("2008-01","2009-06"),("2020-03","2020-04"))
    return "Dated contraction" if any(start <= month <= end for start,end in contractions) else "Outside dated contraction"


def load(path):
    return json.loads(path.read_text())


def changes(start, end):
    two = int(100 * (Decimal(str(end["y2"])) - Decimal(str(start["y2"]))))
    ten = int(100 * (Decimal(str(end["y10"])) - Decimal(str(start["y10"]))))
    return two, ten, ten - two


def median_field(rows, field, absolute=False):
    nums = [r[field] for r in rows if r.get(field) is not None]
    return median([abs(v) for v in nums] if absolute else nums) if nums else None


def summary(rows):
    eligible = [v for v in rows if v["eligible"]]
    return {"events": len(rows), "knownTiming": sum(r["timeET"] is not None for r in rows),
            "distinctEligibleWindows": len(eligible),
            "medianPrior2yBp": median_field(eligible, "prior2yBp"), "medianClose2yBp": median_field(eligible,"close2yBp"),
            "medianAbsClose2yBp": median_field(eligible, "close2yBp", True),
            "medianAbsCloseSlopeBp": median_field(eligible,"closeSlopeBp", True),
            "singleCalendarDayWindows": sum(v["overnights"] == 1 for v in eligible),
            "singleCalendarDayMedianAbsClose2yBp": median_field([v for v in eligible if v["overnights"]==1], "close2yBp", True)}


def stance_comparison(rows, readings):
    by_url = {r["sourceUrl"]: r["score"] for r in readings["records"]}
    if set(by_url) != {r["url"] for r in rows}:
        raise ValueError("Speech market catalogue and scored catalogue differ")
    output = {}
    for label, scores in (("Hawkish", (1, 2)), ("Dovish", (-2, -1)), ("Neutral", (0,))):
        selected = [r for r in rows if by_url[r["url"]] in scores]
        eligible = [r for r in selected if r["eligible"]]
        single_day = [r for r in eligible if r["overnights"] == 1]
        output[label] = {
            "reviewed": len(selected), "eligible": len(eligible),
            "up": sum(r["close2yBp"] > 0 for r in eligible),
            "down": sum(r["close2yBp"] < 0 for r in eligible),
            "flat": sum(r["close2yBp"] == 0 for r in eligible),
            "median2yBp": median_field(eligible, "close2yBp"),
            "medianSlopeBp": median_field(eligible, "closeSlopeBp"),
            "singleCalendarDay": len(single_day),
            "singleCalendarDayMedian2yBp": median_field(single_day, "close2yBp")}
    return output


def published_windows(intraday, jackson_file):
    out = {}
    for entry in intraday["events"]:
        if entry["kind"] != "Speech" or entry["role"] != "Fed Chair":
            continue
        for obs in entry["observations"]:
            if obs["unit"] == "bp":
                out[entry["eventUrl"]] = dict(marketBp=obs["value"],instrument=obs["instrument"],
                    marketWindow=obs["window"]+" ET", marketSource=intraday["studies"][obs["study"]]["url"],
                    marketLocator=obs["locator"])
                break
    with jackson_file.open() as f:
        jackson = {r["official_speech"]: r for r in csv.DictReader(f)}
    return out, jackson


def decision_time(value):
    if not value:
        return None
    found = re.search(r"(\d{1,2}):(\d{2})\s*([ap])", value, re.I)
    if not found:
        return None
    hour = int(found[1]) % 12 + (12 if found[3].lower() == "p" else 0)
    return f"{hour:02d}:{found[2]}"


def build(catalogue, curve, fomc, intraday, jackson_file, option_priors, readings, archives):
    quotes = [r for r in curve["observations"] if r.get("y2") is not None and r.get("y10") is not None]
    days = [r["date"] for r in quotes]
    assert days == sorted(set(days))
    rate_days = [(r["date"], decision_time(r.get("publicationET"))) for r in fomc["records"]]
    archival_times = {r["url"]: r for r in archives}
    narrow, jackson = published_windows(intraday, jackson_file)
    rows = []
    seen = set()
    for s in catalogue:
        day, url = s["date"], s["sourceUrl"]
        if url in seen:
            raise ValueError("Duplicate speech URL: " + url)
        seen.add(url)
        archive = archival_times.get(url, {})
        if archive and archive["date"] != day:
            raise ValueError("Archival cover date differs from Board catalogue")
        stamp = s.get("time") or archive.get("timeET")
        i = bisect_left(days, day)
        same = i < len(days) and days[i] == day
        # Strict calendar-day window is comparable with the statement explorer.
        before, after = i-1, i if same else None
        status = "time-unknown"
        if stamp:
            if len(stamp) != 5 or stamp[2] != ":":
                raise ValueError("Unrecognised Board time: " + stamp)
            if not same:
                status, after = "non-quote-day", i
            elif stamp > "15:30":
                status, before, after = "after-fixing", i, i+1
            elif stamp < "15:30":
                status = "before-fixing"
            else:
                status = "at-fixing"
        elif not same:
            # With no fixing on this date the preceding/following fixings still bracket the speech.
            status, after = "non-quote-day", i
        base = {"url":url, "date":day, "leader":s["leader"], "timeET":stamp,
                "priorStart":None,"priorEnd":None,"prior2yBp":None,"prior10yBp":None,"priorSlopeBp":None,
                "closeDate":None,"close2yBp":None,"close10yBp":None,"closeSlopeBp":None,"overnights":None,
                "windowStatus":status,"overlapCount":0,"fomcOverlap":False,"eligible":False,
                "marketBp":None,"instrument":None,"marketWindow":None,"marketSource":None}
        if archive and not s.get("time"):
            base.update(timeSource=archive["timeSource"], timeEvidence=archive["timeEvidence"])
        if 4 <= before < len(quotes):
            start,end = quotes[before-4],quotes[before]
            base.update(priorStart=start["date"], priorEnd=end["date"])
            base["prior2yBp"],base["prior10yBp"],base["priorSlopeBp"]=changes(start,end)
            if after is not None and after<len(days):
                close = quotes[after]
                base["closeDate"] = close["date"]
                base["close2yBp"],base["close10yBp"],base["closeSlopeBp"]=changes(end,close)
                base["overnights"]=(date.fromisoformat(close["date"])-date.fromisoformat(end["date"])).days
                base["fomcOverlap"] = any(
                    end["date"] < target < close["date"]
                    or target == end["date"] and (not hour or hour >= "15:30")
                    or target == close["date"] and (not hour or hour <= "15:30")
                    for target,hour in rate_days)
        if url in narrow:
            base.update(narrow[url])
        if url in jackson:
            j = jackson[url]
            base["meetingPricing"] = {"beforeAndAfter":j["next_meeting_pricing"],"reading":j["pricing_interpretation"],
                                      "sources":[s for s in j["pricing_sources"].split(" | ") if s]}
            if day == "2023-08-25":
                base.update(marketBp=.5, instrument="September meeting expected change in the fed funds target",
                            marketWindow="10:00 to 10:20 ET, around the 10:05 speech",
                            marketSource=base["meetingPricing"]["sources"][0], marketLocator="Page 16")
        rows.append(base)
    intervals=Counter((r["priorEnd"],r["closeDate"]) for r in rows if r["closeDate"])
    ambiguous = Counter(r["date"] for r in rows if r["windowStatus"] in {"time-unknown","at-fixing"})
    by_leader=defaultdict(list)
    by_cycle=defaultdict(list)
    for r in rows:
        if r["closeDate"]:
            r["overlapCount"]=intervals[r["priorEnd"],r["closeDate"]]
            # An un-timed or exactly-at-fixing speech on the first day could also be within this interval.
            r["overlapCount"] += ambiguous[r["priorEnd"]]
            r["eligible"]=(r["windowStatus"] in {"before-fixing","after-fixing","non-quote-day"}
                           and r["overlapCount"] == 1 and not r["fomcOverlap"])
        r["cycle"] = cycle(r["date"])
        by_cycle[r["cycle"]].append(r)
        market_prior = prior_distribution(r["date"], *option_priors)
        if market_prior:
            r["quarterPricing"] = market_prior
        by_leader[r["leader"]].append(r)
    return {"title":"Treasury yields around speeches by the Federal Reserve Chair",
            "sources":{"quotes":PRICES,"method":TREASURY,"quarterlyOptions":MPT,"cycle":NBER,"boardTime":"https://www.federalreserve.gov/json/ne-speeches.json"},
            "through":days[-1],"method":[
             "Historical release times are taken from the dated delivery instructions on the first page of the FRASER transcript when the Board index omits a time. The pre-speech change runs from the fifth prior Treasury fixing to the final pre-release fixing (four successive changes). The 2s10s spread is the ten-year par yield minus the two-year par yield.",
             "A speech before the approximately 15:30 ET Treasury fixing uses the previous trading day's fixing as its baseline. A later speech uses the same day's fixing and the next available fixing. Non-quote days are bracketed by the adjacent available fixings.",
             "When a trading-day release time is missing, the daily change describes the calendar date only. The change is excluded from the event-window statistics. Speeches listed at exactly the fixing time are also excluded.",
             "The matched sample has a unique speech per fixing interval and excludes FOMC decisions within that interval. A speech or decision with unknown or exactly-at-fixing timing on either boundary can overlap both adjacent windows. Other releases and trading still contribute. The one-calendar-day sensitivity additionally drops holiday and weekend spans.",
             "The observed short-window readings and September meeting prices identify their own instruments and source windows. Daily par yields contain term premia and rate expectations across maturities. They do not identify meeting-specific probabilities.",
             "The Atlanta Fed Market Probability Tracker uses CME options to estimate distributions for average compounded SOFR over a three-month reference window. We select the nearest reference window starting on or after the speech, and the last price date strictly before the speech. The change compares the same reference window on the fifth and last prior price dates. Above/below probabilities refer to the then-current fed funds target range. These are educational calculations from daily option data.",
             "NBER contractions run from the month after a dated peak through the month of its trough. These are retrospective labels." ],
            "summary":summary(rows),"stanceComparison":stance_comparison(rows,readings),"cycles":{k:summary(v) for k,v in by_cycle.items()},"leaders":{k:summary(v) for k,v in by_leader.items()},"records":rows}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalogue",type=Path,default=ROOT/"scripts/fed-chair-catalogue.json")
    p.add_argument("--data",type=Path,default=DATA)
    p.add_argument("--archives",type=Path,default=ROOT/"scripts/fed-archival-speech-times.json")
    p.add_argument("--readings",type=Path,default=DATA/"fed-leader-speeches.json")
    p.add_argument("--options-workbook",type=Path,help="Local Atlanta Fed Market Probability Tracker workbook (default downloads the official release)")
    p.add_argument("--output",type=Path,default=DATA/"fed-speech-markets.json")
    args=p.parse_args()
    result=build(load(args.catalogue),load(args.data/"pre-event-curve.json"),load(args.data/"fed-statement-stance.json"),
                 load(args.data/"speech-intraday.json"),args.data/"jackson-hole-stance.csv",load_option_priors(args.options_workbook),load(args.readings),load(args.archives))
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n")
