"""Estimate intraday co-movements from the bundled official event-window panel.

First generate dist/data/market-events.json from the official editions with
python scripts/build-market-events.py USMPD.xlsx Dataset_EA-MPD.xlsx
Run: python scripts/build-event-study.py
Dependencies: numpy, scipy. No network access is needed.
Optional: --verify-workbooks USMPD.xlsx Dataset_EA-MPD.xlsx (also needs openpyxl).
The optional cross-check verifies the pinned official workbook bytes, source flags,
units and observations against the bundled market panel before estimating.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import t as student_t


DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
WINDOW_FILE = DATA / "market-events.json"
VINTAGE = "2026-11-20"
SOURCES = {
    "fed": {
        "label": "San Francisco Fed · USMPD",
        "url": "https://www.frbsf.org/wp-content/uploads/USMPD.xlsx",
        "documentation": "https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/",
        "sha256": "2b91297c42cf692dd74f65eabf7ee97f81d452676e23fa02edb222bfa60f0d0a",
    },
    "ecb": {
        "label": "European Central Bank · EA-EMPD",
        "url": "https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx",
        "documentation": "https://www.ecb.europa.eu/press/research-publications/resbull/2020/html/ecb.rb200722~528ea64f0d.en.html",
        "sha256": "548abe37c07b2f4535b6a5a480918df3226aea9b1d65d5a74580894c83b3713b",
    },
}
PANEL_DIGEST = "5bfc14e7505361f380e186987f37d853ac868c68ad46018a008c3dbe175e7d85"
PERIODS = [
    {"id": "all", "label": "Full sample", "start": "2000-01-01", "end": VINTAGE},
    {"id": "pre2009", "label": "2000–2008", "start": "2000-01-01", "end": "2008-12-31"},
    {"id": "post2008", "label": "2009 onward", "start": "2009-01-01", "end": VINTAGE},
]
# USMPD Statements.Unscheduled, restricted to this panel's dates. These include
# operational and exceptional communications as well as intermeeting rate decisions.
US_UNSCHEDULED = set("""2001-01-03 2001-04-18 2001-09-17 2007-08-10 2007-08-17
2008-01-22 2008-03-11 2008-10-08 2010-05-09 2019-10-04 2020-03-03 2020-03-15
2020-03-19 2020-03-23 2020-03-31 2020-08-27""".split())
# These two GC_PR / GC_PC entries are only 15 minutes apart, compared with
# 30 or 45 minutes at every other covered meeting. Retain announcement windows.
ECB_EXCEPTIONAL = {"2001-09-17", "2008-10-08"}
LOW_RATE = {
    "fed": [("2008-12-16", "2015-12-15"), ("2020-03-15", "2022-03-15")],
    "ecb": [("2012-07-05", "2022-09-07")],
}
FACTORS = {
    "current": ("MP1", "Current meeting surprise", "Current-target surprise (bp)",
                "The futures-implied surprise in the target at the current FOMC meeting."),
    "next": ("MP2", "Next meeting repricing", "Next-meeting rate repricing (bp)",
             "The change in the futures-implied target for the next scheduled FOMC meeting. It can reflect both the current decision and news about the future."),
    "near": ("OIS_1M", "One-month OIS", "One-month OIS repricing (bp)",
             "The change in one-month euro overnight-indexed swap rates. A short-maturity market rate is a proxy for near-term policy pricing."),
    "path": ("OIS_1Y", "One-year OIS conditional on one month", "One-year OIS residual (bp)",
             "The change in one-year euro OIS holding the one-month change fixed. The scatter removes the fitted one-month component from both axes within the selected sample."),
}
SPECS = {
    "fed": [("statement", "current"), ("statement", "next"), ("conference", "next")],
    "ecb": [("statement", "near"), ("conference", "near"), ("statement", "path"), ("conference", "path")],
}
ASSETS = {
    "fed": ["UST2Y", "UST10Y", "EURUSD", "SP500"],
    "ecb": ["DE2Y", "DE10Y", "EURUSD", "STOXX50"],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rounded(x):
    return round(float(x), 7) or 0.0


def interval(value, se, critical):
    return [rounded(value - critical * se), rounded(value + critical * se)]


def regression(x, y, control=None):
    """OLS and HC3. The final column is always the variable of interest."""
    n = len(y)
    cols = [np.ones(n)]
    if control is not None:
        cols.append(control)
    cols.append(x)
    design = np.column_stack(cols)
    rank = design.shape[1]
    if n < 8 or np.linalg.matrix_rank(design) != rank:
        return None
    weights = np.linalg.pinv(design)
    coefficients = weights @ y
    residual = y - design @ coefficients
    leverage = np.einsum("ij,ji->i", design, weights)
    if np.max(leverage) >= 1 - 1e-10:
        return None
    robust_scores = weights * (residual / (1 - leverage))
    hc3 = robust_scores @ robust_scores.T
    return {
        "design": design, "weights": weights, "coefficients": coefficients,
        "residual": residual, "leverage": leverage, "hc3": hc3,
        "df": n - rank, "critical": student_t.ppf(0.975, n - rank),
    }


def slope(fit):
    beta = 10 * fit["coefficients"][-1]
    se = 10 * np.sqrt(fit["hc3"][-1, -1])
    return rounded(beta), interval(beta, se, fit["critical"])


def arrays(events, key, controlled):
    x = np.array([e["x"] for e in events])
    y = np.array([e["values"][key] for e in events])
    z = np.array([e["control"] for e in events]) if controlled else None
    return x, y, z


def event_flags(bank, date):
    flags = []
    if date in (US_UNSCHEDULED if bank == "fed" else ECB_EXCEPTIONAL):
        flags.append("exceptional")
    if "2020-01-01" <= date < "2022-01-01":
        flags.append("pandemic")
    if any(start <= date <= end for start, end in LOW_RATE[bank]):
        flags.append("low-rate")
    if "2008-01-01" <= date < "2009-01-01":
        flags.append("2008")
    return flags


def sensitivity(events, key, controlled, fit):
    leverage, residual = fit["leverage"], fit["residual"]
    rank = fit["design"].shape[1]
    mse = residual @ residual / fit["df"]
    cooks = residual**2 / (rank * mse) * leverage / (1 - leverage)**2
    high = int(np.argmax(leverage))
    influential = int(np.argmax(cooks))
    subsets = [
        ("exceptional", "Exclude exceptional announcements"),
        ("pandemic", "Exclude calendar 2020–2021"),
        ("low-rate", "Exclude near-zero policy periods"),
        ("2008", "Exclude calendar 2008"),
    ]
    jobs = [(flag, label, [e for e in events if flag not in e["flags"]], {}) for flag, label in subsets]
    for identifier, label, i in [
        ("max-leverage", "Exclude highest-leverage event", high),
        ("max-influence", "Exclude largest Cook’s distance", influential),
    ]:
        jobs.append((identifier, label, events[:i] + events[i+1:], {
            "excludedDate": events[i]["date"], "leverage": rounded(leverage[i]),
            "cooksDistance": rounded(cooks[i]), "excludedX": events[i]["x"],
            "excludedY": events[i]["values"][key],
        }))
    result = []
    for identifier, label, sub, info in jobs:
        if len(sub) == len(events) or len(sub) < 8:
            continue
        refit = regression(*arrays(sub, key, controlled))
        if refit is not None:
            estimate, ci = slope(refit)
            result.append({"id": identifier, "label": label, "n": len(sub), "beta10": estimate,
                           "ci95": ci, **info})
    return result


def estimate(events, key, period, eligible, controlled):
    usable = [e for e in events if key in e["values"]]
    if len(usable) < 8:
        return None
    x, y, z = arrays(usable, key, controlled)
    fit = regression(x, y, z)
    if fit is None:
        return None
    beta, ci = slope(fit)
    weights, residual = fit["weights"], fit["residual"]
    # Newey–West uses successive included events, not calendar days.
    scores = weights * residual
    hac = scores @ scores.T
    for lag in range(1, 4):
        cross = scores[:, lag:] @ scores[:, :-lag].T
        hac += (1 - lag / 4) * (cross + cross.T)
    hac *= len(usable) / fit["df"]
    rss = residual @ residual
    tss = (y - y.mean()) @ (y - y.mean())
    r2 = 1 - rss/tss if tss > 0 else None
    projection = None
    intercept = fit["coefficients"][0]
    plotted_x = x
    if controlled:
        zdesign = np.column_stack([np.ones(len(z)), z])
        px, py = np.linalg.lstsq(zdesign, x, rcond=None)[0], np.linalg.lstsq(zdesign, y, rcond=None)[0]
        projection = dict(zip(("xIntercept", "xSlope", "yIntercept", "ySlope"), map(rounded, [*px, *py])))
        plotted_x = x - zdesign @ px
        intercept = 0  # Both partial-regression axes are residuals after removing an intercept.
    return {
        "period": period, "asset": key, "n": len(usable), "eligible": eligible, "missing": eligible-len(usable),
        "from": usable[0]["date"], "through": usable[-1]["date"], "beta10": beta, "ci95": ci,
        "hac95": interval(10 * fit["coefficients"][-1], 10*np.sqrt(max(hac[-1, -1], 0)), fit["critical"]),
        "intercept": rounded(intercept), "r2": rounded(r2) if r2 is not None else None,
        "projection": projection, "xRange": [rounded(np.min(plotted_x)), rounded(np.max(plotted_x))],
        "xSD": rounded(np.std(plotted_x, ddof=1)),
        "sensitivity": sensitivity(usable, key, controlled, fit),
    }


def period_difference(events, key, controlled):
    """Post-2008 minus pre-2009 slope with separate intercepts and control slopes."""
    rows = [e for e in events if key in e["values"]]
    post = np.array([int(e["date"] >= "2009-01-01") for e in rows])
    if min(post.sum(), len(post)-post.sum()) < 8:
        return None
    x, y, z = arrays(rows, key, controlled)
    cols = [np.ones(len(y)), post, x]
    if controlled:
        cols.extend([z, z*post])
    cols.append(post*x)
    design = np.column_stack(cols)
    if np.linalg.matrix_rank(design) != design.shape[1]:
        return None
    weights = np.linalg.pinv(design)
    coefs = weights @ y
    h = np.einsum("ij,ji->i", design, weights)
    if h.max() >= 1-1e-10:
        return None
    se = np.linalg.norm(weights[-1] * (y-design@coefs)/(1-h))
    df = len(y) - design.shape[1]
    b = coefs[-1]
    return {"asset": key, "beta10Difference": rounded(10*b), "ci95": interval(10*b, 10*se, student_t.ppf(.975, df)),
            "pValue": rounded(2*student_t.sf(abs(b/se), df)) if se>0 else None}


def classified_summary(events, assets):
    grouped = []
    for state in ("tightening", "easing", "balanced", "unclear"):
        rows = [e for e in events if e.get("guidance") == state]
        if not rows:
            continue
        values = {}
        for key in assets:
            yy = [e["values"][key] for e in rows if key in e["values"]]
            if yy:
                values[key] = {"n": len(yy), "median": rounded(np.median(yy))}
        grouped.append({"state": state, "n": len(rows), "assets": values})
    return grouped


def build_spec(bank, window, factor, guidance):
    bankid = bank["id"]
    xfield, label, xlabel, definition = FACTORS[factor]
    control = factor == "path"
    keys = ASSETS[bankid]
    instrument = {v["id"]: v for v in bank["assets"]}
    source = [e for e in bank["events"] if window in e["windows"]]
    excluded = sorted(ECB_EXCEPTIONAL) if bankid == "ecb" and window == "conference" else []
    eligible = [e for e in source if e["date"] not in excluded]
    rows = []
    for e in eligible:
        date, prices = e["date"], e["windows"][window]
        if xfield not in prices or (control and "OIS_1M" not in prices):
            continue
        obs = {"date": date, "x": prices[xfield], "flags": event_flags(bankid, date),
               "values": {k: prices[k] for k in keys if k in prices}}
        if control:
            obs["control"] = prices["OIS_1M"]
        if (date, window) in guidance:
            obs["guidance"] = guidance[date, window]
        rows.append(obs)
    fits = []
    coverage = {}
    for p in PERIODS:
        chosen = [r for r in rows if p["start"] <= r["date"] <= p["end"]]
        count = sum(p["start"] <= r["date"] <= p["end"] for r in eligible)
        coverage[p["id"]] = {"eligible": count, "factorAvailable": len(chosen)}
        for k in keys:
            model = estimate(chosen, k, p["id"], count, control)
            if model:
                fits.append(model)
    breaks = [period_difference(rows, k, control) for k in keys]
    return {"id": f"{bankid}-{window}-{factor}", "bank": bankid, "window": window, "factor": factor,
            "label": label, "xLabel": xlabel, "description": definition, "windowDefinition": bank["windows"][window],
            "assets": [{"id": k, "label": instrument[k]["label"], "unit": instrument[k]["unit"]} for k in keys],
            "sourceWindowCount": len(source), "excludedWindowDates": excluded, "coverage": coverage,
            "events": rows, "fits": fits, "periodDifferences": [b for b in breaks if b],
            "guidance": classified_summary(rows, keys)}



def paired_windows(studies):
    """Compare two separately estimated slopes on the same policy dates.

    Date-matched HC3 influence contributions allow residuals from the two
    windows on a given date to covary in the conference-minus-statement contrast.
    """
    comparisons = []
    groups = {(s["bank"], s["factor"], s["window"]): s for s in studies}
    for bank, factor in [("fed", "next"), ("ecb", "near"), ("ecb", "path")]:
        statement = groups[bank, factor, "statement"]
        conference = groups[bank, factor, "conference"]
        windows = [{e["date"]: e for e in s["events"]} for s in (statement, conference)]
        shared = sorted(windows[0].keys() & windows[1].keys())
        for period in PERIODS:
            dates = [d for d in shared if period["start"] <= d <= period["end"]]
            for asset in ASSETS[bank]:
                valid = [d for d in dates if all(asset in panel[d]["values"] for panel in windows)]
                if len(valid) < 8:
                    continue
                fits = [regression(*arrays([panel[d] for d in valid], asset, factor=="path")) for panel in windows]
                if any(f is None for f in fits):
                    continue
                stat, conf = fits
                delta = 10 * (conf["coefficients"][-1] - stat["coefficients"][-1])
                influence = [f["weights"][-1] * f["residual"] / (1-f["leverage"]) for f in fits]
                se = 10 * np.linalg.norm(influence[1]-influence[0])
                a, aci = slope(stat)
                b, bci = slope(conf)
                comparisons.append({
                    "bank": bank, "factor": factor, "asset": asset, "period": period["id"],
                    "from": valid[0], "through": valid[-1], "nDates": len(valid),
                    "statementBeta10": a, "statementCI95": aci, "conferenceBeta10": b, "conferenceCI95": bci,
                    "conferenceMinusStatement": rounded(delta), "pairedCI95": interval(delta, se, stat["critical"]),
                })
    return comparisons


def verify_workbooks(paths, market):
    from openpyxl import load_workbook

    for bank, path in zip(market["banks"], paths):
        bankid = bank["id"]
        if digest(path) != SOURCES[bankid]["sha256"]:
            raise ValueError(f"{bankid}: official workbook differs from the pinned vintage")
        wb = load_workbook(path, read_only=True, data_only=True)
        official = {}
        exceptional_dates = set()
        if bankid == "fed":
            sheets = {"Statements": "statement", "Press Conferences": "conference"}
        else:
            sheets = {"EA-EMPD": None}
        for sheet, default_window in sheets.items():
            it = wb[sheet].values
            headers = next(it)
            for raw in it:
                if not raw[0] or not 2000 <= raw[0].year <= 2026:
                    continue
                date = raw[0].date().isoformat()
                q = dict(zip(headers, raw))
                window = default_window or {"GC_PR": "statement", "GC_PC": "conference"}.get(q["Event_type"])
                if not window:
                    continue
                if bankid == "fed" and window == "statement" and q["Unscheduled"] == 1:
                    exceptional_dates.add(date)
                official[date, window] = q
        if bankid == "fed" and exceptional_dates != US_UNSCHEDULED:
            raise ValueError("Unscheduled classification does not match the Fed workbook")
        if bankid == "ecb":
            short_gaps = {d for d, w in official if w == "conference" and (
                official[d, w]["Date_time"] - official[d, "statement"]["Date_time"]
            ).total_seconds() < 30*60}
            if short_gaps != ECB_EXCEPTIONAL:
                raise ValueError("Exceptional ECB windows do not match the publisher’s timestamps")
        inputs = {"fed": ["MP1", "MP2"], "ecb": ["OIS_1M", "OIS_1Y"]}[bankid] + ASSETS[bankid]
        checked = set()
        for r in bank["events"]:
            for w in ("statement", "conference"):
                if w not in r["windows"]:
                    continue
                d = r["date"]
                q = official[d, w]
                checked.add((d, w))
                for key in inputs:
                    raw = q["STOXX50E" if key == "STOXX50" else key]
                    value = r["windows"][w].get(key)
                    if not isinstance(raw, (int, float)):
                        if value is not None:
                            raise ValueError(f"Invented observation {bankid}, {d}, {w}, {key}")
                        continue
                    multiplier = 100 if bankid == "fed" and key in ("MP1", "MP2", "UST2Y", "UST10Y") else 1
                    if value is None or not np.isclose(raw*multiplier, value, rtol=0, atol=0.00000501):
                        raise ValueError(f"Market observation mismatch: {bankid}, {d}, {w}, {key}")
        if set(official) != checked:
            raise ValueError(f"{bankid}: source and archive event dates differ")
        wb.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-workbooks", nargs=2, type=Path, metavar=("USMPD", "EA_EMPD"))
    args = parser.parse_args()
    if digest(WINDOW_FILE) != PANEL_DIGEST:
        raise ValueError("Event panel has changed. Reconcile the source vintages and update their hashes first.")
    market = json.loads(WINDOW_FILE.read_text())
    if args.verify_workbooks:
        verify_workbooks(args.verify_workbooks, market)
    studies = []
    guidance_inputs = []
    for bank in market["banks"]:
        bankid = bank["id"]
        gp = DATA / ("policy-guidance.json" if bankid == "fed" else "ecb-guidance.json")
        guidance_inputs.append({"bank": bankid, "path": "data/" + gp.name, "sha256": digest(gp)})
        coded = {
            (r["date"], "conference" if r.get("sourceType") == "press-conference" else "statement"): r["state"]
            for r in json.loads(gp.read_text())["observations"]
        }
        for window, factor in SPECS[bankid]:
            studies.append(build_spec(bank, window, factor, coded))
    result = {
        "schemaVersion": 1, "title": "Intraday policy repricing and asset returns", "asOf": VINTAGE,
        "sources": list(SOURCES.values()), "periods": PERIODS, "specs": studies,
        "inputs": {"marketPanel": {"path": "data/market-events.json", "sha256": PANEL_DIGEST},
                   "guidancePanels": guidance_inputs},
        "pairedWindows": paired_windows(studies),
        "methodology": [
            "One observation per publisher event date and window. The USMPD includes exceptional communications outside scheduled meetings. The ECB panel uses Governing Council events. Meeting totals, speeches, minutes and cross-bank pooled regressions are excluded.",
            "Separate OLS regressions estimate changes in the two- and ten-year government yields (bp), EUR/USD (%) and the home equity index (%) for 10 bp of upward policy repricing in the same window. A positive EUR/USD change means euro appreciation. The scaling is a unit conversion; some windows contain very few moves that large.",
            "Current FOMC target surprises use fed-funds futures (MP1); next-meeting pricing uses MP2. MP1 is omitted from the conference models because the current decision is already public. The two MP2 window models use the same futures definition. Conference observations begin in 2011 and compare a selected set of meetings with earlier statement-only releases.",
            "One-month euro OIS is the near-rate proxy. The alternative one-year model also includes one-month OIS. Its reported coefficient holds the one-month change fixed. For the scatter and fitted line, both axes are residualized against an intercept and one-month OIS separately within each asset and period. This proxy may contain term-premium and information news; it is not an identified structural shock.",
            "Intervals are two-sided 95% HC3 heteroskedasticity-robust intervals using a Student t critical value and residual degrees of freedom. hac95 provides a Bartlett Newey–West comparison with three lags in event order and the n/(n−p) correction. Models use available complete observations without imputation. Pre/post slope differences use an interaction with regime-specific intercepts and control slopes; p-values are unadjusted for multiple comparisons.",
            "The pre-period includes 2008; the post-period starts on 1 January 2009. Sensitivities separately omit all 2008 dates, 2020–2021, low-rate periods and exceptional announcements. Low-rate periods use the FOMC’s post-decision 0–0.25% target range, or an ECB deposit rate at or below zero, on announcement dates. These indicators can overlap.",
            "For the Fed the exceptional flag is the USMPD unscheduled indicator. For the ECB, 17 September 2001 and 8 October 2008 have exceptional 15-minute gaps between announcement and subsequent publisher timestamps. Their announcement data enter the base case. Their second windows are excluded from every conference model because the alignment is not comparable with normal press conferences.",
            "Each fit also removes the event with the largest hat-matrix leverage and, separately, the largest Cook’s distance. The source date, observed factor, outcome and diagnostics are retained. Charts and intervals use event dates rather than time-weighting. Within-window correlation can capture central-bank information about growth, simultaneous policy tools, overlapping shared market measurement, crisis conditions and other news; it is not a causal effect of the announced rate change.",
            "Paired-window results compare the statement and conference slopes using only dates with both windows, the same outcome and the same factor definition. The conference-minus-statement interval combines date-aligned HC3 influence contributions; it allows cross-window residual correlation on each date. Different news composition and window durations still limit interpretation.",
            "Guidance medians describe only manually reviewed statements or conferences matched by exact bank, date and communication window. Unreviewed dates are not assigned a state. Medians are descriptive for a selected set, without weights or a causal interpretation. Overlapping window/factor samples must not be added as independent observations.",
        ],
    }
    path = DATA / "event-study.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)+"\n")
    tmp.replace(path)
    for s in studies:
        print(s["id"],len(s["events"]),"events,",len(s["fits"]),"period/asset fits")


if __name__ == "__main__":
    main()
