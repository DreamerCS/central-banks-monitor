"""Build direct US inflation forecasts using the site's pinned monthly macro panel.

Run python scripts/build-inflation-study.py from any directory. Requires NumPy.
An origin is the reference month of the latest observed data, after its releases.
"""

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np


DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
FIRST_TEST = "1962-01"
PERIODS = [
    ("sixties", "1960s", FIRST_TEST, "1969-12"),
    ("seventies", "1970s", "1970-01", "1979-12"),
    ("disinflation", "1980–84 disinflation", "1980-01", "1984-12"),
    ("moderation", "1985–99", "1985-01", "1999-12"),
    ("preGfc", "Pre-crisis", "2000-01", "2007-11"),
    ("gfc", "Financial crisis", "2007-12", "2009-06"),
    ("postGfc", "Post-crisis", "2009-07", "2020-02"),
    ("pandemic", "Pandemic", "2020-03", "2021-12"),
    ("recent", "2022 onward", "2022-01", None),
]
SPECS = [
    ("yoy1", "Year-on-year inflation · 1 month ahead", 1),
    ("yoy6", "Year-on-year inflation · 6 months ahead", 6),
    ("yoy12", "Year-on-year inflation · 12 months ahead", 12),
    ("fresh6", "New inflation over the next 6 months", 6),
]
MODELS = [
    {"id": "naive", "label": "No change", "description": "Carry the current inflation measure forward."},
    {"id": "ar", "label": "Autoregression", "description": "Direct OLS forecast using an intercept and the three most recent monthly observations of the inflation measure."},
    {"id": "arx", "label": "Autoregression + labour market", "description": "Adds the twelve-month change in the unemployment rate, in percentage points. A rise indicates a weakening labour market. It measures the change in slack, not its equilibrium level."},
]
WINDOWS = [
    {"id": "expanding", "label": "Expanding history", "description": "Use all eligible monthly training observations up to each forecast origin."},
    {"id": "rolling120", "label": "Rolling 10 years", "description": "Use only eligible training outcomes in the last 120 calendar months ending at the origin."},
]
PATH_COLUMNS = ["targetMonth", "originMonth", "actual", "naive", "expandingAr", "expandingArx", "rolling120Ar", "rolling120Arx"]


def index(month):
    year, number = map(int, month.split("-"))
    if not 1 <= number <= 12:
        raise ValueError(f"Invalid month {month}")
    return 12 * year + number - 1


def rounded(value):
    return round(float(value), 5)


def as_array(rows, key):
    return np.array([np.nan if row[key] is None else row[key] for row in rows], dtype=float)


def lag(array, periods):
    shifted = np.full(len(array), np.nan)
    shifted[periods:] = array[:-periods]
    return shifted


def annualized_six_month_rate(prices):
    return 100 * ((prices / lag(prices, 6)) ** 2 - 1)


def forecasts(rows, ident, horizon):
    months = [row["month"] for row in rows]
    inflation = as_array(rows, "cpiYoY")
    if ident == "fresh6":
        inflation = annualized_six_month_rate(as_array(rows, "cpi"))
    unemployment = as_array(rows, "unemployment")
    slack_change = unemployment - lag(unemployment, 12)
    predictors = np.column_stack((np.ones(len(rows)), inflation, lag(inflation, 1), lag(inflation, 2), slack_change))
    # Index each training pair by the origin of the predictors. A label y[s+h]
    # becomes eligible at origin t only if s+h <= t.
    labels = np.full(len(rows), np.nan)
    labels[:-horizon] = inflation[horizon:]
    complete = np.flatnonzero(np.isfinite(predictors).all(axis=1) & np.isfinite(labels))
    paths, sizes = [], []
    for t in range(len(rows) - horizon):
        target = t + horizon
        if months[target] < FIRST_TEST or not np.isfinite(predictors[t]).all() or not np.isfinite(labels[t]):
            continue
        latest = t - horizon
        expanding = complete[:np.searchsorted(complete, latest, side="right")]
        rolling = expanding[np.searchsorted(expanding, latest - 119):]
        if len(rolling) < 100 or latest - 119 < 0:
            continue
        predictions = []
        for sample in (expanding, rolling):
            for width in (4, 5):
                matrix = predictors[sample, :width]
                coefficients, _, rank, _ = np.linalg.lstsq(matrix, labels[sample], rcond=None)
                if rank != width:
                    raise ValueError(f"Singular regression at {months[t]} for {ident}")
                predictions.append(predictors[t, :width] @ coefficients)
        paths.append([months[target], months[t], labels[t], inflation[t], *predictions])
        sizes.append((len(expanding), len(rolling)))
    return paths, sizes


def hac_band(differences, positions, lag_count):
    """Bartlett HAC for a paired mean, matching lags by calendar month."""
    n = len(differences)
    if n < 2:
        return None, None
    mean = float(differences.mean())
    demeaned = dict(zip(positions, differences - mean))
    total = sum(value * value for value in demeaned.values())
    for distance in range(1, lag_count + 1):
        cov_sum = sum(value * demeaned.get(month - distance, 0) for month, value in demeaned.items())
        total += 2 * (1 - distance / (lag_count + 1)) * cov_sum
    se = math.sqrt(max(0, total) / (n * (n - 1)))
    return rounded(mean - 1.96 * se), rounded(mean + 1.96 * se)


def period_results(paths, periods, horizon, fresh):
    results, sparse = [], []
    for period in periods:
        cohort = [p for p in paths if period["start"] <= p[0] <= period["end"]]
        if not cohort:
            continue
        n = len(cohort)
        positions = np.array([index(p[0]) for p in cohort])
        actual = np.array([p[2] for p in cohort])
        benchmark = np.abs(np.array([p[3] for p in cohort]) - actual)
        # The horizon floor reflects dependence from overlapping forecast horizons.
        # The second term allows short-run dependence even at horizon one.
        bandwidth = min(n - 1, max(horizon - 1, math.floor(4 * (n / 100) ** (2 / 9))))
        for window, cols in (("expanding", [3, 4, 5]), ("rolling120", [3, 6, 7])):
            scores = []
            losses_by_model = {}
            for model, col in zip(("naive", "ar", "arx"), cols):
                errors = np.array([p[col] for p in cohort]) - actual
                absolute = np.abs(errors)
                losses_by_model[model] = absolute
                gain = benchmark - absolute
                low, high = (None, None) if model == "naive" else hac_band(gain, positions, bandwidth)
                scores.append({"model": model, "mae": rounded(absolute.mean()),
                               "rmse": rounded(np.sqrt(np.mean(errors ** 2))), "bias": rounded(errors.mean()),
                               "maeGain": rounded(gain.mean()), "ciLow": low, "ciHigh": high})
                if fresh and model != "naive":
                    # Month-of-year phase defines six non-overlapping sequences.
                    phase_gains, sizes = [], []
                    for phase in range(6):
                        phase_sample = gain[positions % 6 == phase]
                        if len(phase_sample):
                            phase_gains.append(phase_sample.mean())
                            sizes.append(len(phase_sample))
                    sparse.append({"period": period["id"], "window": window, "model": model,
                                   "grids": len(sizes), "favourable": sum(bool(x > 0) for x in phase_gains),
                                   "nMin": min(sizes), "nMax": max(sizes),
                                   "minGain": rounded(min(phase_gains)), "maxGain": rounded(max(phase_gains))})
            slack_gain = losses_by_model["ar"] - losses_by_model["arx"]
            low, high = hac_band(slack_gain, positions, bandwidth)
            results.append({"period": period["id"], "window": window, "n": n,
                            "slackIncrement": {"maeGain": rounded(slack_gain.mean()), "ciLow": low, "ciHigh": high}, "firstTarget": cohort[0][0],
                            "lastTarget": cohort[-1][0], "hacLag": bandwidth,
                            "smallSample": n < max(36, 3 * (bandwidth + 1)), "scores": scores})
    return results, sparse


def build(input_path):
    source_bytes = input_path.read_bytes()
    source = json.loads(source_bytes)
    rows = source["rows"]
    months = [index(r["month"]) for r in rows]
    if months != list(range(months[0], months[-1] + 1)):
        raise ValueError("Macro input must contain one row per consecutive calendar month, with explicit nulls")
    if source["geography"] != "United States":
        raise ValueError("This specification requires US data")
    last = rows[-1]["month"]
    periods = [{"id": key, "label": label, "start": start, "end": min(end or last, last)}
               for key, label, start, end in [("all", "Full evaluation", FIRST_TEST, None), *PERIODS] if start <= last]
    studies = []
    for ident, label, horizon in SPECS:
        paths, sizes = forecasts(rows, ident, horizon)
        if not paths:
            raise ValueError(f"No test origins available for {ident}")
        fresh = ident == "fresh6"
        results, sparse = period_results(paths, periods, horizon, fresh)
        definition = (
            "Annualized CPI growth over the six months after the origin, 100 × [(CPI(t+6)/CPI(t))² − 1]. "
            "The no-change forecast repeats the annualized change from t−6 to t. The two price-change intervals are disjoint."
            if fresh else f"Forecast the year-on-year change in the seasonally adjusted CPI index {horizon} month"
            + ("s" if horizon > 1 else "") + " ahead. The no-change forecast repeats the year-on-year rate at the origin."
        )
        studies.append({"id": ident, "label": label, "horizon": horizon,
                        "targetLabel": "% annualized" if fresh else "% YoY", "definition": definition,
                        "trainingRange": {w["id"]: [min(s[i] for s in sizes), max(s[i] for s in sizes)]
                                          for i, w in enumerate(WINDOWS)},
                        "firstTarget": paths[0][0], "lastTarget": paths[-1][0],
                        "path": [[p[0], p[1], *[rounded(v) for v in p[2:]]] for p in paths],
                        "results": results, "sparseChecks": sparse})
    return {
        "schemaVersion": 1, "asOf": source["asOf"], "geography": "United States",
        "inputSha256": hashlib.sha256(source_bytes).hexdigest(), "periods": periods,
        "models": MODELS, "windows": WINDOWS, "pathColumns": PATH_COLUMNS, "studies": studies,
        "methods": [
            "Each horizon has its own direct regression. Coefficients are re-estimated at every monthly origin. A training pair is eligible only after its target month has been reached. The most recent observed outcome can enter training. Subsequent target values are reserved for scoring.",
            "The origin is a reference month after its CPI and labour-market readings have become available. The experiment uses the pinned ALFRED revision vintage throughout. Historical data releases, their original values and their publication lags are not replayed. These retrospective forecasts cannot be used as a real-time trading record.",
            "Both estimators use identical training rows within a window, including the slack variable. Both windows and all models are scored on exactly matched monthly targets. A rolling window spans 120 calendar months of known target dates and requires at least 100 complete training pairs. Missing levels, lags or test outcomes are never filled.",
            "Evaluation periods refer to the realized target month. A forecast for the first month of a crisis may therefore have been formed beforehand. The financial-crisis window includes December 2007, the NBER peak month, and is an evaluation window rather than a recession label.",
            "MAE is mean absolute error. RMSE is root mean square error. Bias is mean forecast minus outcome. All errors are in percentage points. MAE gain is the no-change benchmark’s MAE minus the model’s MAE on the same targets. A positive gain favours the model.",
            "The 95% intervals use a Bartlett Newey–West estimate for paired absolute-loss differences. Calendar-distance lags preserve gaps. The bandwidth is the larger of horizon minus one and floor[4 × (n/100)^(2/9)], capped at n−1. Small subsamples and persistent model changes limit the precision of these pointwise intervals. Multiple comparisons are unadjusted. The incremental slack comparison subtracts the labour-market model’s absolute error from the autoregression’s absolute error.",
            "Year-on-year inflation shares eleven underlying monthly price changes at horizon one and six at horizon six. At horizon twelve there is no shared price-change interval. The separate six-month fresh-inflation target tests entirely subsequent changes. Neighbouring monthly forecasts of that target overlap each other, so we also score all six possible non-overlapping semiannual grids."
        ],
        "sources": [
            {"label": "US inflation · Bureau of Labor Statistics via FRED", "url": source["series"]["cpi"]["sourceUrl"]},
            {"label": "US unemployment · Bureau of Labor Statistics via FRED", "url": source["series"]["unemployment"]["sourceUrl"]},
            {"label": "ALFRED · vintage CPI observations", "url": source["inputs"]["CPIAUCSL"]["url"]},
            {"label": "Newey and West · covariance estimation", "url": "https://www.nber.org/papers/t0055"}
        ],
        "interpretation": interpret(studies)
    }


def interpret(studies):
    def find(study, period, window, model):
        item = next(s for s in studies if s["id"] == study)
        result = next(r for r in item["results"] if r["period"] == period and r["window"] == window)
        return next(s for s in result["scores"] if s["model"] == model)
    def fmt(x):
        return f"{x:.2f}"
    recent = find("yoy6", "recent", "rolling120", "arx")
    base = find("yoy6", "recent", "rolling120", "naive")
    fresh = find("fresh6", "all", "rolling120", "arx")
    six = find("yoy6", "all", "rolling120", "arx")
    crisis = find("yoy6", "gfc", "rolling120", "arx")
    calm = find("yoy6", "postGfc", "rolling120", "arx")
    seventies = next(r for s in studies if s["id"] == "yoy6" for r in s["results"]
                     if r["period"] == "seventies" and r["window"] == "rolling120")["slackIncrement"]
    recent_expanding = find("yoy6", "recent", "expanding", "arx")
    grid = next(r for s in studies if s["id"] == "fresh6" for r in s["sparseChecks"]
                if r["period"] == "recent" and r["window"] == "rolling120" and r["model"] == "arx")
    return [
        f"In the 1970s, adding the twelve-month change in unemployment to a rolling inflation-only model reduced six-month MAE by {fmt(seventies['maeGain'])} points. The paired interval was {fmt(seventies['ciLow'])} to {fmt(seventies['ciHigh'])} points. Both models used the same forecast dates and estimation sample.",
        f"From 2022 onward, the rolling labour-market model’s six-month-ahead inflation MAE was {fmt(recent['mae'])} points, versus {fmt(base['mae'])} for no change. Its paired gain interval was {fmt(recent['ciLow'])} to {fmt(recent['ciHigh'])} points. The same labour-market specification with expanding estimation had MAE of {fmt(recent_expanding['mae'])} points.",
        f"Across all evaluation months, the rolling labour-market model’s gain over persistence was {fmt(six['maeGain'])} points for six-month-ahead year-on-year inflation and {fmt(fresh['maeGain'])} for the fresh six-month rate. These are different targets with different persistence benchmarks.",
        f"For fresh inflation from 2022 onward, rolling labour-market forecasts beat persistence on {grid['favourable']} of the six disjoint semiannual grids. Each grid had only {grid['nMin']} to {grid['nMax']} outcomes, so this checks sensitivity to the choice of months.",
        f"The same six-month rolling model produced an MAE gain of {fmt(crisis['maeGain'])} during the 2007–09 crisis and {fmt(calm['maeGain'])} in the post-crisis evaluation. The crisis comparison contains nineteen target months. Overlap makes it a particularly short test of relative forecasting skill."
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA / "cycle-context.json")
    parser.add_argument("--output", type=Path, default=DATA / "inflation-study.json")
    args = parser.parse_args()
    study = build(args.input)
    payload = json.dumps(study, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=args.output.parent, delete=False) as handle:
        handle.write(payload)
    os.chmod(handle.name, 0o644)
    os.replace(handle.name, args.output)
    print("; ".join(f"{s['id']} {len(s['path'])} matched targets" for s in study["studies"]))


if __name__ == "__main__":
    main()
