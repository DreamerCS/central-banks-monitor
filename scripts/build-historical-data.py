"""Build the historical explorer snapshot from BIS and Taiwan CBC source files."""

import argparse
import csv
import io
import json
import math
from datetime import date
from pathlib import Path
from zipfile import ZipFile


DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
START = date(2000, 1, 1)
BIS_RATES = "https://data.bis.org/topics/CBPOL"
CBC_RATES = "https://www.cbc.gov.tw/en/lp-695-2.html"
SINGAPORE_NEER = "https://data.bis.org/topics/EER/BIS%2CWS_EER%2C1.0/D.N.B.SG"

RATE_CODES = {
    "United States": "US", "Euro area": "XM", "United Kingdom": "GB",
    "Sweden": "SE", "Norway": "NO", "Switzerland": "CH", "Canada": "CA",
    "Australia": "AU", "New Zealand": "NZ", "Japan": "JP", "Mexico": "MX",
    "Colombia": "CO", "Brazil": "BR", "Argentina": "AR", "Peru": "PE",
    "Hungary": "HU", "Poland": "PL", "Czechia": "CZ", "Türkiye": "TR",
    "South Africa": "ZA", "China": "CN", "Taiwan": "TW", "South Korea": "KR",
    "Singapore": "SG", "India": "IN", "Indonesia": "ID", "Malaysia": "MY",
    "Philippines": "PH", "Thailand": "TH",
}


def observations(path, through):
    codes = set(RATE_CODES.values()) - {"TW", "SG"}
    series = {code: {} for code in codes}
    institutions = {}
    with ZipFile(path) as archive, archive.open("WS_CBPOL_csv_flat.csv") as source:
        reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))
        for row in reader:
            period = row["TIME_PERIOD:Time period or range"]
            if not row["FREQ:Frequency"].startswith("D:") or not START.isoformat() <= period <= through.isoformat():
                continue
            code = row["REF_AREA:Reference area"].split(":", 1)[0]
            value = row["OBS_VALUE:Observation Value"]
            if code not in codes or not value or row["OBS_STATUS:Observation Status"].startswith("M:"):
                continue
            assert row["UNIT_MEASURE:Unit of measure"].startswith("368:"), code
            assert row["UNIT_MULT:Unit Multiplier"].startswith("0:"), code
            day = (date.fromisoformat(period) - START).days
            assert day not in series[code], (code, period)
            series[code][day] = float(value)
            institutions[code] = row["SOURCE_REF:Publication Source"].strip()
    assert all(series.values()) and institutions.keys() == codes, "Missing BIS series"
    return series, institutions


def taiwan_schedule(pages, through):
    from lxml import html

    changes = {}
    for path in pages:
        doc = html.parse(str(path))
        rows = doc.xpath('//table[.//th[contains(., "EFFECTIVE DATE")]]//tr[td]')
        assert rows, f"No rate schedule in {path}"
        for row in rows:
            cells = row.xpath("./td")
            year, month, day = map(int, cells[0].text_content().strip().split("/"))
            effective = date(year, month, day)
            if effective <= through:
                value = float(cells[1].text_content().strip())
                assert effective not in changes or changes[effective] == value, effective
                changes[effective] = value
    assert min(changes) <= date(2000, 12, 31), "Taiwan's 2000 schedule page is missing"
    eras = sorted(changes.items())
    series = {}
    for index, (change, rate) in enumerate(eras):
        start = (max(START, change) - START).days
        stop = ((eras[index + 1][0] if index + 1 < len(eras) else through) - START).days
        series.update({day: rate for day in range(start, stop + (index + 1 == len(eras)))})
    return series


def singapore_neer(path, through):
    series = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            assert (row["FREQ"], row["EER_TYPE"], row["EER_BASKET"], row["REF_AREA"]) == ("D", "N", "B", "SG")
            day = date.fromisoformat(row["TIME_PERIOD"])
            value = float(row["OBS_VALUE"] or "nan")
            if START <= day <= through and math.isfinite(value):
                series[(day - START).days] = value
    assert series and min(series) < 7, "Missing daily Singapore NEER coverage"
    return series


def compact(series):
    """Store runs of consecutive, equal observations without filling gaps."""
    runs = []
    for day, value in sorted(series.items()):
        assert math.isfinite(value)
        if runs and runs[-1][0] + runs[-1][1] == day and runs[-1][2] == value:
            runs[-1][1] += 1
        else:
            runs.append([day, 1, value])
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bis-rates", required=True, type=Path, help="BIS WS_CBPOL CSV flat ZIP")
    parser.add_argument("--taiwan-pages", required=True, type=Path, nargs="+", help="Saved CBC rate schedule HTML pages")
    parser.add_argument("--singapore-neer", required=True, type=Path, help="BIS daily broad SG NEER CSV")
    parser.add_argument("--through", required=True, type=date.fromisoformat, help="Source check date (YYYY-MM-DD)")
    args = parser.parse_args()
    rates, institutions = observations(args.bis_rates, args.through)
    rates["TW"] = taiwan_schedule(args.taiwan_pages, args.through)
    institutions["TW"] = "Central Bank of the Republic of China (Taiwan)"
    coverage = json.loads((DATA / "coverage.json").read_text(encoding="utf-8"))["targets"]
    assert {row["name"] for row in coverage} == RATE_CODES.keys()
    series = []
    for target in coverage:
        name = target["name"]
        code = RATE_CODES[name]
        common = {"id": code, "name": name, "region": target["region"]}
        if code == "SG":
            series.append(common | {
                "metric": "neer", "institution": "Bank for International Settlements",
                "source": SINGAPORE_NEER, "observations": compact(singapore_neer(args.singapore_neer, args.through)),
            })
        else:
            series.append(common | {
                "metric": "rates", "institution": institutions[code],
                "source": CBC_RATES if code == "TW" else f"{BIS_RATES}/BIS%2CWS_CBPOL%2C1.0/D.{code}",
                "observations": compact(rates[code]),
            })
    snapshot = {"start": START.isoformat(), "through": args.through.isoformat(), "series": series}
    destination = DATA / "historical-series.json"
    destination.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(rates)} policy-rate series and one effective exchange rate series")


if __name__ == "__main__":
    main()
