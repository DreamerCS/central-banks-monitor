"""Build the three Wednesday comparisons from Board and New York Fed series on FRED.

Usage: python scripts/build-fed-liquidity.py --cache /tmp/fed-liquidity
Input downloads are kept by series. Delete a cached file to fetch its latest vintage.
"""
import argparse
import csv
import hashlib
import json
import urllib.request
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERIES = {
    "WLCFLPCL": "H.4.1 · Primary credit outstanding, Wednesday level",
    "DFEDTAR": "FOMC · Federal funds point target through 2008",
    "DFEDTARU": "FOMC · Upper limit of the target range",
    "DFF": "New York Fed · Effective federal funds rate",
    "RIFSPPFAAD01NB": "Federal Reserve · Overnight AA financial commercial paper",
    "DCPF3M": "H.15 · 90-day AA financial commercial paper",
    "DTB3": "H.15 · Three-month Treasury bill, secondary market, discount basis",
}
EPISODES = {
    "2008": {
        "anchor": "2008-09-17",
        "label": "September 2008 · Lehman failure",
        "context": "On September 16 the FOMC held its point target at 2%. The next day the effective funds rate reached 2.80%, while banks had $33.401 billion of primary credit outstanding. The same H.4.1 return showed a separate $59.780 billion loan balance at the Primary Dealer Credit Facility. These were different borrowers and facilities.",
        "interpretation": "The 90-day paper–bill spread widened from 108 to 263 bp in the first week. The commercial-paper rate actually fell 4 bp. A 159 bp fall in the Treasury-bill yield accounted for the widening. A rush into bills can make this spread look worse even as the quoted price of private borrowing falls.",
        "sources": [
            ["September 16 FOMC decision", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20080916a.htm"],
            ["September 18 H.4.1 release, including dealer lending", "https://www.federalreserve.gov/releases/h41/20080918/h41.pdf"],
        ],
    },
    "2020": {
        "anchor": "2020-03-18",
        "label": "March 2020 · Pandemic",
        "context": "On March 15 the Fed lowered its policy range to 0–0.25%. It also lowered the primary credit rate to 0.25% and offered terms as long as 90 days. Bank borrowing rose from $11 million on March 11 to $28.224 billion on March 18. Both the price and the term of the facility changed, so take-up reflects the terms on offer as well as banks’ need for cash.",
        "interpretation": "By March 25 the overnight AA paper rate was 0.11%, only 1 bp above effective federal funds. The 90-day AA paper rate was 2.53%, against a three-month bill at −0.04%. The resulting 257 bp gap shows how a near-zero overnight rate could coexist with costly term funding. The March 18 term-paper observation is missing.",
        "sources": [
            ["March 15 FOMC decision", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315a.htm"],
            ["March 15 discount-window terms", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315b.htm"],
            ["March 19 H.4.1 release", "https://www.federalreserve.gov/releases/h41/20200319/"],
        ],
    },
    "2023": {
        "anchor": "2023-03-15",
        "label": "March 2023 · Bank failures",
        "context": "Primary credit rose from $4.581 billion on March 8 to $152.853 billion on March 15. Over those two Wednesdays the federal funds ceiling held at 4.75% and overnight AA financial paper traded 2 bp below effective federal funds on both dates. Distress at particular banks could coexist with stable overnight funding prices for highly rated issuers.",
        "interpretation": "The FOMC announced a 25 bp increase on March 22, effective March 23. By April 12 primary credit had fallen to $67.633 billion, but lending through the separate Bank Term Funding Program had increased from $11.943 billion on March 15 to $71.837 billion. Some funding demand could shift across facilities. A decline in one loan category cannot establish that deposit pressure ended.",
        "sources": [
            ["March 12 Bank Term Funding Program terms", "https://www.federalreserve.gov/newsevents/pressreleases/files/monetary20230312a1.pdf"],
            ["March 16 H.4.1 release", "https://www.federalreserve.gov/releases/h41/20230316/"],
            ["March 22 FOMC decision and implementation note", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20230322a.htm"],
            ["April 13 H.4.1 release", "https://www.federalreserve.gov/releases/h41/20230413/"],
        ],
    },
}


def load_series(cache, code):
    path = cache / (code + ".csv")
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + code + "&cosd=2008-09-01&coed=2023-04-30"
    if not path.exists():
        with urllib.request.urlopen(url, timeout=35) as response:
            raw = response.read()
        if not raw.startswith(("observation_date," + code).encode()):
            raise ValueError("Unexpected input header for " + code)
        path.write_bytes(raw)
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["observation_date", code]:
            raise ValueError("Unexpected CSV columns for " + code)
        values = {}
        for row in reader:
            stamp = row["observation_date"]
            if stamp in values:
                raise ValueError("Duplicate observation in " + code + " on " + stamp)
            entry = row[code]
            values[stamp] = Decimal(entry) if entry not in ("", ".") else None
    source = {
        "label": SERIES[code], "url": "https://fred.stlouisfed.org/series/" + code,
        "download": url, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    return values, source


def scaled(series, code, stamp, scale=100, optional=False):
    value = series[code].get(stamp)
    if value is None:
        if optional:
            return None
        raise ValueError("Missing required observation " + code + " on " + stamp)
    result = value * scale
    if result != result.to_integral_value():
        raise ValueError("Unexpected precision in " + code)
    return int(result)


def build(cache):
    cache.mkdir(parents=True, exist_ok=True)
    series = {}
    sources = {}
    for code in SERIES:
        series[code], sources[code] = load_series(cache, code)
    episodes = {}
    for year, episode in EPISODES.items():
        anchor = date.fromisoformat(episode["anchor"])
        if anchor.weekday() != 2:
            raise ValueError("Expected a Wednesday for " + year)
        observations = []
        for weeks in (-1, 0, 1, 4):
            stamp = (anchor + timedelta(weeks=weeks)).isoformat()
            target_series = "DFEDTAR" if year == "2008" else "DFEDTARU"
            observations.append({
                "week": weeks, "date": stamp,
                "primaryMillions": scaled(series, "WLCFLPCL", stamp, scale=1),
                "policyBp": scaled(series, target_series, stamp),
                "effectiveBp": scaled(series, "DFF", stamp),
                "overnightPaperBp": scaled(series, "RIFSPPFAAD01NB", stamp),
                "termPaperBp": scaled(series, "DCPF3M", stamp, optional=True),
                "billBp": scaled(series, "DTB3", stamp),
            })
        episodes[year] = {**episode, "observations": observations}
    return {"sources": sources, "episodes": episodes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/data/fed-liquidity.json")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(args.cache), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
