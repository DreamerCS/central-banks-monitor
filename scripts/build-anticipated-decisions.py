"""Study release-window repricing conditional on comparable pre-decision expectations."""
import argparse
import csv
import io
import json
import math
from collections import Counter
from pathlib import Path
from statistics import fmean, linear_regression, median, stdev

DATA = Path(__file__).resolve().parents[1] / 'dist/data'
START, END = '2000-01-01', '2025-12-31'
THRESHOLDS = (1, 3, 5, 10)
METRICS = ('ois1yBp', 'yield2yBp', 'slope2s10sBp', 'equityPct')
NUMERIC = ('actionBp', 'priorMoveBp', 'pricingGapBp', 'currentMeetingBp', 'yield10yBp', *METRICS)
TEXT = ('bank', 'date', 'leader', 'officialUrl', 'priorQuoteQualifier', 'priorMethod',
        'pricingSource', 'marketSource', 'releaseWindow', 'flags')
METHODS = [
    'The denominator is every official decision in the study period. Window comparisons are restricted to regular, eligible releases. Each asset uses all available paired observations in its group. Missing market values are excluded separately; a recorded zero is retained.',
    'The action gap is the announced move minus eligible meeting-specific prior pricing. The anticipated group includes absolute gaps up to and including the selected tolerance. The ECB reported-step group preserves conventional rate steps described as expected or fully priced. Unpriced covers missing data, early quotes and mismatched instruments. The tolerance describes the decision on the policy rate.',
    'For the Fed, a point target or the upper limit of the target range defines the action. The prior is reconstructed from the change in the target and MP1, the current-meeting futures surprise. The gap therefore reproduces MP1 by construction. Early ECB main refinancing rate proxies and stale quotes are excluded from deposit rate gap comparisons. The ECB primary sample uses three explicitly quantified forward-curve increments at the precision given by the source. Nine rounded expected or fully priced steps are documented separately. Some sources were published after the decision.',
    'Release windows use the scheduled FOMC statement from 10 minutes before to 20 minutes after, or ECB median quotes at 13:25–13:35 and 14:00–14:10 Frankfurt time before July 2022, then 13:55–14:05 and 14:30–14:40. The one-year OIS change covers expectations across multiple meetings as well as risk premia and other information in the same window. Rate changes are in basis points and equity returns in percent.',
    'The curve is the ten-year government yield less the two-year yield. Its direction uses paired observed curve and one-year OIS changes, with a positive curve change classified as steepening. The conditional counts additionally require an absolute OIS change above one basis point. Quartiles use linear interpolation. Threshold comparisons reuse the same events.',
]


def rounded(value):
    return round(value, 7) if value is not None else None


def quartile(sorted_values, fraction):
    pos = fraction * (len(sorted_values) - 1)
    base = int(pos)
    return sorted_values[base] + (pos - base) * (sorted_values[min(base + 1, len(sorted_values) - 1)] - sorted_values[base])


def metric(values):
    v = sorted(values)
    return dict(n=len(v), median=rounded(median(v) if v else None),
                q25=rounded(quartile(v, .25) if v else None), q75=rounded(quartile(v, .75) if v else None),
                medianAbs=rounded(median(abs(x) for x in v) if v else None))


# The source URLs and amounts are kept in the versioned meeting ledger. Only
# figures explicitly attributed to meeting-specific forward-curve increments
# are used for the ECB's primary numerical comparisons.
ECB_AUDIT = {
    '2015-12-03': ('reportedStep', 'The account describes a fully priced ten-basis-point cut and a further cut by September 2016. It gives neither the contract quote nor a precise observation time. A conventional cut size can coexist with some pricing of a larger move.'),
    '2022-12-15': ('reportedStep', 'In its discussion of the OIS curve the account says participants expected 50 bp in December and again in February. It reports an expected policy step without a separately quantified December curve increment.'),
    '2023-05-04': ('reportedCurveIncrement', 'The bulletin specifies a 34 bp May OIS increment and a separate 16 bp June increment as of the 3 May review cutoff. The May decision raised the deposit rate by 25 bp.'),
    '2023-06-15': ('reportedCurveIncrement', 'The account separately quantifies the forward curve at 25 bp for June and 25 bp for July. Its 20% probability of a further hike refers to a subsequent meeting. The exact quote time and sub-basis-point precision are unavailable.'),
    '2023-07-27': ('reportedCurveIncrement', 'The bulletin quantifies an additional 25 bp July hike in the OIS forward curve at the 26 July cutoff, separately from the projected peak rate. The figure has the resolution reported by the ECB.'),
    '2024-06-06': ('reportedStep', 'The account describes the cut as fully priced and also says that markets were almost certain of a quarter-point move. The risk-weighted meeting increment is not separately quantified.'),
    '2024-09-12': ('reportedStep', 'The dated bulletin describes the quarter-point cut as fully priced. Its separately quantified cumulative easing refers to the end of the year.'),
    '2024-10-17': ('reportedStep', 'The account describes the October and December quarter-point steps as priced in. The October bulletin characterises pre-meeting pricing as almost fully incorporating the cut.'),
    '2024-12-12': ('reportedStep', 'The bulletin describes a quarter-point cut as fully priced. The 133 bp figure is cumulative easing through June 2025.'),
    '2025-03-06': ('reportedStep', 'The bulletin describes the March quarter-point cut as fully priced and provides a distinct cumulative figure through year-end. It gives no separate risk-weighted March increment.'),
    '2025-04-17': ('reportedStep', 'The account says markets fully priced the expectation of a quarter-point cut. It does not report the underlying meeting quote.'),
    '2025-06-05': ('reportedStep', 'The account describes a quarter-point cut as fully priced and flags uncertainty about the timing of later easing. It does not separately quantify the June meeting quote.'),
}


def group(row, tolerance):
    if row['priorEvidenceType'] == 'reportedStep':
        return 'reportedStep'
    gap = row['comparisonGapBp']
    if gap is None:
        return 'unpriced'
    return 'anticipated' if abs(gap) <= tolerance else 'surprise'


def summarise(rows):
    metrics = {field: metric(r[field] for r in rows if r[field] is not None) for field in METRICS}
    path = [r['ois1yBp'] for r in rows if r['ois1yBp'] is not None]
    over1, over5 = [sum(abs(x) > t for x in path) for t in (1, 5)]
    pairs = [(r['ois1yBp'], r['slope2s10sBp']) for r in rows if r['ois1yBp'] is not None and r['slope2s10sBp'] is not None]
    def directions(subset):
        return dict(n=len(subset), steeper=sum(s > 0 for _, s in subset),
                    flatter=sum(s < 0 for _, s in subset), unchanged=sum(s == 0 for _, s in subset))
    return dict(n=len(rows), metrics=metrics,
                pathMove=dict(n=len(path), over1Bp=over1, over5Bp=over5,
                              shareOver1Bp=rounded(over1 / len(path)) if path else None,
                              shareOver5Bp=rounded(over5 / len(path)) if path else None),
                pairedCurve={**directions(pairs), 'oisUpOver1Bp': directions([p for p in pairs if p[0] > 1]),
                             'oisDownOver1Bp': directions([p for p in pairs if p[0] < -1])})


def residual_study(rows):
    pairs = [r for r in rows if r['bank'] == 'fed' and r['analysisEligible']
             and r['currentMeetingBp'] is not None and r['ois1yBp'] is not None]
    x, y = zip(*[(r['currentMeetingBp'], r['ois1yBp']) for r in pairs])
    beta, intercept = linear_regression(x, y)
    residuals = []
    for r in pairs:
        fit = intercept + beta * r['currentMeetingBp']
        residual = r['ois1yBp'] - fit
        residuals.append(residual)
        r.update(fittedOis1yBp=rounded(fit), residualOis1yBp=rounded(residual))
    ybar = fmean(y)
    sse = math.fsum(v*v for v in residuals)
    sst = math.fsum((v-ybar)**2 for v in y)
    ordered = sorted(pairs, key=lambda r: r['residualOis1yBp'])
    fields = ('date', 'officialUrl', 'marketSource', 'actionBp', 'pricingGapBp', 'currentMeetingBp',
              'ois1yBp', 'fittedOis1yBp', 'residualOis1yBp', 'yield2yBp', 'slope2s10sBp', 'equityPct')
    return dict(n=len(pairs), firstDate=min(r['date'] for r in pairs), lastDate=max(r['date'] for r in pairs),
                interceptBp=rounded(intercept), slopeBpPerBp=rounded(beta), rSquared=rounded(1 - sse / sst),
                residual=metric(residuals), residualSdBp=rounded(stdev(residuals)), rmseBp=rounded(math.sqrt(sse / len(pairs))),
                examples=[{k: r[k] for k in fields} for r in [*ordered[:3], *reversed(ordered[-3:])]],
                method='In-sample OLS of the one-year OIS change on the same-window current-meeting futures surprise with an intercept. Residuals describe variation left after this linear adjustment. They can reflect policy guidance, economic news, risk premia, market noise or other factors. Examples show the three largest positive and three largest negative residuals.')


def build(data):
    with (data / 'policy-research-meetings.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = []
        for input_row in csv.DictReader(f):
            if not START <= input_row['date'] <= END:
                continue
            row = {k: input_row[k] for k in TEXT}
            for k in NUMERIC:
                row[k] = float(input_row[k]) if input_row[k] else None
                if row[k] is not None and not math.isfinite(row[k]):
                    raise ValueError(f'Non-finite {k} on {row["date"]}')
            row['regularRelease'] = input_row['regularRelease'] == '1'
            row['releaseEligible'] = input_row['releaseEligible'] == '1'
            row['analysisEligible'] = row['regularRelease'] and row['releaseEligible']
            if row['pricingGapBp'] is not None and (row['actionBp'] is None or row['priorMoveBp'] is None
                    or not math.isclose(row['pricingGapBp'], row['actionBp']-row['priorMoveBp'], abs_tol=1e-6)):
                raise ValueError(f'Inconsistent action gap on {row["date"]}')
            raw_gap = row['pricingGapBp']
            if raw_gap is not None and row['bank'] == 'ecb':
                evidence, audit = ECB_AUDIT[row['date']]
            elif raw_gap is not None:
                evidence, audit = 'reconstructedMP1', ''
            elif row['priorMoveBp'] is not None:
                evidence, audit = 'incomparablePrior', ''
            else:
                evidence, audit = 'unavailable', ''
            row.update(priorEvidenceType=evidence, sourceAudit=audit,
                       comparisonGapBp=raw_gap if evidence in ('reportedCurveIncrement', 'reconstructedMP1') else None,
                       pricingStatus={'reportedStep':'rounded reported step', 'reportedCurveIncrement':'comparable',
                                      'reconstructedMP1':'comparable', 'incomparablePrior':'incomparable observed prior',
                                      'unavailable':'no observed prior'}[evidence])
            row.update(defaultGroup=group(row, 5) if row['analysisEligible'] else 'excluded',
                       fittedOis1yBp=None, residualOis1yBp=None)
            rows.append(row)
    if len(rows) != len({(r['bank'], r['date']) for r in rows}):
        raise ValueError('Duplicate bank and event date')
    banks = {}
    for bank in ('fed', 'ecb'):
        frame = [r for r in rows if r['bank'] == bank]
        eligible = [r for r in frame if r['analysisEligible']]
        raw = [r for r in eligible if r['pricingGapBp'] is not None]
        priced = [r for r in eligible if r['comparisonGapBp'] is not None]
        counts = Counter(r['pricingStatus'] for r in eligible)
        coverage = dict(allDecisions=len(frame), regularReleases=sum(r['regularRelease'] for r in frame),
                        eligibleReleases=len(eligible), rawComparableGaps=len(raw), comparableGaps=len(priced),
                        reportedSteps=counts['rounded reported step'],
                        pricedReleaseOis=sum(r['ois1yBp'] is not None for r in priced),
                        noObservedPrior=counts['no observed prior'], incomparablePrior=counts['incomparable observed prior'])
        thresholds=[]
        for t in THRESHOLDS:
            group_keys = ('anticipated', 'surprise', 'reportedStep', 'unpriced') if bank == 'ecb' else ('anticipated', 'surprise', 'unpriced')
            groups={g:summarise([r for r in eligible if group(r,t)==g]) for g in group_keys}
            assert sum(v['n'] for v in groups.values()) == len(eligible)
            thresholds.append(dict(thresholdBp=t, groups=groups))
        banks[bank]=dict(coverage=coverage,thresholds=thresholds)
        if bank == 'ecb':
            if {r['date'] for r in raw} != set(ECB_AUDIT):
                raise ValueError('Review the source wording for every ECB prior with a raw gap')
            fields = ('date','priorEvidenceType','priorMoveBp','pricingGapBp','comparisonGapBp','sourceAudit','pricingSource')
            banks[bank]['priorAudit'] = [{k:r[k] for k in fields} for r in raw]
            banks[bank]['reportedStepSensitivity'] = {
                'note': 'Descriptive sensitivity only. Treating conventional step amounts as point quotes reproduces the earlier grouping. Its bounds and shares depend on the rounding assumption.',
                'thresholdBp': 5,
                'anticipated': summarise([r for r in raw if abs(r['pricingGapBp']) <= 5]),
                'surprise': summarise([r for r in raw if abs(r['pricingGapBp']) > 5]),
            }
    return dict(period=dict(start=START,end=END),defaultThresholdBp=5,methods=METHODS,banks=banks,fedResidual=residual_study(rows)), rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--data', type=Path, default=DATA)
    args = parser.parse_args()
    study, rows = build(args.data)
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    files = {'anticipated-decisions.csv': out.getvalue().encode('utf-8-sig'),
             'anticipated-decisions.json': (json.dumps(study, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()}
    for filename, contents in files.items():
        path = args.data / filename
        if args.check:
            if not path.exists() or path.read_bytes() != contents:
                raise SystemExit('Refresh ' + filename)
        else:
            path.write_bytes(contents)
