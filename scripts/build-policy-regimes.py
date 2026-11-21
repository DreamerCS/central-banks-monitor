"""Rebuild the descriptive one-year OIS response estimates by leader and economic cycle."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
from statistics import fmean

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "dist/data"
spec = importlib.util.spec_from_file_location("policy_response", BASE / "build-policy-response-study.py")
response = importlib.util.module_from_spec(spec)
spec.loader.exec_module(response)
MIN_N = 20
CONTRACTION = "Contraction"
OUTSIDE = "Outside dated contraction"
METHOD = [
    "The predictor is the signed change in one-year domestic overnight indexed swaps during the decision release. Each coefficient describes the asset change associated with a 10 bp higher OIS move. Both outcome and predictor are observed in the same window.",
    "The full frame runs from 2000 through 2025. US one-year OIS observations begin in December 2003. The common-calendar frame starts in January 2004 and retains each bank’s own decision dates. Headline coverage is outside the selection criteria.",
    "Each group uses a separate regression with an intercept and pointwise HC1 95% intervals. A fit requires at least 20 complete meetings, five distinct signed OIS changes, and both positive and negative changes. Eligible meetings count release dates before checking for either quote.",
    "The scale of 10 bp may exceed the subgroup’s entire observed OIS range. The minimum, maximum and median absolute predictor changes describe its support. In narrow samples the coefficient is a rescaling of the fitted slope.",
    "Leader groups identify the incumbent at the release. Cycle groups follow each bank’s retrospective monthly or quarterly business-cycle chronology. Leadership, policy regime, asset-purchase programmes and the economic environment change together.",
    "The preselected two-year sovereign yield comparison fits a pooled regression with a contraction indicator and its interaction with the OIS change. The interaction is the contraction slope minus the outside-contraction slope. Its interval and two-sided p-value use the joint HC1 covariance and a normal reference distribution.",
    "Within each bank, contraction dates may belong to only a few episodes. These exploratory intervals account for heteroskedasticity. They do not adjust for within-episode dependence or multiple subgroup comparisons.",
]


def support(rows):
    if len(rows) < MIN_N:
        return "too few meetings"
    x = {x for _, x, _ in rows}
    if len(x) < 5 or min(x) >= 0 or max(x) <= 0:
        return "insufficient rate variation"
    return "estimated"


def pairs(group, asset):
    return [(r["date"], r["values"]["ois1y"], r["values"][asset]) for r in group
            if response.is_number(r["values"].get("ois1y")) and response.is_number(r["values"].get(asset))]


def estimates(rows):
    status = support(rows)
    if status == "estimated":
        result = response.fit(rows)
    else:
        dates = [r[0] for r in rows]
        result = {"n": len(rows), "firstDate": min(dates, default=None), "lastDate": max(dates, default=None),
                  "slopePer10Bp": None, "ci95": None, "rSquared": None}
    x = sorted(r[1] for r in rows)
    result.update(minPredictorBp=x[0] if x else None, maxPredictorBp=x[-1] if x else None,
                  medianAbsPredictorBp=round(response.percentile(sorted(abs(v) for v in x), .5), 6) if x else None,
                  tenBpExceedsObservedSpan=(x[-1] - x[0] < 10) if x else None)
    return {**result, "status": status}


def centre_fit(rows):
    # HC0 slope variance in one group, before the joint finite-sample correction.
    xbar = fmean(x for _, x, _ in rows)
    ybar = fmean(y for _, _, y in rows)
    centred = [(x - xbar, y - ybar) for _, x, y in rows]
    sxx = math.fsum(x*x for x, _ in centred)
    slope = math.fsum(x*y for x, y in centred) / sxx
    variance = math.fsum((x * (y - slope*x))**2 for x, y in centred) / sxx**2
    return slope, variance


def contrast(groups):
    contraction = pairs(groups.get(CONTRACTION, []), "yield2y")
    outside = pairs(groups.get(OUTSIDE, []), "yield2y")
    result = {"asset": "yield2y", "contractionN": len(contraction), "outsideN": len(outside),
              "differencePer10Bp": None, "ci95": None, "pValue": None}
    for sample in (contraction, outside):
        status = support(sample)
        if status != "estimated":
            return {**result, "status": status}
    # Group-specific intercepts and slopes span the same design as the interacted pooled regression.
    # In the disjoint group parameterisation HC0 has zero cross-group covariance.
    a, va = centre_fit(contraction)
    b, vb = centre_fit(outside)
    n = len(contraction) + len(outside)
    diff = (a - b) * 10
    se = 10 * math.sqrt((va + vb) * n / (n - 4))
    result.update(status="estimated", differencePer10Bp=round(diff, 6),
                  ci95=[round(diff - response.Z95 * se, 6), round(diff + response.Z95 * se, 6)],
                  pValue=round(math.erfc(abs(diff) / (se * math.sqrt(2))), 8) if se > 0 else None)
    return result


def predictor_count(rows):
    return sum(response.is_number(r["values"].get("ois1y")) for r in rows)


def group_rows(rows, attr):
    groups = {}
    for r in rows:
        groups.setdefault(r[attr], []).append(r)
    return groups


def summarise_groups(groups):
    return [{"label": label, "eligibleMeetings": len(rows), "predictorMeetings": predictor_count(rows),
             "outcomes": {asset: estimates(pairs(rows, asset)) for asset in response.OUTCOMES}}
            for label, rows in groups.items()]


def frame(rows, start):
    subset = [r for r in rows if start <= r["date"] <= response.END]
    cycles = group_rows(subset, "cycle")
    if not set(cycles) <= {CONTRACTION, OUTSIDE}:
        raise ValueError(f"Unrecognised cycle groups: {set(cycles)}")
    return {"start": start, "end": response.END, "eligibleMeetings": len(subset), "predictorMeetings": predictor_count(subset),
            "groups": {"leader": summarise_groups(group_rows(subset, "leader")), "cycle": summarise_groups(cycles)},
            "cycleContrast": contrast(cycles)}


def build(data):
    cohorts = json.loads((data / "stance-cohorts.json").read_text())["banks"]
    banks = {}
    for b in cohorts:
        bank = b["id"]
        history = {r["date"]: r for r in b["records"]}
        source = json.loads((data / f"{bank}-cross-asset-events.json").read_text())
        rows = []
        for r in source["records"]:
            if r["stage"] != "release" or r["type"] != "decision" or not r["groupEligible"]:
                continue
            if not response.START <= r["date"] <= response.END:
                continue
            h = history[r["date"]]
            if h["leader"] != r["leader"]:
                raise ValueError(f"Leader mismatch on {bank} {r['date']}")
            rows.append({**r, "cycle": h["cycle"]})
        if len(rows) != len({r["date"] for r in rows}):
            raise ValueError(f"Duplicate eligible announcement in {bank}")
        rows.sort(key=lambda r: r["date"])
        banks[bank] = {"label": b["label"], "sourceUrl": source["source"]["url"],
                       "cycleLabel": b["cycleLabel"], "cycleMethod": b["cycleMethod"],
                       "cycleSourceUrl": b["cycleSources"][0]["url"],
                       "frames": {"full": frame(rows, response.START), "common": frame(rows, response.COMMON_START)}}
    return {"method": METHOD, "banks": banks}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=DATA)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    dest = args.data / "policy-regimes.json"
    raw = json.dumps(build(args.data), ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.check:
        if not dest.exists() or raw != dest.read_text():
            raise SystemExit("Regenerate the policy-regime estimates.")
    else:
        dest.write_text(raw)
