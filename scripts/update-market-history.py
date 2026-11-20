"""Refresh the daily Federal Reserve rates and FX series used on the overview."""
import csv
import io
import math
import os
from pathlib import Path
from urllib.request import urlopen

SERIES = ["DGS2", "DGS10", "DEXUSEU", "DEXJPUS"]
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + ",".join(SERIES)
DESTINATION = Path(__file__).resolve().parents[1] / "dist/data/market-history.csv"


def write_history(contents):
    reader = csv.DictReader(io.StringIO(contents))
    if reader.fieldnames != ["observation_date", *SERIES]:
        raise ValueError("Unexpected series")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(reader.fieldnames)
    previous = ""
    counts = [0] * len(SERIES)
    for row in reader:
        day = row["observation_date"]
        if day < "1999-12-30":
            continue
        if day <= previous:
            raise ValueError("Unordered dates")
        previous = day
        values = [row[s] for s in SERIES]
        for i, value in enumerate(values):
            if value:
                if not math.isfinite(float(value)):
                    raise ValueError("Invalid observation")
                counts[i] += 1
        if any(values):
            writer.writerow([day, *values])
    if min(counts) < 6000:
        raise ValueError("Truncated time series")
    temporary = DESTINATION.with_suffix(".tmp")
    temporary.write_text(buffer.getvalue())
    os.replace(temporary, DESTINATION)


if __name__ == "__main__":
    with urlopen(URL, timeout=45) as response:
        write_history(response.read().decode("utf-8-sig"))
