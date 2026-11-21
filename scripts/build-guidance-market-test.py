"""Compare adjacent official guidance scores with market changes in the corresponding release windows."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
from statistics import median

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
FIRST, LAST = "2000-01-01", "2025-12-31"
PANELS = (
    ("fedRelease", "fed", "release", "Federal Reserve policy statement"),
    ("ecbRelease", "ecb", "release", "ECB decision release"),
    ("ecbConference", "ecb", "conference", "ECB opening statement and press conference"),
)


def load(data, name):
    return json.loads((data / (name + ".json")).read_text())


def document(meeting, bank, stage):
    if bank == "fed" or meeting["sourceType"] == stage:
        return meeting
    return meeting.get("releaseReading") if stage == "release" else None


def rows_for(data, bank, stage):
    name = "fed-statement-stance" if bank == "fed" else "ecb-stance-history"
    documents = load(data, name)["records"]
    markets = load(data, bank + "-cross-asset-events")
    windows = {row["date"]:row for row in markets["records"] if row["stage"] == stage}
    cohort = next(b for b in load(data, "stance-cohorts")["banks"] if b["id"] == bank)
    priors = {r["date"]:r for r in cohort["records"]}
    rows, prev = [], {}
    for meeting in sorted(documents, key=lambda x: x["date"]):
        day = meeting["date"]
        if not FIRST <= day <= LAST:
            continue
        text = document(meeting, bank, stage)
        score = text.get("score") if text else None
        source = (text.get("url") or text["sourceUrl"]) if text else None
        if text:
            window = windows.get(day, {})
            values = window.get("values", {})
            prev_score = prev.get("score")
            shift = score - prev_score if score is not None and prev_score is not None else None
            if score is None:
                reason = "Current document unscored"
            elif not prev or not prev.get("url"):
                reason = "No same-stage document at immediately preceding decision"
            elif prev_score is None:
                reason = "Preceding document unscored"
            else:
                reason = "Paired"
            row = dict(bank=bank, stage=stage, date=day, leader=priors[day]["leader"], url=source,
                       previousDecisionDate=prev.get("date"), previousUrl=prev.get("url"), score=score,
                       previousScore=prev_score, shift=shift, pairing=reason, rule=text["rule"],
                       evidenceKind=text.get("evidenceKind", "Official policy statement"),
                       priorMethod=priors[day].get("priorMethod"), pricingGapBp=priors[day].get("pricingGapBp"),
                       pricingSource=priors[day].get("priorPricingSource"), time=window.get("time"),
                       zone=window.get("timeZone"), window=window.get("window"),
                       marketEligible=bool(window.get("groupEligible")), marketSource=markets["source"]["url"],
                       ois1yBp=values.get("ois1y"), slope2s10sBp=values.get("slope"),
                       equityPct=values.get("equity"), nextMeetingBp=values.get("nextMeeting"))
            rows.append(row)
            if bank == "fed" and shift != meeting["shift"]:
                raise ValueError("Fed shift differs from the original score series at " + day)
        # A missing conference or unscored document resets the comparison.
        prev = dict(score=score, url=source, date=day)
    return rows


def summary_group(label, rows):
    result = dict(direction=label, nText=len(rows))
    for key, count_key, value_key in (
        ("ois1yBp", "nOis", "medianOisBp"), ("slope2s10sBp", "nSlope", "medianSlopeBp"),
        ("equityPct", "nEquity", "medianEquityPct"), ("nextMeetingBp", "nNextMeeting", "medianNextMeetingBp")
    ):
        observed = [r[key] for r in rows if r[key] is not None]
        result[count_key] = len(observed)
        result[value_key] = round(median(observed), 5) if observed else None
    material = [r["ois1yBp"] for r in rows if r["ois1yBp"] is not None and abs(r["ois1yBp"]) > 1]
    aligned = None if label == "unchanged" else sum((bp > 0) == (label == "tighter") for bp in material)
    return dict(**result, materialN=len(material), alignedN=aligned)


def variant(code, label, rows):
    groups = {"tighter":[], "unchanged":[], "easier":[]}
    for r in rows:
        shift = r["shift"]
        direction = "tighter" if shift > 0 else "easier" if shift < 0 else "unchanged"
        groups[direction].append(r)
    return dict(id=code, label=label, nEvents=len(rows), groups=[summary_group(d, rs) for d,rs in groups.items()])


def summarise(panel_id, bank, stage, label, rows):
    paired = [r for r in rows if r["shift"] is not None]
    eligible = [r for r in paired if r["marketEligible"]]
    variants = [variant("all", "All eligible paired stages", eligible)]
    if bank == "fed":
        for cutoff in (5, 2, 10):
            subset = [r for r in eligible if r["pricingGapBp"] is not None and abs(r["pricingGapBp"]) <= cutoff]
            variants.append(variant("close"+str(cutoff), f"Target-rate surprise within ±{cutoff} bp", subset))
    # Compute the 99th percentile across ALL eligible official stages with a price,
    # before conditioning on text availability or direction.
    moves = sorted(abs(r["ois1yBp"]) for r in rows if r["marketEligible"] and r["ois1yBp"] is not None)
    position = (len(moves) - 1)*.99
    a, b = math.floor(position), math.ceil(position)
    trim = moves[a] + (moves[b] - moves[a])*(position-a)
    variants.append(variant("trimmed", "Through 99th percentile of absolute 1Y OIS moves",
                            [r for r in eligible if r["ois1yBp"] is not None and abs(r["ois1yBp"]) <= trim]))
    variants.append(variant("early", "2000–2012", [r for r in eligible if r["date"] < "2013"]))
    variants.append(variant("late", "2013–2025", [r for r in eligible if r["date"] >= "2013"]))
    return dict(id=panel_id, bank=bank, stage=stage, label=label, nEvents=len(rows),
                nScores=sum(r["score"] is not None for r in rows), nPaired=len(paired),
                nChanged=sum(r["shift"] != 0 for r in paired), nUnchanged=sum(r["shift"] == 0 for r in paired),
                nMissingShift=len(rows)-len(paired), nEligiblePaired=len(eligible),
                nMatchedOis=sum(r["ois1yBp"] is not None for r in eligible), trimThresholdBp=round(trim,5),
                missingReasons=dict(Counter(r["pairing"] for r in rows if r["shift"] is None)), variants=variants)


def build(data):
    panels, ledger = [], []
    for panel_id, bank, stage, label in PANELS:
        rows = rows_for(data, bank, stage)
        ledger.extend(rows)
        panels.append(summarise(panel_id, bank, stage, label, rows))
    result = dict(period=dict(start=FIRST,end=LAST), panels=panels, method=[
        "The ordinal wording score runs from −2 to +2. A shift compares the present score to the same document stage at the immediately preceding rate decision. Both scores must be observed. Missing stages and unscored language reset the comparison. An unchanged category can be hawkish, dovish or balanced.",
        "The Fed score represents its policy statement. ECB decision releases and opening statements or Q&A have separate scores and price windows. A conference reading can draw on the chair’s Q&A; its associated prices span that conference. Document links and timing are supplied in the event file.",
        "The main groups use eligible event windows with a paired score. Each price series uses its own available observations. The 1-year OIS and 2s10s (10-year less 2-year sovereign yield) are in basis points; equities are percentage changes in the domestic stock index. For the Fed, next-meeting futures are also reported.",
        "Alignment compares the sign of a non-zero wording change to the sign of a 1-year OIS move larger than one basis point in absolute size. The wording change measures revision from the last document. It does not quantify how much of the current message markets anticipated.",
        "The Fed pricing sensitivity uses the absolute target-rate surprise derived from current-meeting fed funds futures, separately from the 1-year OIS outcome. A small surprise in the current target does not establish that the rest of the announcement was anticipated. The outlier check trims above the panel’s 99th percentile of absolute 1-year OIS moves over all eligible priced stages, including those without text scores.",
        "Only a small number of consecutive texts change wording category in this sample. Medians and sign counts are descriptive, and chronological subgroup splits can contain just one directional observation. The samples are too sparse for an informative significance test. Other news or information about the economy can affect prices in the same interval."
    ])
    (data / "guidance-market-test.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    with (data / "guidance-market-test.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f,fieldnames=list(ledger[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(ledger)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=DATA)
    build(parser.parse_args().data)
