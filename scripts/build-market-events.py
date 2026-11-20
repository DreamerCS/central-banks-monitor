"""Extract published intraday changes, preserving missing cells and each source window.

Usage: python scripts/build-market-events.py USMPD.xlsx EA-EMPD.xlsx
Downloads: https://www.frbsf.org/wp-content/uploads/USMPD.xlsx
           https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx
Requires openpyxl. The two source workbooks include the original definitions.
"""

import json
import math
import sys
from pathlib import Path

from openpyxl import load_workbook


OUTPUT = Path(__file__).resolve().parents[1] / "dist/data/market-events.json"
US = {
    "id": "fed",
    "name": "Federal Reserve",
    "source": "https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/",
    "sourceLabel": "San Francisco Fed · USMPD",
    "windows": {
        "statement": "10 min before to 20 min after the statement.",
        "conference": "10 min before to 60 min after the press conference begins.",
        "meeting": "10 min before the statement to 60 min after the press conference begins. On dates without a conference, the statement window applies.",
    },
}
EA = {
    "id": "ecb",
    "name": "European Central Bank",
    "source": "https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx",
    "sourceLabel": "ECB · EA-EMPD",
    "windows": {
        "statement": "Median quotes at 13:25–13:35 vs 14:00–14:10 Frankfurt time. From July 2022, 13:55–14:05 vs 14:30–14:40.",
        "conference": "Median quotes at 14:15–14:25 vs 15:40–15:50 Frankfurt time. From July 2022, 14:30–14:40 vs 15:55–16:05.",
        "meeting": "Median quotes at 13:25–13:35 vs 15:40–15:50 Frankfurt time. From July 2022, 13:55–14:05 vs 15:55–16:05.",
    },
}
# Field names match those in the original sheets. Slope is computed before rounding.
FED_FIELDS = [
    ("UST2Y", "US 2Y Treasury", "Rates"), ("UST10Y", "US 10Y Treasury", "Rates"),
    ("SLOPE", "US 10Y−2Y slope", "Rates"), ("MP1", "Current meeting surprise", "Rates"),
    ("MP2", "Next meeting repricing", "Rates"), ("OIS1Y", "USD 1Y OIS", "Rates"),
    ("EURUSD", "EUR/USD", "FX"), ("USDJPY", "USD/JPY", "FX"),
    ("DXY", "US dollar index", "FX"), ("SP500", "S&P 500", "Equities"),
]
ECB_FIELDS = [
    ("DE2Y", "German 2Y yield", "Rates"), ("DE10Y", "German 10Y yield", "Rates"),
    ("SLOPE", "German 10Y−2Y slope", "Rates"), ("OIS_1M", "EUR 1M OIS", "Rates"),
    ("OIS_1Y", "EUR 1Y OIS", "Rates"), ("EURUSD", "EUR/USD", "FX"),
    ("EURGBP", "EUR/GBP", "FX"), ("EURJPY", "EUR/JPY", "FX"),
    ("STOXX50", "Euro Stoxx 50", "Equities"), ("SX7E", "Euro Stoxx Banks", "Equities"),
]


def policy_rows(workbook, sheet_names):
    # EA-EMPD records all three windows in one sheet alongside non-meeting speeches.
    if not sheet_names:
        rows = workbook["EA-EMPD"].values
        headers = next(rows)
        periods = {"GC_PR": "statement", "GC_PC": "conference", "GC_ME": "meeting"}
        for row in rows:
            quotes = dict(zip(headers, row))
            period = periods.get(quotes["Event_type"])
            if period:
                quotes["STOXX50"] = quotes["STOXX50E"]
                yield period, quotes["Date_time"], quotes
        return
    for period, sheet in sheet_names.items():
        rows = workbook[sheet].values
        headers = next(rows)
        for row in rows:
            if row[0] is not None:
                yield period, row[0], dict(zip(headers, row))


def extract(path, metadata, fields, sheet_names, yield_columns, rate_multiplier):
    workbook = load_workbook(path, data_only=True, read_only=True)
    assets = [{"id": key, "label": label, "class": group, "unit": "bp" if group == "Rates" else "%"}
              for key, label, group in fields]
    dates = {}
    for period, day, quotes in policy_rows(workbook, sheet_names):
        if not 2000 <= day.year <= 2026:
            continue
        short, long = [quotes[column] for column in yield_columns]
        quotes["SLOPE"] = None if None in (short, long) else long - short
        values = {}
        for key, _, group in fields:
            value = quotes[key]
            if isinstance(value, (int, float)) and math.isfinite(value):
                factor = rate_multiplier if group == "Rates" else 1
                values[key] = round(value * factor, 5) or 0
        if values:
            windows = dates.setdefault(day.date().isoformat(), {})
            if period in windows:
                raise ValueError(f"{period}: duplicate event {day}")
            windows[period] = values
    workbook.close()
    return {**metadata, "assets": assets, "events": [{"date": day, "windows": dates[day]} for day in sorted(dates)]}


if __name__ == "__main__":
    fed_path, ecb_path = sys.argv[1:]
    banks = [
        extract(fed_path, US, FED_FIELDS, {"statement": "Statements", "conference": "Press Conferences", "meeting": "Monetary Events"}, ("UST2Y", "UST10Y"), 100),
        extract(ecb_path, EA, ECB_FIELDS, None, ("DE2Y", "DE10Y"), 1),
    ]
    OUTPUT.write_text(json.dumps({"banks": banks}, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
    for bank in banks:
        events = bank["events"]
        print(bank["name"], len(events), events[0]["date"], events[-1]["date"])
