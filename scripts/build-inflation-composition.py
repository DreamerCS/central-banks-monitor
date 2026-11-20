"""Build the US PCE composition study from SF Fed contributions and BEA price indexes.

python scripts/build-inflation-composition.py
python scripts/build-inflation-composition.py --input-dir /path/to/archived/inputs

The default inputs are the October 29, 2026 vintage. The mutable SF Fed download
is fingerprinted. To update, explicitly specify the new --vintage and --through.
The checked-in JSON retains the observations used to compute every period.
"""

import argparse
import calendar
import csv
import hashlib
import io
import json
import math
import re
from datetime import date
from pathlib import Path
from statistics import fmean
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen

from openpyxl import load_workbook


DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
START = "2000-01"
RELEASE = "2026-10-29"
THROUGH = "2026-09"
PAGE = "https://www.frbsf.org/research-and-insights/data-and-indicators/supply-and-demand-driven-pce-inflation/"
METHOD = "https://www.frbsf.org/research-and-insights/publications/working-papers/decomposing-supply-and-demand-driven-inflation/"
FRBSF = "https://www.frbsf.org/wp-content/uploads/"
WORKBOOK = "supply-demand-pce-inflation.xlsx"
PUBLISHED_HASH = "fbd06baea27cef82db399d0ad9f002c36d3ab14693dd4961bf3a68d318f18113"
INDEX = {"headline": "PCEPI", "core": "PCEPILFE"}
CHARTS = {"headline": "supply-demand-pce-headline-yoy-chart-3.csv",
          "core": "supply-demand-pce-core-yoy-chart-4.csv"}
COLUMNS = {"demand": "Demand-driven Inflation", "supply": "Supply-driven Inflation", "ambiguous": "Ambiguous"}
FIELDS = ("demand", "supply", "ambiguous", "total", "pce", "residual")
PERIODS = [
    ("all", "Full sample", START, None),
    ("pre-gfc", "Before the financial crisis", START, "2007-11"),
    ("gfc", "Financial crisis", "2007-12", "2009-06"),
    ("post-gfc", "Post-crisis expansion", "2009-07", "2019-12"),
    ("pandemic", "Pandemic shock", "2020-03", "2020-12"),
    ("reopening", "Reopening and inflation surge", "2021-01", "2022-12"),
    ("disinflation", "Disinflation", "2023-01", "2024-12"),
    ("recent", "Since January 2025", "2025-01", None),
]
ANCHORS = {
    "2008-07": "Summer 2008", "2009-07": "A year after July 2008",
    "2020-02": "Before the pandemic disruption", "2020-04": "April 2020 contraction",
    "2021-01": "Start of 2021", "2022-06": "June 2022 inflation surge",
    "2022-12": "End of 2022",
}
METHODS = [
    "The San Francisco Fed classifies individual spending categories each month using price and quantity surprises relative to monthly predictions fitted on rolling ten-year windows. Surprises moving together indicate demand. Opposite movements indicate supply. When either surprise is statistically indistinguishable from zero, the Fed assigns the category to the ambiguous group. A category can change groups over time.",
    "Each monthly observation uses the published trailing twelve-month contribution in percentage points. Headline covers the full PCE basket. Core excludes food and energy. Core contributions use their own basket weights, so subtracting the two panels does not isolate an energy contribution.",
    "The three contributions sum to the decomposition total. The BEA comparison is the percentage change in its seasonally adjusted chain-type price index over twelve months, calculated as 100 × (index / year-earlier index − 1). The accounting gap is BEA inflation minus the contribution sum. It is separate from ambiguous inflation and is retained at its observed sign.",
    "Period means weight each monthly twelve-month observation equally. The change within a period is the last observation minus the first. Adjacent observations share eleven months of underlying data. They cannot be added to obtain the price change over the period.",
    "All dates use a common release vintage for retrospective comparison. Earlier observations can differ from the estimates available at the time. Category classifications describe the joint behaviour of prices and quantities. A reading cannot identify how much a particular fiscal measure, rate decision or supply disruption caused.",
]


def numeric(value):
    return round(value, 6) or 0


def month_name(s):
    parts = re.fullmatch(r"(\d{4})m(\d{1,2})", s.strip())
    if not parts:
        raise ValueError(f"Unknown workbook month: {s}")
    year, month = map(int, parts.groups())
    return date(year, month, 1).strftime("%Y-%m")


def month_count(start, end):
    a, b = date.fromisoformat(start + "-01"), date.fromisoformat(end + "-01")
    return (b.year - a.year) * 12 + b.month - a.month + 1


def source_urls(vintage, through):
    last = date.fromisoformat(through + "-01")
    limit = last.replace(day=calendar.monthrange(last.year, last.month)[1]).isoformat()
    result = {name: FRBSF + name for name in [WORKBOOK, *CHARTS.values()]}
    for index in INDEX.values():
        result[index + ".csv"] = ("https://alfred.stlouisfed.org/graph/alfredgraph.csv?"
                                   f"id={index}&cosd=1999-01-01&coed={limit}&vintage_date={vintage}")
    return result


def load_inputs(directory, urls):
    blobs = {}
    for name, url in urls.items():
        if directory:
            blobs[name] = (directory / name).read_bytes()
        else:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=45) as response:
                blobs[name] = response.read()
    return blobs


def component_rows(blob, through):
    book = load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows = iter(book["Data"].values)
    headers = next(rows)
    panels = {basket: {} for basket in INDEX}
    last_source_month = None
    for row in rows:
        if not row[0]:
            continue
        month = month_name(row[0])
        last_source_month = month
        if not START <= month <= through:
            continue
        values = dict(zip(headers, row))
        for basket, panel in panels.items():
            components = {key: values[f"{name} ({basket}, y/y)"] for key, name in COLUMNS.items()}
            if month in panel or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in components.values()):
                raise ValueError(f"Incomplete or duplicate {basket} contributions for {month}")
            panel[month] = components
    book.close()
    if through != last_source_month:
        raise ValueError(f"The workbook ends in {last_source_month}. Use its matching vintage and through month.")
    return panels


def index_levels(blob, index, vintage):
    source = csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))
    column = index + "_" + vintage.replace("-", "")
    if column not in (source.fieldnames or []):
        raise ValueError(f"{index} is not the requested ALFRED vintage {vintage}")
    return {r["observation_date"][:7]: float(r[column]) for r in source if r[column] not in ("", ".")}


def check_chart(blob, published):
    checked = 0
    for row in csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))):
        month = month_name(row["time_month"])
        if month not in published:
            continue
        for key, name in COLUMNS.items():
            if abs(float(row[name]) - published[month][key]) > 0.00001:
                raise ValueError(f"Chart CSV differs from workbook for {month}, {key}")
        checked += 1
    if not checked:
        raise ValueError("The public chart and workbook have no common observations")
    return checked


def period_rows(rows):
    periods = []
    for key, label, start, end in PERIODS:
        sample = [r for r in rows if start <= r["month"] <= (end or rows[-1]["month"])]
        if not sample:
            continue
        first = {k: sample[0][k] for k in FIELDS}
        last = {k: sample[-1][k] for k in FIELDS}
        periods.append(dict(id=key, label=label, start=sample[0]["month"], end=sample[-1]["month"],
                            n=len(sample), first=first, last=last,
                            mean={k: numeric(fmean(r[k] for r in sample)) for k in FIELDS},
                            change={k: numeric(last[k] - first[k]) for k in FIELDS}))
    return periods


def build_panel(basket, components, levels, through):
    rows = []
    for month, components_at_month in sorted(components.items()):
        year_ago = f"{int(month[:4]) - 1}{month[4:]}"
        if month not in levels or year_ago not in levels:
            raise ValueError(f"Missing {basket} BEA price index for {month} or {year_ago}")
        pce = 100 * (levels[month] / levels[year_ago] - 1)
        total = sum(components_at_month.values())
        rows.append(dict(month=month, **{k: numeric(v) for k, v in components_at_month.items()},
                         total=numeric(total), pce=numeric(pce), residual=numeric(pce - total)))
    if len(rows) != month_count(START, through):
        raise ValueError(f"Missing months in the {basket} panel")
    periods = period_rows(rows)
    by_id = {p["id"]: p["mean"] for p in periods}
    reopening, baseline = by_id["reopening"], by_id["post-gfc"]
    difference = {k: numeric(reopening[k] - baseline[k]) for k in FIELDS}
    largest = max(rows, key=lambda r: abs(r["residual"]))
    latest = rows[-1]
    anchors = {**ANCHORS, through: "Latest observation"}
    findings = [
        f'From the post-crisis expansion to the 2021–22 reopening, average {basket} inflation rose '
        f'{difference["pce"]:.2f} percentage points. The supply contribution rose {difference["supply"]:.2f} points, '
        f'demand {difference["demand"]:.2f} and ambiguous {difference["ambiguous"]:.2f}.',
        f'In March–December 2020 the mean demand contribution was {by_id["pandemic"]["demand"]:+.2f} points, '
        f'while supply contributed {by_id["pandemic"]["supply"]:+.2f}. These are twelve-month contributions observed during the shock.',
        f'In {through}, supply contributed {latest["supply"]:.2f} points, demand {latest["demand"]:.2f} '
        f'and ambiguous categories {latest["ambiguous"]:.2f}. The BEA index rose {latest["pce"]:.2f}% over twelve months.',
    ]
    return {"id": basket, "label": basket.title() + " PCE", "rows": rows, "periods": periods, "findings": findings,
            "anchors": [{"month": m, "label": text} for m, text in anchors.items() if m in components],
            "baselineComparison": {"from": "post-gfc", "to": "reopening", "differenceInMeans": difference},
            "accounting": {"meanAbsoluteGap": numeric(fmean(abs(r["residual"]) for r in rows)),
                           "maxAbsoluteGap": abs(largest["residual"]), "maxGapMonth": largest["month"],
                           "signedGapAtMax": largest["residual"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--vintage", default=RELEASE)
    parser.add_argument("--through", default=THROUGH)
    args = parser.parse_args()
    vintage = date.fromisoformat(args.vintage).isoformat()
    through = date.fromisoformat(args.through + "-01").strftime("%Y-%m")
    if through < "2025-01" or through >= vintage[:7]:
        parser.error("Specify an observation month after 2024 and preceding its release.")
    urls = source_urls(vintage, through)
    blobs = load_inputs(args.input_dir, urls)
    fingerprints = {k: hashlib.sha256(v).hexdigest() for k, v in blobs.items()}
    if vintage == RELEASE and fingerprints[WORKBOOK] != PUBLISHED_HASH:
        parser.error("The SF Fed workbook differs from the October 2026 release. Use archived inputs or update the vintage.")
    components = component_rows(blobs[WORKBOOK], through)
    panels = []
    checks = {}
    for basket, index in INDEX.items():
        checks[basket] = check_chart(blobs[CHARTS[basket]], components[basket])
        levels = index_levels(blobs[index + ".csv"], index, vintage)
        panels.append(build_panel(basket, components[basket], levels, through))
    release_month = date.fromisoformat(through + "-01")
    bea_release = (f"https://www.bea.gov/news/{vintage[:4]}/personal-income-and-outlays-"
                   f"{calendar.month_name[release_month.month].lower()}-{release_month.year}")
    study = {"schemaVersion": 1, "title": "Supply and demand in US PCE inflation", "firstMonth": START,
             "lastMonth": through, "vintage": vintage, "methods": METHODS,
             "series": [{"id": k, "label": label, "unit": "%" if k == "pce" else "pp"} for k, label in
                        (("demand", "Demand-driven"), ("supply", "Supply-driven"), ("ambiguous", "Ambiguous"),
                         ("total", "Contribution sum"), ("pce", "BEA PCE inflation"), ("residual", "Accounting gap"))],
             "sources": [{"label": "San Francisco Fed · PCE contributions", "url": PAGE},
                         {"label": "San Francisco Fed · methodology", "url": METHOD},
                         {"label": "BEA · Personal Income and Outlays", "url": bea_release},
                         {"label": "ALFRED · headline PCE vintage", "url": urls["PCEPI.csv"]},
                         {"label": "ALFRED · core PCE vintage", "url": urls["PCEPILFE.csv"]}],
             "panels": panels, "provenance": {"inputs": {k: {"url": url, "sha256": fingerprints[k]} for k, url in urls.items()},
                                              "monthsCrossCheckedWithChartCSVs": checks}}
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=DATA, delete=False) as tmp:
        json.dump(study, tmp, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        tmp.write("\n")
    output = Path(tmp.name)
    output.chmod(0o644)
    output.replace(DATA / "inflation-composition.json")
    print(START, through, len(panels[0]["rows"]), "months per basket;", checks, "chart months verified")


if __name__ == "__main__":
    main()
