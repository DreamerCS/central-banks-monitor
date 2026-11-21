"""Measure changes in fixed-reference SOFR option means around Board-listed speeches."""
import argparse
import csv
import io
import json
import math
import re
import runpy
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from statistics import median
from urllib.parse import urljoin
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dist/data"
BOARD = "https://www.federalreserve.gov/json/ne-speeches.json"
BLS = {"cpi":"Consumer Price Index", "empsit":"Employment Situation"}
BLS_ARCHIVE = "https://www.bls.gov/bls/news-release/{}.htm"
BOARD_INDEX = "https://www.federalreserve.gov/newsevents/speeches.htm"
END = "2025-12-31"
EXISTING = runpy.run_path(str(Path(__file__).with_name("build-fed-speech-markets.py")))
FIELDS = [
    ("nearPriorBp", "Earlier change, near quarter"),
    ("deferredPriorBp", "Earlier change, deferred quarter"),
    ("nearChangeBp", "Across speech, near quarter"),
    ("deferredChangeBp", "Across speech, deferred quarter"),
    ("absNearChangeBp", "Absolute change, near quarter"),
    ("absDeferredChangeBp", "Absolute change, deferred quarter"),
    ("twoYearChangeBp", "Across speech, 2-year Treasury"),
    ("slopeChangeBp", "Across speech, Treasury 2s10s"),
]


def load(name):
    return json.loads((DATA / (name + ".json")).read_text())


def distance(start, end):
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def roster(records):
    events = []
    for row in records:
        if not row.get("d"):
            continue
        day = datetime.strptime(row["d"].split()[0], "%m/%d/%Y").date().isoformat()
        path = row.get("l") or row.get("stub") or "/newsevents/speech/" + day[:4] + "-speeches.htm"
        events.append(dict(date=day, title=unescape(row["t"]).strip(), speaker=unescape(row["s"]).strip(),
                           url=urljoin(BOARD, path), isChair=row["s"].startswith("Chair "),
                           essay=row.get("lo", "").strip().lower() == "essay"))
    return sorted(events, key=lambda item: (item["date"], item["speaker"], item["title"]))


def get_marks(day, dates, prices, curve):
    prev = bisect_left(dates, day) - 1
    nxt = bisect_right(dates, day)
    if prev < 4 or nxt >= len(dates):
        return None
    first, before, after = dates[prev - 4], dates[prev], dates[nxt]
    if distance(before, after) > 7 or distance(first, before) > 12:
        return None
    if before not in curve or after not in curve:
        return None
    refs = sorted(ref for ref, values in prices[before].items() if ref >= day and "meanBp" in values)
    if not refs:
        return None
    near = refs[0]
    deferred = next((ref for ref in refs if 260 <= distance(near, ref) <= 290), None)
    if not deferred:
        return None
    out = {"priorStart": first, "beforeDate": before, "afterDate": after,
           "nearReferenceStart": near, "deferredReferenceStart": deferred}
    for maturity, ref in (("near",near),("deferred",deferred)):
        means = [prices[obs].get(ref, {}).get("meanBp") for obs in (first,before,after)]
        if any(x is None or not math.isfinite(x) for x in means):
            return None
        out[maturity + "PriorBp"] = round(means[1] - means[0], 2)
        out[maturity + "MeanBeforeBp"] = means[1]
        out[maturity + "ChangeBp"] = round(means[2] - means[1], 2)
    two, _, slope = EXISTING["changes"](curve[before],curve[after])
    out.update(twoYearChangeBp=two, slopeChangeBp=slope)
    return out


def quantile(xs, q):
    idx = (len(xs) - 1) * q
    return round(xs[math.floor(idx)] + (xs[math.ceil(idx)] - xs[math.floor(idx)]) * (idx % 1), 2)


def group(label, events):
    metrics = []
    for field, desc in FIELDS:
        if field.startswith("abs"):
            key = field[3].lower() + field[4:]
            values = sorted(abs(r[key]) for r in events)
        else:
            values = sorted(r[field] for r in events)
        metrics.append(dict(key=field, label=desc, unit="bp", n=len(values),
                            median=round(median(values),2) if values else None,
                            q25=quantile(values,.25) if values else None,
                            q75=quantile(values,.75) if values else None))
    signed = [r for r in events if min(abs(r["nearChangeBp"]), abs(r["deferredChangeBp"])) > 1]
    return {"label":label, "n":len(events),"metrics":metrics,
            "bothOver1Bp":len(signed),
            "sameDirectionOver1Bp":sum(r["nearChangeBp"] * r["deferredChangeBp"] > 0 for r in signed)}


def matched_benchmark(events, dates, prices, curve, blocked):
    """Choose nearby comparison dates without looking at the market movements."""
    used = set()
    pairs = []
    fields = {"nearChangeBp":"Near-quarter SOFR mean", "deferredChangeBp":"Deferred-quarter SOFR mean",
              "twoYearChangeBp":"2-year Treasury", "slopeChangeBp":"Treasury 2s10s"}
    for event in events:
        event_day = date.fromisoformat(event["date"])
        event_span = distance(event["beforeDate"], event["afterDate"])
        control = None
        for offset in (week * sign for week in range(7, 43, 7) for sign in (-1,1)):
            candidate = (event_day + timedelta(days=offset)).isoformat()
            if not dates[0] <= candidate <= dates[-1]:
                continue
            marks = get_marks(candidate, dates, prices, curve)
            if marks is None:
                continue
            start, end = marks["beforeDate"], marks["afterDate"]
            if (start, end) in used or distance(start, end) != event_span:
                continue
            if any(start <= d <= end for d in blocked):
                continue
            if any(event[key] != marks[key] for key in ("nearReferenceStart","deferredReferenceStart")):
                continue
            used.add((start,end))
            control = {"date":candidate, **marks}
            break
        if control:
            pairs.append((event,control))
    results = []
    for field,label in fields.items():
        treated = [abs(e[field]) for e,c in pairs]
        controls = [abs(c[field]) for e,c in pairs]
        diff = sorted(round(t-c,2) for t,c in zip(treated,controls))
        results.append({"key":field,"label":label,"n":len(pairs),
                        "speechMedianAbs":round(median(treated),2) if treated else None,
                        "controlMedianAbs":round(median(controls),2) if controls else None,
                        "medianPairedExcessAbs":round(median(diff),2) if diff else None,
                        "q25":quantile(diff,.25) if diff else None, "q75":quantile(diff,.75) if diff else None,
                        "speechLarger":sum(d>0 for d in diff), "equal":sum(d==0 for d in diff)})
    paired = [{"speechDate":e["date"],"controlDate":c["date"],"controlBefore":c["beforeDate"],
               "controlAfter":c["afterDate"], **{key:c[key] for key in fields}} for e,c in pairs]
    return {"eligible":len(events),"n":len(pairs),"metrics":results,"pairs":paired,
            "method":"For each CPI/jobs-screened speech in date order, search one through six weeks away on the same weekday, checking the earlier date first at each distance. Require identical two contract reference dates and bracket length, both Treasury marks, and no Board, FOMC, CPI or Employment Situation date in the inclusive comparison bracket. Never reuse a comparison quote bracket. Match eligibility and date without using the sign or size of the moves. Paired excess equals the absolute speech-bracket move minus the absolute comparison-bracket move, then the median across pairs. Other economic releases remain possible on either date."}


def macro_dates(directory):
    dates = {}
    for code, label in BLS.items():
        page = ((directory / (code + ".html")).read_text() if directory else
                urlopen(BLS_ARCHIVE.format(code), timeout=60).read().decode())
        linked = {datetime.strptime(x, "%m%d%Y").date().isoformat()
                  for x in re.findall(r"/archives/" + code + r"_(\d{8})\.htm", page)}
        if len([d for d in linked if "2023-04-01" <= d <= END]) < 30:
            raise ValueError("BLS archive date coverage is unexpectedly sparse: " + code)
        dates[label] = sorted(linked)
    return dates


def build(board, workbook, releases):
    all_events = roster(board)
    date_counts = Counter(r["date"] for r in all_events)
    dates, prices = EXISTING["load_option_priors"](workbook)
    dates = [day for day in dates if day <= END]
    starts = dates[0]
    listed = [r for r in all_events if starts <= r["date"] <= END]
    curve = {r["date"]:r for r in load("pre-event-curve")["observations"]
             if r.get("y2") is not None and r.get("y10") is not None}
    fomc = load("fed-cross-asset-events")
    policy_dates = ({r["date"] for r in fomc["records"]} | set(fomc["unmatchedMinutes"])
                    | set(fomc["excludedAnnouncements"]) | {r["date"] for r in load("fed-statement-stance")["records"]})
    readings = {(r["date"],r["sourceUrl"]):r.get("score") for r in load("fed-leader-speeches")["records"]}
    coverage = dict(catalogue=len(listed),inTrackerSpan=len(listed),uniqueDates=len({r["date"] for r in listed}),
                    chairInTrackerSpan=sum(r["isChair"] for r in listed),essay=0,insufficientMarks=0,
                    matchedBeforeOverlap=0, otherBoardOnly=0, fomcOnly=0, bothOverlap=0,eligible=0)
    events = []
    for entry in listed:
        if entry["essay"]:
            coverage["essay"] += 1
            continue
        day = entry["date"]
        marks = get_marks(day, dates, prices, curve)
        if marks is None:
            coverage["insufficientMarks"] += 1
            continue
        coverage["matchedBeforeOverlap"] += 1
        before, after = marks["beforeDate"], marks["afterDate"]
        other = sum(n for d,n in date_counts.items() if before <= d <= after) > 1
        policy = any(before <= d <= after for d in policy_dates)
        if other or policy:
            key = "bothOverlap" if other and policy else "otherBoardOnly" if other else "fomcOnly"
            coverage[key] += 1
            continue
        row = {key:val for key,val in entry.items() if key != "essay"}
        row.update(marks)
        row["textScore"] = readings.get((day,row["url"]))
        overlaps = [f"{when} {label}" for label, days in releases.items()
                    for when in days if before <= when <= after]
        row["blsReleaseInBracket"] = " | ".join(sorted(overlaps))
        events.append(row)
    coverage["eligible"] = len(events)
    coverage["chairEligible"] = sum(r["isChair"] for r in events)
    coverage["eligibleSpeakers"] = len({r["speaker"].split()[-1] for r in events})
    coverage["scoredEligible"] = sum(r["textScore"] is not None for r in events)
    assert coverage["inTrackerSpan"] == sum(coverage[k] for k in ("essay","insufficientMarks","otherBoardOnly","fomcOnly","bothOverlap","eligible"))
    assert len({r["date"] for r in events}) == len(events)
    groups = [group("All isolated Board speeches", events),group("Chair Powell", [r for r in events if r["isChair"]]),
              group("Other Board members", [r for r in events if not r["isChair"]])]
    macro_free = [r for r in events if not r["blsReleaseInBracket"]]
    groups.append(group("Excluding CPI and employment-release brackets", macro_free))
    coverage["withoutBlsReleases"] = len(macro_free)
    blocked = set(date_counts) | policy_dates | {day for days in releases.values() for day in days}
    benchmark = matched_benchmark(macro_free, dates, prices, curve, blocked)
    all_metrics = {m["key"]:m for m in groups[0]["metrics"]}
    extreme = max(events, key=lambda event:abs(event["nearChangeBp"]))
    sample = {"title":extreme["title"],"date":extreme["date"],"url":extreme["url"], "speaker":extreme["speaker"],
              "description":(f"The largest absolute near-quarter move in the screened sample was {extreme['nearChangeBp']:+.2f} bp. "
                             f"The prior four observation intervals had moved the same contract {extreme['nearPriorBp']:+.2f} bp. "
                             f"From {extreme['beforeDate']} to {extreme['afterDate']}, the deferred quarter moved "
                             f"{extreme['deferredChangeBp']:+.2f} bp, the 2-year Treasury {extreme['twoYearChangeBp']:+} bp "
                             f"and 10-year minus 2-year slope {extreme['slopeChangeBp']:+} bp. Other news can enter these daily windows.")}
    if extreme["blsReleaseInBracket"]:
        sample["description"] += " The same bracket contains the BLS release " + extreme["blsReleaseInBracket"] + "."
    sensitivity = {m["key"]:m["median"] for m in groups[-1]["metrics"]}
    return {
      "period":{"start":starts,"end":END,"firstEvent":events[0]["date"],"lastEvent":events[-1]["date"]},
      "coverage":coverage, "summary":[
        f"The Board listed {len(listed)} communications across {coverage['uniqueDates']} dates. "
        f"{len(events)} speeches had a fixed pair of SOFR contracts, matching Treasury marks and no other indexed Board or FOMC communication in the quote bracket.",
        f"The median absolute move across the speech bracket was {all_metrics['absNearChangeBp']['median']:.2f} bp for the near quarter "
        f"and {all_metrics['absDeferredChangeBp']['median']:.2f} bp for the quarter starting roughly nine months later.",
        f"Both quarters moved by more than 1 bp on {groups[0]['bothOver1Bp']} dates. "
        f"Of those, {groups[0]['sameDirectionOver1Bp']} repriced in the same direction.",
        f"After excluding daily brackets containing the BLS CPI or jobs report, {len(macro_free)} dates remain. "
        f"The median absolute shifts in the two quarterly means are {sensitivity['absNearChangeBp']:.2f} and {sensitivity['absDeferredChangeBp']:.2f} bp.",
        f"{benchmark['n']} of those {benchmark['eligible']} speeches also match a nearby date with the same contracts, weekday and window length. "
        f"The median paired difference in absolute moves (speech minus comparison) was "
        f"{benchmark['metrics'][0]['medianPairedExcessAbs']:+.2f} bp near and {benchmark['metrics'][1]['medianPairedExcessAbs']:+.2f} bp deferred."
      ],"groups":groups,"example":sample,"benchmark":benchmark,
      "methods":[
        "Start with every communication in the Federal Reserve Board speech index during the Atlanta tracker observation span through the last complete year, including Chair, Vice Chairs and governors. Exclude one written essay as an event, while retaining it for overlap detection. Reserve Bank presidents and Congressional testimony indexed elsewhere fall outside this list.",
        "Using only the last strictly earlier tracker observation, choose the earliest future or current-day quarterly reference start and a reference start 260–290 days farther out. Each of the two fixed contracts must have a mean at all three marks. Earlier change spans the fifth-to-last through last strictly earlier observation (four intervals). Across-speech change runs from the last strictly earlier to the first strictly later tracker date. The maximum spans are 12 and seven calendar days respectively. No event-day quote is used.",
        "The Atlanta Fed recovers option-implied three-month average SOFR means from CME options. Levels and changes are in basis points. A move in these quarterly means can reflect expected policy and risk premia. It does not measure the probability or size of the next FOMC decision.",
        "Treasury 2-year and 10-year par yields use the same two endpoint dates. 2s10s means the 10-year yield minus the 2-year yield. Treasury observations and option inputs have no synchronized intraday timestamp here. Quotes cover market developments before and after the speech.",
        "Screen the inclusive quote bracket for any other Board index entry or FOMC decision, conference or minutes date. Releases, economic news, testimony and Reserve Bank speeches may still overlap. A sensitivity check also excludes the inclusive bracket around BLS Consumer Price Index and Employment Situation releases using the publication dates on archived editions. The four-interval pretrend is context and has no overlap screen. Adjacent brackets can share a price observation, so event counts are descriptive.",
        "Every retained date gets equal weight. Quartiles use linear interpolation on sorted observations. Suppress sign comparisons for jointly small moves by requiring both absolute moves to exceed 1 bp. The Chair subgroup is descriptive. Independently reviewed text scores, when available, are joined by speech URL and event date. Missing text scores remain empty."
      ],"sources":[
        {"label":"Federal Reserve Board speech index", "url":BOARD_INDEX},
        {"label":"Board speech-index data", "url":BOARD},
        {"label":"Atlanta Fed Market Probability Tracker", "url":EXISTING["MPT"]},
        {"label":"Historical option distributions (XLSX)", "url":EXISTING["MPT_FILE"]},
        {"label":"US Treasury daily par yield curve", "url":EXISTING["PRICES"]},
        {"label":"Federal Reserve monetary policy calendars and minutes","url":"https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"},
        {"label":"BLS Employment Situation archived releases", "url":BLS_ARCHIVE.format("empsit")},
        {"label":"BLS Consumer Price Index archived releases", "url":BLS_ARCHIVE.format("cpi")},
        {"label":"SF Fed US Monetary Policy Event-Study Database","url":"https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/"}
      ],"events":events}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board-index", type=Path)
    parser.add_argument("--options-workbook",type=Path)
    parser.add_argument("--bls-directory",type=Path,help="Directory containing archived BLS pages cpi.html and empsit.html.")
    parser.add_argument("--check",action="store_true")
    args = parser.parse_args()
    raw = args.board_index.read_bytes() if args.board_index else urlopen(BOARD, timeout=90).read()
    output = build(json.loads(raw.decode("utf-8-sig")), args.options_workbook, macro_dates(args.bls_directory))
    content = io.StringIO(newline="")
    rows = output["events"]
    writer = csv.DictWriter(content, fieldnames=list(rows[0]),lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    files = {"fed-speech-pricing-study.json":json.dumps(output,ensure_ascii=False,separators=(",",":"))+"\n",
             "fed-speech-pricing-study.csv":content.getvalue()}
    for name, serialized in files.items():
        path = DATA / name
        if args.check:
            if not path.exists() or path.read_bytes() != serialized.encode():
                raise SystemExit(f"Stale study output: {name}")
        else:
            path.write_bytes(serialized.encode())
    print(json.dumps(output["coverage"]))

if __name__ == "__main__":
    main()
