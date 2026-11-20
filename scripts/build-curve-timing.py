"""US Treasury inversion and the next announced FOMC target cut.

Uses Python's standard library. From the repository root:
  python scripts/build-curve-timing.py --save-inputs /tmp/curve-inputs
  python scripts/build-curve-timing.py --input-dir /tmp/curve-inputs

For the published snapshot the exact ALFRED downloads and bundled USMPD announcement
panel are pinned. --as-of accepts newer vintages once the meeting panel includes all
corresponding target changes. --output allows independent replication and comparison.
"""
import argparse
from bisect import bisect_right
import calendar
from collections import defaultdict
import csv
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen


DATA = Path(__file__).resolve().parents[1] / "dist/data"
START = date(2000, 1, 1)
WARMUP = date(1998, 12, 1)
VINTAGE = date(2026, 11, 20)
YIELDS = ("DGS3MO", "DGS6MO", "DGS2", "DGS10")
TARGETS = ("DFEDTAR", "DFEDTARL", "DFEDTARU")
THRESHOLDS = (12.5, 0, 25)
CURVES = {"twoSix": ("2Y minus 6M", "DGS2", "DGS6MO"), "tenThree": ("10Y minus 3M", "DGS10", "DGS3MO")}
PINNED = {
    "DGS3MO": "9510e390a1ec33035b0a57f0c8fee018b1c25a7ca074b994e67344afbc5657ad",
    "DGS6MO": "b789d2aa6f827defa4e5a9ade43f21301bd913f1cf61372742c2f029949174f0",
    "DGS2": "f5fd95cab3fcb5e7bc083835ca330f20d8843dd7979f987618ba0116d81aa2b9",
    "DGS10": "bb2c4f5225c15f078564dcbfccb2206dcca0ec5069757e03b9d6e7f03772f607",
    "DFEDTAR": "324f2be2e1184a89c74d87b4dc13b03c30f57c2d779f4f5940dec5c8616ed019",
    "DFEDTARL": "70341c1b9d2b35defa20b0566d26c6fd41dd07f487a6fd5e95a0552d7d5bb8a7",
    "DFEDTARU": "bed30ceb3a94e22470e3f1cc7fa4a9f754c2b334dc706f8a50532443d97c8566",
    "calendar": "5bfc14e7505361f380e186987f37d853ac868c68ad46018a008c3dbe175e7d85",
}
GROUPS = {
    "all": "All observations",
    "pre2008": "2000–2007 entries",
    "year2008": "2008 entries",
    "post2008": "2009 onward entries",
    "aboveFloor": "Target upper bound above 0.25%",
    "afterHike": "Last target move was a hike",
    "outsideCrisis": "Follow-up excludes the acute 2008 crisis",
}
# Independently verified against US Treasury annual daily yield files, in source order.
TREASURY_CHECKS = {
    "2006-01-17": (438, 447, 433, 434),
    "2022-10-27": (413, 444, 430, 396),
    "2025-12-22": (364, 360, 344, 417),
    "2026-11-18": (434, 443, 480, 507),
}
SELECTIONS = {
    "episodes": "Fresh crossings, minimum 12 months apart",
    "crossings": "Every fresh crossing",
    "invertedDays": "Every qualifying inverted trading day",
}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def verify_pin(series, body, args):
    if args.as_of == VINTAGE and sha(body) != PINNED[series]:
        raise ValueError(f"Input {series} differs from the published vintage")


def load_series(series, args):
    url = ("https://alfred.stlouisfed.org/graph/alfredgraph.csv"
           f"?id={series}&cosd={WARMUP}&coed={args.as_of}&vintage_date={args.as_of}")
    filename = series + ".csv"
    if args.input_dir:
        body = (args.input_dir / filename).read_bytes()
    else:
        with urlopen(url, timeout=90) as response:
            body = response.read()
    verify_pin(series, body, args)
    if args.save_inputs:
        args.save_inputs.mkdir(parents=True, exist_ok=True)
        (args.save_inputs / filename).write_bytes(body)
    rows = csv.reader(io.StringIO(body.decode("utf-8-sig")))
    if next(rows) != ["observation_date", f"{series}_{args.as_of:%Y%m%d}"]:
        raise ValueError(f"Wrong series or vintage for {series}")
    parsed = {}
    prev = date.min
    for stamp, value in rows:
        day = date.fromisoformat(stamp)
        if day <= prev or not WARMUP <= day <= args.as_of:
            raise ValueError(f"Unexpected observation date in {series}: {stamp}")
        prev = day
        if value in ("", "."):
            continue
        # Work in integer basis points before subtracting the quoted Treasury rates.
        bp = Decimal(value) * 100
        if not bp.is_finite() or bp != bp.to_integral_value():
            raise ValueError(f"Invalid input precision: {series} {stamp} {value}")
        parsed[day] = int(bp)
    if not parsed:
        raise ValueError(f"Empty series: {series}")
    meta = {"id": series, "url": f"https://fred.stlouisfed.org/series/{series}",
            "download": url, "sha256": sha(body), "first": str(min(parsed)), "last": str(max(parsed))}
    return parsed, meta


def add_months(day, months):
    year, month0 = divmod(day.year * 12 + day.month - 1 + months, 12)
    month = month0 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def target_changes(series, event_dates, through):
    single, lower, upper = (series[name] for name in TARGETS)
    if set(lower) != set(upper) or set(single) & set(upper):
        raise ValueError("Overlapping or mismatched target periods")
    levels = {day: (val, val) for day, val in single.items()}
    levels.update({day: (lower[day], upper[day]) for day in upper})
    levels = {d: levels[d] for d in sorted(levels) if d <= through}
    if not levels or len(levels) != (max(levels) - min(levels)).days + 1:
        raise ValueError("The policy series must cover all calendar days")
    previous = None
    changes = []
    for series_day, value in levels.items():
        if value == previous:
            continue
        if value[0] > value[1]:
            raise ValueError(f"Invalid target range on {series_day}")
        if previous is not None:
            # A range transition can move its two bounds by different amounts.
            delta = value[1] - previous[1]
            if not delta or (value[0] - previous[0]) * delta <= 0:
                raise ValueError(f"Ambiguous target move on {series_day}")
            day = series_day
            if day >= START:
                candidates = [d for d in (day, day - timedelta(days=1)) if d in event_dates]
                if len(candidates) != 1:
                    raise ValueError(f"No unique FOMC announcement for target change {day}: {candidates}")
                day = candidates[0]
            changes.append({"day": day, "seriesDate": str(series_day), "direction": "cut" if delta < 0 else "hike",
                            "upperChangeBp": delta, "targetLower": value[0] / 100, "targetUpper": value[1] / 100})
        previous = value
    if any(a["day"] >= b["day"] for a, b in zip(changes, changes[1:])):
        raise ValueError("Target announcement sequence must be strictly increasing")
    return changes


def selections(days, slopes, threshold):
    rows = {name: [] for name in SELECTIONS}
    prior = None
    eligible_again = date.min
    for day in days:
        qualifies = slopes[day] < 0 if threshold == 0 else slopes[day] <= -threshold
        if qualifies:
            rows["invertedDays"].append(day)
            # The first available observation cannot itself establish a prior crossing.
            if prior is False:
                rows["crossings"].append(day)
                if day >= eligible_again:
                    rows["episodes"].append(day)
                    eligible_again = add_months(day, 12)
        prior = qualifies
    return {kind: [day for day in selected if day >= START] for kind, selected in rows.items()}


def following(dates, day):
    i = bisect_right(dates, day)
    return dates[i] if i < len(dates) else None


def origin_group(group, day, state, end):
    if group == "all":
        return True
    if group == "pre2008":
        return day.year < 2008
    if group == "year2008":
        return day.year == 2008
    if group == "post2008":
        return day.year > 2008
    if group == "aboveFloor":
        return state["targetUpper"] > 0.25
    if group == "afterHike":
        return state["direction"] == "hike"
    if group == "outsideCrisis":
        return end < date(2008, 9, 15) or day > date(2008, 12, 16)
    raise ValueError(group)


def percent(hits, total):
    return round(100 * hits / total, 2) if total else None


def summary(signal_days, months, benchmark):
    # The control dictionary already excludes ineligible or right-censored dates.
    sig = [d for d in signal_days if d in benchmark]
    n, hits = len(sig), sum(benchmark[d] for d in sig)
    base_n, base_hits = len(benchmark), sum(benchmark.values())
    pct, base_pct = percent(hits, n), percent(base_hits, base_n)
    by_year = defaultdict(list)
    for d, hit in benchmark.items():
        by_year[d.year].append(hit)
    year_rate = {y: sum(values) / len(values) for y, values in by_year.items()}
    matched = sum(year_rate[d.year] for d in sig) / n if n else None
    lift = round(100 * (hits / n - base_hits / base_n), 2) if n and base_n else None
    return {"months": months, "n": n, "hits": hits, "pct": pct,
            "baseN": base_n, "baseHits": base_hits, "basePct": base_pct, "liftPp": lift,
            "yearMatchedBasePct": round(100 * matched, 2) if matched is not None else None,
            "yearMatchedLiftPp": round(100 * (hits / n - matched), 2) if n else None}


def episode(day, days, slopes, state, cut, hike, through, six, twelve, changes):
    observed_hikes = [change for change in changes if change["direction"] == "hike"
                      and day < change["day"] <= (cut or through)]
    i = bisect_right(days, day) - 1
    return {"date": str(day), "slopeBp": slopes[day], "priorDate": str(days[i - 1]), "priorSlopeBp": slopes[days[i - 1]],
            "targetUpper": state["targetUpper"], "lastMove": state["direction"],
            "nextCut": str(cut) if cut else None, "daysToCut": (cut - day).days if cut else None,
            "nextHike": str(hike) if hike else None, "hikesObservedBeforeCutOrEnd": len(observed_hikes),
            "hikeBpBeforeCutOrEnd": sum(change["upperChangeBp"] for change in observed_hikes),
            "hikeBeforeCut": (hike is not None and hike < cut) if cut else None,
            "observedDays": (through - day).days, "hit6": six.get(day), "hit12": twelve.get(day)}


def build(args):
    series, sources = {}, []
    for name in YIELDS + TARGETS:
        series[name], meta = load_series(name, args)
        sources.append(meta)
    body = (DATA / "market-events.json").read_bytes()
    verify_pin("calendar", body, args)
    bank = next(b for b in json.loads(body)["banks"] if b["id"] == "fed")
    event_dates = {date.fromisoformat(row["date"]) for row in bank["events"] if "statement" in row["windows"]}
    sources.append({"id": "calendar", "url": bank["source"], "download": "https://www.frbsf.org/wp-content/uploads/USMPD.xlsx",
                    "localPanel": "data/market-events.json", "sha256": sha(body)})
    common = set.intersection(*(set(series[key]) for key in YIELDS))
    through = min(max(common), max(series["DFEDTARU"]))
    days = sorted(day for day in common if day <= through)
    origins = [d for d in days if d >= START]
    if len(origins) < 2000 or days[0] > add_months(START, -12):
        raise ValueError("Incomplete yield series or warm-up")
    # An announcement on the last yield date may have taken effect the next day.
    changes = [c for c in target_changes(series, event_dates, args.as_of) if c["day"] <= through]
    change_days = [c["day"] for c in changes]
    cuts = [c["day"] for c in changes if c["direction"] == "cut"]
    hikes = [c["day"] for c in changes if c["direction"] == "hike"]
    states = {d: changes[bisect_right(change_days, d) - 1] for d in origins}
    if changes[0]["day"] >= origins[0]:
        raise ValueError("No verified prior target action")
    next_cut = {d: following(cuts, d) for d in origins}
    benchmarks = {}
    for period in (6, 12):
        for group in GROUPS:
            outcomes = {}
            for d in origins:
                end = add_months(d, period)
                if end <= through and origin_group(group, d, states[d], end):
                    outcomes[d] = next_cut[d] is not None and next_cut[d] <= end
            benchmarks[group, period] = outcomes

    monthly = {}
    for d in origins:
        monthly[d.strftime("%Y-%m")] = {"date": str(d), "targetUpper": states[d]["targetUpper"]}
    headlines, sensitivity = [], []
    for curve, (label, long_leg, short_leg) in CURVES.items():
        slopes = {d: series[long_leg][d] - series[short_leg][d] for d in days}
        for row in monthly.values():
            row[curve + "Bp"] = slopes[date.fromisoformat(row["date"])]
        for threshold in THRESHOLDS:
            selected = selections(days, slopes, threshold)
            for mode, sig in selected.items():
                for group in GROUPS:
                    horizons = [summary(sig, n, benchmarks[group, n]) for n in (6, 12)]
                    sensitivity.append({"curve": curve, "thresholdBp": threshold, "group": group,
                                        "selection": mode, "horizons": horizons})
                    if threshold == THRESHOLDS[0] and mode == "episodes" and group == "all":
                        episodes = [episode(d, days, slopes, states[d], next_cut[d], following(hikes, d),
                                            through, benchmarks["all", 6], benchmarks["all", 12], changes) for d in sig]
                        headlines.append({"id": curve, "label": label, "thresholdBp": threshold,
                                          "horizons": horizons, "episodes": episodes})
    for month, row in monthly.items():
        row["month"] = month
        row["partial"] = date.fromisoformat(row["date"]).replace(day=1) == args.as_of.replace(day=1) and (
            args.as_of.day < calendar.monthrange(args.as_of.year, args.as_of.month)[1])
    published_changes = [{**{k: v for k, v in c.items() if k != "day"}, "date": str(c["day"])}
                         for c in changes if c["day"] >= START]
    checks = []
    for stamp, expected in TREASURY_CHECKS.items():
        day = date.fromisoformat(stamp)
        if day > through:
            continue
        actual = tuple(series[code][day] for code in YIELDS)
        if actual != expected:
            raise ValueError(f"Published Treasury and ALFRED quotes disagree on {day}: {actual} {expected}")
        checks.append({"date": stamp, "yieldsPct": {k: v / 100 for k, v in zip(YIELDS, actual)},
                       "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
                              f"?data=daily_treasury_yield_curve&field_tdr_date_value={day.year}"})
    return {
        "schemaVersion": 1, "title": "How soon after inversion does the Fed cut?",
        "asOf": str(args.as_of), "start": str(origins[0]), "through": str(through),
        "commonDays": len(origins), "frequency": "Daily common trading dates",
        "headline": headlines, "monthly": list(monthly.values()), "sensitivity": sensitivity,
        "groups": GROUPS, "selections": SELECTIONS, "policyChanges": published_changes, "sources": sources,
        "sourceChecks": checks, "decisionReferences": [
            {"date": stamp, "url": f"https://www.federalreserve.gov/newsevents/pressreleases/monetary{stamp.replace('-', '')}a.htm"}
            for stamp in ("2007-09-18", "2022-11-02", "2024-09-18") if date.fromisoformat(stamp) <= through
        ],
        "methods": {
            "instrument": "Treasury constant-maturity yields in percent, quoted on an investment basis. Long yield minus short yield, in basis points. Thresholds compare the spread, not a probability or futures price.",
            "signal": "Main signal: today's spread is at or below −12.5 bp and the previous common trading day's spread was above −12.5 bp. Quotes are published to 1 bp precision. A strict negative spread and a threshold of −25 bp are separate sensitivities.",
            "episode": "Accept a fresh crossing only if at least 12 calendar months have elapsed since the last accepted crossing in that curve. Do not re-enter an existing inversion at its anniversary. The rate panel begins in December 1998 to initialize the rule before 2000. Follow-up windows do not overlap within each primary curve.",
            "outcome": "A hit is the first subsequent announced cut to the FOMC target (upper bound from 16 December 2008) strictly after signal close and no later than its six- or twelve-calendar-month anniversary. This includes further cuts in an easing cycle. When 'last move was a hike' is selected, a hit is the first cut after a hiking phase.",
            "timing": "All target changes from 2000 match exactly one San Francisco Fed statement on the ALFRED target-change date or the preceding calendar day. Use the announcement date, including intermeeting and Sunday decisions. The 16 December 2008 transition from 1% to 0–0.25% counts once. Asset purchases and guidance alone do not count.",
            "denominator": "Both signals and comparison trading days require complete follow-up through the last common date. Later observations are excluded at that horizon even if a cut is already observable. Null denotes incomplete follow-up or an empty group. All dates use the latest available common observation across four maturities; no interpolation or forward-filled yields.",
            "benchmark": "The unconditional base is the share of all eligible trading dates followed by a cut at the same horizon, subject to the same subgroup and maturity requirement. The year-matched base gives the eligible trading-day mean within each signal's entry year, then averages those means over signals. It guards against concentration in years with many cuts; it is a retrospective comparator.",
            "regimes": "Pre-2008 = 2000–2007; calendar 2008 is separate; post-2008 starts in 2009. Assignment uses signal date. The acute-crisis sensitivity removes signal-to-horizon intervals touching 15 September through 16 December 2008, inclusive. The above-floor group requires the target upper bound above 0.25% on entry.",
            "uncertainty": "Few distinct easing cycles. Primary signal windows are non-overlapping within each curve, but the two curves may share an event and base-day outcomes overlap. Percentages are descriptive sample frequencies. Treat all crossings and all inverted trading days as dependent sensitivity counts, not extra independent experiments.",
            "chart": "Monthly chart points are the last common observation in each month; the latest month may be partial. Signals and hits are computed from daily observations.",
            "scope": "The first subsequent cut can follow intervening hikes. Treasury slopes also reflect term premia, issuance, liquidity and risk expectations. No excess returns, transaction costs or causal effects are estimated.",
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=VINTAGE)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--save-inputs", type=Path)
    parser.add_argument("--output", type=Path, default=DATA / "curve-timing.json")
    args = parser.parse_args()
    result = build(args)
    args.output.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
    print(f"{result['commonDays']} complete Treasury dates: {result['start']} to {result['through']}.")
    for line in result["headline"]:
        print(line["id"], len(line["episodes"]), [(h["hits"], h["n"], h["basePct"]) for h in line["horizons"]])
