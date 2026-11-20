"""Describe rates/equities sign combinations and two separately measured market outcomes.

Usage: python scripts/build-signal-mix.py
Optional official input audit: add --verify-workbooks USMPD.xlsx Dataset_EA-MPD.xlsx.
The deterministic calculation needs NumPy. Checking workbooks also needs openpyxl.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np


DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
THRESHOLDS = [
    {"id": "base", "label": "1 bp and 0.10%", "rateBp": 1, "equityPct": 0.10},
    {"id": "loose", "label": "0.5 bp and 0.05%", "rateBp": 0.5, "equityPct": 0.05},
    {"id": "strict", "label": "2 bp and 0.20%", "rateBp": 2, "equityPct": 0.20},
]
PERIODS = [
    {"id": "all", "label": "Full window history"},
    {"id": "pre2009", "label": "2000–2008"},
    {"id": "post2008", "label": "2009 onward"},
    {"id": "exPandemic", "label": "Excluding March 2020–December 2021"},
    {"id": "matchedDates", "label": "Dates with both windows priced"},
]
OUTCOMES = [
    {"id": "fx", "label": "Local currency vs the other currency", "unit": "%"},
    {"id": "tenYear", "label": "Domestic ten-year yield", "unit": "bp"},
]
COLUMNS = {
    "fed": {"rate": "UST2Y", "equity": "SP500", "fx": "EURUSD", "tenYear": "UST10Y"},
    "ecb": {"rate": "DE2Y", "equity": "STOXX50", "fx": "EURUSD", "tenYear": "DE10Y"},
}
WINDOWS = ("statement", "conference")
DRAWS = 2999


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rounded(x):
    return round(float(x), 5) or 0.0


def read_events(bank, as_of, excluded):
    fields = COLUMNS[bank["id"]]
    windows = {w: [] for w in WINDOWS}
    seen = set()
    for item in bank["events"]:
        day = item["date"]
        if day in seen:
            raise ValueError(f"Duplicate event: {bank['id']} {day}")
        seen.add(day)
        if day < "2000-01-01" or day > as_of or day in excluded:
            continue
        for w in WINDOWS:
            quotes = item["windows"].get(w)
            if quotes is None:
                continue
            values = {key: quotes.get(column) for key, column in fields.items()}
            if any(not math.isfinite(v) for v in values.values() if v is not None):
                raise ValueError(f"Invalid quote: {bank['id']} {day} {w}")
            windows[w].append({"date": day, **values})
    priced = [{e["date"] for e in windows[w] if e["rate"] is not None and e["equity"] is not None}
              for w in WINDOWS]
    common = priced[0] & priced[1]
    for events in windows.values():
        events.sort(key=lambda e: e["date"])
        for e in events:
            e["matchedDate"] = e["date"] in common
    return windows


def in_period(e, p):
    return {"all": True, "pre2009": e["date"] < "2009",
            "post2008": e["date"] >= "2009", "exPandemic": not ("2020-03" <= e["date"] < "2022"),
            "matchedDates": e["matchedDate"]}[p]


def classify(e, limit):
    rate, equity = e["rate"], e["equity"]
    if rate is None or equity is None:
        return "missing", None
    if abs(rate) < limit["rateBp"] or abs(equity) < limit["equityPct"]:
        return "near", None
    up = rate > 0
    if equity > 0:
        return ("same", "upUp") if up else ("opposite", "downUp")
    return ("opposite", "upDown") if up else ("same", "downDown")


def quarter(day):
    return (int(day[:4]), (int(day[5:7]) - 1) // 3)


def block_medians(values, indices, weights):
    """Each sampled quarter repeats every eligible event by the same multiplicity."""
    order = np.argsort(values)
    values = np.asarray(values)[order]
    ordered_weights = weights[:, np.asarray(indices)[order]]
    cumulative = np.cumsum(ordered_weights, axis=1)
    n = cumulative[:, -1]
    # Zero-indexed median ranks; for an even n, average the two central observations.
    lo = np.argmax(cumulative > ((n - 1) // 2)[:, None], axis=1)
    hi = np.argmax(cumulative > (n // 2)[:, None], axis=1)
    medians = (values[lo] + values[hi]) / 2
    return np.where(n > 0, medians, np.nan)


def describe(group_values, quarter_idx, weights):
    result = {}
    boot = []
    for name in ("opposite", "same"):
        observations = group_values[name]
        values = [v for _, v in observations]
        clusters = [quarter_idx[q] for q, _ in observations]
        result[name] = {"n": len(values), "median": rounded(np.median(values)) if values else None}
        if len(values) >= 8 and len(set(clusters)) >= 6 and len(quarter_idx) >= 12:
            boot.append(block_medians(values, clusters, weights))
    result["difference"] = None
    if all(group_values[g] for g in ("opposite", "same")):
        result["difference"] = rounded(np.median([v for _, v in group_values["opposite"]])
                                       - np.median([v for _, v in group_values["same"]]))
    result["quarters"] = len({q for x in group_values.values() for q, _ in x})
    result["ci95"] = None
    result["validDraws"] = 0
    if len(boot) == 2:
        diffs = boot[0] - boot[1]
        valid = diffs[np.isfinite(diffs)]
        result["validDraws"] = len(valid)
        if len(valid) >= .95 * DRAWS:
            result["ci95"] = [rounded(v) for v in np.quantile(valid, [.025, .975])]
    return result


def cell(bank, events, period, limit, seed):
    quarters = sorted({quarter(e["date"]) for e in events})
    indices = {q: i for i, q in enumerate(quarters)}
    count = len(quarters)
    weights = None
    if count >= 12:
        weights = np.random.default_rng(seed).multinomial(count, np.full(count, 1/count), size=DRAWS)
    counts = dict.fromkeys(("opposite", "same", "near", "missing"), 0)
    quadrants = dict.fromkeys(("upDown", "downUp", "upUp", "downDown"), 0)
    direction_groups = {o["id"]: {"opposite": [], "same": []} for o in OUTCOMES}
    for e in events:
        group, quad = classify(e, limit)
        counts[group] += 1
        if not quad:
            continue
        quadrants[quad] += 1
        for outcome, values in direction_groups.items():
            if e[outcome] is not None:
                orientation = 1 if e["rate"] > 0 else -1
                if bank == "fed" and outcome == "fx":
                    orientation *= -1
                values[group].append((quarter(e["date"]), orientation * e[outcome]))
    return {"threshold": limit["id"], "period": period, "n": len(events), "counts": counts,
            "quadrants": quadrants, "outcomes": {k: describe(v, indices, weights) for k, v in direction_groups.items()}}


def compare_similar_moves(bank, events):
    """Pair opposite/same events on direction, broad era and comparable rate magnitude."""
    sides = {"opposite": [], "same": []}
    for e in events:
        group = classify(e, THRESHOLDS[0])[0]
        if group in sides:
            era = sum(e["date"] >= boundary for boundary in ("2009", "2020"))
            sides[group].append((e, era))
    candidates = []
    for a, era in sides["opposite"]:
        for b, other_era in sides["same"]:
            distance = round(abs(a["rate"] - b["rate"]), 5)
            if era == other_era and a["rate"] * b["rate"] > 0 and distance <= 1:
                candidates.append((distance, a["date"], b["date"], a, b))
    pairs = []
    used = set()
    for gap, d1, d2, a, b in sorted(candidates, key=lambda row: row[:3]):
        if d1 not in used and d2 not in used:
            pairs.append((a, b, gap))
            used.update((d1, d2))
    outcomes = {}
    for field in ("fx", "tenYear"):
        differences = []
        for a, b, _ in pairs:
            if a[field] is None or b[field] is None:
                continue
            sign = np.sign(a["rate"]) * (-1 if bank == "fed" and field == "fx" else 1)
            differences.append(sign * (a[field] - b[field]))
        outcomes[field] = {"nPairs": len(differences),
                           "medianPairedGap": rounded(np.median(differences)) if differences else None}
    return {"nPairs": len(pairs), "medianRateDistanceBp": rounded(np.median([p[2] for p in pairs])) if pairs else None,
            "maxRateDistanceBp": max((p[2] for p in pairs), default=None), "outcomes": outcomes}


def verify_workbooks(banks, paths, sources, as_of):
    from openpyxl import load_workbook

    for bank, path, source in zip(banks, paths, sources, strict=True):
        if digest(path) != source["sha256"]:
            raise ValueError(f"Wrong workbook edition: {path.name}")
        ident = bank["id"]
        wb = load_workbook(path, read_only=True, data_only=True)
        raw_quotes = {}
        sheets = {"Statements": "statement", "Press Conferences": "conference"} if ident == "fed" else {"EA-EMPD": None}
        for sheet, window in sheets.items():
            it = wb[sheet].values
            columns = next(it)
            for row in it:
                if not row[0]:
                    continue
                q = dict(zip(columns, row))
                w = window or {"GC_PR": "statement", "GC_PC": "conference"}.get(q["Event_type"])
                date = row[0].date().isoformat()
                if w and "2000-01-01" <= date <= as_of:
                    if (date, w) in raw_quotes:
                        raise ValueError("Duplicate original event row")
                    raw_quotes[date, w] = q
        checked = set()
        for e in bank["events"]:
            for w in WINDOWS:
                if w not in e["windows"] or not "2000-01-01" <= e["date"] <= as_of:
                    continue
                row = raw_quotes[e["date"], w]
                checked.add((e["date"], w))
                for name, source_key in COLUMNS[ident].items():
                    v = row["STOXX50E" if source_key == "STOXX50" else source_key]
                    published = e["windows"][w].get(source_key)
                    if not isinstance(v, (int, float)):
                        if published is not None:
                            raise ValueError(f"Unexpected numeric quote for {e['date']} {name}")
                    else:
                        scale = 100 if ident == "fed" and name in ("rate", "tenYear") else 1
                        if published is None or abs(v * scale - published) > .0000051:
                            raise ValueError(f"Quote mismatch for {e['date']} {name}")
        wb.close()
        if checked != set(raw_quotes):
            raise ValueError("Original and public window calendars differ")


def build(market_path, study_path, verify):
    market = json.loads(market_path.read_text())
    design = json.loads(study_path.read_text())
    if digest(market_path) != design["inputs"]["marketPanel"]["sha256"]:
        raise ValueError("Market inputs do not match the dated official event study.")
    if [b["id"] for b in market["banks"]] != ["fed", "ecb"]:
        raise ValueError("Expected Fed and ECB panels in their documented order.")
    if verify:
        verify_workbooks(market["banks"], verify, design["sources"], design["asOf"])
    ecb_excluded = next(s["excludedWindowDates"] for s in design["specs"] if s["id"] == "ecb-conference-near")
    panels = []
    for bank in market["banks"]:
        ident = bank["id"]
        exclusions = ecb_excluded if ident == "ecb" else []
        windows = read_events(bank, design["asOf"], exclusions)
        labels = {a["id"]: a["label"] for a in bank["assets"]}
        for window, events in windows.items():
            if not events:
                raise ValueError(f"Empty {ident}/{window} window")
            cells = []
            for threshold in THRESHOLDS:
                for period in PERIODS:
                    subset = [e for e in events if in_period(e, period["id"])]
                    # Reuse identical draws whenever the sampled quarter calendar is identical.
                    calendar = sorted({quarter(e["date"]) for e in subset})
                    seed = int.from_bytes(hashlib.sha256(f"{ident}:{window}:{calendar}".encode()).digest()[:8], "big")
                    cells.append(cell(ident, subset, period["id"], threshold, seed))
            examples = []
            # Illustrate typical event sizes, separately within the two classified groups.
            for cat in ("same", "opposite"):
                eligible = [e for e in events if classify(e, THRESHOLDS[0])[0] == cat
                            and e["fx"] is not None and e["tenYear"] is not None]
                if eligible:
                    median_abs_rate = np.median([abs(e["rate"]) for e in eligible])
                    example = min(eligible, key=lambda e: (abs(abs(e["rate"]) - median_abs_rate), e["date"]))
                    examples.append({"group": cat, **example})
            panels.append({"bank": ident, "window": window, "label": bank["name"] + " · " +
                           ("Decision release" if window == "statement" else "Press conference"),
                           "start": events[0]["date"], "end": events[-1]["date"], "rateLabel": labels[COLUMNS[ident]["rate"]],
                           "equityLabel": labels[COLUMNS[ident]["equity"]], "windowDefinition": bank["windows"][window],
                           "excludedDates": exclusions, "cells": cells, "examples": examples, "events": events,
                           "matchedMagnitude": compare_similar_moves(ident, events)})
    data = {"schemaVersion": 1, "title": "When rates and equities move together", "asOf": design["asOf"],
            "thresholds": THRESHOLDS, "periods": PERIODS, "outcomes": OUTCOMES, "panels": panels, "sources": design["sources"],
            "inputs": {"marketSha256": digest(market_path), "eventStudySha256": digest(study_path)}, "draws": DRAWS,
            "methods": [
                "Each observation is one official release or conference window. Relative signs use the US Treasury or German government two-year yield and the S&P 500 or EURO STOXX 50. Same means both rise or both fall. Opposite means one rises as the other falls. Positive threshold values are inclusive. Near means at least one observed move falls below its cutoff, missing means at least one classification quote is unavailable.",
                "The return of EUR/USD and the local ten-year yield are separate outcomes. Multiply each by the sign of the two-year move. Also reverse the EUR/USD sign for the Fed to express dollar strength. Positive oriented FX means the local currency strengthens on rate-up dates or weakens on rate-down dates. Positive oriented ten-year yield means it moves with the two-year yield. FX uses the signed reported EUR/USD percentage change, with no reciprocal exchange-rate conversion.",
                "The displayed gap is the opposite-sign group median minus the same-sign group median. Each outcome uses its own available observations. The signed yield and equity quadrants are kept separately, and daily examples have raw, unoriented prices. The secondary outcomes play no role in allocating groups.",
                "Pointwise 95% percentile bands resample all represented calendar quarters with replacement, jointly across categories and retaining every observation within a sampled quarter. Bands need at least 12 represented quarters, eight observations in each category, six distinct quarters per category and at least 95% valid draws among 2,999 seeded replications. Intervals do not adjust for multiple comparisons or dependence between quarters.",
                "Each bank and event window is analysed separately. Two ECB dates with only 15 minutes between the release and conference are excluded from both windows. Matched dates require both classification quotes in both windows, before imposing a threshold. The pandemic check excludes March 2020 through December 2021. Examples are closest to their group's median absolute two-year move, with the earlier date breaking ties.",
                "The magnitude sensitivity pairs one opposite-sign event with one same-sign event under the base threshold. Both must have the same sign of the two-year move, the same broad period (2000–08, 2009–19 or 2020 onward) and rate moves within 1 bp. The nearest eligible pair is taken first without replacement, with earlier dates breaking ties. The reported paired median uses outcome-complete pairs. This changes the sample and estimand and cannot control for simultaneous news.",
                "An opposite-sign pattern can occur with discount-rate news and a same-sign pattern can occur with growth news. Many mixtures generate either pattern. These figures cannot distinguish policy actions, policymakers' information, public news or risk premia as structural shocks. Different window lengths, instruments and sample coverage affect comparisons.",
            ]}
    data["findings"] = findings(panels)
    return data


def findings(panels):
    def main_cell(panel):
        return next(c for c in panel["cells"] if c["threshold"] == "base" and c["period"] == "all")

    def gap(panel):
        outcome = main_cell(panel)["outcomes"]["fx"]
        band = outcome["ci95"]
        if outcome["difference"] is None:
            return "unavailable"
        text = f"{outcome['difference']:+.2f} percentage points"
        if band:
            text += f" (95% interval {band[0]:+.2f} to {band[1]:+.2f})"
        return text

    by_key = {(p["bank"], p["window"]): p for p in panels}
    european = by_key["ecb", "conference"]
    euro = main_cell(european)
    matched = european["matchedMagnitude"]["outcomes"]["fx"]
    findings = [
        f"At ECB press conferences, two-year yields and shares moved in opposite directions in {euro['counts']['opposite']} "
        f"windows and in the same direction in {euro['counts']['same']}. The median euro move, oriented to the direction "
        f"of rates, was {gap(european)} larger in the opposite-sign group.",
        f"Matching ECB conferences on the direction, era and size of the two-year move left {matched['nPairs']} pairs. "
        f"The median within-pair currency gap was {matched['medianPairedGap']:+.2f} percentage points. "
        f"For ECB decision releases, the unpaired currency gap was {gap(by_key['ecb', 'statement'])}.",
        f"For the Fed, the corresponding dollar gap was {gap(by_key['fed', 'statement'])} around releases and "
        f"{gap(by_key['fed', 'conference'])} around conferences.",
    ]
    bands = [main_cell(p)["outcomes"]["tenYear"]["ci95"] for p in panels]
    if all(b is not None and b[0] <= 0 <= b[1] for b in bands):
        findings.append("For ten-year yields, the median differences are less precisely estimated. "
                        "All four full-sample intervals include zero.")
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-workbooks", nargs=2, type=Path, metavar=("USMPD", "EA_EMPD"))
    parser.add_argument("--output", type=Path, default=DATA / "signal-mix.json")
    args = parser.parse_args()
    study = build(DATA / "market-events.json", DATA / "event-study.json", args.verify_workbooks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=args.output.parent, delete=False, encoding="utf-8") as f:
        json.dump(study, f, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        f.write("\n")
    os.chmod(f.name, 0o644)
    os.replace(f.name, args.output)
    for line in study["findings"]:
        print(line)


if __name__ == "__main__":
    main()
