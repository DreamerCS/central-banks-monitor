"""Regenerate the descriptive Fed and ECB announcement-window regressions."""
import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist, fmean

DATA = Path(__file__).resolve().parents[1] / "dist/data"
START, END = "2000-01-01", "2025-12-31"
OUTCOMES = ("yield2y", "yield10y", "slope", "equity", "eurusd")
COMMON_START = "2004-01-01"
Z95 = NormalDist().inv_cdf(.975)
OIS = "The one-year overnight indexed swap reprices the average overnight rate over a year. The change can reflect the current decision, the future policy path and risk premia."
INSTRUMENTS = {
    "fed": {
        "ois1y": ("US dollar 1-year OIS repricing", OIS),
        "currentMeeting": ("Current-meeting Fed target surprise (MP1)", "The current-month federal funds futures surprise, scaled by the provider to express the unexpected component of the current rate decision in basis points."),
    },
    "ecb": {
        "ois1y": ("Euro 1-year OIS repricing", OIS),
        "ois1m": ("Euro 1-month OIS repricing", "A one-month overnight indexed swap covers settlement before and after the decision. Its sensitivity to a change in the policy rate depends on the effective date and any other meeting within the contract horizon."),
    },
}
WINDOWS = {
    "fed": "Scheduled FOMC statement, ten minutes before to twenty minutes after release (US Eastern time).",
    "ecb": "ECB decision release, median Frankfurt quotes at 13:25–13:35 and 14:00–14:10 before July 2022, then at 13:55–14:05 and 14:30–14:40.",
}
METHODS = [
    "The study uses every eligible decision-release window in the event databases from 2000 through 2025, independently of press coverage or a text score. Each bank contributes at most one release per date. Unscheduled FOMC releases and ECB observations excluded by the source build are omitted.",
    "Each row is a separate ordinary least squares regression of a signed asset change on a signed rate repricing, with an intercept. A coefficient measures the fitted change for a 10 bp higher predictor. Both increases and decreases enter the fit. A 10 bp comparison can be large relative to typical observations.",
    "The 95% intervals use HC1 heteroskedasticity-robust standard errors and a normal critical value. They are pointwise and allow no correction for serial dependence across meetings or for multiple comparisons.",
    "Sensitivity estimates omit absolute predictor changes above the 95th percentile for the bank and predictor, calculated using linear interpolation. Observations equal to the threshold are retained. Original zero changes enter both fits. Missing asset quotes are excluded separately for each regression.",
    "The rate and asset move occupy the same release window. A shift in the expected policy path, new economic information or a contemporaneous announcement can move both. The results describe co-movement. The conference window is excluded, and some FOMC statements are released alongside economic projections.",
    "For one-year OIS the report check estimates separate regressions for decisions with at least one verified report and for the complementary sample. Preview-only dates fall in the second group. Coverage is counted once per decision, including verified reports published later. It describes archive selection and uses information that may have become available after the meeting. The two fits do not test for a difference in coefficients.",
    "The common-calendar fit for one-year OIS starts in 2004, the first full year with US observations, and runs through 2025. Each bank retains its own decision dates and release window.",
    "US and German sovereign yields and 10-year minus 2-year slopes are in basis points. Stock index and EUR/USD coefficients show percentage points of return. Positive EUR/USD means euro appreciation in both panels. Quote windows, available history and policy regimes differ by bank.",
]


def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def percentile(sorted_values, fraction):
    pos = fraction * (len(sorted_values) - 1)
    i = int(pos)
    return sorted_values[i] + (pos - i) * (sorted_values[min(i+1, len(sorted_values)-1)] - sorted_values[i])


def fit(rows):
    # Each input is one observed (date, signed rate move in bp, signed asset move).
    n = len(rows)
    result = {"n": n, "slopePer10Bp": None, "ci95": None, "rSquared": None,
              "firstDate": min((r[0] for r in rows), default=None),
              "lastDate": max((r[0] for r in rows), default=None)}
    if n < 3:
        return result
    xbar = fmean(x for _, x, _ in rows)
    ybar = fmean(y for _, _, y in rows)
    centred = [(x - xbar, y - ybar) for _, x, y in rows]
    sxx = math.fsum(dx * dx for dx, _ in centred)
    if not sxx:
        return result
    syy = math.fsum(dy * dy for _, dy in centred)
    sxy = math.fsum(dx * dy for dx, dy in centred)
    beta = sxy / sxx
    meat = math.fsum((dx * (dy - beta * dx)) ** 2 for dx, dy in centred)
    se = math.sqrt(n / (n - 2) * meat) / sxx
    result.update(slopePer10Bp=round(10 * beta, 6),
                  ci95=[round(10 * (beta - Z95 * se), 6), round(10 * (beta + Z95 * se), 6)],
                  rSquared=round(sxy*sxy / (sxx * syy), 6) if syy else None)
    return result


def analyse_bank(bank, data, reported_dates):
    events = [r for r in data["records"] if r["stage"] == "release" and r["type"] == "decision"
              and r["groupEligible"] and START <= r["date"] <= END]
    if len(events) != len({r["date"] for r in events}):
        raise ValueError(f"Duplicate decision release in {bank}")
    assets = {r["id"]: r for r in data["assets"]}
    predictors = {}
    for key, (label, description) in INSTRUMENTS[bank].items():
        observed = [r for r in events if is_number(r["values"].get(key))]
        if not observed:
            raise ValueError(f"No {bank} observations for {key}")
        magnitudes = sorted(abs(r["values"][key]) for r in observed)
        cutoff = percentile(magnitudes, .95)
        outcomes = {}
        for asset in OUTCOMES:
            rows = [(r["date"], r["values"][key], r["values"][asset]) for r in observed if is_number(r["values"].get(asset))]
            estimates = fit(rows)
            if key == "ois1y":
                estimates["reportCoverage"] = {
                    "covered": fit([r for r in rows if r[0] in reported_dates]),
                    "withoutReport": fit([r for r in rows if r[0] not in reported_dates]),
                }
                estimates["commonCalendar"] = fit([r for r in rows if r[0] >= COMMON_START])
            sensitivity = fit([row for row in rows if abs(row[1]) <= cutoff])
            sensitivity["maxAbsPredictorBp"] = round(cutoff, 6)
            outcomes[asset] = {**estimates, "sensitivity": sensitivity,
                               "label": assets[asset]["label"], "unit": assets[asset]["unit"]}
        predictors[key] = {"label": label, "description": description, "firstDate": min(r["date"] for r in observed),
                           "lastDate": max(r["date"] for r in observed), "observedMeetings": len(observed),
                           "medianAbsPredictorBp": round(percentile(magnitudes,.5), 6),
                           "maxAbsPredictorBp": round(max(magnitudes), 6), "outcomes": outcomes}
    return {"label": "Federal Reserve" if bank == "fed" else "European Central Bank",
            "eligibleMeetings": len(events), "window": WINDOWS[bank], "sourceUrl": data["source"]["url"],
            "sourceLabel": data["source"]["label"], "predictors": predictors}


def build(data):
    reports = json.loads((data / "news-framing.json").read_text())["records"]
    banks = {}
    for bank in INSTRUMENTS:
        reported_dates = {r["date"] for r in reports if r["bank"] == bank and r["type"] == "decision"
                          and r["coverageMode"] == "report"}
        source = json.loads((data / f"{bank}-cross-asset-events.json").read_text())
        banks[bank] = analyse_bank(bank, source, reported_dates)
    return {"period": {"start": START, "end": END, "commonStart": COMMON_START}, "methods": METHODS, "banks": banks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--check", action="store_true", help="Compare the generated result with the checked-in version.")
    args = parser.parse_args()
    target = args.data / "policy-response-study.json"
    output = json.dumps(build(args.data), ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.check:
        if not target.exists() or target.read_text() != output:
            raise SystemExit("Regenerate the policy-response study.")
    else:
        target.write_text(output)
