"""Evaluate source-stage policy guidance against held-out one-year OIS changes.

Usage: python scripts/build-guidance-repricing.py
Optional source audit: --verify-workbooks USMPD.xlsx Dataset_EA-MPD.xlsx
The calculation uses NumPy. The source audit also requires openpyxl.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
FILES = {"fed": "policy-guidance.json", "ecb": "ecb-guidance.json"}
KEYS = {
    "fed": {"ois1y": "OIS1Y", "twoYear": "UST2Y", "fx": "EURUSD", "nearRate": "MP2", "mp1": "MP1"},
    "ecb": {"ois1y": "OIS_1Y", "twoYear": "DE2Y", "fx": "EURUSD", "nearRate": "OIS_1M"},
}
PROTOCOLS = [
    {
        "id": "frozen2022",
        "label": "Fixed pre-2022 estimation",
        "description": "Estimate once on labelled windows through December 2021, then keep that calibration fixed.",
    },
    {
        "id": "annual",
        "label": "Year-by-year held-out test",
        "description": "At each January, estimate on labelled windows through the preceding December. Hold all of the new year's outcomes aside.",
    },
]
MODELS = [
    {"id": k, "label": v}
    for k, v in [
        ("zero", "Zero repricing"),
        ("recent", "Last 12 releases"),
        ("action", "Action only"),
        ("guidance", "Action and wording"),
    ]
]
COHORTS = [
    {"id": k, "label": v}
    for k, v in [
        ("all", "All eligible releases"),
        ("holds", "Unchanged policy rate"),
        ("nearPricedHolds", "Holds with |MP1| ≤ 2 bp"),
        ("supported", "Action and wording cell observed at least three times"),
    ]
]
STATES = ("tightening", "easing", "balanced", "unclear")
ACTIONS = ("hold", "raise", "cut")
MIN_TRAIN = 8
MIN_CELL = 3
DRAWS = 3999


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rounded(value):
    return round(float(value), 5) or 0.0


def stage(bank, obs):
    if bank == "ecb":
        return {"decision-release": "statement", "press-conference": "conference"}[obs["sourceType"]]
    source = obs.get("sourceType", "decision-release")
    return {"decision-release": "statement", "statement": "statement", "press-conference": "conference"}[source]


FED_CONFERENCE_CASES = {
    "2022-11-02": {
        "heading": "A slower pace and a higher destination",
        "interpretation": "The statement introduced the cumulative tightening already delivered and its delayed effects as considerations for the pace of future increases. Powell later said newer data pointed to a higher ultimate rate than previously expected and considered talk of a pause premature. The one-year swap and equities reversed direction during the later window. The two full-window observations cannot attribute the reversal to a particular sentence.",
        "url": "https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20221102.pdf",
        "pages": "pp. 3, 10–11",
    },
    "2024-01-31": {
        "heading": "The possibility of a cut and the timing of the first cut",
        "interpretation": "The Committee held the rate and required greater confidence in sustained disinflation before reducing it. In the conference Powell judged it unlikely that the Committee would have that confidence by March. The one-year swap rate rose during each window. A conditional easing direction leaves room for investors to move an expected cut further out.",
        "url": "https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20240131.pdf",
        "pages": "pp. 3, 17–18",
    },
}


def match_text(panel, bank, as_of, excluded):
    ident = bank["id"]
    market = {r["date"]: r["windows"] for r in bank["events"] if r["date"] <= as_of}
    grouped = {"statement": [], "conference": []}
    seen = set()
    for obs in sorted(panel["observations"], key=lambda x: x["date"]):
        date = obs["date"]
        if date < "2000-01-01" or date > as_of:
            continue
        w = stage(ident, obs)
        if (
            obs["bank"] != ident
            or (date, w) in seen
            or obs["state"] not in STATES
            or obs["action"] not in ACTIONS
        ):
            raise ValueError(f"Multiple or unrecognised guidance records on {ident}/{date}/{w}.")
        seen.add((date, w))
        quotes = market.get(date, {}).get(w)
        overlap = date in excluded
        prices = {k: (quotes or {}).get(raw) if not overlap else None for k, raw in KEYS[ident].items()}
        if any(not np.isfinite(v) for v in prices.values() if v is not None):
            raise ValueError("Non-finite market input")
        event = {
            "date": date,
            "action": obs["action"],
            "state": obs["state"],
            "changeBp": obs.get("rateChangeBps"),
            "url": obs["url"],
            "evidence": obs["evidence"],
            "analysis": obs.get("analysis"),
            "voice": obs.get("voice", "Federal Open Market Committee" if ident == "fed" else None),
            "hasWindow": quotes is not None,
            "overlapExcluded": overlap,
            "ois1y": None,
            "mp1": None,
            **prices,
            "forecasts": {},
        }
        if ident == "fed" and w == "statement" and date in FED_CONFERENCE_CASES:
            windows = market.get(date, {})
            instruments = [
                ("One-year USD OIS", "bp", "OIS1Y"), ("Two-year Treasury yield", "bp", "UST2Y"),
                ("S&P 500", "%", "SP500"), ("EUR/USD", "%", "EURUSD"),
            ]
            event["companion"] = {
                **FED_CONFERENCE_CASES[date],
                "windowDefinition": bank["windows"]["conference"],
                "instruments": [
                    {"label": label, "unit": unit, "statement": windows.get("statement", {}).get(code),
                     "conference": windows.get("conference", {}).get(code)}
                    for label, unit, code in instruments
                ],
            }
        grouped[w].append(event)
    return grouped


def fit(training, e):
    same_action = [r["ois1y"] for r in training if r["action"] == e["action"]]
    condition = [r["ois1y"] for r in training if r["action"] == e["action"] and r["state"] == e["state"]]
    recent = float(np.median([r["ois1y"] for r in training[-12:]]))
    action = float(np.median(same_action)) if len(same_action) >= MIN_CELL else recent
    guidance = float(np.median(condition)) if len(condition) >= MIN_CELL else action
    # Hold rate-change magnitude fixed as an additional check. The exact-size text model
    # falls back only to its size-matched action comparator, never a different text cell.
    by_size = [
        r
        for r in training
        if e["changeBp"] is not None and r["changeBp"] == e["changeBp"] and r["action"] == e["action"]
    ]
    with_state = [r["ois1y"] for r in by_size if r["state"] == e["state"]]
    size_only = float(np.median([r["ois1y"] for r in by_size])) if len(by_size) >= MIN_CELL else action
    size_text = float(np.median(with_state)) if len(with_state) >= MIN_CELL else size_only
    return {
        "trainN": len(training),
        "actionN": len(same_action),
        "cellN": len(condition),
        "exactSize": {
            "actionN": len(by_size),
            "cellN": len(with_state),
            "action": size_only,
            "guidance": size_text,
        },
        "trainThrough": training[-1]["date"],
        "predictions": {"zero": 0.0, "recent": recent, "action": action, "guidance": guidance},
    }


def predict(events):
    with_prices = [e for e in events if e["ois1y"] is not None]
    for protocol in PROTOCOLS:
        method = protocol["id"]
        for e in events:
            year = e["date"][:4]
            if method == "frozen2022" and year < "2022":
                continue
            cutoff = "2022-01-01" if method == "frozen2022" else year + "-01-01"
            training = [t for t in with_prices if t["date"] < cutoff]
            if len(training) < MIN_TRAIN:
                continue
            e["forecasts"][method] = fit(training, e)


def selected_cohort(e, forecast, key):
    if key == "holds":
        return e["action"] == "hold"
    if key == "nearPricedHolds":
        return e["action"] == "hold" and e["mp1"] is not None and abs(e["mp1"]) <= 2
    if key == "supported":
        return forecast["cellN"] >= MIN_CELL
    return True


def quarter(e):
    return e["date"][:4] + "Q" + str(1 + (int(e["date"][5:7]) - 1) // 3)


def paired_gain(loss, rows, weights, quarter_index):
    if len(rows) == 0:
        return {"gain": None, "ci95": None}
    gain = rounded(np.mean(loss))
    if weights is None:
        return {"gain": gain, "ci95": None}
    # Bootstrap the mean across events, retaining every observation in any sampled quarter.
    qsum = np.bincount(quarter_index, weights=loss)
    qsize = np.bincount(quarter_index)
    boot = (weights @ qsum) / (weights @ qsize)
    return {"gain": gain, "ci95": [rounded(x) for x in np.quantile(boot, [0.025, 0.975])]}


def evaluate(events, method, cohort):
    sample = [
        e
        for e in events
        if e["ois1y"] is not None
        and method in e["forecasts"]
        and selected_cohort(e, e["forecasts"][method], cohort)
    ]
    quarters = [quarter(e) for e in sample]
    groups, quarter_index = np.unique(quarters, return_inverse=True)
    g, n = len(groups), len(sample)
    weights = None
    if n >= 24 and g >= 12:
        dates = ",".join(e["date"] for e in sample)
        seed = int.from_bytes(hashlib.sha256(dates.encode()).digest()[:8], "big")
        weights = np.random.default_rng(seed).multinomial(g, np.full(g, 1 / g), size=DRAWS)
    scores, absolute = [], {}
    y = np.array([e["ois1y"] for e in sample])
    for m in MODELS:
        key = m["id"]
        error = np.array([e["forecasts"][method]["predictions"][key] for e in sample]) - y
        absolute[key] = np.abs(error)
        scores.append(
            {
                "model": key,
                "mae": rounded(absolute[key].mean()) if n else None,
                "rmse": rounded(np.sqrt((error**2).mean())) if n else None,
                "bias": rounded(error.mean()) if n else None,
            }
        )
    size_preds = [e["forecasts"][method]["exactSize"] for e in sample]
    size_a = np.abs(np.array([f["action"] for f in size_preds]) - y)
    size_g = np.abs(np.array([f["guidance"] for f in size_preds]) - y)
    exact_size = {
        "actionMae": rounded(size_a.mean()) if n else None,
        "guidanceMae": rounded(size_g.mean()) if n else None,
        "supportedN": sum(f["cellN"] >= MIN_CELL for f in size_preds),
        "guidanceVsAction": paired_gain(size_a - size_g, sample, weights, quarter_index),
    }
    return {
        "protocol": method,
        "cohort": cohort,
        "n": n,
        "exactSize": exact_size,
        "first": sample[0]["date"] if n else None,
        "last": sample[-1]["date"] if n else None,
        "clusters": g,
        "scores": scores,
        "supportedN": sum(e["forecasts"][method]["cellN"] >= MIN_CELL for e in sample),
        "predictionChangedN": sum(
            abs(
                e["forecasts"][method]["predictions"]["guidance"]
                - e["forecasts"][method]["predictions"]["action"]
            )
            > 1e-10
            for e in sample
        ),
        "guidanceVsAction": paired_gain(
            absolute["action"] - absolute["guidance"], sample, weights, quarter_index
        ),
        "guidanceVsZero": paired_gain(absolute["zero"] - absolute["guidance"], sample, weights, quarter_index),
        "guidanceVsRecent": paired_gain(
            absolute["recent"] - absolute["guidance"], sample, weights, quarter_index
        ),
    }


def coding_sensitivity(events):
    changes = {
        "2023-03-16": "Conditional baseline for further tightening during financial stress.",
        "2023-07-27": "A further hike and holding rates steady were both discussed.",
    }
    candidates = {e["date"]: e for e in events}
    if not all(d in candidates and candidates[d]["state"] == "tightening" for d in changes):
        raise ValueError("Recheck the source-specific wording sensitivity against the underlying codebook.")
    alternative = [dict(e, state="unclear" if e["date"] in changes else e["state"], forecasts={}) for e in events]
    predict(alternative)
    cases = []
    for label, rows in (("original", events), ("alternative", alternative)):
        tested = [e for e in rows if e["date"] >= "2022-01-01"]
        summary = evaluate(tested, "annual", "all")
        cases.append(
            {
                "id": label,
                "n": summary["n"],
                "first": summary["first"],
                "last": summary["last"],
                "supportedN": summary["supportedN"],
                "scores": summary["scores"],
                "guidanceVsAction": summary["guidanceVsAction"],
            }
        )
    dates = [
        e["date"]
        for e in events
        if e["date"] >= "2022-01-01" and e["ois1y"] is not None and "annual" in e["forecasts"]
    ]
    other_by_date = {e["date"]: e for e in alternative}
    changed = sum(
        abs(
            candidates[d]["forecasts"]["annual"]["predictions"]["guidance"]
            - other_by_date[d]["forecasts"]["annual"]["predictions"]["guidance"]
        )
        > 1e-10
        for d in dates
    )
    return {
        "protocol": "annual",
        "start": "2022-01-01",
        "recoded": [
            {"date": d, "from": "tightening", "to": "unclear", "reason": reason} for d, reason in changes.items()
        ],
        "changedPredictionN": changed,
        "variants": cases,
        "description": "A retrospective alternative interpretation of two ECB conferences. Re-estimate every calendar-year model with both the held-out assignments and subsequent training labels changed. The original labels, market data and test dates are preserved.",
    }


def descriptive(events, action, state):
    rows = [e for e in events if (action == "all" or e["action"] == action) and state == e["state"]]
    arr = np.array([e["ois1y"] for e in rows if e["ois1y"] is not None])
    result = {
        "action": action,
        "state": state,
        "n": len(arr),
        "coded": len(rows),
        "median": None,
        "q25": None,
        "q75": None,
        "min": None,
        "max": None,
        "higher": int(sum(arr > 0)),
        "lower": int(sum(arr < 0)),
        "zero": int(sum(arr == 0)),
    }
    if len(arr):
        statistics = zip(("min", "q25", "median", "q75", "max"), np.quantile(arr, [0, 0.25, 0.5, 0.75, 1]))
        result.update({k: rounded(v) for k, v in statistics})
    return result


def examples(events):
    cells = {}
    for e in events:
        if e["ois1y"] is None or e["changeBp"] is None:
            continue
        cells.setdefault((e["action"], e["changeBp"], e["state"]), []).append(e)
    options = []
    for (action, size, state), dates in cells.items():
        if len(dates) < 4:
            continue
        up = [e for e in dates if e["ois1y"] > 0]
        down = [e for e in dates if e["ois1y"] < 0]
        if not up or not down:
            continue
        # Choose the closest observation to each side's median, with a stable date tie-break.
        pair = []
        for side in (down, up):
            middle = np.median([e["ois1y"] for e in side])
            pair.append(min(side, key=lambda e: (abs(e["ois1y"] - middle), e["date"]))["date"])
        options.append(
            {
                "action": action,
                "changeBp": size,
                "state": state,
                "n": len(dates),
                "lower": len(down),
                "higher": len(up),
                "dates": sorted(pair),
            }
        )
    return sorted(options, key=lambda r: (-r["n"], r["action"], r["state"], r["changeBp"]))[:3]


def summarize(panels):
    out = []
    for p in panels:
        fixed = next(x for x in p["tests"] if x["protocol"] == "frozen2022" and x["cohort"] == "all")
        if fixed["n"] < 8:
            continue
        mae = {m["model"]: m["mae"] for m in fixed["scores"]}
        out.append(
            f"{p['label']} had {fixed['n']} priced post-2021 releases eligible for the fixed test. "
            f"Median-based estimates using action and wording missed the one-year OIS move by "
            f"{mae['guidance']:.2f} bp on average, versus {mae['action']:.2f} bp using the action "
            f"and {mae['zero']:.2f} bp for zero repricing. The text cell had sufficient earlier observations "
            f"on {fixed['supportedN']} dates."
        )
    for p in panels:
        condition = next((g for g in p["examples"] if g["action"] == "hold" and g["state"] == "tightening"), None)
        if condition:
            out.append(
                f"Across {condition['n']} {p['label'].lower()} windows with unchanged rates and tightening "
                f"guidance, one-year OIS rose {condition['higher']} times and fell {condition['lower']} times. "
                "The common wording category alone leaves the expected part of the announcement unobserved."
            )
            break
    return out


def verify_originals(banks, paths, sources, as_of):
    from openpyxl import load_workbook

    for bank, path, source in zip(banks, paths, sources, strict=True):
        ident = bank["id"]
        if digest(path) != source["sha256"]:
            raise ValueError(f"Unexpected {ident} workbook vintage")
        sheets = (
            {"Statements": "statement", "Press Conferences": "conference"}
            if ident == "fed"
            else {"EA-EMPD": None}
        )
        actual = {}
        workbook = load_workbook(path, read_only=True, data_only=True)
        for sheet, window in sheets.items():
            rows = workbook[sheet].values
            columns = next(rows)
            for r in rows:
                if r[0] is None:
                    continue
                date = r[0].date().isoformat()
                values = dict(zip(columns, r))
                w = window or {"GC_PR": "statement", "GC_PC": "conference"}.get(values["Event_type"])
                if w and "2000-01-01" <= date <= as_of:
                    if (date, w) in actual:
                        raise ValueError("Duplicate official event window")
                    actual[date, w] = values
        workbook.close()
        checked = set()
        for e in bank["events"]:
            if not "2000-01-01" <= e["date"] <= as_of:
                continue
            for w in ("statement", "conference"):
                if w not in e["windows"]:
                    continue
                key = (e["date"], w)
                for name, quoted in KEYS[ident].items():
                    raw = actual[key][quoted]
                    local = e["windows"][w].get(quoted)
                    if isinstance(raw, (int, float)):
                        factor = 100 if ident == "fed" and name != "fx" else 1
                        if local is None or abs(raw * factor - local) > 0.0000051:
                            raise ValueError(f"Price mismatch on {key} in {quoted}")
                    elif local is not None:
                        raise ValueError(f"Missing official quote on {key} in {quoted}")
                checked.add(key)
        if set(actual) != checked:
            raise ValueError("Official event calendar differs from bundled windows")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=DATA)
    ap.add_argument("--output", type=Path, default=DATA / "guidance-repricing.json")
    ap.add_argument("--verify-workbooks", type=Path, nargs=2, metavar=("USMPD", "EA_EMPD"))
    args = ap.parse_args()
    d = args.data_dir
    market = json.loads((d / "market-events.json").read_text())
    design = json.loads((d / "event-study.json").read_text())
    as_of = design["asOf"]
    if digest(d / "market-events.json") != design["inputs"]["marketPanel"]["sha256"]:
        raise ValueError("Unexpected market-event vintage")
    if args.verify_workbooks:
        verify_originals(market["banks"], args.verify_workbooks, design["sources"], as_of)
    publications = []
    sources = list(design["sources"])
    for bank in market["banks"]:
        ident = bank["id"]
        text = json.loads((d / FILES[ident]).read_text())
        sources.append({"label": text["publisher"] + " · source decisions", "url": text["calendarUrl"]})
        exceptions = (
            next(s["excludedWindowDates"] for s in design["specs"] if s["id"] == "ecb-conference-near")
            if ident == "ecb"
            else []
        )
        for w, events in match_text(text, bank, as_of, set(exceptions)).items():
            if not events:
                continue
            predict(events)
            priced = [e for e in events if e["ois1y"] is not None]
            tests = [
                evaluate(events, protocol["id"], cohort["id"])
                for protocol in PROTOCOLS
                for cohort in COHORTS
                if cohort["id"] != "nearPricedHolds" or (ident == "fed" and w == "statement")
            ]
            groups = [descriptive(events, a, s) for a in ("all", *ACTIONS) for s in STATES]
            market_dates = [
                r["date"]
                for r in bank["events"]
                if w in r["windows"] and r["date"] not in exceptions and r["date"] <= as_of
            ]
            publications.append(
                {
                    "bank": ident,
                    "window": w,
                    "label": bank["name"]
                    + " · "
                    + ("Decision release" if w == "statement" else "Press conference"),
                    "unit": "bp",
                    "targetLabel": "One-year " + ("USD" if ident == "fed" else "EUR") + " OIS change",
                    "windowDefinition": bank["windows"][w],
                    "coverage": {
                        "coded": len(events),
                        "matched": len(priced),
                        "first": priced[0]["date"] if priced else None,
                        "last": priced[-1]["date"] if priced else None,
                        "sourceWindows": len(market_dates),
                        "sourceThrough": market_dates[-1],
                        "pre2022": sum(e["date"] < "2022" for e in priced),
                        "absentWindow": sum(not e["hasWindow"] for e in events),
                        "missingTarget": sum(
                            e["hasWindow"] and not e["overlapExcluded"] and e["ois1y"] is None for e in events
                        ),
                        "overlapExcluded": sum(e["overlapExcluded"] for e in events),
                    },
                    "events": events,
                    "groups": groups,
                    "tests": tests,
                    "examples": examples(events),
                    "codingSensitivity": (
                        coding_sensitivity(events) if ident == "ecb" and w == "conference" else None
                    ),
                }
            )
    result = {
        "schemaVersion": 1,
        "asOf": as_of,
        "title": "Does forward guidance help explain the repricing of one-year rates?",
        "thresholds": {"minTrain": MIN_TRAIN, "minCell": MIN_CELL, "rollingEvents": 12, "draws": DRAWS},
        "sources": sources,
        "inputs": {f: digest(d / f) for f in ("market-events.json", "event-study.json", *FILES.values())},
        "protocols": PROTOCOLS,
        "cohorts": COHORTS,
        "models": MODELS,
        "panels": publications,
        "findings": summarize(publications),
        "methods": [
            "The target is the signed market change in a one-year overnight indexed swap in basis points, measured around the stage where the underlying words appeared. The Fed and ECB workbooks use different local windows and each stage has a separate estimation history. One-year OIS reflects the expected path of overnight rates and risk premia. Its change is different from the enacted policy-rate change.",
            "Guidance comes from the selected official release or conference. Tightening and easing indicate a contemplated future direction, balanced covers an explicitly steady or two-sided path, and unclear means the document did not specify a path. An individual dissent is distinct from the majority wording. Classification is retrospective and available only after reading the source. Identically coded texts can contain different surprises, conditionality or balance-sheet news.",
            "For each eligible date the models use zero, the median of the last 12 earlier matched releases, the median for its announced action (raise, cut or hold), or the median for that action and guidance state. At least eight training dates are required. An action cell with fewer than three cases uses the recent median. A wording cell with fewer than three uses the action estimate. Verify support counts before attributing results to additional text.",
            "One test fixes estimation at the end of 2021. The second withholds one calendar year at a time, using only complete earlier years. All models are scored on exactly the same priced releases in each comparison. The test dates are chronologically held out. The underlying document selection and retrospective labelling were not frozen in real time. This tests conditional historical calibration and does not establish a tradable signal.",
            "MAE and RMSE are in basis points, and bias is estimated minus observed repricing. A positive gain is lower mean absolute error for the wording model. Pointwise 95% percentile intervals resample the observed test quarters jointly across both models. They require at least 24 dates in 12 quarters. Conditional on the fitted training history, they convey sampling variation among the tested outcomes. Intervals are unadjusted for multiple panels or comparisons.",
            "The hold-only comparison fixes the actual rate action at zero. The Fed subgroup additionally requires a measured current-meeting futures surprise within ±2 bp in the statement window (MP1). It is an ex-post diagnostic, never a predictor. A hold alone does not establish that markets anticipated the decision. The ECB one-month OIS combines current and expected rates, so no equivalent priced-hold filter is applied there.",
            "A further sensitivity conditions on the numerical size of the announced rate move. Its action benchmark uses the same action and exact rate change if at least three earlier examples exist, otherwise the original action benchmark. Adding wording then requires at least three earlier matches on action, exact size and guidance. Lower support shifts this check toward its benchmark.",
            "The catalogued texts are a selected subset of meetings, including historical milestones and more recent decisions. Sparse stages and unavailable early one-year OIS quotes remain visible. A recorded absence is never set to a zero move. The two exceptional ECB dates with overlapping release and conference windows are excluded from matching. Examples select opposite responses among texts with the same state, action and policy-rate change; each example is nearest its sign subgroup’s median.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=args.output.parent, delete=False, encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        handle.write("\n")
    os.chmod(handle.name, 0o644)
    os.replace(handle.name, args.output)
    for p in publications:
        print(p["label"], p["coverage"])


if __name__ == "__main__":
    main()
