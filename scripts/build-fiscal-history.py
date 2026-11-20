"""Build calendar-year fiscal outturns from the October 2026 WEO and vintage BEA data.

Run with Python and openpyxl. Inputs default to the published source URLs.
Optional --weo and --bea-csv arguments accept downloaded copies of those releases.
"""

import argparse
import csv
import io
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

from openpyxl import load_workbook


AS_OF = "2026-11-20"
START = 2000
END = 2026
OUTPUT = Path(__file__).resolve().parents[1] / "dist/data/fiscal-history.json"
WEO = (
    "https://data.imf.org/-/media/iData/External-Storage/Documents/"
    "0FA3DC49A04D446E9D69DBEB29979E1C/en/WEOOct2026all.xlsx"
)
BEA = (
    "https://alfred.stlouisfed.org/graph/alfredgraph.csv?"
    "id=AD01RC1A027NBEA,GDPA&cosd=2000-01-01&coed=2000-01-01"
    "&vintage_date=2026-11-20,2026-11-20"
)
INDICATOR = "GGXCNL_NGDP"


def source_bytes(path, url):
    if path:
        return path.read_bytes()
    request = Request(url, headers={"User-Agent": "Central Bank Intelligence fiscal history"})
    with urlopen(request, timeout=90) as response:
        return response.read()


def outturns(sheet, economy):
    rows = iter(sheet.values)
    fields = [str(name) for name in next(rows)]
    for row in rows:
        data = dict(zip(fields, row))
        if data["COUNTRY.ID"] != economy or data["INDICATOR.ID"] != INDICATOR:
            continue
        if (data["FREQUENCY"], data["UNIT"], data["START_END_MONTHS_OF_REPORTING_YEAR"]) != (
            "Annual", "Percent", "January/December"
        ):
            raise ValueError(f"Unexpected unit, frequency or reporting period for {economy}")
        last_actual = int(data["LATEST_ACTUAL_ANNUAL_DATA"])
        observations = []
        for year in range(START, min(END, last_actual) + 1):
            value = data[str(year)]
            if value is None:
                continue
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f"Invalid {economy} outturn for {year}")
            observations.append({"year": year, "value": value})
        if not observations or observations[-1]["year"] != last_actual:
            raise ValueError(f"Missing latest actual for {economy}")
        return last_actual, observations
    raise ValueError(f"Missing {economy}.{INDICATOR}.A")


def us_2000(data):
    rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    row = next((r for r in rows if r["observation_date"] == "2000-01-01"), None)
    if row is None:
        raise ValueError("No 2000 BEA observation")
    net_lending = float(row["AD01RC1A027NBEA_20261120"])
    nominal_gdp = float(row["GDPA_20261120"])
    if not math.isfinite(net_lending) or not math.isfinite(nominal_gdp) or nominal_gdp <= 0:
        raise ValueError("Invalid BEA net lending or GDP")
    return {"year": 2000, "value": round(100 * net_lending / nominal_gdp, 3), "sourceId": "bea-nipa"}


def build(weo_data, bea_data):
    workbook = load_workbook(io.BytesIO(weo_data), read_only=True, data_only=True)
    try:
        entries = []
        for id_, economy, sheet, label in (
            ("us", "USA", "Countries", "United States"),
            ("ea", "G163", "Country Groups", "Euro area"),
        ):
            last_actual, observations = outturns(workbook[sheet], economy)
            series = {
                "id": id_,
                "label": label,
                "scope": "General government net lending (+) or net borrowing (−)",
                "periodBasis": "Calendar year (January–December), accrual basis",
                "unit": "% of GDP",
                "source": "IMF World Economic Outlook, October 2026",
                "sourceUrl": WEO,
                "sourceId": "imf-weo",
                "latestActualYear": last_actual,
                "observations": observations,
            }
            if id_ == "us" and observations[0]["year"] > START:
                observations.insert(0, us_2000(bea_data))
                series["source"] += "; US BEA national accounts for 2000"
                series["supplement"] = {
                    "sourceId": "bea-nipa",
                    "source": "US Bureau of Economic Analysis, via ALFRED",
                    "sourceUrl": BEA,
                    "year": 2000,
                    "detail": (
                        "Government net lending or borrowing (NIPAs, AD01RC1A027NBEA) "
                        "divided by nominal GDP (GDPA), both in billions of dollars. "
                        "The IMF US series starts in 2001 and uses IMF fiscal-statistics adjustments."
                    ),
                }
            if id_ == "ea":
                members = [row[3] for row in workbook["Country Group Composition"].values if row[0] == economy]
                series["scope"] += f", IMF euro area aggregate ({len(members)} members in this vintage)"
            entries.append(series)
    finally:
        workbook.close()
    return {"asOf": AS_OF, "indicator": "General government fiscal balance", "series": entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weo", type=Path)
    parser.add_argument("--bea-csv", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    data = build(source_bytes(args.weo, WEO), source_bytes(args.bea_csv, BEA))
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
