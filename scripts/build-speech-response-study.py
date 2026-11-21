"""Compare independently reviewed official speech texts with observed market changes."""
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import median

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
START = "2000-01-01"
END = "2025-12-31"
GROUPS = ("Hawkish", "Dovish", "Neutral")
ECB_ASSETS = {"yield2y": "German 2Y", "slope": "German 2s10s", "ois1y": "1Y euro OIS"}
FED_ASSETS = {"yield2y": "US 2Y", "slope": "US 2s10s"}
PRIOR_ASSETS = {"prior2yBp": "Prior US 2Y", "priorSlopeBp": "Prior US 2s10s"}


def read(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def group(score):
    return "Hawkish" if score > 0 else "Dovish" if score < 0 else "Neutral"


def percentile(values, p):
    values = sorted(values)
    position = (len(values) - 1) * p
    low = int(position)
    return round(values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (position - low), 3)


def readings(events, assets):
    result = []
    for key, name in assets.items():
        values = [r["values"][key] for r in events if r["values"].get(key) is not None]
        result.append(dict(name=name, n=len(values), unit="bp",
                           median=round(median(values), 3) if values else None,
                           q1=percentile(values, .25) if values else None, q3=percentile(values, .75) if values else None))
    return result


def groups(events, assets):
    output = []
    for label in GROUPS:
        cohort = [r for r in events if r["group"] == label]
        output.append(dict(label=label, n=len(cohort), readings=readings(cohort, assets)))
    return output


def strata(events, dimension):
    rows = []
    for value in sorted({e[dimension] for e in events}):
        subset = [r for r in events if r[dimension] == value]
        counts = Counter(r["group"] for r in subset)
        rows.append(dict(label=value, dimension=dimension, n=len(subset),
                         **{g.lower(): counts[g] for g in GROUPS}))
    return rows


def measure(events, stance, asset):
    values = [e["values"][asset] for e in events if e["group"] == stance and e["values"].get(asset) is not None]
    return median(values) if values else None


def event(row, score, cycle, url, names):
    return dict(id=row["id"], date=row["date"], leader=row["leader"], cycle=cycle, group=group(score), score=score,
                speaker=row["speaker"], title=row["title"], url=url, window=row["window"],
                values={k: row["values"][k] for k in names if k in row["values"]})


def ecb_panel():
    with (DATA / "ecb-speech-stance.csv").open(encoding="utf-8", newline="") as f:
        texts = {r["speech_id"]: r for r in csv.DictReader(f)}
    events, reviewed = [], 0
    total = matched = 0
    for file in sorted(DATA.glob("ecb-cross-asset-speeches-*.json")):
        for row in read(file.name)["records"]:
            if not START <= row["date"] <= END:
                continue
            total += 1
            text = texts.get(row["id"].removeprefix("ecb-speech-"))
            if not text:
                continue
            matched += 1
            if text["text_score"] == "":
                continue
            score = int(text["text_score"])
            if not text["evidence"] or not text["transcript"] or row.get("score") != score:
                raise ValueError("Invalid independent text link: " + row["id"])
            reviewed += 1
            if not row["groupEligible"] or text["conditions"]:
                continue
            events.append(event(row, score, text["cycle"], text["transcript"], ECB_ASSETS))
    sorted_events = sorted(events, key=lambda e: (e["date"], e["id"]))
    return dict(bank="ecb", label="ECB speeches and hearings · intraday",
                description="Changes between median quotes 20–10 minutes before the scheduled start and 40–50 minutes after it. The curve is the German 10Y yield less the 2Y yield.",
                coverage=f"{total:,} timed communications, {matched:,} unique official text matches, {reviewed} scored and {len(events)} eligible for comparison.",
                eventCounts=dict(timed=total, textMatched=matched, scored=reviewed, eligible=len(events)),
                groups=groups(events, ECB_ASSETS), strata=strata(events, "leader") + strata(events, "cycle"),
                notes=["Exclude out-of-session or overlapping ECB speech windows, decision days and missing 1Y OIS. A missing German maturity reduces the curve sample.",
                       "The ECB workbook supplies changes. The starting OIS level and the probability assigned to the next meeting are unavailable here."],
                events=sorted_events)


def fed_panel():
    catalogue = [r for r in read("fed-leader-speeches.json")["records"] if START <= r["date"] <= END]
    texts = {r["sourceUrl"]: r for r in catalogue}
    universe = [r for r in read("fed-speech-cross-asset-events.json")["records"] if START <= r["date"] <= END]
    prices = {r["url"]: r for r in read("fed-speech-markets.json")["records"]}
    events = []
    for row in universe:
        text = texts[row["documentUrl"]]
        if text["score"] is None:
            continue
        if not text["evidenceSentence"] or row["score"] != text["score"]:
            raise ValueError("Invalid independent text link: " + row["id"])
        m = prices[row["documentUrl"]]
        if row["endDate"] > END or not row["groupEligible"] or not m["eligible"] or not m["timeET"] or m["overlapCount"] != 1 or m["fomcOverlap"]:
            continue
        e = event(row, text["score"], m["cycle"], row["documentUrl"], FED_ASSETS)
        e.update(startDate=row["startDate"], endDate=row["endDate"], priorStart=m["priorStart"],
                 priorEnd=m["priorEnd"], calendarDays=m["overnights"])
        for k in PRIOR_ASSETS:
            if m.get(k) is not None:
                e["values"][k] = m[k]
        if m.get("quarterPricing"):
            e["quarterPricing"] = m["quarterPricing"]
        events.append(e)
    timed_fx = [r for r in read("fed-speech-intraday-assets.json")["records"] if START <= r["date"] <= END]
    fx_scores = sum(r["groupEligible"] and r.get("score") is not None for r in timed_fx)
    option_n = sum("quarterPricing" in e for e in events)
    scored = sum(r["score"] is not None for r in catalogue)
    return dict(bank="fed", label="Fed Chair speeches · daily Treasury fixings",
                description="Two consecutive Treasury observations bracket the speech. Each pre-speech measure runs from the fifth prior fixing to the last available pre-speech fixing.",
                coverage=f"{len(catalogue)} archived speeches, {scored} scored texts, {len(universe)} matched daily cross-asset windows and {len(events)} scored eligible windows.",
                eventCounts=dict(archived=len(catalogue), scored=scored, dailyMatched=len(universe), eligible=len(events),
                                 quarterPricing=option_n, intradayFxScored=fx_scores),
                groups=groups(events, FED_ASSETS | PRIOR_ASSETS), strata=strata(events, "leader") + strata(events, "cycle"),
                notes=[f"Market history also has {fx_scores} eligible scored intraday FX windows. A systematic intraday Treasury or dollar OIS comparison is unavailable in those data.",
                       f"Quarterly SOFR option distributions cover {option_n} of these speeches. The underlying horizon is a three-month average. Prior Treasury moves also include term premia.",
                       "Daily changes include other news. A single-calendar-day check drops fixings separated by weekends or holidays."],
                oneDaySensitivity=groups([e for e in events if e["calendarDays"] == 1], FED_ASSETS),
                events=events)


def main():
    ecb, fed = ecb_panel(), fed_panel()
    e, f = ecb["events"], fed["events"]
    def comparison(rows, asset):
        return " versus ".join(f"{measure(rows, g, asset):+.2f}" for g in GROUPS[:2])
    hawks = [x for x in e if x["group"] == "Hawkish"]
    active_leaders = Counter(x["leader"] for x in hawks)
    largest, largest_n = active_leaders.most_common(1)[0]
    doves = [x for x in e if x["group"] == "Dovish"]
    dove_leader, dove_n = Counter(x["leader"] for x in doves).most_common(1)[0]
    ecb["notes"].append(f"{largest_n} of {len(hawks)} hawkish observations fall in the {largest} presidency and {dove_n} of {len(doves)} dovish observations in the {dove_leader} presidency. Differences in economic conditions and speakers can affect the comparison.")
    fed["withinLeader"] = {leader: groups([r for r in f if r["leader"] == leader], FED_ASSETS)
                          for leader in sorted({r["leader"] for r in f})
                          if all(sum(r["leader"] == leader and r["group"] == g for r in f) >= 5 for g in GROUPS[:2])}
    sample = next(r for r in read("fed-speech-markets.json")["records"] if r["date"] == "2023-08-25" and r.get("meetingPricing"))
    match = next(r for r in f if r["url"] == sample["url"])
    pricing = sample["meetingPricing"]
    result = dict(start=START, through=END, title="How did rates move around policy speeches?",
                  summary=[f"ECB median 1Y OIS changes were {comparison(e, 'ois1y')} bp for hawkish versus dovish language. German 2Y changes were {comparison(e, 'yield2y')} bp. The 2s10s medians were {comparison(e, 'slope')} bp.",
                           f"Across the wider Fed daily window, median US 2Y changes were {comparison(f, 'yield2y')} bp. The pre-speech 2Y changes were {comparison(f, 'prior2yBp')} bp."],
                  methods=["The primary window covers calendar years 2000 through 2025. Sample counts use event dates within that period.",
                           "Direction is read from reviewed official speech text. Scores +1 and +2 are hawkish, −1 and −2 dovish, and zero indicates explicit support for the existing stance. Unscored texts are excluded.",
                           "Medians and the 25th and 75th percentiles describe the selected speeches. Each asset reports its own sample size. Economic-cycle labels use retrospective CEPR–EABCN and NBER contraction dates.",
                           "A level of guidance can repeat the existing message. Market participants may already have incorporated it. Timing, selection and concurrent releases limit causal interpretation."],
                  panels=[ecb, fed],
                  example=dict(title="Powell at Jackson Hole · 25 August 2023", url=match["url"],
                               description=f"Powell kept further tightening conditional. The source reports the September hike probability at 19.5% five minutes before the speech and 21.5% 15 minutes afterwards. Under a hold-or-25 bp hike interpretation, that adds 0.50 bp to the expected September move (4.88 to 5.38 bp). In the daily window US 2Y moved {match['values']['yield2y']:+g} bp and 2s10s {match['values']['slope']:+g} bp.",
                               marketSource=pricing["sources"][0]),
                  sources=[dict(label="ECB extended monetary policy event-study database", url="https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx"),
                           dict(label="ECB official speech corpus", url="https://www.ecb.europa.eu/press/key/html/downloads.en.html"),
                           dict(label="Federal Reserve Board speeches", url="https://www.federalreserve.gov/newsevents/speeches.htm"),
                           dict(label="US Treasury yield curve methodology", url=read("fed-speech-markets.json")["sources"]["method"]),
                           dict(label="Atlanta Fed Market Probability Tracker", url=read("fed-speech-markets.json")["sources"]["quarterlyOptions"])])
    (DATA / "speech-response-study.json").write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
