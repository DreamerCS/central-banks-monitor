"""Build the archive from the official-source manifest and reviewed evidence records.
Run from any directory. The monthly US cycle panel is produced by the site's macro-history builder.
Use --verify-text to check current Board HTML against reviewed sentence fingerprints (lxml needed).
Optional --cache points to a local collection of Board HTML files.
"""
import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parents[1]
SCRIPT = BASE / 'scripts'
DATA = BASE / 'dist' / 'data'


def verify(pair):
    from lxml import html
    row, review, cache = pair
    url = row['sourceUrl']
    basename = (hashlib.sha1(url.encode()).hexdigest()[:12] + '.htm'
                if '/boarddocs/' in url else url.rsplit('/', 1)[-1])
    filename = cache / (row['date'] + '-' + basename) if cache else None
    data = (filename.read_bytes() if filename and filename.exists() else
            urlopen(Request(url, headers={'User-Agent': 'Central Bank Intelligence research'}), timeout=30).read())
    doc = html.fromstring(data)
    elements = doc.xpath('//*[@id="article"]/div[contains(@class,"col-md-8") and not(contains(@class,"heading"))][1]//p')
    if not elements:
        elements = doc.xpath('//td//p | //body/p')
    sentences = []
    for paragraph in elements:
        for footnote in paragraph.xpath('.//sup'):
            footnote.drop_tree()
        text = unicodedata.normalize('NFKC', paragraph.text_content()).replace('’', "'").replace('—', '–')
        text = ' '.join(text.split())
        if len(text) >= 20 and 'Return to text' not in text:
            sentences.extend(s for s in re.split(r'(?<=[.?!])\s+(?=(?:[A-Z]|"|\())', text) if len(s) > 25)
    expected = review['textSha256']
    if not any(hashlib.sha256(s.encode()).hexdigest() == expected for s in sentences):
        raise ValueError(f'Review the changed evidence at {url}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycle', type=Path, default=DATA / 'cycle-context.json')
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--verify-text', action='store_true')
    args = parser.parse_args()
    catalogue = json.loads((SCRIPT / 'fed-chair-catalogue.json').read_text())
    readings = json.loads((SCRIPT / 'fed-chair-readings.json').read_text())
    reviews = {r['url']: r for r in readings}
    urls = {row['sourceUrl'] for row in catalogue}
    if len(urls) != len(catalogue) or len(reviews) != len(readings) or reviews.keys() - urls:
        raise ValueError('Duplicate or unlinked source URL')
    cycles = {r['month']: r for r in json.loads(args.cycle.read_text())['rows']}
    rows = []
    verified = []
    prior = {}
    for item in sorted(catalogue, key=lambda r: (r['date'], r['sourceUrl'])):
        row = dict(item)
        leader, day = row['leader'], row['date']
        cycle = cycles.get(day[:7], {}).get('recession')
        row['cycle'] = {0: 'Expansion', 1: 'Recession'}.get(cycle, 'Pending month')
        # Only tag clearly non-policy title categories. Other unscored speeches stay open.
        title = row['title'].lower()
        if re.search(r'commencement|swearing.in|award|dedication|anniversary|memorial|tribute|class day', title):
            status = 'Ceremonial subject'
        elif re.search(r'supervis|bank regulation|payment|consumer (?:credit|protection)|education|community bank|mortgage banking|financial literacy|workforce|deposit insurance|philanthrop', title):
            status = 'Technical or institutional subject'
        else:
            status = 'No directional reading assigned'
        score = shift = previous = interval = None
        evidence = locator = None
        review = reviews.get(row['sourceUrl'])
        if review:
            if (review['date'], review['leader']) != (day, leader) or review['score'] not in (-2,-1,0,1,2):
                raise ValueError(f'Mismatched review: {day} {leader}')
            score, evidence, locator = review['score'], review['rationale'], review['sentence']
            status = 'Reviewed policy signal'
            if leader in prior:
                previous, last_score = prior[leader]
                interval = (date.fromisoformat(day) - date.fromisoformat(previous)).days
                shift = score - last_score
            prior[leader] = (day, score)
            verified.append((row, review, args.cache))
        elif day == '2026-08-28' and leader == 'Warsh':
            evidence = 'Warsh discussed inflation persistence, employment, and his decision framework. He left the next rate decision open.'
        elif day == '2026-11-16' and leader == 'Warsh':
            status = 'Technical or institutional subject'
            evidence = 'Warsh discussed the economic impact of artificial intelligence and potential implications for future monetary policy.'
        row.update(score=score, evidence=evidence, evidenceSentence=locator, shift=shift,
                   previousDate=previous, daysSincePreviousScore=interval, status=status)
        rows.append(row)
    if args.verify_text:
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(verify, verified))
    out = {'title': 'Federal Reserve chair speeches', 'asOf': '2026-11-20',
           'unit': 'One prepared speech listed by the Board, delivered as sitting chair.',
           'sources': ['https://www.federalreserve.gov/newsevents/speech/2000speech.htm',
                       'https://www.federalreserve.gov/json/ne-speeches.json'],
           'summary': {'catalogued': len(rows), 'reviewed': len(reviews),
                       'byLeader': dict(Counter(r['leader'] for r in rows))},
           'records': rows}
    (DATA / 'fed-leader-speeches.json').write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
