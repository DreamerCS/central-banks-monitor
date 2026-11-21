"""Join Reuters' decision wraps for a complete FOMC calendar year to market observations."""
import argparse
import csv
import io
import json
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / 'dist/data'
PRICE_FIELDS = (
    'actionBp', 'priorMoveBp', 'pricingGapBp', 'ois1yBp', 'conferenceOis1yBp',
    'yield2yBp', 'conferenceYield2yBp', 'slope2s10sBp', 'conferenceSlope2s10sBp',
    'equityPct', 'conferenceEquityPct',
)


def build():
    with (DATA / 'policy-research-meetings.csv').open(encoding='utf-8-sig', newline='') as stream:
        meetings = {r['date']: r for r in csv.DictReader(stream)
                    if r['bank'] == 'fed' and r['regularRelease'] == '1' and r['date'].startswith('2025-')}
    articles = json.loads((BASE / 'reuters-fomc-2025-sources.json').read_text())
    if sorted(r['date'] for r in articles) != sorted(meetings):
        raise ValueError('The Reuters panel must contain one row per scheduled 2025 FOMC decision')
    rows = []
    for article in sorted(articles, key=lambda r: r['date']):
        day = article['date']
        r = meetings[day]
        if article['articleUrl'] and urlparse(article['articleUrl']).hostname not in ('www.reuters.com','reuters.com'):
            raise ValueError(f'Unexpected publisher on {day}')
        obs = {k: round(float(r[k]), 5) if r[k] else None for k in PRICE_FIELDS}
        rows.append({**article, **obs, 'officialUrl': r['officialUrl'], 'marketSource': r['marketSource']})
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return {
        'reuters-fomc-2025.csv': stream.getvalue().encode('utf-8-sig'),
        'reuters-fomc-2025.json': (json.dumps(rows, ensure_ascii=False, indent=2)+'\n').encode(),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for name, contents in build().items():
        path = DATA / name
        if args.check:
            if path.read_bytes() != contents:
                raise SystemExit('Refresh '+name)
        else:
            path.write_bytes(contents)
