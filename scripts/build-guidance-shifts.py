"""Build consecutive policy-guidance comparisons from the published meeting datasets."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FED_STRATEGY = "https://www.federalreserve.gov/monetarypolicy/monetary-policy-strategy-tools-and-communications-statement-on-longer-run-goals-monetary-policy-strategy-"
ECB_PR = "https://www.ecb.europa.eu/press/pr/date/"
EUROSTR = "https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_short-term_rate/html/eurostr_overview.en.html"
BREAKS = {
    "fed": [
        ("2012-01-24", "Longer-run goals adopted", FED_STRATEGY + "2019-2020.htm"),
        ("2020-08-27", "2020 strategy revision", FED_STRATEGY + "2019-2020.htm"),
        ("2025-08-22", "2025 strategy revision", FED_STRATEGY + "2025.htm"),
    ],
    "ecb": [
        ("2000-06-28", "Variable-rate main refinancing tenders take effect", ECB_PR + "2000/html/pr000608.en.html"),
        ("2003-05-08", "2003 monetary policy strategy", ECB_PR + "2003/html/pr030508_2.en.html"),
        ("2008-10-08", "Fixed-rate full allotment announced", ECB_PR + "2008/html/pr081008_2.en.html"),
        ("2019-10-02", "EONIA methodology changes", EUROSTR),
        ("2021-07-08", "Symmetric inflation target adopted", ECB_PR + "2021/html/ecb.pr210708~dc78cc4b0d.en.html"),
        ("2022-01-03", "EONIA discontinued", EUROSTR),
        ("2024-09-18", "New refinancing spread takes effect", ECB_PR + "2024/html/ecb.pr240313~807e240020.en.html"),
        ("2025-06-30", "2025 monetary policy strategy", ECB_PR + "2025/html/ecb.pr250630~aabf988af8.en.html"),
    ],
}
WHY = {
    "stage": "This meeting has no archived communication for this stage.",
    "current": "The current communication has no explicit scored rate guidance.",
    "first": "This is the first meeting in the sample.",
    "previous": "The immediately preceding meeting has no scored guidance for this stage.",
    "chair": "The person chairing the institution changed between these meetings.",
    "framework": "An identified strategy, operating-framework or benchmark boundary falls between the meetings.",
    "window": "The event-window convention changes between these meetings.",
    "target": "The Fed target changes between a point and a range.",
}
ECB_LABEL = {
    "conditional-withdrawal": "Conditional withdrawal of accommodation",
    "vigilance": "Inflation vigilance as a conditional tightening signal",
    "lower-option": "A cut kept open alongside a hold",
    "conditional-cut": "Further cuts subject to conditions",
    "dated-hold": "Hold for a stated horizon",
    "low-rate-promise": "Low rates until conditions are met",
    "further-increase": "Further tightening signalled",
    "plateau": "Restrictive rate plateau",
    "reviewed-tightening": "Further tightening discussed",
    "reviewed-easing": "Further easing discussed",
    "reviewed-balanced": "Explicitly balanced or steady path",
    "reviewed-early-reply": "Direction clarified in questions and answers",
}


def prepare(bank, stage, meeting, fed_text):
    if bank == "ecb" and stage == "conference" and meeting["sourceType"] != "conference":
        return None
    entry = meeting
    if bank == "ecb" and stage == "release":
        entry = meeting.get("releaseReading") or meeting
    score = entry["score"]
    if score not in (None, -2, -1, 0, 1, 2):
        raise ValueError(f"Unknown score on {meeting['date']}")
    if bank == "fed":
        source = meeting["url"]
        rule_label = fed_text["rules"][entry["rule"]]["label"]
    else:
        source = entry.get("sourceUrl") or entry.get("url")
        rule_label = ECB_LABEL.get(entry["rule"])
        if score is not None and not rule_label:
            raise ValueError(f"Unmapped ECB rule {entry['rule']}")
    return {
        "date": meeting["date"], "chair": meeting["leader"],
        "cycle": meeting["cycle"], "phase": meeting["policyPhase"],
        "score": score, "rule": entry.get("rule"), "reading": rule_label,
        "explanation": entry["rationale"] if score is not None else None,
        "url": source, "marketBp": entry["marketBp"], "window": entry["marketWindow"],
        "actionBp": meeting["actionBp"], "gapBp": meeting.get("pricingGapBp"),
        "pricedBp": meeting.get("priorMoveBp") if meeting.get("pricingGapBp") is not None else None,
    }


def build_stage(bank, stage, meetings, fed_text, target):
    records = []
    for meeting in meetings:
        day = meeting["date"]
        entry = prepare(bank, stage, meeting, fed_text)
        previous = records[-1] if records else None
        row = entry or {"date": day, "chair": meeting["leader"], "score": None}
        row["previousDate"] = previous["date"] if previous else None
        reason = None
        if not entry:
            reason = "stage"
        elif row["score"] is None:
            reason = "current"
        elif not previous:
            reason = "first"
        elif previous.get("score") is None:
            reason = "previous"
        elif previous["chair"] != row["chair"]:
            reason = "chair"
        else:
            boundary = next((name for date, name, _ in BREAKS[bank] if previous["date"] < date <= day), None)
            if boundary:
                row["boundary"] = boundary
                reason = "framework"
            elif bank == "fed" and target[day] != target[previous["date"]]:
                reason = "target"
            elif previous["window"] != row["window"]:
                reason = "window"
        row["reason"] = reason
        if reason is None:
            row["shift"] = row["score"] - previous["score"]
        records.append(row)
    return {"bank": bank, "stage": stage, "records": [
        {k: v for k, v in row.items() if v is not None} for row in records
    ]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "dist/data")
    ap.add_argument("--output", type=Path, default=ROOT / "dist/data/guidance-shifts.json")
    args = ap.parse_args()
    cohorts = json.loads((args.data / "stance-cohorts.json").read_text())
    fed_text = json.loads((args.data / "fed-statement-stance.json").read_text())
    target = {r["date"]: r["targetType"] for r in fed_text["records"]}
    panels = []
    for bank in cohorts["banks"]:
        meetings = bank["records"]
        dates = [row["date"] for row in meetings]
        if dates != sorted(set(dates)):
            raise ValueError("Meeting records must use unique ascending dates")
        for stage in (["release"] if bank["id"] == "fed" else ["release", "conference"]):
            panel = build_stage(bank["id"], stage, meetings, fed_text, target)
            panel["marketSource"] = bank["marketUrl"]
            panel["instrument"] = bank["marketLabel"]
            panels.append(panel)
    output = {"asOf": cohorts["asOf"], "exclude": WHY, "boundaries": BREAKS, "panels": panels}
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
