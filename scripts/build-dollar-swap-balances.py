"""Reconstruct daily USD swap balances for the four 2008/2020 common counterparties."""
import argparse
import csv
import io
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen

BOARD_FILE = "https://www.federalreserve.gov/regreform/files/cbls.csv"
DESK_FILE = "https://markets.newyorkfed.org/api/fxs/all/search.json?startDate=03/01/2020&endDate=05/31/2020"
BANKS = {
    "Banco Central do Brasil": "Brazil",
    "Banco de Mexico": "Mexico",
    "Bank of Korea": "Korea",
    "Monetary Authority of Singapore": "Singapore",
}
EPISODES = [
    ("2008-10-29", "2008-12-31", 30_000),
    ("2020-03-19", "2020-05-31", 60_000),
]
DEST = Path(__file__).resolve().parents[1] / "dist/data/dollar-swap-balances.csv"


def source(local, url):
    if local:
        return Path(local).read_bytes()
    with urlopen(Request(url, headers={"User-Agent": "The Policy Tape research"}), timeout=50) as response:
        return response.read()


def crisis_loans(data):
    reader = csv.reader(io.StringIO(data.decode("latin-1")))
    next(reader)
    header = [field.strip() for field in next(reader)]
    for values in reader:
        row = dict(zip(header, values))
        name = row.get("Central bank counterparty", "").strip()
        if name in BANKS:
            start, end = [
                datetime.strptime(row[key].strip(), "%b %d %Y").date()
                for key in ("Settlement date", "Maturity date")
            ]
            amount = Decimal(row["Amount extended"].replace(",", "").strip())
            yield BANKS[name], start, end, amount


def pandemic_loans(data):
    for row in json.loads(data)["fxSwaps"]["operations"]:
        name = row["counterparty"]
        if name in BANKS and row["currency"] == "USD" and row["operationType"] == "U.S. Dollar Liquidity Swap":
            yield (
                BANKS[name], date.fromisoformat(row["settlementDate"]),
                date.fromisoformat(row["maturityDate"]), Decimal(str(row["amount"])) / 1_000_000,
            )


def balances(rows, beginning, ending):
    changes = defaultdict(lambda: defaultdict(Decimal))
    for bank, settlement, maturity, amount in rows:
        if settlement >= maturity or amount <= 0:
            raise ValueError("Invalid settlement, maturity or principal")
        changes[settlement][bank] += amount
        changes[maturity][bank] -= amount
    if not any(beginning <= d <= ending for d in changes):
        raise ValueError("No transactions in the selected period")
    # The four temporary lines opened at zero on their respective announcement dates.
    outstanding = dict.fromkeys(BANKS.values(), Decimal(0))
    day = beginning
    while day <= ending:
        for bank, delta in changes.get(day, {}).items():
            outstanding[bank] += delta
        if min(outstanding.values()) < 0:
            raise ValueError("Negative outstanding principal")
        yield [day, *(format(balance.normalize(), "f") for balance in outstanding.values())]
        day += timedelta(days=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board-csv")
    parser.add_argument("--desk-json")
    parser.add_argument("--out", type=Path, default=DEST)
    args = parser.parse_args()
    loans = [crisis_loans(source(args.board_csv, BOARD_FILE)), pandemic_loans(source(args.desk_json, DESK_FILE))]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["date", "line_per_country_usd_m", *(bank.lower() + "_usd_m" for bank in BANKS.values())])
    for records, (beginning, ending, ceiling) in zip(loans, EPISODES):
        for day, *amounts in balances(records, date.fromisoformat(beginning), date.fromisoformat(ending)):
            if any(Decimal(value) > ceiling for value in amounts):
                raise ValueError("Outstanding principal exceeds the line ceiling")
            writer.writerow([day, ceiling, *amounts])
    args.out.write_text(output.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    main()
