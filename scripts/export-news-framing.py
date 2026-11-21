"""Export the public event-linked annotations as CSV. Supply --check to verify the export."""
import argparse
import csv
import io
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "dist/data"
FIELDS = (
    "id", "bank", "date", "type", "speaker", "publisher", "publicationDate",
    "coverageMode", "evidenceKind", "angle", "focus", "action", "path", "pathBasis",
    "markets", "publishedAt", "updatedAt", "editionAt", "versionNote", "url",
    "leader", "cycle", "actionBp", "priorMoveBp", "priorQuoteQualifier", "pricingGapBp",
    "pricingGapMethod", "priorMethod", "priorPricingSource", "marketBp", "marketInstrument",
    "marketWindow", "marketUrl", "evidenceUrl", "officialSource", "workbookHeadlineId", "workbookEventId", "headlineSha256",
)


def render(records, meetings):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in records:
        record = {key: row.get(key) for key in FIELDS}
        if row["type"] == "decision":
            meeting = meetings[(row["bank"], row["date"])]
            for field in FIELDS[FIELDS.index("leader"):FIELDS.index("marketUrl")+1]:
                record[field] = meeting.get(field)
        record["markets"] = " | ".join(f"{m['asset']} ({m['direction']})" for m in row["markets"])
        writer.writerow(record)
    return output.getvalue().encode("utf-8-sig")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rows = json.loads((DATA / "news-framing.json").read_text())["records"]
    target = DATA / "news-framing.csv"
    cohorts = json.loads((DATA / "stance-cohorts.json").read_text())["banks"]
    meetings = {(bank["id"], r["date"]): r for bank in cohorts for r in bank["records"]}
    content = render(rows, meetings)
    if args.check:
        if not target.exists() or target.read_bytes() != content:
            raise SystemExit("Run scripts/export-news-framing.py to refresh the CSV.")
    else:
        target.write_bytes(content)
