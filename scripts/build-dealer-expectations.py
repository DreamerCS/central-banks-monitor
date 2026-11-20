"""Rebuild the 24-meeting study. Requires openpyxl and lxml. --cache can reuse original downloads."""
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from lxml import html
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
PDF = json.loads((ROOT / 'scripts/dealer-expectations-pdf.json').read_text())
SHEETS = {
    '2023-07-26':'jul','2023-09-20':'sep','2023-11-01':'oct','2023-12-13':'dec',
    '2024-01-31':'jan','2024-03-20':'mar','2024-05-01':'apr-may','2024-06-12':'jun',
    '2024-07-31':'jul','2024-09-18':'sep','2024-11-07':'nov','2024-12-18':'dec'
}
SURVEYS = 'https://www.newyorkfed.org/medialibrary/media/markets/survey/'
BOARD = 'https://www.federalreserve.gov/newsevents/pressreleases/monetary'
MARKETS = {
    '2022-09-21': {'date':'2022-09-12','step':75,'p':80,'source':'IMF Global Markets Monitor, p. 2','url':'https://www.imfconnect.org/content/dam/imf/News%20and%20Generic%20Content/GMM/archive/GMM%20Sept%2012%2C%202022.pdf#page=2','note':'The IMF reported an 80% market-implied chance of a 75 bp hike. Its market discussion references fed funds and eurodollar futures. It gives no fixing time for the probability.'},
    '2024-09-18': {'date':'2024-09-09','step':-50,'p':25,'source':'Reuters reporting LSEG calculations','url':'https://www.kitco.com/news/off-the-wire/2024-09-09/us-dollar-regains-footing-traders-pare-bets-big-fed-rate-cut','note':'Reuters reported roughly a 25% chance of a half-point cut from LSEG’s US rate-futures calculations. The article describes intraday trading and gives no fixing time for those odds.'}
}

def get(url, file, cache):
    if cache and (cache / file).exists():
        return (cache / file).read_bytes()
    req = Request(url, headers={'User-Agent':'Mozilla/5.0','Accept':'*/*'})
    with urlopen(req, timeout=40) as response:
        content = response.read()
    if cache:
        (cache / file).write_bytes(content)
    return content


def pct(x):
    return round(x * 100, 5) if x is not None else None


def pdf_bins(record):
    if 'p' not in record:
        return []
    first = record['firstCutoff']
    bins = []
    for i, prob in enumerate(record['p']):
        low = None if i == 0 else round(first + (i-1)*.25 + .01, 2)
        if first == 0 and i == 1:
            low = 0
        high = None if i == 9 else first + i*.25
        if i == 0:
            label = '< 0.00%' if first == 0 else f'≤ {high:.2f}%'
        elif high is None:
            label = f'≥ {low:.2f}%'
        else:
            label = f'{low:.2f}–{high:.2f}%'
        bins.append({'low':low,'high':high,'label':label,'p':prob})
    return bins


def read_sheet(blob, day):
    it = load_workbook(BytesIO(blob), read_only=True, data_only=True).active.values
    headings = next(it)
    rows = [r for values in it if (r:=dict(zip(headings,values)))['panel_type']=='SPD' and r['horizon_date']==day]
    mode = {r['aggregation']:r for r in rows if r['question_tag']=='fftr_pathofmodes'}
    med = mode['pctl50']
    p = [r for r in rows if str(r['question_tag']).startswith('fftr_probdist_')]
    bins = [{'low':pct(r['bucket_low']), 'high':pct(r['bucket_high']), 'label':r['bucket_range'].replace('<=','≤').replace('>=','≥').replace(' - ','–'), 'p':pct(r['aggregation_value'])} for r in p if r['aggregation']=='avg']
    n = {r['aggregation_value'] for r in p if r['aggregation']=='count'}
    if bins and len(n)!=1:
        raise ValueError('Different respondent counts across probability bins')
    result = {'sent':med['survey_release_date'], 'due':med['survey_due_date'], 'mode':f"{pct(med['aggregation_value']):.2f}",'modeN':mode['count']['aggregation_value'],'modeQ':med['spd_question_number'], 'probQ':p[0]['spd_question_number'] if p else '2c','probN':next(iter(n),None),'bins':bins}
    if not p:
        result['reason'] = 'December’s distribution is for the end of the year, after the meeting.'
    return result


def range_from_statement(content):
    text = ' '.join(html.fromstring(content).text_content().split()).replace('‑','-')
    pair = re.search(r'target range for the federal funds rate (?:by [\d/]+ percentage point (?:to )?|at |to )([0-9/-]+) to ([0-9/-]+) percent',text)
    if not pair:
        raise ValueError('Unrecognised FOMC target-range decision')
    return [sum(float(Fraction(part)) for part in rate.split('-')) for rate in pair.groups()]


def collect(day, cache):
    year = day[:4]
    slug = PDF[day]['slug'] if day in PDF else SHEETS[day]
    base = f'{SURVEYS}{year}/{slug}-{year}'
    if day in PDF:
        rec = dict(PDF[day])
        rec['bins'] = pdf_bins(rec)
        for key in ('slug','firstCutoff','p'):
            rec.pop(key,None)
    else:
        source = base + '-data.xlsx'
        rec = read_sheet(get(source, source.rsplit('/',1)[1], cache), day)
        rec['workbook'] = source
    code = day.replace('-','')
    statement = BOARD + code + 'a.htm'
    rec.update({'meeting':day,'pdf':base+'-spd-results.pdf','statement':statement,
                'target':range_from_statement(get(statement,'fomc-'+code+'.htm',cache))})
    return rec


def main(cache):
    if cache:
        cache.mkdir(exist_ok=True, parents=True)
    dates = sorted(PDF.keys() | SHEETS.keys())
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(lambda d: collect(d,cache), dates))
    previous = .125  # 0–0.25% going into January 2022, as in the January FOMC statement.
    for row in records:
        midpoint = sum(row['target'])/2
        decimals = Decimal(row['mode'])
        actual = Decimal(str(midpoint)).quantize(decimals,rounding=ROUND_HALF_UP)
        row.update({'priorMid':previous,'midpoint':midpoint,'stepBp':round((midpoint-previous)*100),
                    'errorBp':int((actual-decimals)*100)})
        assert row['sent'] <= row['due'] < row['meeting']
        if row['bins']:
            hits = [i for i,b in enumerate(row['bins']) if (b['low'] is None or midpoint>=b['low']) and (b['high'] is None or midpoint<=b['high'])]
            assert len(hits)==1 and 97<=sum(b['p'] for b in row['bins'])<=103
            row['realisedBin']=hits[0]
        if row['meeting'] in MARKETS:
            row['market']=MARKETS[row['meeting']]
        previous = midpoint
    dest = ROOT/'dist/data/dealer-expectations.json'
    dest.write_text(json.dumps({'meetings':records},ensure_ascii=False,separators=(',',':'))+'\n')
    print(len(records),'decisions,',sum(bool(r['bins']) for r in records),'next-meeting distributions')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path)
    main(parser.parse_args().cache)
