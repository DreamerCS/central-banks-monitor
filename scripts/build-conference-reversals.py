"""Compare signed one-year OIS moves in two distinct official intraday windows."""
import argparse
import csv
import io
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median

DATA = Path(__file__).resolve().parents[1] / 'dist/data'
END = '2025-12-31'
CUTOFF = '2026-11-20'
STAGES = ('release', 'conference', 'combined')
METRICS = {'ois1yBp': 'ois1y', 'yield2yBp': 'yield2y', 'slope2s10sBp': 'slope', 'equityPct': 'equity'}
TOLERANCES = (1, 2, 5)


def number(value):
    return None if value is None or value == '' else float(value)


def field(stage, metric):
    return stage + metric[0].upper() + metric[1:]


def quantile(values, p):
    k = p * (len(values) - 1)
    return values[int(k)] + (k % 1) * (values[math.ceil(k)] - values[int(k)])


def metric(values):
    s = sorted(x for x in values if x is not None)
    return dict(n=len(s), median=round(median(s), 7) if s else None,
                medianAbs=round(median(abs(x) for x in s), 7) if s else None,
                q25=round(quantile(s, .25), 7) if s else None, q75=round(quantile(s, .75), 7) if s else None)


def direction(row, threshold):
    x, y = row['releaseOis1yBp'], row['conferenceOis1yBp']
    if not row['pairEligible'] or x is None or y is None:
        return 'missing'
    if min(abs(x), abs(y)) <= threshold:
        return 'quietOrSmall'
    return 'opposite' if x*y < 0 else 'reinforce'


def magnitude_class(row):
    release, conference = row['releaseOis1yBp'], row['conferenceOis1yBp']
    delta = round(abs(conference)-abs(release), 7)
    return 'partialGiveback' if delta < 0 else 'netOvertake' if delta > 0 else 'exactOffset'


def brief(rows, threshold):
    counts = Counter(direction(r, threshold) for r in rows)
    directional = counts['opposite'] + counts['reinforce']
    return dict(thresholdBp=threshold, pairedN=len(rows)-counts['missing'], quietOrSmallN=counts['quietOrSmall'],
                directionalN=directional, oppositeN=counts['opposite'], reinforceN=counts['reinforce'],
                reversalShare=round(counts['opposite']/directional, 7) if directional else None)


def summary(rows, threshold):
    result = brief(rows, threshold)
    groups = {name:[r for r in rows if direction(r, threshold) == name] for name in ('opposite','reinforce')}
    opp = groups['opposite']
    over = Counter(magnitude_class(r) for r in opp)
    usable = [r for r in opp if r['combinedOis1yBp'] is not None]
    full = [r['combinedOis1yBp'] * r['releaseOis1yBp'] for r in usable]
    result.update(partialGivebackN=over['partialGiveback'], exactOffsetN=over['exactOffset'], netOvertakeN=over['netOvertake'],
                  fullWindowN=len(usable), fullWindowOppositeToReleaseN=sum(v<0 for v in full),
                  fullWindowSameAsReleaseN=sum(v>0 for v in full), fullWindowZeroN=full.count(0))
    result['groups']={name:dict(n=len(values),stages={stage:{k:metric(r[field(stage,k)] for r in values)
                         for k in METRICS} for stage in STAGES}) for name, values in groups.items()}
    return result


def build(data):
    def read(stem):
        return json.loads((data/(stem+'.json')).read_text())
    with (data/'policy-research-meetings.csv').open(encoding='utf-8-sig',newline='') as f:
        history={(r['bank'],r['date']):r for r in csv.DictReader(f)}
    all_rows, banks = [], {}
    for bank in read('stance-cohorts')['banks']:
        code = bank['id']
        if code not in ('fed','ecb'):
            continue
        package=read(code+'-cross-asset-events')
        windows={}
        for r in package['records']:
            if (r['stage'],r['type']) in {('release','decision'),('conference','conference'),('combined','decision')}:
                key=(r['date'],r['stage'])
                if key in windows:
                    raise ValueError(f'Duplicate {code} window: {key}')
                windows[key]=r
        rows=[]
        for event in bank['records']:
            day=event['date']
            if not '2000-01-01' <= day <= CUTOFF:
                continue
            old=history.get((code,day))
            if day<=END and old is None:
                raise ValueError(f'Missing historical decision in ledger: {code} {day}')
            row=dict(bank=code,date=day,leader=event['leader'],period='historical' if day<=END else '2026 YTD',
                     officialUrl=event.get('releaseUrl') or event['url'],marketSource=package['source']['url'])
            for stage in STAGES:
                window=windows.get((day,stage))
                eligible=bool(window and window['groupEligible'])
                row[stage+'Eligible']=eligible
                row[stage+'Window']=window['window'] if window else ''
                for k,v in METRICS.items():
                    value=window['values'].get(v) if eligible else None
                    if old is not None and stage in ('release','conference'):
                        ledger_name=k if stage=='release' else field('conference',k)
                        ledger_value=number(old[ledger_name])
                        if eligible != (old[stage+'Eligible']=='1') or (eligible and value!=ledger_value):
                            raise ValueError(f'Ledger/window mismatch: {code} {day} {stage} {k}')
                    row[field(stage,k)]=value
            row['pairEligible']=row['releaseEligible'] and row['conferenceEligible']
            row['classification1Bp']=direction(row,1)
            paired=row['pairEligible'] and row['releaseOis1yBp'] is not None and row['conferenceOis1yBp'] is not None
            row['twoWindowSumBp']=round(row['releaseOis1yBp']+row['conferenceOis1yBp'],7) if paired else None
            row['givebackClass']=magnitude_class(row) if row['classification1Bp']=='opposite' else ''
            rows.append(row)
        past=[r for r in rows if r['period']=='historical']
        current=[r for r in rows if r['period']=='2026 YTD']
        counts=brief(past,1)
        cases=[r for r in past if r['classification1Bp']=='opposite' and r['combinedOis1yBp'] is not None
               and all(r[field(stage,k)] is not None for stage in STAGES for k in METRICS)]
        examples=[]
        for positive in (True,False):
            pool=[r for r in cases if (r['releaseOis1yBp']>0)==positive]
            if pool:
                examples.append(max(pool,key=lambda r:abs(r['conferenceOis1yBp'])))
        leaders=[]
        for name in dict.fromkeys(r['leader'] for r in past):
            subset=[r for r in past if r['leader']==name]
            stats=brief(subset,1)
            stats.update(leader=name,officialN=len(subset))
            if stats['directionalN']<8:
                stats['reversalShare']=None
            leaders.append(stats)
        banks[code]=dict(coverage=dict(officialDecisions=len(past),releaseEligibleN=sum(r['releaseEligible'] for r in past),
                     pairedStageN=sum(r['pairEligible'] for r in past),pairedOisN=counts['pairedN']),
                     thresholds=[summary(past,t) for t in TOLERANCES],leaders=leaders,examples=examples,
                     holdout2026=dict(through=CUTOFF,officialDecisions=len(current),thresholds=[summary(current,t) for t in TOLERANCES]))
        all_rows.extend(rows)
    methods=[
        'A pair requires a standard eligible policy release and conference on the same date plus a one-year OIS quote in both windows. A meeting is directional only if both absolute OIS changes strictly exceed the threshold. The reversal share divides opposite-sign pairs by directional pairs. Small and missing observations are reported separately.',
        'For opposite moves, a smaller conference move is a partial giveback; equal magnitudes exactly offset in the two-window sum; a larger conference move overtakes the release in that sum. The observed combined-window change is recorded separately. Its sign includes any gap between windows and can differ from the sum classification.',
        'Fed statement changes use 30-minute windows and conferences use 70-minute windows. The timing of a conference relative to its statement has varied, especially at early meetings. The ECB uses pre- and post-window median quotes and changed release times in July 2022. Each row gives its actual window labels. Conferences are longer than releases, so their absolute moves are not comparable per minute.',
        'Medians describe signed contemporaneous market moves; median absolute values describe magnitude. Steeper 2s10s means the ten-year yield rose relative to the two-year yield. Equity changes are in percent. Directional classes use OIS only; other asset counts depend on quote availability. Central-bank information, journalists’ questions and other news can coincide with a reversal.',
        'Leadership counts use the 1 bp rule and suppress shares below eight directional meetings. Examples select the largest absolute conference move for each release direction among opposite pairs with all displayed assets. Separate 2026 figures through the stated cutoff use the historical rules without changing any threshold.',
    ]
    return dict(period=dict(start='2000-01-01',end=END,holdoutThrough=CUTOFF),methods=methods,banks=banks),all_rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--data',type=Path,default=DATA)
    args=parser.parse_args()
    info,rows=build(args.data)
    out=io.StringIO(newline='')
    writer=csv.DictWriter(out,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    files={'conference-reversals.csv':out.getvalue().encode('utf-8-sig'),
           'conference-reversals.json':(json.dumps(info,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()}
    for k,content in files.items():
        path=args.data/k
        if args.check:
            if not path.exists() or path.read_bytes()!=content:
                raise SystemExit('Refresh '+k)
        else:
            path.write_bytes(content)
