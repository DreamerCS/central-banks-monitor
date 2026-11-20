"""Reconstruct intraday research returns from HistData M1 ASCII quote archives.

Pass the directory containing local ZIP downloads and --data-dir dist/data.
Files use pair-year.zip or pair-year-month.zip (case-insensitive pairs), or
the original HISTDATA_COM_ASCII_PAIR_M1_YYYY[MM].zip download names.
Use --download to fetch missing archives using the provider's public form.
No level, tick, or underlying quote archive is included in the output.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from http.cookiejar import CookieJar
from pathlib import Path
from statistics import correlation,median,StatisticsError
import io
import json
import zipfile
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo('America/New_York')
MIN = timedelta(minutes=1)
LONDON = ZoneInfo('Europe/London')
OFFSETS = (0, 5, 15, 30)
INSTRUMENTS = {'eurusd': ('EUR/USD', 'FX', 'US dollars per euro. Positive means euro appreciation.'),
               'usdjpy': ('USD/JPY', 'FX', 'Yen per US dollar. Positive means dollar appreciation.'),
               }
PAIRS = {'eurusd':'EURUSD', 'usdjpy':'USDJPY'}
SOURCE = 'https://www.histdata.com/download-free-forex-historical-data/'
SPEC = 'https://www.histdata.com/f-a-q/data-files-detailed-specification/'
FAQ = 'https://www.histdata.com/f-a-q/'
# Board release-date corrections for unmatched dates in the SF Fed workbook.
# Both dates in each disagreement are conservatively excluded.
MINUTES_DATES = {'2003-12-11','2025-12-30','2026-10-07'}
ADDITIONAL_RELEASE_DATES = {'2019-10-11'}
# Documented concurrent releases on specific prominently analysed speech dates.
KNOWN_RELEASES = {
    '2022-08-26': ('University of Michigan final consumer sentiment, 10:00 ET',
        'https://economics.bmo.com/en/publications/detail/18c1d54b-8557-4bfa-9927-82756d906996/'),
    '2024-08-23': ('Census Bureau new residential sales, 10:00 ET',
        'https://www.census.gov/construction/nrs/pdf/newressales_202407.pdf'),
}
METHOD = [
    'Each row uses a public release or scheduled delivery time for a Federal Reserve Chair speech. A FRASER cover link identifies historical timing evidence where available. The documented clock may precede or follow the actual first spoken words or news headlines.',
    'At each boundary use the closing bid of the immediately preceding one-minute bar. That quote falls within the preceding minute. Changes are 100 times (ending bid / baseline bid − 1), from five minutes before the scheduled event. The principal window ends 30 minutes afterwards. Intermediate checkpoints show how the cumulative move evolved.',
    'The archive’s published clock description conflicts with the observed FX bars in summer. We match New York wall time only during periods when New York and London agree on daylight saving. Each currency and year-season must also pass a time check against independently timed San Francisco Fed currency returns. Transition weeks when the two regions disagree are omitted. Quote continuity requires all five exact endpoint bars and at least one quote in every three consecutive minutes. The feed supplies indicative bid quotes.',
    'Clock validation uses at least four separate USMPD statement or minutes windows in each currency, year and season. Require correlation of at least 0.70 and median absolute discrepancies of at most 0.06 percentage points and below 65% of both one-hour-shifted alternatives. Indicative bid and midpoint measures naturally differ. Archive hashes and validation statistics accompany the data.',
    'Exclude weekends, untimed speeches, overlapping Chair speech windows, and dates with any recorded FOMC policy release or minutes. Verified concurrent data releases are flagged on selected dates and kept outside group statistics. No complete economic-news overlap calendar is available. Other speakers, economic releases and financial news may share these windows. Direction and magnitude describe co-movement.',
]

def read_json(path):
    return json.loads(path.read_text())

def fetch_zip(pair, year, month, outfile):
    from lxml import html
    period = str(year) if month is None else f'{year}/{month}'
    url = SOURCE + '?/ascii/1-minute-bar-quotes/' + pair.lower() + '/' + period
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    agent = {'User-Agent':'Historical event-window research client'}
    page = opener.open(Request(url, headers=agent), timeout=40)
    doc = html.fromstring(page.read())
    forms = doc.xpath('//form[.//input[@name="tk"]]')
    if not forms:
        return False
    form = forms[0]
    payload = {i.get('name'): i.get('value') for i in form.xpath('.//input[@name][@value]')}
    if payload.get('fxpair') != pair or payload.get('platform') != 'ASCII' or payload.get('timeframe') != 'M1':
        raise ValueError(f'unexpected download form for {pair} {period}')
    request = Request('https://www.histdata.com/get.php', data=urlencode(payload).encode(),
                      headers={**agent,'Referer':url})
    with opener.open(request, timeout=50) as response:
        archive = response.read()
    if not zipfile.is_zipfile(io.BytesIO(archive)):
        return False
    outfile.write_bytes(archive)
    return True

def candidates(cache,pair,year,months,fetch):
    old = (cache/f'{pair.lower()}-{year}.zip', cache/f'HISTDATA_COM_ASCII_{pair}_M1_{year}.zip')
    annual = next((p for p in old if p.exists()), None)
    if not annual and fetch and year < datetime.now(timezone.utc).year and fetch_zip(pair,year,None,old[0]):
        annual = old[0]
    if annual:
        return [annual]
    output = []
    for month in sorted(months):
        possible = (cache/f'{pair.lower()}-{year}-{month}.zip',
                    cache/f'HISTDATA_COM_ASCII_{pair}_M1_{year}{month:02d}.zip')
        monthly = next((p for p in possible if p.exists()), None)
        if not monthly and fetch and fetch_zip(pair,year,month,possible[0]):
            monthly=possible[0]
        if monthly: output.append(monthly)
    return output

def source_clock(et):
    # The integer hour here labels archive bars, not an actual UTC-05 instant.
    return et.replace(tzinfo=None)

def aligned_season(t):
    return bool(t.dst())==bool(t.astimezone(LONDON).dst())

def benchmark_windows(fomc):
    rows=[]
    for r in fomc['records']:
        if r['stage'] not in {'release','minutes'} or not r.get('time'): continue
        t=datetime.fromisoformat(r['date']+'T'+r['time']).replace(tzinfo=EASTERN)
        if aligned_season(t):
            rows.append((t,r['values']))
    return rows

def wanted_bars(events,benchmarks):
    byyear=defaultdict(dict)
    def want(stamp):
        byyear[stamp.year][stamp.strftime('%Y%m%d %H%M00').encode()]=stamp
    for event in events:
        clock=source_clock(event['clock'])
        for offset in range(-6,30): want(clock+offset*MIN)
    for t,_ in benchmarks:
        clock=source_clock(t)
        for hour in (-60,0,60):
            for offset in (-11,-10,-9,17,18,19,20): want(clock+(hour+offset)*MIN)
    return byyear

def verified_seasons(rows,bars,asset):
    groups=defaultdict(list)
    for t,values in rows:
        observed=values.get(asset)
        if observed is None: continue
        anchor=source_clock(t)
        returns=[]
        for shift in (-60,0,60):
            p=anchor+shift*MIN
            left=[bars[p+m*MIN] for m in (-11,-10,-9) if p+m*MIN in bars]
            right=[bars[p+m*MIN] for m in (17,18,19,20) if p+m*MIN in bars]
            if min(len(left),len(right))<2: break
            returns.append(100*(median(right)/median(left)-1))
        if len(returns)==3:
            groups[(t.year,bool(t.dst()))].append((observed,returns))
    stats={}
    for k,records in sorted(groups.items()):
        if len(records)<4:continue
        ref=[x[0] for x in records]
        series=list(zip(*(x[1] for x in records)))
        try:rho=correlation(ref,series[1])
        except StatisticsError:continue
        err=[median(abs(a-b) for a,b in zip(ref,seq)) for seq in series]
        ok=rho>=0.70 and err[1]<=0.06 and err[1]<0.65*min(err[0],err[2])
        stats[k]=dict(verified=ok,n=len(ref),correlation=round(rho,4),
                      medianAbsoluteErrorsPct=[round(v,5) for v in err])
    return stats

def load_sample(cache,asset,dates,fetch):
    out = {}
    files = []
    pair=PAIRS[asset]
    for year,keys in sorted(dates.items()):
        for p in candidates(cache,pair,year,{v.month for v in keys.values()},fetch):
            with zipfile.ZipFile(p) as z:
                names=[s for s in z.namelist() if s.upper().endswith('.CSV') and f'_{pair}_M1_{year}' in s.upper()]
                if len(names)!=1:
                    raise ValueError(f'unexpected contents in {p}')
                with z.open(names[0]) as fh:
                    for line in fh:
                        stamp=line[:15]
                        if stamp not in keys: continue
                        _,opening,high,low,close,_=line.split(b';')
                        o,h,l,c=map(float,(opening,high,low,close))
                        if c<=0 or not l<=min(o,c)<=max(o,c)<=h or keys[stamp] in out:
                            raise ValueError(f'invalid or overlapping {pair} data at {stamp!r}')
                        out[keys[stamp]]=c
            files.append({'name':p.name,'sha256':sha256(p.read_bytes()).hexdigest()})
    return out,files

def returns(clock,bars):
    # Boundary t uses the last bid from [t−1 min, t), so never looks forward.
    stamps=[clock+(m-1)*MIN for m in (-5,*OFFSETS)]
    if not all(t in bars for t in stamps): return None
    gap=0
    for i in range(-6,30):
        gap=0 if clock+i*MIN in bars else gap+1
        if gap>2: return None
    baseline=bars[stamps[0]]
    return [round(100*(bars[t]/baseline-1),5) for t in stamps[1:]]

def build(data,cache,fetch):
    texts=read_json(data/'fed-leader-speeches.json')['records']
    times=read_json(data/'fed-speech-markets.json')['records']
    fomc=read_json(data/'fed-cross-asset-events.json')
    excluded_dates={r['date'] for r in fomc['records']} | set(fomc.get('unmatchedMinutes',[])) | MINUTES_DATES | ADDITIONAL_RELEASE_DATES
    for b in read_json(data/'stance-cohorts.json')['banks']:
        if b['id']=='fed': excluded_dates.update(r['date'] for r in b['records'])
    text_by_url={r['sourceUrl']:r for r in texts}
    events=[]
    for r in times:
        timing=r['timeET'];d=r['date']
        clock=datetime.fromisoformat(d+'T'+timing).replace(tzinfo=EASTERN) if timing else None
        events.append({'source':r, 'text':text_by_url[r['url']], 'clock':clock})
    exclusions=Counter()
    keep=[]
    for e in events:
        day=e['source']['date'];dt=e['clock']
        if not dt: reason='Undocumented time'
        elif dt.weekday()>=5: reason='Weekend'
        elif not aligned_season(dt): reason='US and European daylight-saving transitions differ'
        elif day in excluded_dates: reason='FOMC announcement or minutes date'
        elif any(o is not e and ((o['clock'] and abs((o['clock']-dt).total_seconds())<=35*60)
                              or (not o['clock'] and o['source']['date']==day)) for o in events):
            reason='Second Chair speech could overlap'
        else:
            keep.append(e);continue
        exclusions[reason]+=1
    benchmarks=benchmark_windows(fomc)
    byyear=wanted_bars(keep,benchmarks)
    data_by_asset={};manifest={};validation={}
    for a in INSTRUMENTS:
        data_by_asset[a],manifest[a]=load_sample(cache,a,byyear,fetch)
        validation[a]=verified_seasons(benchmarks,data_by_asset[a],a)
    rows=[]
    for e in keep:
        r,s=e['source'],e['text'];dt=e['clock']
        profile=[{'minutes':m,'values':{}} for m in OFFSETS]
        for a,bars in data_by_asset.items():
            if not validation[a].get((dt.year,bool(dt.dst())),{}).get('verified'):
                continue
            changes=returns(source_clock(dt),bars)
            if changes is not None:
                for item,value in zip(profile,changes):
                    item['values'][a]=value
        if not profile[-1]['values']:
            exclusions['No series passed both clock and quote checks']+=1
            continue
        name=s['speaker']
        for prefix in ('Chairman ','Chairwoman ','Chair '):
            if name.startswith(prefix):
                name=name[len(prefix):];break
        beginning=dt-5*MIN;ending=dt+30*MIN
        utc=lambda when:when.astimezone(timezone.utc).isoformat(timespec='minutes').replace('+00:00','Z')
        rows.append(dict(id='fed-speech-intraday-'+r['date']+'-'+r['timeET'].replace(':',''),date=r['date'],
                         time=r['timeET'],timeZone='America/New_York',type='speech',stage='speechFx',
                         title=s['title'],leader=name,speaker=name,cycle=r['cycle'],score=s['score'],
                         evidence=s.get('evidence'),documentUrl=r['url'],sourceUrl=SOURCE,timeSource=r.get('timeSource') or r['url'],
                         timeEvidence=r.get('timeEvidence') or 'Public Board speech release or scheduled delivery time',
                         window=f'{beginning:%H:%M}–{ending:%H:%M} ET (−5 to +30 minutes, indicative bid quotes)',
                         startUtc=utc(beginning),endUtc=utc(ending),
                         flags=["Concurrent release: "+KNOWN_RELEASES[r['date']][0]] if r['date'] in KNOWN_RELEASES else [],
                         groupEligible=r['date'] not in KNOWN_RELEASES,
                         values=profile[-1]['values'],path=profile))
    for row in rows:
        if row['date'] in KNOWN_RELEASES:
            row['overlapSource']=KNOWN_RELEASES[row['date']][1]
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('duplicate record identifiers')
    coverage={'catalogued':len(events),'knownTime':sum(e['clock'] is not None for e in events),'candidateWindows':len(keep),
              'observed':len(rows),'scored':sum(r['score'] is not None for r in rows),'first':min(r['date'] for r in rows),
              'last':max(r['date'] for r in rows),'byAsset':{a:sum(a in r['values'] for r in rows) for a in INSTRUMENTS},
              'exclusions':dict(exclusions)}
    return dict(bank='fed',timeZone='America/New_York',source={'label':'HistData · minute bid quotes','url':SOURCE},
                sources=[{'label':'Currency clock reference · San Francisco Fed USMPD','url':fomc['source']['url']},{'label':'Quote specification','url':SPEC},{'label':'Pricing and clock convention','url':FAQ}],
                method=METHOD,coverage=coverage,sourceArchives=manifest,
                clockValidation={a:{f'{y}-{"daylight" if d else "standard"}':v for (y,d),v in checks.items()} for a,checks in validation.items()},
                assets=[dict(id=a,label=t[0],unit='%',group=t[1],description=t[2]) for a,t in INSTRUMENTS.items()],
                stages={'speechFx':{'label':'Chair speech · intraday FX','window':'−5 to +30 minutes, bid quote returns'}},records=rows)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path('dist/data'))
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('dist/data/fed-speech-intraday-assets.json'))
    parser.add_argument('--download',action='store_true')
    a=parser.parse_args()
    a.cache.mkdir(parents=True,exist_ok=True)
    result=build(a.data_dir,a.cache,a.download)
    a.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(result['coverage'],indent=2))
