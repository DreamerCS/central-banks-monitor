"""Build annual UK market results from the Bank of England's UKMPD workbook.

Download the workbook at WORKBOOK_URL and run
python scripts/build-uk-market-years.py UKMPD.xlsx
Requires openpyxl. The published site serves the resulting JSON without network dependencies.
"""
import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from statistics import median

from openpyxl import load_workbook


WORKBOOK_URL = "https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2023/measuring-monetary-policy-in-the-uk-the-ukmpesd.xlsx"
LANDING = "https://www.bankofengland.co.uk/working-paper/2023/measuring-monetary-policy-in-the-uk-ukmpd"
OUTPUT = Path(__file__).resolve().parents[1] / "dist/data/uk-market-years.json"
FIRST_YEAR = 2000
# Column names are from 'surprises'. The workbook's descriptions use variant RIC spellings.
ASSETS = {
    "gilt2": ("GB2YT=RR", "2-year UK benchmark gilt yield", "bp", 100),
    "ois2": ("GBP2YOIS=", "2-year sterling overnight indexed swap rate", "bp", 100),
    "sterling": ("GBP=", "GBP/USD spot exchange rate", "%", 1),
    "ftse": (".FTSE", "FTSE 100 cash index", "%", 1),
}
WINDOWS = ("announcement", "conference")


def summarize(events, asset):
    quotes = [(stamp.date().isoformat(), moves[asset]) for stamp, moves in events if asset in moves]
    if not quotes:
        return {"quoted": 0, "medianAbs": None, "peaks": []}
    sizes = [abs(value) for _, value in quotes]
    largest = max(sizes)
    return {
        "quoted": len(quotes),
        "medianAbs": round(median(sizes), 7),
        "peaks": [{"date": day, "value": value} for day, value in quotes if abs(value) == largest],
    }


def build(path):
    book = load_workbook(path, read_only=True, data_only=True)
    groups = defaultdict(list)
    keys = set()
    try:
        rows = iter(book["surprises"].values)
        header = next(rows)
        required = {"Datetime", "isMPC", *(spec[0] for spec in ASSETS.values())}
        if not required.issubset(header):
            raise ValueError(f"Missing source columns: {sorted(required.difference(header))}")
        for raw in rows:
            row = dict(zip(header, raw))
            stamp = row["Datetime"]
            if stamp is None:
                continue
            if not isinstance(stamp, datetime) or not isinstance(row["isMPC"], bool):
                raise ValueError(f"Unexpected UKMPD event identifier: {stamp}, {row['isMPC']}")
            if stamp.year < FIRST_YEAR:
                continue
            window = "announcement" if row["isMPC"] else "conference"
            key = (stamp, window)
            if key in keys:
                raise ValueError(f"Duplicate UKMPD event: {key}")
            keys.add(key)
            quotes = {}
            for asset, (column, _, _, factor) in ASSETS.items():
                value = row[column]
                if value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                    raise ValueError(f"Unexpected {column} quote at {stamp}: {value}")
                # Normalize floating-point residues before identifying exact ties.
                quotes[asset] = round(value * factor, 7) or 0
            groups[(stamp.year, window)].append((stamp, quotes))
    finally:
        book.close()
    if not keys:
        raise ValueError("No UKMPD events since 2000")

    end = max(stamp for stamp, _ in keys)
    years = {}
    for year in range(FIRST_YEAR, end.year + 1):
        windows = {}
        for window in WINDOWS:
            events = sorted(groups[(year, window)])
            windows[window] = {
                "recorded": len(events),
                "series": {asset: summarize(events, asset) for asset in ASSETS},
            }
        years[year] = windows
    return {
        "source": {"page": LANDING, "workbook": WORKBOOK_URL, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
        "through": end.date().isoformat(),
        "assets": {key: {"label": label, "unit": unit} for key, (_, label, unit, _) in ASSETS.items()},
        "years": years,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    options = parser.parse_args()
    options.output.write_text(json.dumps(build(options.workbook), ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
