"""Rebuild the annual policy ledger directly from US, UK and euro-area policy instruments."""
import argparse
import csv
import io
import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BANKS = {
    'US': {'bank': 'Federal Reserve', 'instrument': 'Fed funds target / target-range midpoint',
           'url': 'https://www.federalreserve.gov/monetarypolicy/openmarket.htm', 'dataUrl':
           'https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTAR,DFEDTARL,DFEDTARU&cosd=1999-12-01'},
    'GB': {'bank': 'Bank of England', 'instrument': 'Official Bank Rate (repo rate in early years)',
           'url': 'https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp'},
    'EA': {'bank': 'European Central Bank', 'instrument': 'Deposit facility rate', 'url':
           'https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html',
           'dataUrl': 'https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV?startPeriod=1999-12-01&format=csvdata'},
}
FIRST = date(2000, 1, 1)


def fetch(item):
    bank, meta = item
    req = Request(meta.get('dataUrl', meta['url']), headers={'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'})
    with urlopen(req, timeout=40) as f:
        return bank, f.read().decode('utf-8-sig')


def extract(bank, text):
    if bank == 'GB':
        cells = re.findall(r'<td[^>]*>\s*(\d{2} [A-Za-z]{3} \d{2})\s*</td>\s*<td[^>]*>\s*([\d.]+)\s*</td>', text, re.I)
        # History extends back centuries. The table is newest first; stop after the 1999 baseline.
        result = {}
        for raw, rate in cells:
            d = datetime.strptime(raw, '%d %b %y').date()
            result[d] = Decimal(rate)
            if d < FIRST:
                break
        return result
    result = {}
    for row in csv.DictReader(io.StringIO(text)):
        if bank == 'EA':
            value = Decimal(row['OBS_VALUE'])
            day = row['TIME_PERIOD']
        else:
            day = row['observation_date']
            if day < '2008-12-16':
                value = Decimal(row['DFEDTAR'])
            else:
                low, high = Decimal(row['DFEDTARL']), Decimal(row['DFEDTARU'])
                if low > high:
                    raise ValueError(f'Inverted US target range on {day}')
                value = (low + high) / 2
        result[date.fromisoformat(day)] = value
    return result


def build(raw, through, readings):
    series = {bank: extract(bank, contents) for bank, contents in raw.items()}
    # The UK table is a change ledger; do not cap coverage at the latest UK rate change.
    end = min(through, max(series['EA']), max(series['US']))
    if (through - end).days > 7:
        raise ValueError('The daily policy rate sources are stale')
    years = {}
    for y in range(FIRST.year, end.year + 1):
        record = readings.get(str(y))
        if record:
            announcement = date.fromisoformat(record['date'])
            if announcement.year != y or record['bank'] not in BANKS:
                raise ValueError(f'Invalid decision record for {y}')
            if announcement > end:
                record = None
        years[str(y)] = {'banks': {}, 'record': record}
    for bank, history in series.items():
        observed = sorted((d, v) for d, v in history.items() if d <= end)
        if not observed or observed[0][0] >= FIRST:
            raise ValueError(f'Missing prior-year baseline for {bank}')
        if bank != 'GB' and any((d2-d1).days != 1 for (d1, _), (d2, _) in zip(observed, observed[1:])):
            raise ValueError(f'Daily observations missing for {bank}')
        prior = next(v for d, v in reversed(observed) if d < FIRST)
        for y, row in years.items():
            target_year = int(y)
            moves = []
            initial = prior
            for d, level in observed:
                if d.year != target_year or level == prior:
                    continue
                moves.append([d.isoformat(), float(prior), float(level), float((level-prior)*100)])
                prior = level
            rises = sum(m[3] for m in moves if m[3] > 0)
            cuts = -sum(m[3] for m in moves if m[3] < 0)
            if rises - cuts != float(100 * (prior-initial)):
                raise ValueError(f'Net change failed for {bank} in {target_year}')
            row['banks'][bank] = {'open': float(initial), 'close': float(prior), 'hikes': rises,
                                  'cuts': cuts, 'net': rises-cuts, 'moves': moves}
    return {'through': end.isoformat(), 'banks': BANKS, 'years': years}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    readings = json.loads((ROOT/'scripts/policy-year-records.json').read_text())
    with ThreadPoolExecutor(max_workers=3) as pool:
        raw = dict(pool.map(fetch, BANKS.items()))
    result = build(raw, args.through, readings)
    target = ROOT/'dist/data/policy-year-ledger.json'
    with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, delete=False) as f:
        json.dump(result, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
    temp = Path(f.name)
    temp.chmod(0o644)
    temp.replace(target)
    print(f"{len(result['years'])} annual records through {result['through']}")
