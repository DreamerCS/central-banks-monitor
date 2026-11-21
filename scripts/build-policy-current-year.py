"""Apply the frozen 2000–2025 release-window fit to observed 2026 repricing."""
import argparse
import json
from pathlib import Path
from statistics import linear_regression

DATA = Path(__file__).resolve().parents[1] / 'dist/data'
AS_OF = '2026-11-20'
TRAINING_START, TRAINING_END = '2000-01-01', '2025-12-31'


def load(name):
    return json.loads((DATA / (name + '.json')).read_text())


def build():
    historical = load('policy-response-study')
    if (historical['period']['start'], historical['period']['end']) != (TRAINING_START, TRAINING_END):
        raise ValueError('The historical estimation period has changed')

    models, rows = {}, []
    for bank in load('stance-cohorts')['banks']:
        code = bank['id']
        if code not in ('fed', 'ecb'):
            continue
        market = load(code + '-cross-asset-events')
        source = market['source'].get('workbook', market['source']['url'])
        releases = {r['date']: r for r in market['records']
                    if r['type'] == 'decision' and r['stage'] == 'release' and r['groupEligible']}
        pairs = [(r['values']['ois1y'], r['values']['yield2y']) for day, r in releases.items()
                 if TRAINING_START <= day <= TRAINING_END
                 and r['values'].get('ois1y') is not None and r['values'].get('yield2y') is not None]
        x, y = zip(*pairs)
        beta, intercept = linear_regression(x, y)
        official_fit = historical['banks'][code]['predictors']['ois1y']['outcomes']['yield2y']
        if len(pairs) != official_fit['n'] or round(beta * 10, 6) != official_fit['slopePer10Bp']:
            raise ValueError(f'{code} historical fit no longer reproduces')

        models[code] = dict(n=len(pairs), interceptBp=round(intercept, 8),
                            slopePer10Bp=official_fit['slopePer10Bp'],
                            latestWindowDate=max(d for d in releases if d <= AS_OF),
                            sourceUrl=source)
        for event in bank['records']:
            day = event['date']
            if not TRAINING_END < day <= AS_OF:
                continue
            release = releases.get(day)
            values = release['values'] if release else {}
            ois, actual = values.get('ois1y'), values.get('yield2y')
            fitted = intercept + beta * ois if ois is not None and actual is not None else None
            eligible = event.get('priorGapEligible') and event.get('pricingGapBp') is not None
            rows.append(dict(
                bank=code, date=day, leader=event['leader'],
                officialUrl=event.get('releaseUrl') or event['url'], actionBp=event['actionBp'],
                priorMoveBp=round(event['priorMoveBp'], 6) if eligible else None,
                pricingGapBp=round(event['pricingGapBp'], 6) if eligible else None,
                priorMethod=event.get('priorMethod') if eligible else None,
                priorSource=event.get('priorPricingSource') if eligible else None,
                releaseStatus='Observed release window' if release else 'No eligible window in source edition',
                marketSource=source, ois1yBp=ois, yield2yBp=actual, slope2s10sBp=values.get('slope'),
                equityPct=values.get('equity'), fitted2yBp=round(fitted, 6) if fitted is not None else None,
                residual2yBp=round(actual - fitted, 6) if fitted is not None else None))
    if len({(r['bank'], r['date']) for r in rows}) != len(rows):
        raise ValueError('Duplicate official decision')
    return dict(asOf=AS_OF, trainingPeriod=dict(start=TRAINING_START, end=TRAINING_END), method=[
        'Each row is an official 2026 decision through the cutoff. Missing market windows or meeting-specific prior estimates are blank.',
        'The fitted two-year yield change applies the historical bank-specific intercept and slope to the observed one-year OIS move in the same release window. The residual equals the actual two-year move minus this fitted value. This is a contemporaneous comparison using the 2000–2025 coefficients. No 2026 data enter their estimation.',
        'Rates and the 10-year minus 2-year yield spread are changes in basis points. Equity returns are percentages. Fed priors are reconstructed using MP1; ECB priors require eligible meeting-specific deposit rate pricing.',
    ], models=models, records=sorted(rows, key=lambda r: (r['date'], r['bank'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    output = DATA / 'policy-current-year.json'
    result = json.dumps(build(), indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    if args.check:
        if not output.exists() or output.read_text() != result:
            raise SystemExit('Refresh policy-current-year.json')
    else:
        output.write_text(result)
