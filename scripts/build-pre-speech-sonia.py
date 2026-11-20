"""Daily sterling OIS curves before selected Bank of England speeches.

Rebuild from the checked-in observed market inputs with Python's standard library:
  python scripts/build-pre-speech-sonia.py
Refresh those inputs from the live official ZIPs (requires openpyxl):
  python scripts/build-pre-speech-sonia.py --refresh
Or supply both named downloads in a directory and write alternative outputs:
  python scripts/build-pre-speech-sonia.py --source-dir DIR --grid /tmp/grid.csv --output /tmp/events.json
"""
import argparse
from bisect import bisect_left
import calendar
import csv
from datetime import date, datetime
import io
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

DATA = Path(__file__).resolve().parents[1] / "dist/data"
BANK = "https://www.bankofengland.co.uk"
CURVES = BANK + "/statistics/yield-curves"
MEDIA = BANK + "/-/media/boe/files/statistics/yield-curves/"
ARCHIVE = "oisddata.zip"
CURRENT = "latest-yield-curve-data.zip"
HORIZONS = (3, 6, 12)
# An endpoint one/two valid curve sessions before the speech, and 1/5/20 observations earlier.
LOOKBACKS = (1, 2, 3, 6, 7, 21, 22)
TENORS = tuple(range(1, 16))
CASES = [
    ("2026-11-18", "Andrew Bailey", "The UK’s regional growth: unlocking the economy’s full potential",
     "2026/november/andrew-bailey-speech-at-the-annual-institute-of-economic-development-conference-london",
     "Bailey explained the November increase to 4% and why the duration of the energy shock mattered for subsequent decisions.", "2026-11-18-a584e8b634"),
    ("2026-11-10", "Clare Lombardelli", "The low-gear labour market",
     "2026/november/clare-lombardelli-speech-at-the-bank-watchers-conference",
     "Lombardelli saw a conditional case for another near-term increase, despite weaker hiring. She discussed whether that weakness would ease wage pressure.", "2026-11-10-5537220d00"),
    ("2026-06-02", "Megan Greene", "Here we go again? Assessing the inflation risks of the recent energy shock",
     "2026/june/megan-greene-speech-at-university-of-derby-business-school",
     "Greene examined how the energy shock could pass into wages and prices, and what the evidence would mean for the policy response.", None),
    ("2024-08-23", "Andrew Bailey", "Reflecting on recent times",
     "2024/august/andrew-bailey-speech-federal-reserve-bank-of-kansas-annual-jackson-hole-economic-policy-symposium",
     "At Jackson Hole, Bailey judged inflation less persistent than previously feared, while arguing that policy still needed to remain restrictive.", None),
    ("2022-10-12", "Huw Pill", "Monetary policy: an anchor in challenging times",
     "2022/october/huw-pill-in-conversation-with-scdi",
     "Pill expected a significant policy response at the November meeting and distinguished that judgement from the Bank’s intervention in gilt markets.", None),
    ("2021-01-11", "Silvana Tenreyro", "Let’s talk about negative interest rates",
     "2021/january/silvana-tenreyro-lets-talk-about-negative-interest-rates",
     "Tenreyro examined negative policy rates as an option if further stimulus became necessary.", None),
    ("2013-08-28", "Mark Carney", "Speech and press conference at the East Midlands Conference Centre",
     "2013/mark-carney-speech-and-press-conference-east-midlands-conference-centre",
     "Carney explained that reaching the unemployment threshold would prompt a reassessment. It would not trigger an automatic increase in Bank Rate.", None),
]
CONTEXT = [
    ("2013-08-14", "The MPC published minutes setting out its conditional 7% unemployment threshold.", "/minutes/2013/monetary-policy-committee-august-2013"),
    ("2022-09-22", "The MPC raised Bank Rate by 50 basis points to 2.25%.", "/monetary-policy-summary-and-minutes/2022/september-2022"),
    ("2024-08-01", "The MPC cut Bank Rate by 25 basis points to 5%.", "/monetary-policy-summary-and-minutes/2024/august-2024"),
    ("2026-11-05", "The MPC raised Bank Rate by 25 basis points to 4%.", "/monetary-policy-summary-and-minutes/2026/november-2026"),
]


def load_zip(name, folder):
    if folder:
        return (folder / name).read_bytes()
    request = Request(MEDIA + name, headers={"User-Agent": "Mozilla/5.0 (research data download)"})
    with urlopen(request, timeout=90) as response:
        return response.read()


def parse_workbook(body):
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        sheet = next((key for key in ("1. fwds, short end", "1. fwd curve") if key in book.sheetnames), None)
        if not sheet:
            raise ValueError("No recognised OIS forward worksheet")
        rows = book[sheet].values
        head = [next(rows) for _ in range(4)]
        if "instantaneous OIS forward curve" not in str(head[0][1]) or head[3][0] != "years:":
            raise ValueError("Expected Bank of England instantaneous forward grid")
        for m in TENORS:
            if abs(head[2][m] - m) > 0.0001 or abs(head[3][m] - m / 12) > 1e-9:
                raise ValueError(f"Unexpected tenor in column {m + 1}")
        curves = {}
        for row in rows:
            if not isinstance(row[0], datetime):
                continue
            usable = [v for v in row[1:] if isinstance(v, (float, int)) and math.isfinite(v)]
            if usable:
                curves[row[0].date()] = tuple(v if isinstance(v, (float, int)) and math.isfinite(v) else None
                                               for v in row[1:len(TENORS) + 1])
        return curves
    finally:
        book.close()


def source_grid(folder):
    curves = {}
    for filename in (ARCHIVE, CURRENT):
        with ZipFile(io.BytesIO(load_zip(filename, folder))) as archive:
            names = [n for n in archive.namelist() if n.startswith("OIS daily data") and n.endswith(".xlsx")]
            if not names:
                raise ValueError(f"No OIS member in {filename}")
            for name in names:
                for day, values in parse_workbook(archive.read(name)).items():
                    # The historical archive is the settled copy where releases overlap.
                    curves.setdefault(day, values)
    days = sorted(curves)
    chosen = set()
    for stamp, *_ in CASES:
        prior = prior_sessions(days, date.fromisoformat(stamp))
        chosen.update(prior)
    return {day: curves[day] for day in sorted(chosen)}


def prior_sessions(days, event):
    end = bisect_left(days, event)
    prior = days[max(0, end - max(LOOKBACKS)):end]
    if len(prior) < max(LOOKBACKS) or max((b - a).days for a, b in zip(prior, prior[1:] + [event])) > 7:
        raise ValueError(f"Incomplete run of preceding OIS observations: {event}")
    return prior


def write_grid(path, curves):
    with path.open("w", newline="") as dest:
        writer = csv.writer(dest, lineterminator="\n")
        writer.writerow(["quotation_date", *(f"fwd_{m}m_pct" for m in TENORS)])
        for day, values in sorted(curves.items()):
            writer.writerow([day, *values])


def read_grid(path):
    result = {}
    with path.open(newline="") as source:
        rows = csv.reader(source)
        if next(rows) != ["quotation_date", *(f"fwd_{m}m_pct" for m in TENORS)]:
            raise ValueError("Unexpected forward grid header")
        for stamp, *cells in rows:
            day = date.fromisoformat(stamp)
            values = tuple(None if c == "" else float(c) for c in cells)
            if day in result or len(values) != len(TENORS) or any(v is not None and not math.isfinite(v) for v in values):
                raise ValueError(f"Invalid curve observation: {stamp}")
            result[day] = values
    return result


def add_months(day, n):
    year, month0 = divmod(day.year * 12 + day.month - 1 + n, 12)
    month = month0 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def interpolate(values, quote, target):
    # The source annual fraction is Actual/365; source knots are 1/12 years apart.
    month = 12 * (target - quote).days / 365
    low, high = math.floor(month), math.ceil(month)
    if low < TENORS[0] or high > TENORS[-1]:
        return None
    left, right = values[low - 1], values[high - 1]
    if left is None or right is None:
        return None
    return round(left + (month - low) * (right - left), 8)


def build(curves):
    days = sorted(curves)
    events = []
    for stamp, name, title, path, abstract, note in CASES:
        speech = date.fromisoformat(stamp)
        sessions = prior_sessions(days, speech)
        targets = [add_months(speech, n) for n in HORIZONS]
        observations = []
        for back in LOOKBACKS:
            quote = sessions[-back]
            observations.append({"sessionsBefore": back, "date": str(quote),
                                 "rates": [interpolate(curves[quote], quote, t) for t in targets]})
        mentions = [{"date": d, "text": desc, "url": BANK + link} for d, desc, link in CONTEXT
                    if str(sessions[0]) < d < stamp]
        events.append({"date": stamp, "speaker": name, "title": title, "url": BANK + "/speech/" + path,
                       "context": abstract, "note": note, "targets": list(map(str, targets)),
                       "observations": observations, "policyDates": mentions})
    return {"curveSource": CURVES, "dailyArchive": MEDIA + ARCHIVE, "latestMonth": MEDIA + CURRENT,
            "months": HORIZONS, "events": events}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--refresh", action="store_true")
    inputs.add_argument("--source-dir", type=Path)
    parser.add_argument("--grid", type=Path, default=DATA / "pre-speech-sonia-grid.csv")
    parser.add_argument("--output", type=Path, default=DATA / "pre-speech-sonia.json")
    args = parser.parse_args()
    if args.refresh or args.source_dir:
        curves = source_grid(args.source_dir)
        write_grid(args.grid, curves)
    else:
        curves = read_grid(args.grid)
    args.output.write_text(json.dumps(build(curves), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
