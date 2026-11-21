"""Build a fixed-composition euro-area monthly panel from Eurostat JSON-stat data.

    python scripts/build-euro-cycle-context.py --save-inputs /tmp/ea-source
    python scripts/build-euro-cycle-context.py --as-of 2026-11-20 --input-dir /tmp/ea-source

Eurostat revises its live datasets. Keep the four original JSON responses for an
exact rebuild. A past observation-month cutoff alone does not recover an old vintage.
"""

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
VIEW = "https://ec.europa.eu/eurostat/databrowser/view/"
DATA = Path(__file__).resolve().parents[1] / "dist" / "data" / "euro-cycle-context.json"
START = "2000-01"
WARMUP = "1999-01"
GEOGRAPHY = "Fixed euro area of 21 countries, including Bulgaria for the entire historical series. The set of countries using the euro at the time differed before 2026."
SOURCES = {
    "unemployment": ("une_rt_m", dict(s_adj="SA", sex="T", age="TOTAL", unit="PC_ACT"),
                     "Unemployment rate", "%", "Seasonally adjusted share of the labour force unemployed, total age and sex groups."),
    "cpi": ("prc_hicp_minr", dict(unit="I25", coicop18="TOTAL"),
            "Harmonised consumer price index", "2025 = 100", "All-items HICP level, ECOICOP version 2, unadjusted."),
    "cpiYoY": ("prc_hicp_minr", dict(unit="RCH_A", coicop18="TOTAL"),
               "HICP inflation", "% YoY", "Eurostat's published annual change in all-items consumer prices, unadjusted."),
    "industrialProduction": ("sts_inpr_m", dict(indic_bt="PRD", s_adj="SCA", nace_r2="B-D", unit="I21"),
                             "Industrial production", "2021 = 100", "Seasonally and calendar-adjusted industrial output volume for mining, manufacturing and energy supply (NACE Rev. 2 sections B–D)."),
}


def previous_year(month):
    return f"{int(month[:4]) - 1:04d}{month[4:]}"


def load_source(key, cutoff, args):
    dataset, filters, label, unit, definition = SOURCES[key]
    params = {"lang": "en", "freq": "M", "geo": "EA21", "sinceTimePeriod": WARMUP,
              "untilTimePeriod": cutoff, **filters}
    url = API + dataset + "?" + urlencode(params)
    if args.input_dir:
        body = (args.input_dir / (key + ".json")).read_bytes()
    else:
        request = Request(url, headers={"User-Agent": "ThePolicyTape/1.0 (historical indicators)"})
        with urlopen(request, timeout=90) as response:
            body = response.read()
        if args.save_inputs:
            args.save_inputs.mkdir(parents=True, exist_ok=True)
            (args.save_inputs / (key + ".json")).write_bytes(body)
    doc = json.loads(body)
    dims = doc["dimension"]
    if doc["source"] != "ESTAT" or doc["extension"]["id"].lower() != dataset:
        raise ValueError(f"Wrong source response for {key}")
    selected = {"freq": "M", "geo": "EA21", **filters}
    if doc["id"][-1] != "time" or set(doc["id"][:-1]) != set(selected):
        raise ValueError(f"Unexpected dimensions for {key}")
    for dim, expected in selected.items():
        if dims[dim]["category"]["index"] != {expected: 0}:
            raise ValueError(f"Unexpected {dataset} {dim} selection")
    if datetime.fromisoformat(doc["updated"]).date() > args.as_of:
        raise ValueError(f"{dataset} was updated after the requested date. Supply the saved source vintage.")
    indexed = {int(pos): month for month, pos in dims["time"]["category"]["index"].items()}
    if not indexed or min(indexed.values()) < WARMUP or max(indexed.values()) > cutoff:
        raise ValueError(f"Unexpected reference months for {dataset}")
    flags = {indexed[int(pos)]: value for pos, value in doc.get("status", {}).items()}
    flag_labels = doc["extension"].get("status", {}).get("label", {})
    observations = {}
    for pos, value in doc["value"].items():
        month = indexed[int(pos)]
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Invalid {key} observation for {month}")
        if key == "unemployment" and not 0 <= value <= 100:
            raise ValueError(f"Invalid unemployment rate for {month}")
        if key in ("cpi", "industrialProduction") and value <= 0:
            raise ValueError(f"Invalid {key} index for {month}")
        status = flags.get(month, "").split()
        if not any("forecast" in flag_labels.get(flag, "").lower() or flag == "f" for flag in status):
            observations[month] = value
    if not observations:
        raise ValueError(f"Empty source for {key}")
    info = {"label": label, "unit": unit, "source": "Eurostat", "sourceUrl": VIEW + dataset + "/default/table?lang=en",
            "seriesId": dataset + "/" + ".".join(selected[dim] for dim in doc["id"][:-1]), "definition": definition,
            "sourceUpdated": doc["updated"]}
    receipt = {"url": url, "sha256": hashlib.sha256(body).hexdigest()}
    return observations, flags, flag_labels, info, receipt


def build(args):
    cutoff = (args.as_of.replace(day=1) - timedelta(days=1)).isoformat()[:7]
    if cutoff < START:
        raise ValueError("The requested snapshot predates January 2000")
    values, flags, sources, inputs, labels = {}, {}, {}, {}, {}
    for key in SOURCES:
        values[key], flags[key], flag_labels, sources[key], inputs[key] = load_source(key, cutoff, args)
        labels.update(flag_labels)
    derived = "industrialProductionYoY"
    ip = values["industrialProduction"]
    values[derived], flags[derived] = {}, {}
    for month, current in ip.items():
        prior = previous_year(month)
        if prior in ip:
            rate = (Decimal(str(current)) / Decimal(str(ip[prior])) - 1) * 100
            values[derived][month] = float(round(rate, 3))
            flags_used = {f for m in (month, prior) for f in flags["industrialProduction"].get(m, "").split()}
            if flags_used:
                flags[derived][month] = " ".join(sorted(flags_used))
    sources[derived] = {**sources["industrialProduction"], "label": "Industrial production growth", "unit": "% YoY",
                        "definition": "Own calculation from the published adjusted volume index, compared with the same month a year earlier. Flags on either input apply to the growth rate."}
    last = max(max(series) for series in values.values())
    month = date.fromisoformat(START + "-01")
    rows = []
    while month.isoformat()[:7] <= last:
        name = month.isoformat()[:7]
        rows.append({"month": name, **{key: series.get(name) for key, series in values.items()}})
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    for key, info in sources.items():
        available = [r for r in rows if r[key] is not None]
        info.update(firstMonth=available[0]["month"] if available else None,
                    lastMonth=available[-1]["month"] if available else None,
                    lastValue=available[-1][key] if available else None, observations=len(available))
    status = {key: {m: flag for m, flag in by_month.items() if START <= m <= last}
              for key, by_month in flags.items()}
    return {
        "schemaVersion": 1, "geography": "Euro area", "geographyCode": "EA21", "membership": GEOGRAPHY,
        "frequency": "monthly", "asOf": args.as_of.isoformat(), "firstMonth": START, "lastMonth": last,
        "vintage": "Released observations from Eurostat's indicated dataset vintages. History can be revised. Dates refer to the observation month, not the date the value first became known. Closed months only.",
        "series": sources, "inputs": inputs, "statusLabels": labels, "statusByMonth": {k: v for k, v in status.items() if v},
        "sourceNotes": {"reuse": "https://ec.europa.eu/eurostat/help/copyright-notice"}, "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--output", type=Path, default=DATA)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--input-dir", type=Path)
    group.add_argument("--save-inputs", type=Path)
    args = parser.parse_args()
    if args.as_of > datetime.now(timezone.utc).date():
        parser.error("The requested snapshot date must already exist")
    panel = build(args)
    text = json.dumps(panel, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=args.output.parent, delete=False) as handle:
        handle.write(text)
    os.chmod(handle.name, 0o644)
    os.replace(handle.name, args.output)
    print(f"{len(panel['rows'])} months, {START} to {panel['lastMonth']}: {args.output}")


if __name__ == "__main__":
    main()
