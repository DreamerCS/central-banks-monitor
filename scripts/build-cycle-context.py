"""Build monthly US macro context from ALFRED vintages and the NBER chronology.

    python scripts/build-cycle-context.py --as-of 2026-11-20 --save-inputs /tmp/cycles
    python scripts/build-cycle-context.py --as-of 2026-11-20 --input-dir /tmp/cycles

The optional input directory contains four unmodified ALFRED series CSVs and the
NBER chronology page. USREC is used only to verify our calculation from NBER dates.
Requires lxml for the official chronology table.
"""

import argparse
import calendar
import csv
import hashlib
import io
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lxml import html


START = date(1948, 1, 1)
WARMUP = date(1947, 1, 1)
DATA = Path(__file__).resolve().parents[1] / "dist" / "data" / "cycle-context.json"
NBER = "https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions"
FRED = "https://fred.stlouisfed.org/series/"
ALFRED = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
BLS = "U.S. Bureau of Labor Statistics, via FRED / ALFRED"
BOARD = "Board of Governors of the Federal Reserve System, via FRED / ALFRED"
MONTH_NAMES = {name: i for i, name in enumerate(calendar.month_name) if name}
SERIES = {
    "unemployment": ("UNRATE", "Unemployment rate", "%", BLS,
                     "Seasonally adjusted U-3 unemployment rate for the civilian labor force aged 16 and over."),
    "cpi": ("CPIAUCSL", "Consumer price index", "1982–84 = 100", BLS,
            "Seasonally adjusted all-items index for urban consumers, U.S. city average."),
    "cpiYoY": ("CPIAUCSL", "Consumer price inflation", "% YoY", BLS,
               "Percentage change from the same month one year earlier in the seasonally adjusted all-items CPI index. BLS conventionally reports headline 12-month inflation from its unadjusted index."),
    "industrialProduction": ("INDPRO", "Industrial production", "2017 = 100", BOARD,
                             "Seasonally adjusted index of real output in manufacturing, mining and utilities."),
    "industrialProductionYoY": ("INDPRO", "Industrial production growth", "% YoY", BOARD,
                                "Percentage change from the same month one year earlier in the seasonally adjusted industrial production index."),
}


def get_input(name, url, args):
    if args.input_dir:
        return (args.input_dir / name).read_bytes()
    request = Request(url, headers={"User-Agent": "Central-Banks-Monitor/1.0 (historical indicators)"})
    with urlopen(request, timeout=90) as response:
        body = response.read()
    if args.save_inputs:
        args.save_inputs.mkdir(parents=True, exist_ok=True)
        (args.save_inputs / name).write_bytes(body)
    return body


def read_series(body, code, as_of, cutoff):
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    column = f"{code}_{as_of:%Y%m%d}"
    if reader.fieldnames != ["observation_date", column]:
        raise ValueError(f"Expected dated ALFRED column {column}, received {reader.fieldnames}")
    observations = {}
    for row in reader:
        day = date.fromisoformat(row["observation_date"])
        if day.day != 1 or not WARMUP <= day <= cutoff or day in observations:
            raise ValueError(f"Unexpected {code} observation date {day}")
        raw = row[column].strip()
        value = None if raw in ("", ".") else Decimal(raw)
        if value is not None:
            if not value.is_finite() or value < 0:
                raise ValueError(f"Invalid {code} value on {day}: {value}")
            if code == "USREC" and value not in (0, 1):
                raise ValueError(f"Unexpected USREC value on {day}: {value}")
            if code in ("CPIAUCSL", "INDPRO") and value == 0:
                raise ValueError(f"Unexpected zero {code} index on {day}")
        observations[day] = value
    if not any(v is not None for v in observations.values()):
        raise ValueError(f"No observations in {code}")
    return observations


def turning_month(cell):
    match = re.match(r"^([A-Za-z]+)\s+(\d{4})\b", cell)
    if match and match[1] in MONTH_NAMES:
        return date(int(match[2]), MONTH_NAMES[match[1]], 1)
    return None


def recession_intervals(body):
    doc = html.fromstring(body)
    tables = doc.xpath("//table[.//tr[contains(., 'Peak Month') and contains(., 'Trough Month')]]")
    if len(tables) != 1:
        raise ValueError("Could not identify NBER's monthly peak and trough table")
    intervals = []
    for row in tables[0].xpath(".//tr"):
        cells = [" ".join(c.text_content().split()) for c in row.xpath("./th|./td")]
        if len(cells) < 2 or not (peak := turning_month(cells[0])):
            continue
        trough = turning_month(cells[1])
        if (cells[1] and not trough) or (trough and trough <= peak):
            raise ValueError(f"Unexpected NBER turning points: {cells[:2]}")
        if intervals and (not intervals[-1][1] or peak <= intervals[-1][1]):
            raise ValueError("Overlapping or unsorted NBER cycles")
        intervals.append((peak, trough))
    if not intervals or intervals[0][0] >= START:
        raise ValueError("NBER chronology does not cover the postwar starting date")
    return intervals


def yoy(series, month):
    previous = series.get(month.replace(year=month.year - 1))
    current = series.get(month)
    if previous is None or current is None:
        return None
    return float(round(100 * (current / previous - 1), 3))


def period(day):
    return day.isoformat()[:7]


def build(args):
    cutoff = args.as_of.replace(day=1) - timedelta(days=1)
    if cutoff < START:
        raise ValueError("The requested snapshot predates January 1948")
    data = {}
    inputs = {}
    for code in ("UNRATE", "CPIAUCSL", "INDPRO", "USREC"):
        query = urlencode({"id": code, "cosd": WARMUP, "coed": cutoff, "vintage_date": args.as_of})
        url = f"{ALFRED}?{query}"
        body = get_input(code + ".csv", url, args)
        data[code] = read_series(body, code, args.as_of, cutoff)
        inputs[code] = {"url": url, "sha256": hashlib.sha256(body).hexdigest()}

    intervals = recession_intervals(get_input("nber-cycles.html", NBER, args))
    last = max(day for series in data.values() for day, value in series.items() if value is not None)
    rows = []
    month = START
    while month <= last:
        reference = data["USREC"].get(month)
        phase = None
        if reference is not None:
            phase = int(any(peak < month and (end is None or month <= end) for peak, end in intervals))
            if phase != reference:
                raise ValueError(f"NBER dates and the ALFRED validation vintage disagree for {month}. "
                                 "Use the chronology captured with this vintage.")
        row = {"month": period(month)}
        for key, (code, *_) in SERIES.items():
            level = data[code].get(month)
            if key.endswith("YoY"):
                row[key] = yoy(data[code], month)
            else:
                row[key] = float(level) if level is not None else None
        row["recession"] = phase
        rows.append(row)
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)

    metadata = {}
    for key, (code, label, unit, source, definition) in SERIES.items():
        metadata[key] = {"label": label, "unit": unit, "source": source, "sourceUrl": FRED + code,
                         "seriesId": code, "definition": definition}
    metadata["recession"] = {
        "label": "NBER recession", "unit": "0 or 1", "source": "National Bureau of Economic Research",
        "sourceUrl": NBER, "seriesId": "NBER peak/trough chronology", "validationUrl": FRED + "USREC",
        "definition": "Computed from NBER turning-point dates. Months after a peak through the trough are 1. Other classified months are 0. Dating is retrospective and recent months can be reclassified."
    }
    for key, info in metadata.items():
        present = [row for row in rows if row[key] is not None]
        info["firstMonth"] = present[0]["month"] if present else None
        info["lastMonth"] = present[-1]["month"] if present else None
        info["lastValue"] = present[-1][key] if present else None
        info["observations"] = len(present)
    return {
        "schemaVersion": 1, "geography": "United States", "frequency": "monthly", "asOf": args.as_of.isoformat(),
        "firstMonth": rows[0]["month"], "lastMonth": rows[-1]["month"],
        "vintage": "Levels use one ALFRED vintage for the whole history. Earlier observations include revisions known by the vintage date. Dates label observation months, not publication dates. Only closed calendar months are shown. Missing levels or comparison months yield null.",
        "series": metadata, "inputs": inputs,
        "sourceNotes": {
            "blsReuse": "https://www.bls.gov/bls/linksite.htm",
            "boardReuse": FRED + "INDPRO",
            "recessionAttribution": "Own monthly calculation from NBER business-cycle peak and trough dates, checked against the Federal Reserve Bank of St. Louis USREC vintage.",
            "october2025Gap": "https://www.bls.gov/bls/bls-handling-of-missing-data.htm"
        },
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--output", type=Path, default=DATA)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--input-dir", type=Path, help="Use previously captured source files")
    group.add_argument("--save-inputs", type=Path, help="Keep source files for an exact offline rebuild")
    args = parser.parse_args()
    if args.as_of > datetime.now(timezone.utc).date():
        parser.error("The requested vintage must already exist")
    payload = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=args.output.parent, encoding="utf-8", delete=False) as handle:
        tmp = Path(handle.name)
        try:
            json.dump(payload, handle, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    tmp.chmod(0o644)
    os.replace(tmp, args.output)
    print(f"{len(payload['rows'])} months, {payload['firstMonth']} to {payload['lastMonth']}: {args.output}")


if __name__ == "__main__":
    main()
