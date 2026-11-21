"""Compare release-window one-year OIS with event-level, publisher-balanced headline readings."""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
import runpy
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parents[1] / "dist/data"
RUBRIC = runpy.run_path(str(Path(__file__).with_name("build-headline-policy-study.py")))
OUTLETS, WSJ = RUBRIC["OUTLETS"], RUBRIC["WSJ"]
SIGNED = {"tighter", "easier"}


def release_clocks(data, bank):
    records = json.loads((data / f"{bank}-cross-asset-events.json").read_text())["records"]
    clocks = {}
    for r in records:
        if r["stage"] == "release" and r.get("time"):
            local = datetime.fromisoformat(r["date"] + "T" + r["time"]).replace(tzinfo=ZoneInfo(r["timeZone"]))
            clocks[r["date"]] = local.astimezone(timezone.utc)
    return clocks


def chronology(title, release):
    if not release:
        return "release clock unavailable"
    if title.get("publishedAt"):
        posted = datetime.fromisoformat(title["publishedAt"].replace("Z", "+00:00"))
        if posted.utcoffset() is None:
            raise ValueError("Publisher clock lacks a timezone: " + title["id"])
        return "post-release article clock" if posted > release else "published at or before release"
    if title.get("publicationDate"):
        # Source date without timezone: UTC+14 supplies the earliest possible instant.
        day = datetime.fromisoformat(title["publicationDate"]).date()
        earliest = datetime.combine(day, time.min, tzinfo=timezone(timedelta(hours=14)))
        if earliest > release:
            return "strictly later edition date"
    return "edition timing unresolved"


def vote(titles):
    buckets = defaultdict(list)
    for t in titles:
        buckets[t["publisher"]].append(t)
    ballots = {p: RUBRIC["outlook"](rows) for p, rows in sorted(buckets.items())}
    return dict(direction=RUBRIC["meeting_vote"](ballots.values()) if ballots else "noReport", ballots=ballots)


def summarise(rows, field):
    stats = Counter()
    directions = Counter()
    for r in rows:
        result = r[field]
        direction = result["direction"]
        observed = r["ois1yBp"]
        stats["nDecisions"] += 1
        stats["nWithReport"] += bool(result["ballots"])
        stats["nMultiOutlet"] += len(result["ballots"]) > 1
        stats["nWithOis"] += observed is not None
        directions[direction] += 1
        if direction in SIGNED:
            stats["nDirectional"] += 1
            if observed is not None:
                stats["nDirectionalWithOis"] += 1
                if abs(observed) > 1:
                    stats["nMaterialDirectional"] += 1
                    aligned = (observed > 0) == (direction == "tighter")
                    stats["nAligned" if aligned else "nOpposite"] += 1
    fields = ("nDecisions", "nWithReport", "nMultiOutlet", "nDirectional", "nWithOis", "nDirectionalWithOis",
              "nMaterialDirectional", "nAligned", "nOpposite")
    n = stats["nMaterialDirectional"]
    return {**{k: stats[k] for k in fields}, "shareAlignedPct": round(100 * stats["nAligned"] / n, 2) if n else None,
            "eventVotes": {k: directions[k] for k in ("tighter", "easier", "split", "noDirectionalSignal", "noReport")}}


def build(data):
    with (data / "anticipated-decisions.csv").open(encoding="utf-8-sig", newline="") as f:
        meetings = [r for r in csv.DictReader(f) if r["analysisEligible"] == "True"]
    news = json.loads((data / "news-framing.json").read_text())["records"]
    reports = defaultdict(list)
    for t in news:
        if t["type"] == "decision" and t["coverageMode"] == "report" and t["publisher"] in OUTLETS:
            reports[t["bank"], t["date"]].append(t)
    events, results = [], []
    for bank in ("fed", "ecb"):
        clocks = release_clocks(data, bank)
        frame = []
        source_dates = Counter()
        source_matched = Counter()
        timing_counts = Counter()
        for m in meetings:
            if m["bank"] != bank:
                continue
            day = m["date"]
            source = reports[bank, day]
            clock = clocks.get(day)
            tags = [(t, chronology(t, clock)) for t in source]
            primary = [t for t, label in tags if label in {"post-release article clock", "strictly later edition date"}]
            row = dict(bank=bank, date=day, officialUrl=m["officialUrl"], releaseUtc=clock.isoformat() if clock else None,
                       anticipated=m["defaultGroup"] == "anticipated", pricingClass=m["defaultGroup"],
                       pricingGapBp=float(m["comparisonGapBp"]) if m["comparisonGapBp"] else None,
                       priorEvidenceType=m["priorEvidenceType"], pricingSource=m["pricingSource"] or None,
                       ois1yBp=float(m["ois1yBp"]) if m["ois1yBp"] else None, marketSource=m["marketSource"],
                       postRelease=vote(primary), withoutWSJ=vote([t for t in primary if t["publisher"] != WSJ]),
                       retrospective=vote(source),
                       reports=[dict(id=t["id"], publisher=t["publisher"], url=t["url"], path=t["path"],
                                     pathBasis=t["pathBasis"], publicationDate=t["publicationDate"],
                                     publishedAt=t["publishedAt"], chronology=label) for t, label in tags])
            if row["anticipated"]:
                timing_counts.update(label for _, label in tags)
                source_dates.update({t["publisher"] for t in primary})
                if (row["postRelease"]["direction"] in SIGNED and row["ois1yBp"] is not None and abs(row["ois1yBp"]) > 1):
                    source_matched.update({pub for pub, ballot in row["postRelease"]["ballots"].items() if ballot in SIGNED})
            frame.append(row)
        anticipated = [r for r in frame if r["anticipated"]]
        reported_steps = [r for r in frame if r["pricingClass"] == "reportedStep"]
        results.append(dict(bank=bank, reportedStep=summarise(reported_steps, "postRelease"),
                            timingCounts=dict(timing_counts), anticipated=summarise(anticipated, "postRelease"), allEligible=summarise(frame, "postRelease"),
                            withoutWSJ=summarise(anticipated, "withoutWSJ"), retrospective=summarise(anticipated, "retrospective"),
                            sourceCoverage=[dict(publisher=p, anticipatedMeetings=source_dates[p], directionalMatchedMeetings=source_matched[p]) for p in OUTLETS]))
        events.extend(frame)
    link_domains = {
        "publisherReports": sorted({urlsplit(t["url"]).hostname for e in events for t in e["reports"]}),
        "marketData": sorted({urlsplit(e["marketSource"]).hostname for e in events if e["marketSource"]}),
        "officialDecisions": sorted({urlsplit(e["officialUrl"]).hostname for e in events if e["officialUrl"]}),
        "anticipatedPriors": sorted({urlsplit(e["pricingSource"]).hostname for e in events if e["anticipated"] and e["pricingSource"]}),
    }
    return dict(linkDomains=link_domains, period={"start": "2000-01-01", "end": "2025-12-31"}, banks=results, events=events, methods=[
        "The primary set contains eligible regular releases with an absolute announced-minus-expected policy move of at most 5 bp. For the ECB only numerical meeting-specific curves comparable to the announced deposit rate step can enter this group. A separately labelled sensitivity covers reports describing anticipated steps in round numbers. These descriptions cannot resolve a five-basis-point gap. The reference includes all regular eligible releases, including those with unavailable prior pricing. The US and euro-area samples both use the signed release-window change in one-year OIS. Absolute changes strictly above 1 bp enter the agreement denominator.",
        "Only reviewed reports from the four named publishers enter the vote. Each outlet casts one vote per event. Explicit tighter and easier paths determine direction. Within-outlet disagreement abstains, and opposed votes of equal weight have no event direction. Rate actions alone, mixed paths, conditional paths and guidance for unchanged rates supply no directional vote.",
        "For the primary test the article posting clock must be strictly after the release, or its edition date must begin after the release even in UTC+14. This lower bound permits dates without a confirmed zone. At-release and earlier posting clocks remain ineligible even if the article was later updated. Headlines can change after publication, and post-release reports can incorporate the press conference or later developments.",
        "The retrospective sensitivity includes all verified decision reports without the posting-time screen. The outlet sensitivity removes The Wall Street Journal before recalculating the event vote. The exercise measures retrospective agreement with a price change. It cannot establish predictive ability or identify the information that moved prices."
    ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.data / "anticipated-headlines.json"
    encoded = json.dumps(build(args.data), ensure_ascii=False, separators=(",", ":")) + "\n"
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != encoded:
            raise SystemExit("Regenerate anticipated-headlines.json")
    else:
        output.write_text(encoded, encoding="utf-8")
