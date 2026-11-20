"""Validate and normalise public central bank publication records."""
import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dist" / "data"
FIELDS = ("jurisdiction", "date", "institution", "title", "type", "url")
TYPES = {"Decision", "Minutes", "Forecast", "Speech", "Research", "Testimony", "Statement"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_records(path):
    return read_json(path) if path.is_file() else [
        row for source in sorted(path.glob("*.json")) for row in read_json(source)
    ]


def public_url(raw):
    url = urlsplit(raw)
    assert url.scheme == "https" and url.hostname and not url.username and not url.password, raw
    return (url.hostname, url.path.rstrip("/"), url.query, url.fragment)


def build(records):
    periods = read_json(DATA / "archive-periods.json")
    targets = {target["name"] for target in read_json(DATA / "coverage.json")["targets"]}
    assert records, "The archive is empty"
    unique = set()
    counts = Counter()
    result = []
    for record in records:
        assert all(isinstance(record[key], str) and record[key].strip() for key in FIELDS), record["url"]
        day = record["date"]
        assert date.fromisoformat(day).isoformat() == day
        assert record["jurisdiction"] in targets and record["type"] in TYPES, record["url"]
        period = next((item for item in periods if item["start"] <= day <= item["end"]), None)
        assert period is not None, day
        counts[period["id"]] += 1
        identity = public_url(record["url"])
        assert identity not in unique, f"Duplicate publication URL: {record['url']}"
        unique.add(identity)
        row = {key: value for key, value in record.items() if key in FIELDS}
        if record.get("related"):
            row["related"] = []
            for link in record["related"]:
                public_url(link["url"])
                row["related"].append({"label": link["label"], "url": link["url"]})
        result.append(row)
    for period in periods:
        print(f"{period['label']}: {counts[period['id']]} publications")
    return sorted(result, key=lambda row: (row["date"], row["title"]), reverse=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fragments", type=Path, help="Read publication records from a local input directory")
    args = parser.parse_args()
    archive = DATA / "research-archive.json"
    rows = build(load_records(args.fragments or archive))
    archive.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
