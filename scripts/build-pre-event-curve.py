"""Build paired daily Treasury par yields and the Fed Board's dated, linked speeches.

Run python scripts/build-pre-event-curve.py [--through YYYY-MM-DD].
The default includes only events published by the time of the run in New York.
Data stays in place if either official source is unavailable or incomplete.
"""
import argparse
import html
import json
import os
import re
import runpy
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'dist/data/pre-event-curve.json'
TREASURY = runpy.run_path(str(ROOT / 'scripts/update-treasury.py'))
SPEECHES = 'https://www.federalreserve.gov/json/ne-speeches.json'
SPEECH_INDEX = 'https://www.federalreserve.gov/newsevents/speeches-testimony.htm'
TREASURY_TABLE = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve'
METHOD = 'https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology'
NY = ZoneInfo('America/New_York')
FIRST_DATE = date(1999, 12, 1)


def download(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'})
    with urlopen(req, timeout=40) as response:
        return response.read()


def year_rates(year):
    url = f"{TREASURY['BASE']}?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    rows = TREASURY['records'](download(url))
    if not rows or any(not day.startswith(f'{year}-') for day in rows):
        raise ValueError(f'Empty or misdated Treasury response for {year}')
    return rows


def observations(through, previous=()):
    # Re-fetch the current and preceding year to catch recent official corrections.
    # A new checkout or --full rebuilds every year directly from Treasury.
    first_year = min(int(previous[-1]['date'][:4]), through.year - 1) if previous else FIRST_DATE.year
    retained = [row for row in previous if row['date'] < f'{first_year}-01-01']
    years = range(first_year, through.year + 1)
    result = list(retained)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for year, rows in zip(years, pool.map(year_rates, years)):
            if year < through.year and len(rows) < 240:
                raise ValueError(f'Incomplete Treasury history for {year}')
            for day, pair in sorted(rows.items()):
                if FIRST_DATE.isoformat() <= day <= through.isoformat():
                    result.append({'date': day, 'y2': pair['twoYear'], 'y10': pair['tenYear']})
    if not result or (through - date.fromisoformat(result[-1]['date'])).days > 7:
        raise ValueError('Latest Treasury observation is unexpectedly old')
    return result


def plain(value):
    return ' '.join(html.unescape(value).split())


def speech_events(items, cutoff):
    if sum(bool(item.get('l')) for item in items) < 1000:
        raise ValueError('Fed speech catalogue is unexpectedly short')
    events = []
    seen = set()
    for item in items:
        link = item.get('l', '')
        if not re.fullmatch(r'/newsevents/speech/[a-zA-Z0-9_-]+\.htm', link):
            continue
        stamp = item['d']
        timed = ' ' in stamp.strip()
        dt = datetime.strptime(stamp.strip(), '%m/%d/%Y %I:%M:%S %p' if timed else '%m/%d/%Y')
        if dt.replace(tzinfo=NY) > cutoff:
            continue
        if not timed and dt.date() == cutoff.date() and cutoff.hour < 23:
            continue
        title, speaker = plain(item['t']), plain(item['s'])
        if not title or not speaker or link in seen:
            raise ValueError(f'Invalid or duplicate speech metadata for {link}')
        seen.add(link)
        events.append({'date': dt.date().isoformat(), 'time': dt.strftime('%H:%M') if timed else None,
                       'timezone': NY.key, 'speaker': speaker, 'title': title, 'kind': 'Speech',
                       'institution': 'Federal Reserve', 'url': urljoin(SPEECHES, link)})
    if not events:
        raise ValueError('No published Board speeches within this date range')
    return sorted(events, key=lambda row: (row['date'], row['time'] or '', row['url']), reverse=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', type=date.fromisoformat, help='Last date, New York time')
    parser.add_argument('--full', action='store_true', help='Re-fetch historical Treasury years')
    args = parser.parse_args()
    now = datetime.now(NY)
    cutoff = now
    if args.through:
        cutoff = min(now, datetime.combine(args.through, datetime.max.time(), tzinfo=NY))
    old = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {}
    rates = observations(cutoff.date(), () if args.full else old.get('observations', ()))
    events = speech_events(json.loads(download(SPEECHES).decode('utf-8-sig')), cutoff)
    data = {'asOfDate': rates[-1]['date'], 'eventsThrough': events[0]['date'],
            'market': {'currency': 'USD', 'tenors': ['2Y', '10Y'], 'timezone': NY.key,
                       'fixingTime': '15:30', 'unit': 'percent per annum',
                       'sources': [{'label': 'U.S. Treasury daily par yields', 'url': TREASURY_TABLE},
                                   {'label': 'Treasury curve methodology', 'url': METHOD},
                                   {'label': 'Federal Reserve Board speeches', 'url': SPEECH_INDEX},
                                   {'label': 'Board speech publication timestamps', 'url': SPEECHES}]},
            'observations': rates, 'events': events}
    if old and (old['asOfDate'] > data['asOfDate'] or old['eventsThrough'] > data['eventsThrough']
                or len(rates) < len(old['observations'])):
        raise ValueError('Refusing to replace the catalogue with an older or truncated snapshot')
    with tempfile.NamedTemporaryFile(mode='w', dir=OUTPUT.parent, delete=False, encoding='utf-8') as tmp:
        json.dump(data, tmp, separators=(',', ':'), ensure_ascii=False)
        tmp.write('\n')
    os.chmod(tmp.name, 0o644)
    os.replace(tmp.name, OUTPUT)
    print(f"{len(rates)} observations ({rates[0]['date']} to {rates[-1]['date']}); "
          f"{len(events)} speeches ({events[-1]['date']} to {events[0]['date']})")


if __name__ == '__main__':
    main()
