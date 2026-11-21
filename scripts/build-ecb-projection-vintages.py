"""Build the ECB staff projection panel. Requires lxml.
Supply --table, --hicp and --gdp for an offline build using ECB source downloads.
"""
import argparse
import csv
import io
import json
import re
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen

from lxml import html

DATA = Path(__file__).resolve().parents[1] / 'dist/data'
TABLE = 'https://www.ecb.europa.eu/mopo/devel/ecana/html/table.en.html'
MPD = 'https://data-api.ecb.europa.eu/service/data/MPD/A.U2.{}.A..0000?format=csvdata'
SERIES = 'https://data.ecb.europa.eu/data/datasets/MPD/MPD.A.U2.{}.A.{}.0000'
FIRST_PUBLICATION = 'https://www.ecb.europa.eu/press/pr/date/2000/html/pr001116_1.en.html'
QUARTERLY_PUBLICATION = 'https://www.ecb.europa.eu/press/press_conference/monetary-policy-statement/2004/html/is040603.en.html'
JUNE_2025 = 'https://www.ecb.europa.eu/pub/pdf/other/eurosystemstaffprojectionsbreakdown202506.en.pdf'
MONTHS = {'March':3, 'June':6, 'September':9, 'December':12}
CODES = {3:'W',6:'G',9:'S',12:'A'}
START, END = '2000-03', '2026-09'


def read(path, url):
    if path:
        return path.read_bytes()
    with urlopen(Request(url,headers={'User-Agent':'ThePolicyTape/1.0'}),timeout=45) as response:
        return response.read()


def was_public(vintage):
    if vintage is None:
        return None
    return vintage >= '2004-09' or (vintage >= '2000-12' and vintage[-2:] in ('06', '12'))


def cell(text):
    # A leading figure followed by [low - high] is a released point plus its interval.
    # Older tables give only [low , high].
    text=' '.join(text.replace('−','-').split())
    head, _, tail=text.partition('[')
    low=high=None
    if tail:
        endpoints=re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*(?:,|\s-\s)\s*(-?\d+(?:\.\d+)?)\s*\]',tail)
        if not endpoints:
            raise ValueError('Unrecognised forecast interval '+text)
        low,high=map(float,endpoints.groups())
        if low>high:
            raise ValueError('Inverted forecast interval')
    if head.strip():
        value=float(head.strip())
        basis='Published point'
    elif low is not None:
        value=round((low+high)/2,3)
        basis='Midpoint of archived range'
    else:
        raise ValueError('Empty projection value')
    return value,basis,low,high


def table_values(raw):
    observations={}
    # Malformed ECB page markup places older vintage tables outside the main element.
    for table in html.fromstring(raw).xpath('//table'):
        cap=' '.join(table.xpath('string(.//caption)').split())
        m=re.match(r'(March|June|September|December) (\d{4})',cap)
        if not m:
            continue
        year=int(m[2])
        vintage=f'{year:04}-{MONTHS[m[1]]:02}'
        rows=table.xpath('.//tr')
        years=[c.text_content().strip() for c in rows[0].xpath('./th|./td')][1:]
        # The first two rows give the baseline. Some releases append adverse and severe scenarios.
        if [r.xpath("string(./th[1])").strip() for r in rows[1:3]] != ["HICP", "Real GDP"]:
            raise ValueError("Unrecognised baseline labels "+vintage)
        for row in rows[1:3]:
            fields=[' '.join(c.text_content().split()) for c in row.xpath('./th|./td')]
            if not fields or fields[0] not in ('HICP','Real GDP'):
                continue
            metric='hicp' if fields[0]=='HICP' else 'gdp'
            for target,text in zip(years,fields[1:]):
                if target.isdigit() and int(target)>=year:
                    k=(vintage,int(target),metric)
                    if k in observations:
                        raise ValueError(f'Duplicate HTML cell: {k}')
                    observations[k]=cell(text)
    return observations


def build(table_raw, sources):
    table=table_values(table_raw)
    official_vintages={v for v,_,_ in table if START<=v<=END}
    values={}
    for metric,raw in sources.items():
        for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
            if r['OBS_STATUS']!='F':
                continue
            stamp=re.search(r'(March|June|September|December) (\d{4})\s+staff macroeconomic projections',r['TITLE_COMPL'])
            if not stamp:
                raise ValueError('Unknown vintage '+r['TITLE_COMPL'])
            year=int(stamp[2])
            vintage=f'{year:04}-{MONTHS[stamp[1]]:02}'
            target=int(r['TIME_PERIOD'])
            if START<=vintage<=END and target>=year:
                k=(vintage,target,metric)
                if k in values:
                    raise ValueError(f'Duplicate forecast in MPD: {k}')
                values[k]=float(r['OBS_VALUE'])
    vintages=sorted({v for v,_,_ in values} | {v for v,_,_ in table if START<=v<=END})
    expected=[f'{y}-{m:02}' for y in range(2000,2027) for m in (3,6,9,12) if START<=f'{y}-{m:02}'<=END]
    if vintages!=expected:
        raise ValueError('Missing quarterly vintage in the official union')
    if official_vintages!={v for v in expected if v>='2000-12'}:
        raise ValueError('Missing vintage in the original ECB archive tables')
    def fetch(v,target,metric):
        k=(v,target,metric)
        if k in table:
            return table[k]
        if k in values:
            return values[k],'ECB database forecast',None,None
        return None,None,None,None
    rows=[]
    for i,v in enumerate(vintages):
        year,month=map(int,v.split('-'))
        code=CODES[month]+v[2:4]
        previous=vintages[i-1] if i else None
        for lead,horizon in ((0,'currentYear'),(1,'nextYear')):
            target=year+lead
            row=dict(vintage=v,targetYear=target,horizon=horizon,previousVintage=previous,
                     publicAtVintage=was_public(v),previousPublicAtVintage=was_public(previous),
                     hicpSeriesUrl=SERIES.format('HIC',code),gdpSeriesUrl=SERIES.format('YER',code))
            for metric in ('hicp','gdp'):
                value,basis,low,high=fetch(v,target,metric)
                if value is None:
                    raise ValueError(f'Missing current forecast {(v,target,metric)}')
                prior,prior_basis,*_=fetch(previous,target,metric)
                row.update({metric+'Pct':value,metric+'Basis':basis,metric+'LowPct':low,metric+'HighPct':high,
                            'previous'+metric.title()+'Pct':prior,'previous'+metric.title()+'Basis':prior_basis,
                            metric+'RevisionPp':round(value-prior,3) if prior is not None else None})
            h,g=row['hicpRevisionPp'],row['gdpRevisionPp']
            if h is None or g is None:
                pattern='No comparable prior'
            elif h>0 and g<0:
                pattern='Inflation up, growth down'
            elif h<0 and g>0:
                pattern='Inflation down, growth up'
            elif h>0 and g>0:
                pattern='Both up'
            elif h<0 and g<0:
                pattern='Both down'
            elif h==0 and g==0:
                pattern='Both unchanged'
            else:
                pattern='Only one changed'
            row.update(pattern=pattern,tableUrl=TABLE if (v,target,'hicp') in table else None)
            rows.append(row)
    def summarise(subset):
        result={'vintages':len(subset),'comparablePairs':sum(r['pattern']!='No comparable prior' for r in subset),
                'patterns':dict(Counter(r['pattern'] for r in subset))}
        for metric in ('hicp','gdp'):
            ns=[r[metric+'RevisionPp'] for r in subset if r[metric+'RevisionPp'] is not None]
            result[metric]=dict(n=len(ns),up=sum(x>0 for x in ns),down=sum(x<0 for x in ns),unchanged=ns.count(0))
        return result
    horizons={h:summarise([r for r in rows if r['horizon']==h]) for h in ('currentYear','nextYear')}
    disagree=[dict(vintage=v,targetYear=t,metric=m,releasedPct=table[v,t,m][0],databasePct=x)
              for (v,t,m),x in values.items() if (v,t,m) in table and abs(x-table[v,t,m][0])>.051 and int(v[:4])<=t<=int(v[:4])+1]
    latest=[r for r in rows if r['vintage']==vintages[-1]]
    extreme=[]
    for label in ('Inflation up, growth down','Inflation down, growth up'):
        sub=[r for r in rows if r['horizon']=='currentYear' and r['pattern']==label]
        extreme.append(max(sub,key=lambda r:abs(r['hicpRevisionPp'])+abs(r['gdpRevisionPp'])))
    return dict(coverage=dict(firstVintage=vintages[0],lastVintage=vintages[-1],vintages=len(vintages),
                tableVintages=len(official_vintages),publicVintages=sum(was_public(v) for v in vintages),targetRows=len(rows),
                comparableRows=sum(r['pattern']!='No comparable prior' for r in rows)),
                sources=dict(table=TABLE,hicpDatabase=MPD.format('HIC'),gdpDatabase=MPD.format('YER'),
                             publicationHistory=FIRST_PUBLICATION,quarterlyPublication=QUARTERLY_PUBLICATION,june2025Release=JUNE_2025),
                methods=[
                    'Each revision subtracts the immediately preceding quarterly vintage for the identical target calendar year. Current and next year refer to the year of the new vintage. Changes are percentage points in annual HICP inflation or real GDP growth.',
                    'Values come first from the ECB published archive tables. A published point takes precedence over any accompanying interval. An archive table giving only a range is represented by its arithmetic midpoint. For the three pre-publication exercises available only in the ECB Macroeconomic Projection Database (MPD), we use the database forecast observation.',
                    'The Eurosystem first published its projections in December 2000 and initially released only June and December exercises. March and September exercises became public from September 2004. Both current and prior rows carry a publication flag. Vintage months identify exercises; they do not establish the precise release date or the information available at a particular meeting.',
                    'The euro-area aggregate follows each vintage’s composition. Growth and price revisions can reflect changed assumptions, new information and data revisions. Counts use the reported precision. Examples select the largest sum of absolute current-year revisions for each direction of disagreement.',
                ],horizons=horizons, crossSourceDifferences=disagree, examples=extreme,latest=latest,records=rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('table','hicp','gdp'):
        p.add_argument('--'+name,type=Path)
    p.add_argument('--check',action='store_true')
    args=p.parse_args()
    result=build(read(args.table,TABLE),{'hicp':read(args.hicp,MPD.format('HIC')),'gdp':read(args.gdp,MPD.format('YER'))})
    buf=io.StringIO(newline='')
    writer=csv.DictWriter(buf,fieldnames=list(result['records'][0]),lineterminator='\n')
    writer.writeheader()
    writer.writerows(result['records'])
    files={'ecb-projection-vintages.json':(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode(),
           'ecb-projection-vintages.csv':buf.getvalue().encode('utf-8-sig')}
    for name, contents in files.items():
        dest=DATA/name
        if args.check:
            if not dest.exists() or dest.read_bytes()!=contents:
                raise SystemExit('Refresh '+name)
        else:
            dest.write_bytes(contents)
