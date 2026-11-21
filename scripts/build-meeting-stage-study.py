"""Export one row per official decision and compare paired release and press-conference windows."""
import argparse
import csv
import io
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
START = "2000-01-01"
END = "2025-12-31"
ASSETS = {
    "currentMeetingBp": "currentMeeting", "nextMeetingBp": "nextMeeting",
    "ois1mBp": "ois1m", "ois1yBp": "ois1y", "yield2yBp": "yield2y", "yield10yBp": "yield10y",
    "slope2s10sBp": "slope", "equityPct": "equity", "eurusdPct": "eurusd"
}


def load(name):
    return json.loads((DATA / (name+".json")).read_text())


def window_map(events):
    windows = {}
    for r in events["records"]:
        if (r["stage"], r["type"]) in {("conference", "conference"), ("release", "decision")}:
            key = r["date"], r["stage"]
            if key in windows:
                raise ValueError(f"Duplicate window for {key}")
            windows[key] = r
    return windows


def meetings():
    articles = defaultdict(list)
    for r in load("news-framing")["records"]:
        if r["type"] == "decision":
            articles[r["bank"],r["date"]].append(r)
    rows = []
    for bank in load("stance-cohorts")["banks"]:
        key = bank["id"]
        events = load(key+"-cross-asset-events")
        windows = window_map(events)
        for r in bank["records"]:
            day = r["date"]
            if not START <= day <= END:
                continue
            release = windows.get((day,"release"), {})
            conference = windows.get((day,"conference"), {})
            reports = articles[key,day]
            row = dict(bank=key, date=day, leader=r["leader"], cycle=r["cycle"],
                       officialUrl=r.get("releaseUrl") or r["url"], actionBp=r.get("actionBp"),
                       priorMoveBp=r.get("priorMoveBp"), priorMethod=r.get("priorMethod"),
                       priorQuoteQualifier=r.get("priorQuoteQualifier"), pricingGapBp=r.get("pricingGapBp"),
                       pricingSource=r.get("priorPricingSource"), regularRelease=int(bool(release.get("groupEligible"))),
                       releaseEligible=int(bool(release.get("groupEligible"))), releaseWindow=release.get("window"),
                       conferenceEligible=int(bool(conference.get("groupEligible"))), conferenceWindow=conference.get("window"))
            for field, asset in ASSETS.items():
                row[field] = release.get("values",{}).get(asset)
                row["conference"+field[0].upper()+field[1:]] = conference.get("values",{}).get(asset)
            row["releaseScore"] = r.get("score") if r["sourceType"]=="release" else (r.get("releaseReading") or {}).get("score")
            row["conferenceScore"] = r.get("score") if r["sourceType"]=="conference" else conference.get("score")
            row.update(newsArticles=len(reports), newsOutlets=len({a["publisher"] for a in reports}),
                       reportCount=sum(a["coverageMode"]=="report" for a in reports),
                       previewCount=sum(a["coverageMode"]=="preview" for a in reports),
                       marketSource=events["source"]["url"],
                       flags=" | ".join(release.get("flags",[])), conferenceFlags=" | ".join(conference.get("flags",[])))
            rows.append(row)
    return rows


def describe(label, rows):
    a = [abs(row["ois1yBp"]) for row in rows]
    b = [abs(row["conferenceOis1yBp"]) for row in rows]
    # Float noise below one millionth of a basis point is treated as a tie.
    delta = [round(y-x,6) for x,y in zip(a,b)]
    return dict(label=label, n=len(rows), releaseMedianAbsBp=round(median(a),4) if a else None,
                conferenceMedianAbsBp=round(median(b),4) if b else None, conferenceLarger=sum(x>0 for x in delta),
                releaseLarger=sum(x<0 for x in delta), ties=delta.count(0))


def build(rows):
    res={"start":START, "through":END, "banks":{}, "method":[
        "Each comparison pairs two observations from the same decision date. Both windows must be aggregation-eligible and have a reported one-year overnight indexed swap rate change.",
        "Medians use absolute changes in basis points. The count of larger press-conference moves compares the two windows within each meeting. Windows have different durations and can include other information.",
        "The close-to-pricing subgroup requires a comparable expected action and a difference of at most 5 basis points in absolute value. This fixed threshold describes the target-rate decision; guidance can still reprice the path.",
        "US prior pricing is reconstructed from the current-meeting fed funds futures surprise. ECB gap observations use comparable documented meeting-specific quotes. The history is much shorter for these euro-area quotes."
    ]}
    for bank in ("fed","ecb"):
        frame=[r for r in rows if r["bank"]==bank]
        paired=[r for r in frame if r["releaseEligible"] and r["conferenceEligible"]
                and r["ois1yBp"] is not None and r["conferenceOis1yBp"] is not None]
        gap=[r for r in paired if r["pricingGapBp"] is not None]
        groups=[describe("Both windows observed",paired),
                describe("Action within 5 bp of prior pricing",[r for r in gap if abs(r["pricingGapBp"])<=5]),
                describe("Action more than 5 bp from prior pricing",[r for r in gap if abs(r["pricingGapBp"])>5])]
        res["banks"][bank]={"decisionCount":len(frame),"groups":groups,
            "note":("US release windows span 30 minutes; press-conference windows span 70 minutes. The paired sample begins with the introduction of Fed press conferences in 2011." if bank=="fed" else "The ECB release and press-conference windows use median quotes around different local times. The press-conference interval is longer. Meeting-specific prior pricing covers selected dates.")}
    return res


def main():
    parse=argparse.ArgumentParser(description=__doc__)
    parse.add_argument("--check", action="store_true")
    args=parse.parse_args()
    rows=meetings()
    if len({(r["bank"],r["date"]) for r in rows})!=len(rows): raise ValueError("Duplicate decision dates")
    out=io.StringIO(newline="")
    writer=csv.DictWriter(out,fieldnames=list(rows[0]),lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    files={"policy-research-meetings.csv":out.getvalue().encode("utf-8-sig"),
           "meeting-stage-study.json":(json.dumps(build(rows),ensure_ascii=False,indent=2)+"\n").encode()}
    for name, data in files.items():
        path=DATA/name
        if args.check:
            if not path.exists() or path.read_bytes()!=data:raise ValueError("Refresh "+name)
        else:path.write_bytes(data)


if __name__=="__main__":
    main()
