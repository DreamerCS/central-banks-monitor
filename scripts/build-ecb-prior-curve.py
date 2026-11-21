"""Join ECB decisions to the last pre-decision AAA sovereign spot curves.

Run from the site checkout with Python 3. For the exact published historical span use
--through with the output coverage.lastFixing date. A local --quotes directory with
2y.csv, 10y.csv and spread.csv can be used to reproduce this without network access.
"""
import argparse
import csv
import io
import json
from bisect import bisect_left
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "B.U2.EUR.4F.G_N_A.SV_C_YM."
PORTAL = "https://data.ecb.europa.eu/data/datasets/YC/YC."
API = "https://data-api.ecb.europa.eu/service/data/YC/"
METHOD = "https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_area_yield_curves/html/index.en.html"
SERIES = {"2y": "SR_2Y", "10y": "SR_10Y", "spread": "SRS_10Y_2Y"}


def read_series(name, source_dir, through):
    key = BASE + SERIES[name]
    if source_dir:
        raw = (source_dir / (name + ".csv")).read_bytes()
    else:
        params = {"format": "csvdata", "detail": "dataonly", "startPeriod": "2000-01-01"}
        if through:
            params["endPeriod"] = through
        url = API + key + "?" + urlencode(params)
        request = Request(url, headers={"User-Agent": "The Policy Tape research"})
        with urlopen(request, timeout=60) as response:
            raw = response.read()
    series = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        if row["KEY"] != "YC." + key:
            raise ValueError("Unexpected ECB series in " + name)
        day = row["TIME_PERIOD"]
        if not row["OBS_VALUE"] or through and day > through:
            continue
        if day in series:
            raise ValueError("Duplicate ECB fixing on " + day)
        value = Decimal(row["OBS_VALUE"])
        if not value.is_finite():
            raise ValueError("Non-finite value in " + name)
        series[day] = value
    if not series:
        raise ValueError("No observations in " + name)
    return series


def rounded(value, decimals):
    return float(round(value, decimals))


def day_gap(start, end):
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def build(meetings, quotes):
    short, long, official_spread = (quotes[name] for name in SERIES)
    days = sorted(short.keys() & long.keys())
    if not days:
        raise ValueError("No matched two-year and ten-year observations")
    slopes = {day: (long[day] - short[day]) * 100 for day in days}
    for day in days:
        if day not in official_spread or abs(slopes[day] - official_spread[day] * 100) > Decimal("0.00001"):
            raise ValueError("Derived curve slope does not match the ECB spread on " + day)

    reports = []
    for meeting in meetings:
        day = meeting["date"]
        index = bisect_left(days, day)
        row = dict(date=day, status="before-series", priorStart=None, priorEnd=None,
                   prior2yPct=None, prior10yPct=None, priorSlopeBp=None,
                   change2yBp=None, change10yBp=None, changeSlopeBp=None,
                   calendarGapDays=None, changeCalendarDays=None)
        reports.append(row)
        if not index:
            continue
        end = days[index - 1]
        gap = day_gap(end, day)
        row.update(priorEnd=end, calendarGapDays=gap, status="stale")
        if gap > 7:
            continue
        row.update(prior2yPct=rounded(short[end], 6), prior10yPct=rounded(long[end], 6),
                   priorSlopeBp=rounded(slopes[end], 4), status="insufficient-history")
        if index < 6:
            continue
        start = days[index - 6]
        row.update(priorStart=start, status="observed", changeCalendarDays=day_gap(start, end),
                   change2yBp=rounded(100 * (short[end] - short[start]), 4),
                   change10yBp=rounded(100 * (long[end] - long[start]), 4),
                   changeSlopeBp=rounded(slopes[end] - slopes[start], 4))

    if len({r["date"] for r in reports}) != len(reports):
        raise ValueError("Duplicate decisions in the ECB meeting catalogue")
    observed = [r["date"] for r in reports if r["status"] == "observed"]
    return {
        "title": "AAA euro-area sovereign yield curve before ECB decisions",
        "sources": {"curve": METHOD, **{name: PORTAL + BASE + series for name, series in SERIES.items()}},
        "coverage": {"firstFixing": days[0], "lastFixing": days[-1], "pairedFixings": len(days),
                     "decisions": len(reports), "observed": len(observed),
                     "firstObservedDecision": min(observed, default=None), "lastObservedDecision": max(observed, default=None)},
        "method": [
            "The ECB fits continuously compounded zero-coupon spot rates to nominal euro-area central government bonds rated AAA. Membership and the eligible issuer set can change with time.",
            "Two-year and ten-year spot rates are quoted in percent per annum. The slope is the ten-year rate minus the two-year rate, in basis points, cross-checked against the ECB’s published 10Y–2Y spread.",
            "The reference date is the latest paired fixing strictly before the decision. The change runs from the sixth to the last prior paired fixing, five observed intervals. TARGET closures and other missing quotations remain calendar gaps. A gap exceeding seven calendar days is marked stale.",
            "These sovereign yields combine expected short rates and bond risk premia across maturities. A meeting-specific expected move requires a separate source such as meeting-dated OIS."
        ],
        "records": reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meetings", type=Path, default=ROOT / "dist/data/ecb-stance-history.json")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/data/ecb-prior-curve.json")
    parser.add_argument("--through", help="Include fixings through this ISO date")
    parser.add_argument("--quotes", type=Path, help="Read previously downloaded ECB csvdata extracts")
    args = parser.parse_args()
    if args.through:
        date.fromisoformat(args.through)
    meetings = json.loads(args.meetings.read_text())["records"]
    quotes = {name: read_series(name, args.quotes, args.through) for name in SERIES}
    result = build(meetings, quotes)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
