"""Extract Table 1 SEP medians and align like-for-like revisions with meeting windows."""
import argparse
import csv
import io
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / 'dist/data'
READINGS = BASE / 'fed-projection-readings.json'
START = '2015-09-17'
AS_OF = '2026-11-20'
PREFIX = 'https://www.federalreserve.gov/monetarypolicy/fomcprojtabl'
FACTORS = {'funds': 'Federal funds rate', 'growth': 'Change in real GDP',
           'inflation': 'PCE inflation', 'core': 'Core PCE inflation', 'unemployment': 'Unemployment rate'}


def read_source(day, folder):
    from lxml import html
    tree = html.fromstring((folder / (day.replace('-', '')+'.html')).read_bytes())
    tables = [t for t in tree.xpath('//table') if 'Federal funds rate' in t.text_content() and 'Central' in t.text_content()]
    if not tables:
        raise ValueError('No SEP median table on '+day)
    table = tables[0]
    cells = [[' '.join(c.text_content().split()) for c in row.xpath('./th|./td')] for row in table.xpath('.//tr')]
    columns = cells[1][1:] if cells[1][0] == 'Variable' else cells[1]
    assert cells[0][1].startswith('Median') and columns[0] == day[:4], day
    start = int(day[:4])
    years = [start, start+1]
    data = {}
    comparison = None
    for key, name in FACTORS.items():
        i = next(i for i, row in enumerate(cells) if re.sub(r'\d+$','',row[0]).strip().lower() == name.lower())
        current, previous = cells[i], cells[i+1]
        if 'projection' not in previous[0].lower() or (comparison and comparison != previous[0]):
            raise ValueError(f'Inconsistent previous vintage on {day}')
        comparison = previous[0]
        for y in years:
            index = columns.index(str(y)) + 1
            if y not in data:
                data[y] = {}
            def value(row):
                s = row[index].replace('−','-')
                return None if s in ('','n.a.','NA','–','—') else float(s)
            data[y][key] = [value(current),value(previous)]
    return dict(date=day,previousLabel=comparison,years=data)


def stage_quote(market, day, stage, name):
    r = market.get((day,stage))
    return r['values'].get(name) if r and r['groupEligible'] else None


def build(readings, market):
    rows = []
    for v in readings:
        day = v['date']
        for y, factors in v['years'].items():
            row = dict(date=day,targetYear=int(y),horizon='current' if int(y)==int(day[:4]) else 'next',
                       frame='historical' if day<'2026' else '2026 YTD',priorTableLabel=v['previousLabel'])
            for metric in FACTORS:
                new, old = factors[metric]
                row[metric+'MedianPct']=new
                row[metric+'PreviousPct']=old
                # Rates in bp, all macro forecast revisions in percentage points.
                row[metric+('RevisionBp' if metric=='funds' else 'RevisionPp')] = (
                    round((new-old)*(100 if metric=='funds' else 1),5) if old is not None and new is not None else None)
            for name, col in [('ois1y','Ois1yBp'),('yield2y','Yield2yBp'),('yield10y','Yield10yBp'),('slope','Slope2s10sBp'),('equity','EquityPct')]:
                for stage in ('release','conference'):
                    row[stage+col] = stage_quote(market,day,stage,name)
            row['projectionSource']=PREFIX+('e' if day=='2022-03-16' else '')+day.replace('-','')+'.htm'
            row['marketSource']='https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/'
            rows.append(row)
    return rows


def encode(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()


def install(path, data, check):
    if check:
        if data != path.read_bytes():
            raise SystemExit('Refresh '+path.name)
    else:
        path.write_bytes(data)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,help='Re-extract original FOMC Table 1 HTML files named YYYYMMDD.html.')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    events=json.loads((DATA/'fed-cross-asset-events.json').read_text())['records']
    market={(r['date'],r['stage']):r for r in events if r['stage'] in ('release','conference')}
    dates=sorted(r['date'] for r in events if r['stage']=='release' and r.get('sep') and START<=r['date']<=AS_OF)
    if args.source_dir:
        readings=[read_source(day,args.source_dir) for day in dates]
        install(READINGS,encode(readings),args.check)
    else:
        readings=json.loads(READINGS.read_text())
    if [r['date'] for r in readings]!=dates:
        raise ValueError('Source vintages do not match the official projection meeting calendar')
    rows=build(readings,market)
    out=io.StringIO(newline='')
    writer=csv.DictWriter(out,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    install(DATA/'fed-projection-vintages.csv',out.getvalue().encode('utf-8-sig'),args.check)
    install(DATA/'fed-projection-vintages.json',encode(rows),args.check)
