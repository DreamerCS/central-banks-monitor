"""Join New York Fed ACM estimates to Treasury closes preceding Fed events.

Run after build-market-events.py and build-pre-event-curve.py.
An optional --acm input reproduces a particular New York Fed workbook vintage.
Dependencies: xlrd for the official BIFF workbook.
"""
import argparse
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
from urllib.request import urlopen

import xlrd

DATA = Path(__file__).resolve().parents[1] / 'dist' / 'data'
ACM = 'https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls'
LEGS = (2, 10)
WINDOWS = (5, 20)


def sheet(data):
    book = xlrd.open_workbook(file_contents=data, on_demand=True)
    page = book.sheet_by_name('ACM Daily')
    header = page.row_values(0)
    cols = [header.index(f'{name}{leg:02d}') for name in ('ACMRNY', 'ACMTP', 'ACMY') for leg in LEGS]
    history = {}
    for index in range(1, page.nrows):
        row = page.row_values(index)
        day = datetime.strptime(row[0], '%d-%b-%Y').date().isoformat()
        if day < '1999-10-01':
            continue
        vals = [row[col] for col in cols]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
            continue
        if day in history or any(abs(vals[i] + vals[2+i] - vals[4+i]) > 0.00001 for i in (0, 1)):
            raise ValueError(f'Unexpected ACM model identity or duplicate on {day}')
        history[day] = vals[:4]
    return history


def build(model, treasury, market):
    quotes = {r['date']: [r['y2'], r['y10']] for r in treasury['observations']
              if all(isinstance(r[k], (int, float)) and math.isfinite(r[k]) for k in ('y2', 'y10'))}
    days = sorted(quotes)
    dates = defaultdict(lambda: {'speeches': 0, 'statement': False})
    fed = next(bank for bank in market['banks'] if bank['id'] == 'fed')
    for item in fed['events']:
        if 'statement' in item['windows']:
            dates[item['date']]['statement'] = True
    for r in treasury['events']:
        if r['kind'].lower() == 'speech':
            dates[r['date']]['speeches'] += 1
    output = []
    for day, description in sorted(dates.items()):
        if day < '2000-01-01':
            continue
        stop = bisect_left(days, day)
        windows = {}
        for size in WINDOWS:
            if stop < size:
                continue
            start, end = days[stop-size], days[stop-1]
            if (date.fromisoformat(day) - date.fromisoformat(end)).days > 7:
                continue
            if start not in model or end not in model:
                continue
            # Changes in basis points. Two-year then ten-year for each component.
            v0, v1 = quotes[start] + model[start], quotes[end] + model[end]
            changes = [round((b-a)*100, 5) for a, b in zip(v0, v1)]
            windows[size] = [start, end, *changes]
        output.append({'date': day, **description, 'windows': windows})
    return output


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--acm', type=Path)
    cli.add_argument('--market', type=Path, default=DATA/'market-events.json')
    cli.add_argument('--treasury', type=Path, default=DATA/'pre-event-curve.json')
    cli.add_argument('--output', type=Path, default=DATA/'curve-components.json')
    args = cli.parse_args()
    if args.acm:
        raw = args.acm.read_bytes()
    else:
        with urlopen(ACM, timeout=90) as response:
            raw = response.read()
    series = sheet(raw)
    treasury = json.loads(args.treasury.read_text())
    observations = build(series, treasury, json.loads(args.market.read_text()))
    if not observations or not any(r['windows'] for r in observations):
        raise ValueError('No matched event windows')
    result = {'modelThrough': max(series), 'treasuryThrough': treasury['asOfDate'],
              'speechesThrough': treasury['eventsThrough'], 'workbook': ACM,
              'workbookSha256': sha256(raw).hexdigest(), 'events': observations}
    args.output.write_text(json.dumps(result, separators=(',', ':'))+'\n')
    print(f'{len(observations)} distinct event dates, model through {max(series)}')


if __name__ == '__main__':
    main()
