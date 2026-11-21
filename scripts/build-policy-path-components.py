"""Fit two-predictor regressions of asset changes around eligible Fed and ECB decisions."""
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
SHORT = {"fed": "currentMeeting", "ecb": "ois1m"}
SCALE = 5
METHOD = [
    "Each decision contributes one eligible release window from 2000–2025. The two predictors are the signed changes in a near-term rate and domestic one-year OIS, both measured in basis points. A complete case requires both prices and the selected asset. Selection is independent of news coverage.",
    "The Fed’s near-term measure is the current-meeting federal funds futures surprise (MP1). The ECB’s one-month OIS averages overnight rates across the contract horizon, so meeting timing and other expected decisions affect it. Both one-year OIS measures combine expected rates and risk premia.",
    "Each asset regression includes an intercept and the two signed repricings. Each coefficient is scaled to a 5 bp increase holding the other repricing fixed. A near-term increase with the one-year rate unchanged implies a change in the shape of the expected path. Same-window co-movements can reflect other information and changes in risk premia.",
    "Partial R-squared measures the share of residual asset variation explained by the selected predictor after controlling for the other. Conditional standard deviation measures the residual variation in that predictor after a linear fit on the other. Pointwise HC1 intervals use a normal 95% critical value and do not adjust for multiple comparisons or serial dependence.",
    "The sensitivity fit drops a meeting when either absolute predictor exceeds its own 95th percentile in the bank’s complete predictor pairs, keeping ties. The common-calendar fit spans 2004–2025, retaining each bank’s meeting dates and release window.",
    "The event-level residual is one-year repricing less the fitted one-year repricing given the short move, using an intercept estimated across all eligible paired decision dates for that bank. It is an in-sample statistical residual, not an independently identified policy shock. Event examples use the largest absolute residual and the strongest opposite-sign pair, measured by the smaller of the two absolute changes.",
]


def rounded(x):
    return round(x, 8) if x is not None else None


def sumsq(values):
    return math.fsum(v*v for v in values)


def dot(a, b):
    return math.fsum(x*y for x,y in zip(a,b))


def residuals(values, control):
    total = sumsq(control)
    if total <= 0:
        raise ValueError("No variation in covariate")
    slope = dot(values, control) / total
    return [v-slope*c for v,c in zip(values, control)], slope


def subtract_mean(values):
    mu = fmean(values)
    return [x-mu for x in values]


def coefficient(resid_x, resid_y, errors, beta, n):
    ssx = sumsq(resid_x)
    ssy = sumsq(resid_y)
    se = math.sqrt(n/(n-3) * sumsq([x*e for x,e in zip(resid_x,errors)])) / ssx
    return {"slopePer5Bp": rounded(SCALE*beta),
            "ci95": [rounded(SCALE*(beta-response.Z95*se)), rounded(SCALE*(beta+response.Z95*se))],
            "partialRSquared": rounded(max(0., min(1., 1 - sumsq(errors) / ssy))) if ssy else None,
            "conditionalSdBp": rounded(math.sqrt(ssx/(n-1))),
            "conditionalMinBp": rounded(min(resid_x)), "conditionalMaxBp": rounded(max(resid_x))}


def fit(rows):
    n = len(rows)
    result = {"n":n, "firstDate":min((r[0] for r in rows), default=None),
              "lastDate":max((r[0] for r in rows), default=None), "rSquared":None, "short":None, "path":None}
    if n <= 3:
        return result
    x = subtract_mean([r[1] for r in rows])
    z = subtract_mean([r[2] for r in rows])
    y = subtract_mean([r[3] for r in rows])
    if not sumsq(x) or not sumsq(z):
        return result
    xz, _ = residuals(x,z)
    zx, _ = residuals(z,x)
    if min(sumsq(xz)/sumsq(x),sumsq(zx)/sumsq(z)) < 1e-12:
        return result
    b = dot(y,xz)/sumsq(xz)
    c = dot(y,zx)/sumsq(zx)
    errors = [yi-b*xi-c*zi for yi,xi,zi in zip(y,x,z)]
    ygz, _ = residuals(y,z)
    ygx, _ = residuals(y,x)
    result.update(short=coefficient(xz,ygz,errors,b,n), path=coefficient(zx,ygx,errors,c,n),
                  rSquared=rounded(1-sumsq(errors)/sumsq(y)) if sumsq(y) else None)
    return result


def bank_result(bank, data, path_key="ois1y", start=response.START, end=response.END):
    path_label = response.INSTRUMENTS[bank]["ois1y"][0] if path_key == "ois1y" else "Next-meeting fed funds futures (MP2)"
    rows = [r for r in data["records"] if r["type"]=="decision" and r["stage"]=="release" and r["groupEligible"]
            and start <= r["date"] <= end]
    short = SHORT[bank]
    if len({r["date"] for r in rows}) != len(rows):
        raise ValueError(f"Duplicate release dates for {bank}")
    paired = sorted((r for r in rows if response.is_number(r["values"].get(short)) and response.is_number(r["values"].get(path_key))),
                    key=lambda r:r["date"])
    near = [r["values"][short] for r in paired]
    far = [r["values"][path_key] for r in paired]
    x,z = subtract_mean(near), subtract_mean(far)
    residual_path, gamma = residuals(z,x)
    short_cutoff = response.percentile(sorted(abs(v) for v in near), .95)
    path_cutoff = response.percentile(sorted(abs(v) for v in far), .95)
    rho = dot(x,z)/math.sqrt(sumsq(x)*sumsq(z))
    pairs = list(zip(near,far))
    summary = {"n":len(paired),"firstDate":paired[0]["date"],"lastDate":paired[-1]["date"],
               "shortPathCorrelation":rounded(rho),"shortPathVif":rounded(1/(1-rho*rho)),
               "sameSigns":sum(a*b>0 for a,b in pairs),"oppositeSigns":sum(a*b<0 for a,b in pairs),
               "withZero":sum(a*b==0 for a,b in pairs),"pathOnShortSlope":rounded(gamma),
               "pathOnShortInterceptBp":rounded(fmean(far)-gamma*fmean(near)),
               "shortAbs95Bp":rounded(short_cutoff),"pathAbs95Bp":rounded(path_cutoff),
               "signDefinition":"Strict signs of observed changes. Pairs with either observed value equal to zero are reported separately."}
    assets = {r["id"]:r for r in data["assets"]}
    outcomes = {}
    for key in response.OUTCOMES:
        observations = [(r["date"],x,z,r["values"][key]) for r,x,z in zip(paired,near,far)
                        if response.is_number(r["values"].get(key))]
        trim = [r for r in observations if abs(r[1]) <= short_cutoff and abs(r[2]) <= path_cutoff]
        common = [r for r in observations if r[0] >= response.COMMON_START]
        outcomes[key] = {**fit(observations), "label":assets[key]["label"],"unit":assets[key]["unit"],
                         "sensitivity":fit(trim), "commonCalendar":fit(common)}
    events = [{"date":r["date"],"shortBp":a,"pathBp":b,"residualPathBp":rounded(e),
               "values":{k:r["values"][k] for k in response.OUTCOMES if response.is_number(r["values"].get(k))},
               "officialSource":r.get("documentUrl") or r["sourceUrl"]}
              for r,a,b,e in zip(paired,near,far,residual_path)]
    highest = max(events,key=lambda e:abs(e["residualPathBp"]))
    examples = [{"date":highest["date"],"reason":("Largest absolute residual one-year repricing" if path_key == "ois1y" else "Largest absolute residual next-meeting repricing")}]
    opposite = [e for e in events if e["shortBp"]*e["pathBp"]<0]
    if opposite:
        strongest = max(opposite,key=lambda e:min(abs(e["shortBp"]),abs(e["pathBp"])))
        examples.append({"date":strongest["date"],"reason":"Largest opposite-sign pair by the smaller absolute move"})
    return {"label":"Federal Reserve" if bank=="fed" else "European Central Bank","eligibleMeetings":len(rows),
            "window":response.WINDOWS[bank],"sourceUrl":data["source"]["url"],"shortLabel":response.INSTRUMENTS[bank][short][0],
            "pathLabel":path_label,"pairSummary":summary,
            "outcomes":outcomes,"events":events,"examples":examples}


def next_meeting_study(fed):
    frames = {}
    for key, end in [("early", "2003-12-31"), ("benchmark", response.END)]:
        frame = bank_result("fed", fed, "nextMeeting", end=end)
        example_reasons = {}
        for example in frame["examples"]:
            example_reasons.setdefault(example["date"], []).append(example["reason"])
        examples = [{**r, "reason": " / ".join(example_reasons[r["date"]])} for r in frame["events"]
                    if r["date"] in example_reasons]
        outcomes = frame["outcomes"]
        for outcome in outcomes.values():
            # The separate benchmark already supplies a full calendar comparison.
            outcome.pop("commonCalendar")
        frames[key] = {"start": response.START, "end": end, "eligibleMeetings": frame["eligibleMeetings"],
                       "pairSummary": frame["pairSummary"], "outcomes": outcomes, "examples": examples, "events": frame["events"]}
    return {
        "shortLabel": "Current-meeting Fed target surprise (MP1)", "pathLabel": "Next-meeting fed funds futures (MP2)",
        "sourceUrl": fed["source"]["url"], "methodologyUrl": "https://www.frbsf.org/wp-content/uploads/wp2025-30.pdf",
        "description": "MP2 measures the change, around the current statement, in the rate implied for the next scheduled FOMC meeting. The San Francisco Fed uses contracts corresponding to that next meeting, adjusting the monthly average for the days before the next decision and the MP1 surprise. When the next meeting is close to month-end, the provider uses a later contract. The published MP2 enters this regression directly. It is distinct from one-year OIS repricing.",
        "method": "Each coefficient gives the asset change per 5 bp increase in the indicated futures measure holding the other fixed. The early frame includes all eligible releases in 2000–2003, including the first US one-year OIS observation in December 2003. The full-period benchmark repeats the identical two-futures specification and includes the early observations. Tail checks use each frame’s own 95th-percentile thresholds.",
        "frames": frames,
    }


def build(data):
    sources = {bank: json.loads((data / f"{bank}-cross-asset-events.json").read_text()) for bank in SHORT}
    return {"period": {"start": response.START, "end": response.END, "commonStart": response.COMMON_START},
            "method": METHOD, "banks": {bank: bank_result(bank, source) for bank, source in sources.items()},
            "fedNextMeeting": next_meeting_study(sources["fed"])}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data",type=Path,default=DATA)
    ap.add_argument("--check",action="store_true")
    args = ap.parse_args()
    text = json.dumps(build(args.data), ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    output = args.data/"policy-path-components.json"
    if args.check:
        if not output.exists() or text != output.read_text():
            raise SystemExit("Regenerate the path decomposition.")
    else:
        output.write_text(text)
