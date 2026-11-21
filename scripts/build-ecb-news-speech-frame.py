"""Rebuild the independent speech denominator from the ECB's public speeches CSV
and its English publications catalogue. Only document metadata are exported.
The ECB's speech classification includes opening statements, hearings and lectures.
Pass --through YYYY-MM-DD to fix the event cutoff, and --cache to reuse downloads.
"""
import argparse
import csv
import hashlib
import html
import json
import math
import re
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

DOMAIN = 'https://www.ecb.europa.eu'
PORTAL = DOMAIN + '/press/key/html/downloads.en.html'
VERSION_URL = DOMAIN + '/foedb/dbs/foedb/publications.en/versions.json'
OUTPUT = Path(__file__).resolve().parents[1] / 'dist/data/ecb-news-speech-frame.csv'
TERMS = [
    ('2000-01-01', 'Willem F. Duisenberg'),
    ('2003-11-01', 'Jean-Claude Trichet'),
    ('2011-11-01', 'Mario Draghi'),
    ('2019-11-01', 'Christine Lagarde'),
]
FIELDS = ['event_id', 'date', 'speaker', 'title', 'url', 'president', 'president_speaks', 'source']


def clean(value):
    return ' '.join(html.unescape(value or '').split())


def identity(value):
    return ' '.join(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', value).casefold()))


def key(day, speaker, title):
    title = identity(title)
    prefix = identity(speaker)
    if prefix and title.startswith(prefix + ' '):
        title = title[len(prefix) + 1:]
    return day, prefix, title


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', type=date.fromisoformat, default=date.today())
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    cutoff = args.through.isoformat()
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)

    def read(url):
        cached = args.cache / hashlib.sha256(url.encode()).hexdigest() if args.cache else None
        if cached and cached.exists():
            return cached.read_bytes()
        with urlopen(Request(url, headers={'User-Agent': 'ThePolicyTape/1.0'}), timeout=60) as response:
            data = response.read()
        if cached:
            cached.write_bytes(data)
        return data

    page = read(PORTAL).decode()
    match = re.search(r'href=["\']([^"\']*all_ECB_speeches\.csv[^"\']*)', page)
    if not match:
        raise ValueError('Bulk speech download missing from ECB portal')
    bulk = defaultdict(list)
    lines = read(urljoin(PORTAL, html.unescape(match[1]))).decode('utf-8-sig').split('\r\n')
    if lines[0] != 'date|speakers|title|subtitle|contents':
        raise ValueError('Unexpected ECB bulk speech fields')
    for line in lines[1:]:
        if not line:
            continue
        day, speakers, title, _, _ = line.split('|', 4)
        if '2000-01-01' <= day <= cutoff:
            speaker = '; '.join(clean(s) for s in speakers.split(','))
            title = clean(title)
            bulk[key(day, speaker, title)].append((day, speaker, title))

    board_names = {name for rows in bulk.values() for _, authors, _ in rows
                  for name in authors.split('; ') if name}
    version = json.loads(read(VERSION_URL))[0]
    base = urljoin(VERSION_URL, f'{version["version"]}/{version["hash"]}/')
    spec = json.loads(read(base + 'metadata.json'))
    fields = spec['header']
    pages = math.ceil(spec['total_records'] / spec['chunk_size'])
    urls = [base + f'data/{i // spec["chunk_group_size"]}/chunk_{i}.json' for i in range(pages)]
    records = []
    read_count = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        for chunk in pool.map(read, urls):
            flat = json.loads(chunk)
            if len(flat) % len(fields):
                raise ValueError('Incomplete ECB publications catalogue chunk')
            for i in range(0, len(flat), len(fields)):
                item = dict(zip(fields, flat[i:i + len(fields)]))
                read_count += 1
                routes = [urljoin(DOMAIN, u) for u in (item['documentTypes'] or []) if '/press/key/' in u]
                if not routes:
                    continue
                day = datetime.fromtimestamp(item['pub_timestamp'], ZoneInfo('Europe/Berlin')).date().isoformat()
                if not '2000-01-01' <= day <= cutoff:
                    continue
                speaker = '; '.join(clean(s) for s in (item['boardmember'] or '').split('|'))
                title = clean(item['publicationProperties']['Title'])
                row_key = key(day, speaker, title)
                matched = bool(bulk[row_key])
                if matched:
                    bulk[row_key].pop()
                if not speaker:
                    subtitle = item['publicationProperties'].get('Subtitle') or ''
                    if isinstance(subtitle, list):
                        subtitle = ' '.join(subtitle)
                    # Recover an explicit credit in the publisher's subtitle, including German slides.
                    credits = [name for name in board_names if re.search(
                        r'\b(?:by|von)\s+' + re.escape(name) + r'(?=,|\s|$)', clean(subtitle), re.I)]
                    if len(credits) == 1:
                        speaker = credits[0]
                url = sorted(routes, key=lambda u: (not u.endswith('.en.html'), not u.endswith('.en.pdf'), u))[0]
                records.append((f'ecb-{item["id"]}', day, speaker, title, url, 'bulk+catalogue' if matched else 'catalogue'))
    if read_count != spec['total_records']:
        raise ValueError('Incomplete ECB publications catalogue')
    for unmatched in bulk.values():
        for day, speaker, title in unmatched:
            token = hashlib.sha256(f'{day}|{speaker}|{title}'.encode()).hexdigest()[:16]
            records.append((f'ecb-bulk-{token}', day, speaker, title, '', 'bulk'))
    if len({r[0] for r in records}) != len(records):
        raise ValueError('Duplicate ECB speech identifiers')
    records.sort(key=lambda r: (r[1], r[2], r[3], r[0]))
    with args.output.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(FIELDS)
        for event_id, day, speaker, title, url, source in records:
            president = next(name for since, name in reversed(TERMS) if since <= day)
            writer.writerow((event_id, day, speaker, title, url, president, int(president in speaker.split('; ')), source))
    print(f'{len(records)} ECB documents up to {cutoff}, catalogue version {version["version"]}.')


if __name__ == '__main__':
    main()
