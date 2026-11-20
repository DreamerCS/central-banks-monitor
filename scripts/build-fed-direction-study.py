"""Join pre-statement 2Y par yield changes to intraday USMPD Treasury changes.

Run after refreshing the site's pre-event Treasury history:
    python scripts/build-fed-direction-study.py /path/to/USMPD.xlsx
Requires openpyxl. The workbook is https://www.frbsf.org/wp-content/uploads/USMPD.xlsx.
"""
import argparse
import bisect
import csv
import hashlib
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import median

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dist/data"
ERAS = [("all", 2000, None), ("2000-07", 2000, 2007), ("2008-15", 2008, 2015),
        ("2016-19", 2016, 2019), ("2020-on", 2020, None)]
SIZES = ["all", "small", "large"]
RULES = ["raw", "one-bp"]
FIELD_NAMES = ["date", "start", "end", "start2yPct", "end2yPct", "priorBp",
               "statementBp", "scheduled", "releaseTimeET"]
CSV_NAMES = ["statement_date", "fifth_prior_quote", "last_prior_quote", "start_2y_pct",
             "end_2y_pct", "prior_change_bp", "statement_change_bp", "scheduled", "release_time_et"]


def sign(x):
    return (x > 0) - (x < 0)


def summary(rows):
    directions = Counter((sign(r["priorBp"]), sign(r["statementBp"])) for r in rows)
    active = [r for r in rows if r["priorBp"] != 0 and r["statementBp"] != 0]
    aligned = [sign(r["priorBp"]) * r["statementBp"] for r in active]
    same = sum(v > 0 for v in aligned)
    scheduled = [r for r in active if r["scheduled"]]
    omitted_years = []
    for year in sorted({r["date"][:4] for r in active}):
        other = [r for r in active if r["date"][:4] != year]
        if other:
            omitted_years.append(100 * sum(r["priorBp"] * r["statementBp"] > 0 for r in other) / len(other))
    matrix = [[directions[p, a] for a in (1, -1, 0)] for p in (1, -1, 0)]
    # For a descriptive benchmark, keep the yearly margins of both signs fixed.
    strata = {}
    for r in active:
        year = r["date"][:4]
        counts = strata.setdefault(year, [0, 0, 0])
        counts[0] += 1
        counts[1] += r["priorBp"] > 0
        counts[2] += r["statementBp"] > 0
    expected = sum((up * after_up + (n - up) * (n - after_up)) / n
                   for n, up, after_up in strata.values())
    return {"n": len(rows), "same": same, "opposite": len(active) - same,
            "ties": len(rows) - len(active), "matrix": matrix,
            "medianAlignedBp": round(median(aligned), 5) if aligned else None,
            "samePct": round(100 * same / len(active), 2) if active else None,
            "yearMarginBenchmarkPct": round(100 * expected / len(active), 2) if active else None,
            "omitYearRangePct": [round(min(omitted_years), 2), round(max(omitted_years), 2)] if omitted_years else None,
            "scheduledDirectional": len(scheduled),
            "scheduledSame": sum(r["priorBp"] * r["statementBp"] > 0 for r in scheduled)}


def select_rows(rows, start, end, size, rule):
    result = []
    for row in rows:
        year = int(row["date"][:4])
        if year < start or (end is not None and year > end):
            continue
        prior, announcement = abs(row["priorBp"]), abs(row["statementBp"])
        if (size == "small" and prior >= 10) or (size == "large" and prior < 10):
            continue
        if rule == "one-bp" and (prior < 1 or announcement < 1):
            continue
        result.append(row)
    return result


def pre_window(quotes, dates, event_date, through):
    index = bisect.bisect_left(dates, event_date)
    if index < 5 or event_date > through:
        return None
    first, last = quotes[index - 5], quotes[index - 1]
    # Treasury publishes these yields to hundredths of a percentage point.
    delta = (Decimal(str(last["y2"])) - Decimal(str(first["y2"]))) * 100
    if delta != delta.to_integral_value():
        raise ValueError("Unexpected pre-event yield precision")
    return {"start": first["date"], "end": last["date"], "start2yPct": first["y2"],
            "end2yPct": last["y2"], "priorBp": int(delta)}


def build(workbook_path, treasury_path, speeches_path, until):
    curve = json.loads(treasury_path.read_text())
    quotes = [row for row in curve["observations"] if isinstance(row.get("y2"), (int, float)) and isinstance(row.get("y10"), (int, float))]
    dates = [row["date"] for row in quotes]
    if dates != sorted(set(dates)) or not dates:
        raise ValueError("Treasury dates must be unique and in ascending order")
    through = max(filter(None, [dates[-1], curve.get("asOfDate"), curve.get("eventsThrough")]))
    book = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        source = book["Statements"].values
        headers = next(source)
        rows, missing, seen = [], [], set()
        for raw in source:
            r = dict(zip(headers, raw))
            if not r["Date"] or not (2000 <= r["Date"].year and r["Date"].date() <= until):
                continue
            day = r["Date"].date().isoformat()
            if day in seen:
                raise ValueError("Duplicate USMPD statement date: " + day)
            seen.add(day)
            pre = pre_window(quotes, dates, day, through)
            if not pre or not isinstance(r["UST2Y"], (int, float)):
                missing.append({"date":day, "reason":"prior quotes" if not pre else "statement quote"})
                continue
            if r["Unscheduled"] not in (0, 1):
                raise ValueError("Unknown statement schedule flag: " + day)
            # Match the site's market-event extractor: percentage points to bp,
            # remove machine-level noise in Excel without attenuating genuine 0.01 bp moves.
            change = round(100 * r["UST2Y"], 5) or 0
            rows.append({"date":day, **pre, "statementBp":change,
                         "scheduled":r["Unscheduled"] == 0,
                         "releaseTimeET":r["date_time"].strftime("%H:%M")})
    finally:
        book.close()
    rows.sort(key=lambda r:r["date"])
    if not rows:
        raise ValueError("No matched statement events")
    analysis = {}
    for era, start, stop in ERAS:
        for size in SIZES:
            for rule in RULES:
                key = "/".join([era,size,rule])
                analysis[key] = summary(select_rows(rows,start,stop,size,rule))
    cases = []
    speeches = json.loads(speeches_path.read_text())
    for item in speeches["events"]:
        for obs in item["observations"]:
            if obs["instrument"] != "2-year Treasury yield" or obs["unit"] != "bp":
                continue
            if item["date"] > until.isoformat():
                continue
            window = pre_window(quotes,dates,item["date"],through)
            if window:
                cases.append({"date":item["date"], "title":item["title"], "speaker":item["speaker"], **window,
                              "speechBp":obs["value"], "window":obs["window"],
                              "study":speeches["studies"][obs["study"]]["url"], "locator":obs["locator"],
                              "eventUrl":item["eventUrl"]})
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [workbook_path,treasury_path,speeches_path]}
    result = {"version":1, "calendarDates":len(seen), "missing":missing,
              "first":rows[0]["date"], "last":rows[-1]["date"], "sourceSha256":hashes,
              "fields":FIELD_NAMES, "rows":[[r[c] for c in FIELD_NAMES] for r in rows],
              "groups":analysis, "speechCases":cases}
    return result, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("usmpd", type=Path)
    parser.add_argument("--treasury", type=Path, default=DATA / "pre-event-curve.json")
    parser.add_argument("--speeches", type=Path, default=DATA / "speech-intraday.json")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output-dir", type=Path, default=DATA)
    args = parser.parse_args()
    result, rows = build(args.usmpd, args.treasury, args.speeches, args.as_of)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir/"fed-direction-study.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",",":"))+"\n")
    with (args.output_dir/"fed-direction-study.csv").open("w", newline="") as handle:
        writer = csv.writer(handle,lineterminator="\n")
        writer.writerow(CSV_NAMES)
        writer.writerows([[r[k] for k in FIELD_NAMES] for r in rows])
    print(f"{len(rows)}/{result['calendarDates']} statement dates, {len(result['groups'])} groups, {len(result['speechCases'])} separate speech case(s).")


if __name__ == "__main__":
    main()
