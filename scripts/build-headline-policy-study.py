"""Compare reviewed decision-headline guidance with announcement-window repricing."""
import argparse
from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path
from statistics import median

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
WSJ = "The Wall Street Journal"
OUTLETS = ("Bloomberg", "Financial Times", "Reuters", WSJ)
DIRECTIONS = ("tighter", "easier", "noDirectionalSignal", "split")
PRICE = {
    "fed": ("nextMeeting", "Next-meeting federal funds futures (MP2)", "FOMC announcement, −10 to +20 minutes"),
    "ecb": ("ois1y", "1-year euro OIS", "Frankfurt decision-release window, before the press conference"),
}


def read(data, stem):
    return json.loads((data / (stem + ".json")).read_text())


def outlook(titles, basis=None):
    directions = {row["path"] for row in titles if row["path"] in ("tighter", "easier")
                  and (basis is None or row["pathBasis"] == basis)}
    if len(directions) == 2:
        return "split"
    if directions:
        return directions.pop()
    return "noDirectionalSignal"


def meeting_vote(outlet_votes):
    counts = Counter(outlet_votes)
    margin = counts["tighter"] - counts["easier"]
    if margin:
        return "tighter" if margin > 0 else "easier"
    if counts["split"] or counts["tighter"]:
        return "split"
    return "noDirectionalSignal"


def summarise(events, prices, mode, exclusion=None, basis=None):
    grouped = {direction: [] for direction in DIRECTIONS}
    multi_outlet = 0
    for day, outlets in events.items():
        votes = [outlook(titles, basis) for publisher, titles in outlets.items() if publisher != exclusion]
        if not votes or (basis and all(vote == "noDirectionalSignal" for vote in votes)):
            continue
        multi_outlet += len(votes) > 1
        grouped[meeting_vote(votes)].append(prices.get(day))
    groups = []
    for direction, observations in grouped.items():
        observed = [bp for bp in observations if bp is not None]
        material = [bp for bp in observed if abs(bp) > 1]
        aligned = None
        if direction in ("tighter", "easier"):
            aligned = sum((bp > 0) == (direction == "tighter") for bp in material)
        groups.append(dict(direction=direction, nEvents=len(observations), nPriced=len(observed),
                           medianBp=round(median(observed), 4) if observed else None,
                           materialN=len(material), alignedN=aligned))
    return dict(mode=mode, exclusion=exclusion,
                nEvents=sum(x["nEvents"] for x in groups), nPriced=sum(x["nPriced"] for x in groups),
                nMultiOutlet=multi_outlet, groups=groups)


def overlaps(events):
    pairs = []
    for first, second in combinations(OUTLETS, 2):
        shared = [outlets for outlets in events.values() if first in outlets and second in outlets]
        votes = [(outlook(outlets[first]), outlook(outlets[second])) for outlets in shared]
        direct = [(a, b) for a, b in votes if a in ("tighter", "easier") and b in ("tighter", "easier")]
        pairs.append(dict(publisherA=first, publisherB=second, nShared=len(shared),
                          nBothDirectional=len(direct), nSameDirection=sum(a == b for a, b in direct)))
    return pairs


def build(data):
    news = read(data, "news-framing")
    rosters = read(data, "stance-cohorts")["banks"]
    by_bank = []
    for bank in rosters:
        key = bank["id"]
        if key not in PRICE:
            continue
        rate, instrument, window = PRICE[key]
        roster = {row["date"] for row in bank["records"] if "2000-01-01" <= row["date"] <= "2025-12-31"}
        rates = read(data, key + "-cross-asset-events")["records"]
        prices = {row["date"]: row["values"].get(rate) for row in rates
                  if row["stage"] == "release" and row["groupEligible"] and row["date"] in roster}
        samples = {mode: defaultdict(lambda: defaultdict(list)) for mode in ("report", "preview")}
        for row in news["records"]:
            if row["bank"] == key and row["type"] == "decision" and row["date"] in roster:
                samples[row["coverageMode"]][row["date"]][row["publisher"]].append(row)
        reports = samples["report"]
        variants = [summarise(events, prices, mode, dropped) for mode, events in samples.items()
                    for dropped in (None, WSJ)]
        basis_checks = [dict(basis=basis, **summarise(reports, prices, "report", basis=basis))
                        for basis in ("level", "revision")]
        concentration = []
        for publisher in OUTLETS:
            count = sum(publisher in outlets for outlets in reports.values())
            only = sum(set(outlets) == {publisher} for outlets in reports.values())
            concentration.append(dict(publisher=publisher, nReportEvents=count, nSoleOutlet=only))
        by_bank.append(dict(bank=key, instrument=instrument, window=window, variants=variants,
                            overlap=overlaps(reports), basisChecks=basis_checks, concentration=concentration,
                            nDecisionDates=len(roster), nEligiblePrices=sum(v is not None for v in prices.values())))
    return dict(asOf=news["asOf"], start="2000-01-01", end="2025-12-31", banks=by_bank, method=[
        "The study covers completed calendar years 2000–2025. Each decision date contributes once per bank, sample and coverage mode. The study uses reviewed titles linked to a rate decision. Counts cover observed titles, and the sample depends on archive recovery.",
        "Each outlet gets one vote per date. Repeated titles with the same direction have one vote in total. Both directions in one outlet count as a split. A majority of directional outlet votes determines the event label. Equal and opposing votes, or only internally split votes, give a split. Reports and previews are counted separately.",
        "Direction requires an explicit tighter or easier forward policy path in the headline. A description of a completed hike or cut alone is insufficient. The no-directional-signal group also includes conditional, steady and mixed path codes. It does not measure neutral policy. The main comparison includes both future levels and revisions. The basis checks retain only dates with an explicit directional code of the chosen basis.",
        "Price is the signed change, in basis points, in the release window. Positive means a higher expected rate. Non-standard windows and unavailable prices are excluded from price statistics. The two instruments have different horizons. For directional groups, agreement uses only moves above one basis point in absolute size.",
        "These are descriptive event-level comparisons. Publishers can revise headlines, and reports can include later remarks from the press conference. A preview classification identifies its subject and does not establish that its reviewed wording was available before release.",
        "Removing The Wall Street Journal repeats the vote on the remaining reports. Dates with no remaining outlet drop out. The market-move difference can reflect this change in which meetings are covered. Pairwise overlap counts compare two outlets on identical dates.",
    ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args()
    result = build(args.data)
    (args.data / "headline-policy-study.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
