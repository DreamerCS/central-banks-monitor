"""Build dated US rate expectations from public Federal Reserve releases.

Usage: python scripts/build-event-expectations.py --cache /tmp/rate-expectations
The current Atlanta Fed workbook supersedes prior versions. A cache retains the
input bytes for exact reproduction. Delete a cached source to refresh it.
"""
import argparse
import bisect
import hashlib
import json
import re
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from lxml import html
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
BOARD = 'https://www.federalreserve.gov'
INDEX = BOARD + '/monetarypolicy/mpr_default.htm'
ATLANTA = 'https://www.atlantafed.org/en/research-and-data/data/market-probability-tracker'
WORKBOOK = 'https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/research-and-data/data/market-probability-tracker/mpt_histdata.xlsx'
DAILY_SPEECHES = [
    '2023-08-25', '2023-10-19', '2024-05-17', '2024-08-23', '2024-11-14',
    '2025-08-22', '2025-10-14', '2026-08-28', '2026-11-10', '2026-11-12',
    '2026-11-13', '2026-11-19', '2026-11-20'
]


def get(cache, filename, url):
    path = cache / filename
    if not path.exists():
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=45) as response:
            content = response.read()
        path.write_bytes(content)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def iso_header(s):
    cleaned = ' '.join(s.replace(',', ' ').replace('.', '').split())
    for pattern in ['%B %d %Y', '%b %d %Y']:
        try:
            return datetime.strptime(cleaned, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError('Unexpected rate path date: '+s)


def report_curves(cache):
    index = get(cache, 'mprindex.html', INDEX)
    reports = []
    for link in html.parse(str(index)).xpath('//a[contains(text(), "Chart Data and Descriptions")]'):
        url = urljoin(BOARD, link.get('href'))
        pdf = link.xpath('preceding-sibling::a[contains(@href, ".pdf")][1]/@href')
        stamp = re.search(r'(20\d{6})_mprfullreport', pdf[0]) if pdf else None
        if not stamp or stamp[1] < '20170707':
            continue
        pub = datetime.strptime(stamp[1], '%Y%m%d').date().isoformat()
        file = get(cache, stamp[1]+'.html', url)
        doc = html.parse(str(file))
        headings = [h for h in doc.xpath('//h4|//h5|//h6')
                    if re.search(r'Market.implied federal funds rate(?: path)?$', h.text_content().strip(), re.I)]
        if len(headings) != 1:
            raise ValueError(f'{pub}: expected one market-implied rate figure')
        heading = headings[0]
        table = heading.xpath('following::table[1]')[0]
        foot = ' '.join(table.xpath('following::p[1]')[0].text_content().lower().split())
        if not ('overnight index swaps' in foot and 'spline' in foot and '0 basis points' in foot):
            raise ValueError(f'{pub}: the fitted contract or term-premium convention changed')
        rows = [[col.text_content().strip() for col in row.xpath('th|td')] for row in table.xpath('.//tr')]
        dates = [iso_header(v) for v in rows[0][1:]]
        order = sorted(range(len(dates)), key=dates.__getitem__)
        assert len(order) == 2 and dates[order[0]] < dates[order[1]] <= pub
        matched = {}
        for row in rows[1:]:
            if len(row) != 3 or not re.fullmatch(r'\d{4}:Q[1-4]', row[0]):
                continue
            values = [row[i+1] for i in order]
            if all(re.fullmatch(r'-?\d+(?:\.\d+)?', v) for v in values):
                matched[row[0].replace(':', ' ')] = [float(v) for v in values]
        if not matched:
            raise ValueError(f'{pub}: no common observation horizons')
        ref = heading.get('id') or heading.getparent().get('id') or (heading.xpath('preceding-sibling::a[@id or @name][1]/@id | preceding-sibling::a[@id or @name][1]/@name') or [''])[0]
        reports.append(dict(published=pub, dates=[dates[i] for i in order], quarters=matched,
                            figure=heading.text_content().strip().split('.')[0], source=url+('#'+ref if ref else ''),
                            report=urljoin(BOARD,pdf[0]), sourceSha256=digest(file)))
    return sorted(reports, key=lambda r:r['published'])


def daily_means(cache, event_dates):
    wbfile = get(cache, 'mpt.xlsx', WORKBOOK)
    workbook = openpyxl.load_workbook(wbfile, read_only=True, data_only=True)
    means = defaultdict(dict)
    sheet = workbook['DATA']
    sheet.reset_dimensions()
    for obs, start, target, field, value in sheet.iter_rows(min_row=2, max_col=5, values_only=True):
        if field != 'Rate: mean':
            continue
        obsday = obs if isinstance(obs, str) else obs.date().isoformat()
        refday = start.date().isoformat() if isinstance(start, datetime) else start.isoformat()
        if refday in means[obsday]:
            raise ValueError(f'Duplicate contract {obsday}, {refday}')
        means[obsday][refday] = float(value)
    workbook.close()
    dates = sorted(means)
    results = {}
    for day in sorted(set(event_dates)):
        pos = bisect.bisect_left(dates, day)-1
        if pos < 5 or date.fromisoformat(day)-date.fromisoformat(dates[pos]) > timedelta(days=5):
            continue
        before, later = dates[pos-5], dates[pos]
        # Compare only the same fixed, as-yet-unstarted reference quarter.
        observed_dates = dates[pos-5:pos+1]
        common = set.intersection(*(set(means[d]) for d in observed_dates))
        overlap = sorted(q for q in common if q > day)
        if overlap:
            ref = overlap[0]
            results[day] = dict(earlier=before, later=later, referenceStart=ref,
                                meanBp=[means[before][ref],means[later][ref]],
                                path=[[d, means[d][ref]] for d in observed_dates])
    return results, digest(wbfile), dates[-1]


def main():
    opts = argparse.ArgumentParser()
    opts.add_argument('--cache', type=Path, required=True)
    opts.add_argument('--through', default='2026-11-20')
    opts.add_argument('--output', type=Path, default=ROOT/'dist/data/event-expectations.json')
    args = opts.parse_args()
    asof = date.fromisoformat(args.through).isoformat()
    args.cache.mkdir(parents=True, exist_ok=True)
    meeting_path = ROOT/'dist/data/meeting-sequence.json'
    banks = json.loads(meeting_path.read_bytes())['banks']
    meetings = [event['date'] for bank in banks if bank['id']=='fed' for event in bank['events']]
    days = [v for v in DAILY_SPEECHES+meetings if v<=asof]
    daily, book_hash, last_obs = daily_means(args.cache, days)
    probabilities = json.loads((ROOT/'scripts/event-probability-observations.json').read_bytes())
    for day,v in probabilities.items():
        assert v['earlier'][0] < v['later'][0] < day and all(0<=v[k][1]<=100 for k in ['earlier','later'])
    result = dict(schemaVersion=1, asOf=asof, reports=[r for r in report_curves(args.cache) if r['published']<=asof],
                  daily=daily, meetingOdds={d:v for d,v in probabilities.items() if d<=asof},
                  sources=dict(reportIndex=INDEX, tracker=ATLANTA, workbook=WORKBOOK,
                               workbookSha256=book_hash, workbookLastInputDate=last_obs,
                               fedwatch='https://www.cmegroup.com/tools-information/quikstrike/cme-fedwatch-tool-user-guide.html'))
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')


if __name__ == '__main__':
    main()
