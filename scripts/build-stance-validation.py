"""Match text-based changes in FOMC guidance to scheduled U.S. statement windows.

Refresh the score and market inputs first, then supply the San Francisco Fed
workbook (https://www.frbsf.org/wp-content/uploads/USMPD.xlsx). Requires openpyxl.
    python scripts/build-stance-validation.py --usmpd /path/to/USMPD.xlsx
"""
import argparse
import hashlib
import json
import math
import statistics
from datetime import date
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from openpyxl import load_workbook


DATA = Path(__file__).resolve().parents[1] / "dist/data"
DOCUMENTATION = "https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/"
PAPER = "https://www.frbsf.org/wp-content/uploads/wp2025-30.pdf"
BAND_BP = 1


def indexed(rows):
    by_date = {}
    for row in rows:
        day = row["date"]
        date.fromisoformat(day)
        if day in by_date:
            raise ValueError(f"Duplicate date {day}")
        by_date[day] = row
    return by_date


def ranks(values):
    """Rank ties at the mean of their one-based positions."""
    ranked = [0.0] * len(values)
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    start = 1
    for _, equal_values in groupby(ordered, key=lambda item: item[1]):
        group = list(equal_values)
        midpoint = start + (len(group) - 1) / 2
        for index, _ in group:
            ranked[index] = midpoint
        start += len(group)
    return ranked


def summarize(rows):
    changes = [row["shift"] for row in rows]
    yields = [row["yieldBp"] for row in rows]
    rho = None
    if len(set(changes)) > 1 and len(set(yields)) > 1:
        rho = round(statistics.correlation(ranks(changes), ranks(yields)), 4)
    directional = [row for row in rows if row["shift"] != 0 and row["yieldBp"] != 0]
    return {
        "n": len(rows),
        "rho": rho,
        "comparable": len(directional),
        "sameSign": sum(row["shift"] * row["yieldBp"] > 0 for row in directional),
        "flatYield": sum(value == 0 for value in yields),
    }


def surprise_bp(value):
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError("Non-finite futures surprise")
    return value * 100


def next_meeting_direction(bp):
    if bp is None:
        return None, None
    # Excel stores binary approximations for decimal quotes exactly at the band edge.
    if abs(bp) <= BAND_BP or math.isclose(abs(bp), BAND_BP, rel_tol=0, abs_tol=1e-9):
        return 0, "Within 1 bp of prior pricing"
    if bp > 0:
        return 1, "More hawkish than priced"
    return -1, "More dovish than priced"


def expectations(score_rows, workbook_path, releases, closes):
    book = load_workbook(workbook_path, read_only=True, data_only=True)
    observations = []
    try:
        records = book["Statements"].values
        columns = next(records)
        for values in records:
            release = dict(zip(columns, values))
            stamp = release["Date"]
            if stamp is None:
                continue
            day = stamp.date().isoformat()
            if day not in score_rows or release["Unscheduled"] != 0:
                continue
            record = score_rows[day]
            mp1, mp2 = surprise_bp(release["MP1"]), surprise_bp(release["MP2"])
            sign, label = next_meeting_direction(mp2)
            # The upper-bound action is interchangeable with a midpoint change only for constant width.
            action = record["actionBp"]
            prior = score_rows.get(record["previousDate"])
            comparable_target = action is not None
            if prior:
                width = record["targetUpper"] - record["targetLower"]
                prior_width = prior["targetUpper"] - prior["targetLower"]
                comparable_target = comparable_target and record["targetType"] == prior["targetType"] and math.isclose(width, prior_width)
            prior_move = action - mp1 if comparable_target and mp1 is not None else None
            observations.append({"date": day, "score": record["score"], "actionBp": action,
                                 "impliedPriorMoveBp": prior_move, "currentSurpriseBp": mp1,
                                 "nextRepricingBp": mp2, "marketDirection": sign, "marketLabel": label,
                                 **curve_context(releases.get(day), closes)})
    finally:
        book.close()
    observations = sorted(indexed(observations).values(), key=lambda row: row["date"])
    directional = [row for row in observations if row["score"] not in (None, 0)]
    comparable = [row for row in directional if row["marketDirection"] not in (None, 0)]
    opposite = sum(row["score"] * row["marketDirection"] < 0 for row in comparable)
    return {
        "bandBp": BAND_BP, "unit": "basis points",
        "matched": len(observations), "firstDate": observations[0]["date"] if observations else None,
        "lastDate": observations[-1]["date"] if observations else None,
        "priorMoveAvailable": sum(row["impliedPriorMoveBp"] is not None for row in observations),
        "directionalText": len(directional), "comparable": len(comparable),
        "opposite": opposite, "same": len(comparable) - opposite,
        "flatMarket": sum(row["marketDirection"] == 0 for row in directional),
        "missingNext": sum(row["marketDirection"] is None for row in directional),
        "method": [
            "The two market readings come from changes in federal funds futures during the scheduled statement window. MP1 measures the surprise at the current meeting. MP2 measures repricing of the expected rate at the next scheduled meeting.",
            "The approximate move priced before this decision equals the announced target change minus MP1. This assumes full resolution of the current decision during the window and a stable spread between the effective funds rate and the target point or range midpoint. The first point-to-range transition has no comparable move. Futures conventions, especially near month end, can affect the estimate.",
            "The next-meeting label uses the unrounded MP2 reading and a fixed inclusive band of ±1 bp. Positive moves outside the band indicate tighter next-meeting pricing, negative moves indicate easier pricing. These are changes in expected rates; no meeting probabilities are inferred.",
            "The comparison uses directional wording levels and non-flat next-meeting repricing. Opposite signs can arise when listeners already expected stronger language, or when accompanying decisions and projections move rates. A signed disagreement does not identify its cause."
        ],
        "observations": observations,
    }


def curve_context(quote, closes):
    if quote is None:
        return dict.fromkeys(("priorStart", "priorEnd", "prior2yBp", "prior2s10sBp", "yieldBp"))
    day, first, last = quote["date"], quote["start"], quote["end"]
    if not first < last < day:
        raise ValueError(f"Invalid pre-release observation dates on {day}")
    deltas = {
        tenor: (Decimal(str(closes[last][tenor])) - Decimal(str(closes[first][tenor]))) * 100
        for tenor in ("y2", "y10")
    }
    if deltas["y2"] != Decimal(str(quote["priorBp"])):
        raise ValueError(f"Two-year history disagrees with market extract on {day}")
    return {"priorStart": first, "priorEnd": last, "prior2yBp": quote["priorBp"],
            "prior2s10sBp": float(deltas["y10"] - deltas["y2"]), "yieldBp": quote["statementBp"]}


def build(score_rows, releases, closes, curve):
    coverage = dict.fromkeys(("unscored", "noPriorScore", "noMarket", "unscheduled", "matched"), 0)
    observations = []
    for day in sorted(score_rows):
        record = score_rows[day]
        quote = releases.get(day)
        if record["score"] is None:
            coverage["unscored"] += 1
        elif record["shift"] is None:
            coverage["noPriorScore"] += 1
        elif quote is None or quote["statementBp"] is None:
            coverage["noMarket"] += 1
        elif quote["scheduled"] is False:
            coverage["unscheduled"] += 1
        else:
            if quote["scheduled"] is not True or not math.isfinite(quote["statementBp"]):
                raise ValueError(f"Invalid statement window on {day}")
            if not math.isfinite(record["shift"]):
                raise ValueError(f"Invalid stance shift on {day}")
            coverage["matched"] += 1
            observations.append({"date": day, "shift": record["shift"], "actionBp": record["actionBp"],
                                 **curve_context(quote, closes)})
    if sum(coverage.values()) != len(score_rows):
        raise ValueError("Unreconciled coverage")
    groups = []
    for direction, name in [(1, "More hawkish"), (0, "Unchanged"), (-1, "More dovish")]:
        members = [row for row in observations if (row["shift"] > 0) - (row["shift"] < 0) == direction]
        group = {"name": name, "n": len(members)}
        for result_key, field in (("medianBp", "yieldBp"), ("medianPrior2yBp", "prior2yBp"),
                                  ("medianPrior2s10sBp", "prior2s10sBp")):
            group[result_key] = round(statistics.median(row[field] for row in members), 5) if members else None
        groups.append(group)
    return {
        "version": 1,
        "series": "U.S. two-year Treasury yield change (UST2Y, basis points)",
        "window": "Scheduled FOMC statements, 10 minutes before to 20 minutes after release",
        "sourceUrl": DOCUMENTATION,
        "treasuryUrl": curve["market"]["sources"][0]["url"],
        "methodUrl": PAPER,
        "firstDate": observations[0]["date"] if observations else None,
        "lastDate": observations[-1]["date"] if observations else None,
        "coverage": {"records": len(score_rows), **coverage},
        "groups": groups,
        "all": summarize(observations),
        "hold": summarize([row for row in observations if row["actionBp"] == 0]),
        "method": [
            "One exact-date match per scheduled FOMC statement with a two-year yield change and a comparable change in its text score. The score builder uses statement language independently of this market series.",
            "The USMPD Statements worksheet reports yields in percentage points. The market input converts them to basis points. Positive values mean the yield rose.",
            "Before each release, changes use the last and fifth-most-recent joint U.S. Treasury two- and ten-year daily par quotes. The 2s10s slope equals the ten-year yield minus the two-year yield. Positive changes mean steepening. The pre-release curve describes cumulative market moves over four trading intervals and cannot isolate the probability assigned to a particular meeting.",
            "Spearman correlation ranks the full signed score shifts and yield changes with average ranks for ties, including unchanged scores and yields. A constant series has no defined correlation.",
            "The directional count requires both the text shift and yield move to be nonzero. The held-rate subset requires an observed zero change in the target range's upper bound.",
            "The window also captures the announced rate decision and any projections released alongside the statement. An anticipated change in guidance can produce little repricing. The relationship is descriptive."
        ],
        "observations": observations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, default=DATA / "fed-statement-stance.json")
    parser.add_argument("--market", type=Path, default=DATA / "fed-direction-study.json")
    parser.add_argument("--curve", type=Path, default=DATA / "pre-event-curve.json")
    parser.add_argument("--usmpd", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DATA / "stance-validation.json")
    args = parser.parse_args()
    score_bytes, market_bytes, curve_bytes = args.scores.read_bytes(), args.market.read_bytes(), args.curve.read_bytes()
    market = json.loads(market_bytes)
    scores = indexed(json.loads(score_bytes)["records"])
    curve = json.loads(curve_bytes)
    releases = indexed(dict(zip(market["fields"], row, strict=True)) for row in market["rows"])
    closes = indexed(curve["observations"])
    result = build(scores, releases, closes, curve)
    workbook_hash = hashlib.sha256(args.usmpd.read_bytes()).hexdigest()
    if workbook_hash != market["sourceSha256"]["usmpd.xlsx"]:
        raise ValueError("Refresh the market extract with the same USMPD workbook")
    result["expectations"] = expectations(scores, args.usmpd, releases, closes)
    result["sourceSha256"] = {args.scores.name: hashlib.sha256(score_bytes).hexdigest(),
                              args.market.name: hashlib.sha256(market_bytes).hexdigest(),
                              args.curve.name: hashlib.sha256(curve_bytes).hexdigest(),
                              "usmpd.xlsx": market["sourceSha256"]["usmpd.xlsx"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("coverage", "groups", "all", "hold")}))


if __name__ == "__main__":
    main()
