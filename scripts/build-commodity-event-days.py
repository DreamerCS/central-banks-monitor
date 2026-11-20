"""Rebuild daily spot oil context for the event explorer from EIA's public workbooks.
Pass --input-dir with rwtc.xls and rbrte.xls to use downloaded source files.
"""
import argparse
import io
import json
import math
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

import xlrd

ROOT = Path(__file__).resolve().parents[1]
SERIES = [
    ("rbrte", "Brent", "Europe Brent Spot Price FOB"),
    ("rwtc", "WTI", "Cushing, OK WTI Spot Price FOB"),
]


def load_prices(key, label, expected, folder, through):
    url = f"https://www.eia.gov/dnav/pet/hist_xls/{key.upper()}d.xls"
    if folder:
        raw = (folder / (key + ".xls")).read_bytes()
    else:
        with urlopen(Request(url, headers={"User-Agent": "CBI research data"}), timeout=60) as response:
            raw = response.read()
    book = xlrd.open_workbook(file_contents=raw)
    sheet = book.sheet_by_name("Data 1")
    if sheet.cell_value(1, 1) != key.upper() or sheet.cell_value(2, 1) != expected + " (Dollars per Barrel)":
        raise ValueError(f"Unexpected EIA series or units for {key}")
    data = []
    for i in range(3, sheet.nrows):
        serial, price = sheet.row_values(i)[:2]
        if not isinstance(serial, (int, float)) or not isinstance(price, (float, int)):
            continue
        day = xlrd.xldate_as_datetime(serial, book.datemode).date().isoformat()
        if day < "1999-12-01" or day > through:
            continue
        if not math.isfinite(price) or (data and day <= data[-1][0]):
            raise ValueError(f"Duplicate or invalid observation on {day}")
        data.append([day, price])
    if not data:
        raise ValueError("No matching observations")
    return {"label": label, "series": key.upper(), "url": f"https://www.eia.gov/dnav/pet/hist/{key}d.htm", "rows": data}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--through", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output", type=Path, default=ROOT / "dist/data/commodity-event-days.json")
    args = parser.parse_args()
    assets = [load_prices(*s, args.input_dir, args.through.isoformat()) for s in SERIES]
    result = {"unit": "USD per barrel", "assets": assets}
    args.output.write_text(json.dumps(result, separators=(",", ":")) + "\n")
