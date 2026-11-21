"""Build event-window observations from the San Francisco Fed's USMPD workbook.

Run after build-stance-cohorts.py. Requires openpyxl, lxml and exchange-calendars.
Pass the USMPD workbook and a directory for Federal Reserve calendar HTML downloads.
Optional --data and --output select site inputs and output during a local rebuild.
"""
import argparse
import hashlib
import json
import math
import re
import runpy
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import exchange_calendars
from lxml import html
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
BOARD = 'https://www.federalreserve.gov'
DB = 'https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/'
WORKBOOK = 'https://www.frbsf.org/wp-content/uploads/USMPD.xlsx'
PAPER = 'https://www.frbsf.org/wp-content/uploads/wp2025-30.pdf'
TZ = ZoneInfo('America/New_York')
SHEETS = {'release':'Statements', 'conference':'Press Conferences', 'combined':'Monetary Events', 'minutes':'Minutes'}
TYPES = {'release':'decision','conference':'conference','combined':'decision','minutes':'minutes'}
TITLES = {'release':'FOMC policy announcement','conference':'FOMC press conference','combined':'FOMC announcement and press conference','minutes':'FOMC minutes release'}
# The Board calendar verifies the release dates for intermeeting announcements that
# are outside the archive of scored target-rate decisions.
OTHER_ANNOUNCEMENTS = {
    '2007-08-10': ('Liquidity support for the federal funds market', '20070810a'),
    '2007-08-17': ('FOMC assessment of credit conditions and growth risks', '20070817b'),
    '2008-03-11': ('Term Securities Lending Facility and expanded dollar swaps', '20080311a'),
    '2010-05-09': ('Central banks reopen temporary dollar liquidity swaps', '20100509a'),
    '2020-03-19': ('Temporary dollar swap lines with nine central banks', '20200319b'),
    '2020-03-23': ('Treasury and agency MBS purchases to support market functioning', '20200323a'),
    '2020-03-31': ('Repo facility for foreign and international monetary authorities', '20200331a'),
    '2020-08-27': ('Revision to the FOMC longer-run monetary policy strategy', '20200827a'),
}
# The October 4 videoconference was private. Its balance-sheet announcement was
# published at 11:00 ET on October 11. Do not move October 4 asset prices to that day.
PUBLICATION_CONFLICTS = {
    '2019-10-04': BOARD+'/newsevents/pressreleases/monetary20191011a.htm',
}
ASSETS = [
    ('equity','SP500','S&P 500','Equities','%','Cash index return. A positive value is an equity gain. Both quote intervals must be inside the NYSE cash session.'),
    ('yield2y','UST2Y','US 2Y Treasury','Rates','bp','Change in the benchmark two-year Treasury yield.'),
    ('yield10y','UST10Y','US 10Y Treasury','Rates','bp','Change in the benchmark ten-year Treasury yield.'),
    ('slope','SLOPE','US 2s10s','Rates','bp','Change in the ten-year yield minus the two-year yield. Positive means steepening.'),
    ('ois1y','OIS1Y','USD 1Y OIS','Rates','bp','One-year overnight indexed swap rate. An increase implies a higher rate over this horizon.'),
    ('eurusd','EURUSD','EUR/USD','FX','%','US dollars per euro. Positive means euro appreciation against the US dollar.'),
    ('usdjpy','USDJPY','USD/JPY','FX','%','Japanese yen per US dollar. Positive means dollar appreciation against the yen.'),
    ('dxy','DXY','US dollar index','FX','%','Dollar index return. Positive means broad dollar appreciation against its currency basket.'),
    ('equityFutures','SPFUT','S&P 500 E-mini futures','Equities','%','Front-contract futures return. Trading hours differ from those of the cash index.'),
    ('nextMeeting','MP2','Next meeting · fed funds futures','Rates','bp','Change in the fed funds rate expected for the next scheduled meeting. For minutes this refers to the upcoming decision.'),
    ('currentMeeting','MP1','Current meeting · fed funds futures','Rates','bp','Current-meeting target surprise inferred from fed funds futures. Minutes have no current decision.'),
    ('yield5y','UST5Y','US 5Y Treasury','Rates','bp','Change in the benchmark five-year Treasury yield.'),
    ('yield30y','UST30Y','US 30Y Treasury','Rates','bp','Change in the benchmark thirty-year Treasury yield.'),
    ('tips5y','TIPS5Y','US 5Y real yield','Inflation','bp','Change in the yield of the benchmark five-year inflation-protected Treasury.'),
    ('tips10y','TIPS10Y','US 10Y real yield','Inflation','bp','Change in the yield of the benchmark ten-year inflation-protected Treasury.'),
    ('breakeven5y','BE5','US 5Y inflation compensation','Inflation','bp','Nominal five-year yield change minus the TIPS yield change. Includes inflation risk and liquidity premia.'),
    ('breakeven10y','BE10','US 10Y inflation compensation','Inflation','bp','Nominal ten-year yield change minus the TIPS yield change. Includes inflation risk and liquidity premia.'),
]


def fetch_calendar(cache, key, url):
    path = cache / key
    if not path.exists():
        req = Request(url, headers={'User-Agent':'The Policy Tape research'})
        with urlopen(req,timeout=45) as response:
            content = response.read()
        path.write_bytes(content)
    return html.fromstring(path.read_bytes())


def official_sources(cache):
    cache.mkdir(parents=True,exist_ok=True)
    current_url = BOARD + '/monetarypolicy/fomccalendars.htm'
    rolling = fetch_calendar(cache, 'fomccalendars.html', current_url)
    dates = [int(x) for x in re.findall(r'fomcminutes(20\d\d)\d{4}\.htm',html.tostring(rolling,encoding='unicode'))]
    if not dates:
        raise ValueError('Could not resolve the first year of the current Board calendar')
    docs = [rolling]
    for year in range(2000,min(dates)):
        url = BOARD + f'/monetarypolicy/fomchistorical{year}.htm'
        docs.append(fetch_calendar(cache, f'calendar{year}.html', url))
    minutes = {}
    conferences = {}
    for doc in docs:
        for el in doc.xpath('//a[@href]'):
            url = urljoin(BOARD,el.get('href'))
            found = re.search(r'fomcpress?conf(\d{8})\.htm',url)
            if found:
                conferences[datetime.strptime(found[1],'%Y%m%d').date().isoformat()] = url
        for el in doc.xpath('//p[a] | //div[contains(@class,"fomc-meeting__minutes")]'):
            description = ' '.join(el.text_content().split())
            found = re.search(r'\bMinutes\b.*?Released\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',description,re.I)
            if not found:
                continue
            month,day,year = found[1].replace(',','').split()
            release = datetime.strptime(f'{month[:3]} {day} {year}','%b %d %Y').date().isoformat()
            targets = []
            for a in el.xpath('.//a[@href]'):
                target = urljoin(BOARD,a.get('href'))
                if ('minut' in target.lower() or a.text_content().strip()=='HTML') and re.search(r'\.htm[l]?(?:#.*)?$',target,re.I):
                    targets.append(target.split('#')[0])
            if len(set(targets))==1:
                minutes.setdefault(release,set()).add(targets[0])
    return {date:next(iter(urls)) for date,urls in minutes.items() if len(urls)==1}, conferences


def finite(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)


def linked_prices(row, stage, cash_open):
    quotes = dict(row)
    for name, high, low in [('SLOPE','UST10Y','UST2Y'),('BE5','UST5Y','TIPS5Y'),('BE10','UST10Y','TIPS10Y')]:
        if finite(row[high]) and finite(row[low]):
            quotes[name] = row[high] - row[low]
    prices = {}
    for key,col,_,_,unit,_ in ASSETS:
        value = quotes.get(col)
        if not finite(value) or (col=='SP500' and not cash_open) or (col=='MP1' and stage=='minutes'):
            continue
        prices[key] = round(value * (100 if unit=='bp' else 1),7) or 0
    return prices


def build(args):
    joins = runpy.run_path(str(args.data.parents[1]/'scripts/build-stance-cohorts.py'))
    terms = joins['leadership_terms']('fed',args.data)
    fed = next(b for b in json.loads((args.data/'stance-cohorts.json').read_text())['banks'] if b['id']=='fed')
    policies = {r['date']:r for r in fed['records']}
    book = load_workbook(args.workbook,read_only=True,data_only=True)
    by_stage = {}
    try:
        for stage,sheet in SHEETS.items():
            rows = iter(book[sheet].values)
            headers = next(rows)
            observations = [r for r in rows if r[0] and r[0].year>=2000]
            by_stage[stage] = {r[0].date().isoformat():dict(zip(headers,r)) for r in observations}
            if len(by_stage[stage])!=len(observations):
                raise ValueError('Multiple USMPD events share a date within '+sheet)
    finally:
        book.close()
    dates = sorted(k for d in by_stage.values() for k in d)
    minutes_docs, pc_docs = official_sources(args.calendar_cache)
    cash = exchange_calendars.get_calendar('XNYS', start=dates[0], end=dates[-1])
    records = []
    unmatched_minutes = []
    for stage, days in by_stage.items():
        for date,r in days.items():
            if stage=='release' and date in PUBLICATION_CONFLICTS:
                continue
            if stage=='minutes' and date not in minutes_docs:
                # Never attribute prices from a different date to a minutes release.
                unmatched_minutes.append(date)
                continue
            if stage=='combined' and r['PC']==0:
                # Same window as the release. Do not offer the duplicate as another event.
                continue
            stamp = r['date_time'].replace(tzinfo=TZ)
            if stamp.date().isoformat()!=date:
                raise ValueError('Communication and timestamp date disagree: '+date)
            first = stamp - timedelta(minutes=10)
            end_stamp = by_stage['conference'][date]['date_time'].replace(tzinfo=TZ) if stage=='combined' else stamp
            last = end_stamp + timedelta(minutes=60 if stage in ('combined','conference') else 20)
            open_cash = cash.is_session(date) and (first-timedelta(minutes=5)>=cash.session_open(date) and last+timedelta(minutes=5)<=cash.session_close(date))
            meeting = by_stage['release'].get(date,{}) if stage!='minutes' else {}
            off_schedule = bool(meeting.get('Unscheduled'))
            flags = []
            if off_schedule:
                flags.append('Unscheduled or intermeeting announcement. Excluded from standard group comparisons.')
            if meeting.get('SEP') and stage in ('release','combined'):
                flags.append('This meeting included a Summary of Economic Projections. Its release timing should be checked before attributing the move to a single document.')
            if not open_cash:
                flags.append('The cash equity quote windows fall partly or wholly outside the New York Stock Exchange session. Cash index return unavailable.')
            if stage=='combined':
                flags.append('Overlaps the release and conference windows. The combined return is measured directly.')
            row = dict(id=f'fed-{date}-{stage}',date=date,time=stamp.strftime('%H:%M'),timeZone=TZ.key,type=TYPES[stage],stage=stage,
                       title=TITLES[stage],leader=joins['label_tenure'](terms,date),cycle=joins['cycle_at']('fed',stamp.date()),
                       groupEligible=not off_schedule,flags=flags,window=f'{first:%H:%M}–{last:%H:%M} ET ({int((last-first).total_seconds()//60)} minutes, quote midpoints)',
                       sourceUrl=DB,values=linked_prices(r,stage,open_cash))
            if date=='2020-03-15' and stage in ('release','combined'):
                flags.append('Weekend emergency. The researchers used the Friday market close as the pre-announcement price. Other weekend news can affect this interval.')
                if stage=='release':
                    row['window']='Friday close to Sunday futures reopening at 18:00 ET (exceptional weekend window)'
                else:
                    row['window']='Friday close through the Sunday press conference (exceptional combined window)'
            if stage in ('release','combined'):
                row['scheduled'] = not off_schedule
                row['sep'] = bool(meeting.get('SEP'))
            if stage=='release' and date in OTHER_ANNOUNCEMENTS:
                title, suffix = OTHER_ANNOUNCEMENTS[date]
                row.update(title=title, documentUrl=BOARD+'/newsevents/pressreleases/monetary'+suffix+'.htm')
                if date=='2020-08-27':
                    flags.append('The strategy release and the Chair’s Jackson Hole speech coincided.')
            policy = policies.get(date,{})
            if stage=='release' and policy:
                row['documentUrl']=policy['url']
                if policy['score'] is not None:
                    row['score']=policy['score']
                    row['scoreSource']='FOMC statement forward-rate guidance'
                if policy.get('shift') is not None:
                    row['shift']=policy['shift']
            elif stage=='conference' and date in pc_docs:
                row['documentUrl']=pc_docs[date]
            elif stage=='minutes' and date in minutes_docs:
                row['documentUrl']=minutes_docs[date]
            records.append(row)
    order = {stage:i for i,stage in enumerate(SHEETS)}
    records.sort(key=lambda r:(r['date'],order[r['stage']]))
    return dict(bank='fed',timeZone=TZ.key,unmatchedMinutes=sorted(unmatched_minutes),excludedAnnouncements=PUBLICATION_CONFLICTS,
                source={'label':'San Francisco Fed · USMPD','url':DB,'workbook':WORKBOOK,'sha256':hashlib.sha256(args.workbook.read_bytes()).hexdigest()},
                sources=[{'label':'Event windows and asset definitions','url':PAPER},{'label':'Board meeting calendars','url':BOARD+'/monetarypolicy/fomccalendars.htm'},{'label':'US equity sessions','url':'https://www.nyse.com/markets/hours-calendars'}],
                method=['Rows show measured intraday changes around a dated communication. A single day can contain a statement, conference, and overlapping full-meeting window.',
                        'Quote midpoints shown in Eastern time. The provider uses medians of ten-minute quote samples centred on each endpoint and can extend a sample for illiquid instruments. Other simultaneous news can affect the measured move.',
                        'USMPD interest-rate changes are converted from percentage points to basis points. Equity and FX percentages retain the original scale. EUR/USD and USD/JPY have different base currencies.',
                        'Cash S&P 500 returns require both ten-minute quote samples inside the NYSE session, accounting for holidays and early closes. The workbook can report carried or displaced cash-index prices outside the session.',
                        'Group comparisons exclude unscheduled FOMC communications. Each stage is analysed separately. A minutes release carries its own publication date. Minutes require an exact same-day match in the Board publication calendars. Original workbook dates without that confirmation are listed in unmatchedMinutes and excluded. Only release rows with a scored original statement carry a guidance score.'],
                assets=[dict(id=k,label=l,unit=u,group=g,description=d) for k,_,l,g,u,d in ASSETS],
                stages={s:{'label':TITLES[s],'window':w} for s,w in [('release','−10 to +20 minutes'),('conference','−10 to +60 minutes'),('combined','−10 before the announcement to +60 after the conference starts'),('minutes','−10 to +20 minutes')]},
                records=records)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('workbook',type=Path)
    p.add_argument('calendar_cache',type=Path)
    p.add_argument('--data',type=Path,default=ROOT/'dist/data')
    p.add_argument('--output',type=Path,default=ROOT/'dist/data/fed-cross-asset-events.json')
    args=p.parse_args()
    data=build(args)
    args.output.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
    print(len(data['records']),'Fed windows')
