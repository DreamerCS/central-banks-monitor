"""Build monthly and regime summaries from the Fed's 1971–74 New York noon quotes.

Run with no arguments to fetch the two official H.10 ASCII releases. To reproduce
offline, pass --gbp PATH --dem PATH. --output defaults to dist/data/historical-fx.json.
"""
import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, median
from typing import NamedTuple
from urllib.request import Request, urlopen


DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
START = date(1971, 1, 4)
END = date(1974, 12, 31)
SOURCE = "Federal Reserve Board · H.10"
RELEASES = {
    "gbp": ("Pound sterling", "uk", "$US/POUND STERLING", "US dollars per pound"),
    "dem": ("Deutsche mark", "ge", "DM/US$", "Deutsche marks per US dollar"),
}
# The principal windows exclude the sterling float, the February dollar
# devaluation and the March joint float, including the immediate reopening.
WINDOWS = [
    ("Smithsonian bands", "1971-12-21", "1972-06-16"),
    ("Sterling floating, mark in dollar band", "1972-07-03", "1973-01-19"),
    ("Both floating against dollar, before October oil shock", "1973-03-26", "1973-09-28"),
    ("Both floating, through end 1974", "1973-03-26", "1974-12-31"),
    ("Before May 1971 mark float, contextual", "1971-01-04", "1971-04-30"),
    ("Early joint float, ahead of June mark realignment", "1973-03-26", "1973-06-22"),
]
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
QUOTE_LINE = re.compile(r"\s*(\d{1,2})-([A-Za-z]{3})-(\d{2})\s+(\d+\.\d+|ND)\s*")


class Return(NamedTuple):
    start: date
    end: date
    gbp: float
    dem: float


def load_quotes(key, path):
    label, suffix, quote_header, quote_unit = RELEASES[key]
    url = f"https://www.federalreserve.gov/releases/h10/hist/dat89_{suffix}.txt"
    if path:
        raw = path.read_bytes()
    else:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=45) as response:
            raw = response.read()
    lines = raw.decode("ascii").splitlines()
    if not any(quote_header in line for line in lines[:8]):
        raise ValueError(f"Expected {label} H.10 header containing {quote_header}")
    quotes = {}
    for line in lines:
        match = QUOTE_LINE.fullmatch(line)
        if not match:
            continue
        day, month, year, value = match.groups()
        when = date(1900 + int(year), 1 + MONTHS.index(month), int(day))
        if START <= when <= END:
            if when in quotes:
                raise ValueError(f"Duplicate {key} quote on {when}")
            quotes[when] = None if value == "ND" else float(value)
    weekdays = {
        day for offset in range((END - START).days + 1)
        if (day := START + timedelta(days=offset)).weekday() < 5
    }
    if quotes.keys() != weekdays:
        raise ValueError(f"{label} calendar is incomplete or contains a non-weekday")
    if any(value <= 0 for value in quotes.values() if value is not None):
        raise ValueError(f"{label} contains a nonpositive quote")
    return quotes, {
        "label": label,
        "source": SOURCE,
        "sourceUrl": url,
        "unit": "Percent",
        "rawQuoteUnit": quote_unit,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def matched_returns(gbp, dem):
    returns = []
    for end in sorted(gbp):
        start = end - timedelta(days=3 if end.weekday() == 0 else 1)
        values = gbp.get(start), gbp[end], dem.get(start), dem[end]
        if None in values:
            continue
        old_gbp, new_gbp, old_dem, new_dem = values
        # Normalize to dollars per unit of foreign currency.
        returns.append(Return(start, end, 100 * math.log(new_gbp / old_gbp),
                              -100 * math.log(new_dem / old_dem)))
    return returns


def summarize(sample):
    currency = {}
    for key in RELEASES:
        values = [getattr(row, key) for row in sample]
        absolute = [abs(value) for value in values]
        currency[key] = {
            "meanAbsolutePct": round(mean(absolute), 8),
            "medianAbsolutePct": round(median(absolute), 8),
            "rootMeanSquarePct": round(math.sqrt(mean(value ** 2 for value in values)), 8),
            "zeroMoves": values.count(0),
            "maxAbsolutePct": round(max(absolute), 8),
        }
    return {
        "firstReturnEnd": sample[0].end.isoformat(),
        "lastReturnEnd": sample[-1].end.isoformat(),
        "n": len(sample),
        "currency": currency,
    }


def build_windows(returns):
    windows = []
    for label, start, end in WINDOWS:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        sample = [r for r in returns if first <= r.start and r.end <= last]
        window = {
            "label": label,
            "permittedQuoteRange": [start, end],
            "main": summarize(sample),
            "common100": summarize(sample[:100]) if len(sample) >= 100 else None,
            "bothQuotesChanged": summarize([r for r in sample if r.gbp and r.dem]),
            "noMondays": summarize([r for r in sample if r.end.weekday() != 0]),
        }
        if first == date(1971, 12, 21):
            # The official 3.2781 DM/$ fixing is bracketed by 3.1666 and 3.1736.
            fixing = date(1972, 3, 17)
            window["excludingMarch17Fixing"] = summarize(
                [r for r in sample if r.start != fixing and r.end != fixing]
            )
        windows.append(window)
    return windows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gbp", type=Path, help="Local copy of the sterling H.10 ASCII release")
    parser.add_argument("--dem", type=Path, help="Local copy of the German H.10 ASCII release")
    parser.add_argument("--output", type=Path, default=DATA / "historical-fx.json")
    args = parser.parse_args()
    gbp, gbp_source = load_quotes("gbp", args.gbp)
    dem, dem_source = load_quotes("dem", args.dem)
    returns = matched_returns(gbp, dem)
    months = defaultdict(list)
    for row in returns:
        months[row.end.strftime("%Y-%m")].append(row)
    monthly = [{
        "month": month,
        "gbp": round(mean(abs(r.gbp) for r in observations), 8),
        "dem": round(mean(abs(r.dem) for r in observations), 8),
        "n": len(observations),
    } for month, observations in sorted(months.items())]
    output = {
        "series": {"gbp": gbp_source, "dem": dem_source},
        "statistic": "Mean absolute daily log change against the US dollar, percent",
        "observation": "New York noon buying rate for cable transfers",
        "calendar": "Each return requires both currencies on consecutive weekdays. Friday to Monday qualifies. Missing quotes are never carried forward. Repeated quotes remain in the main estimates.",
        "monthlyRule": "All matched returns are assigned to the month of their ending quote, including transitions. Both endpoints must lie inside each regime window.",
        "coverage": {"firstQuote": START.isoformat(), "lastQuote": END.isoformat(),
                     "weekdayRows": len(gbp), "matchedReturns": len(returns)},
        "rows": monthly,
        "windows": build_windows(returns),
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                           encoding="utf-8")


if __name__ == "__main__":
    main()
