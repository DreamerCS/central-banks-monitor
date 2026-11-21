"""Screen a private headline catalogue against the full Fed/ECB rate-decision roster.

The public CSV contains only counts. The optional review queue contains licensed
or third-party metadata and should be written outside the site's public files.
Example: python scripts/screen-news-candidates.py catalogue.csv --queue /tmp/review.csv
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
OUTLETS = {
    "Bloomberg": "bloomberg.com",
    "Financial Times": "ft.com",
    "Reuters": "reuters.com",
    "The Wall Street Journal": "wsj.com",
}
BANKS = {
    "fed": ("Fed", re.compile(r"\b(?:Fed(?:eral Reserve)?|FOMC|Federal Open Market Committee)\b", re.I)),
    "ecb": ("ECB", re.compile(r"\b(?:ECB|European Central Bank)\b", re.I)),
}
POLICY = re.compile(
    r"\b(?:rates?|hikes?|hiking|cuts?|cutting|eas(?:e|es|ing)|tighten(?:s|ed|ing)?|"
    r"taper(?:s|ed|ing)?|QE\d*|QT|quantitative easing|quantitative tightening|"
    r"policy (?:move|meeting|decision|statement|outlook|path)|"
    r"monetary policy|policy[- ]makers|forward guidance|dot plot|"
    r"asset purchases?|bond[- ]buy(?:ing|s)|stimulus|press conference|"
    r"(?:Fed|ECB|FOMC) (?:meeting|decision|statement)|"
    r"(?:holds?|stays?|stands?) (?:steady|pat)|on hold)\b", re.I,
)
QUEUE_FIELDS = (
    "bank", "date", "publisher", "headlineId", "recordedDate", "dayOffset", "headline",
    "articleUrl", "urlStatus", "dateEvidence", "chronologyBasis", "timestampUtcIfExplicit",
    "centralBanks", "sourceCatalogues", "nameMatch", "policyMatch",
)
COUNT_FIELDS = ("bank", "date", "publisher", "candidateCount", "originalHostCount")


def url_status(url, publisher):
    try:
        link = urlsplit(url)
        host = link.hostname
        if link.scheme not in {"http", "https"} or not host:
            return "missing or invalid URL"
        if link.username or link.password or link.port:
            return "other URL"
    except ValueError:
        return "missing or invalid URL"
    if host in {OUTLETS[publisher], "www." + OUTLETS[publisher]}:
        return "original host; article unchecked"
    if host == "news.google.com":
        return "Google News redirect"
    return "other host or redirect"


def chronology(evidence):
    label = evidence.lower()
    if any(term in label for term in ("observation", "gdelt", "index date", "index and", "catalogue", "wire utc or archive")):
        return "index, catalogue or mixed date"
    if "publisher" in label:
        return "publisher-attributed metadata"
    return "other or unresolved date"


def decision_frames():
    frames = json.loads((DATA / "stance-cohorts.json").read_text())["banks"]
    cells, windows = {}, defaultdict(list)
    for bank in frames:
        key = bank["id"]
        if key not in BANKS:
            continue
        for row in bank["records"]:
            event_day = date.fromisoformat(row["date"])
            leader = row["leader"].split()[-1]
            leader_pattern = re.compile(r"\b" + re.escape(leader) + r"\b", re.I)
            for publisher in OUTLETS:
                cells[key, row["date"], publisher] = [0, 0]
            for offset in (-1, 0, 1):
                observed = (event_day + timedelta(days=offset)).isoformat()
                windows[observed].append((key, row["date"], offset, leader_pattern))
    return cells, windows


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogue", type=Path)
    parser.add_argument("--queue", type=Path, help="Private reviewer output")
    parser.add_argument("--counts", type=Path, default=DATA / "news-candidate-counts.csv")
    args = parser.parse_args()
    if args.queue and (DATA.parent in args.queue.resolve().parents or args.queue.resolve() == args.counts.resolve()):
        parser.error("Choose a private queue location outside the published site and distinct from --counts.")
    cells, windows = decision_frames()
    candidates = {}
    with args.catalogue.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            day, publisher = row["Recorded date"], row["Publisher"]
            if publisher not in OUTLETS or day not in windows:
                continue
            title = row["Headline"]
            policy = POLICY.search(title)
            if not policy:
                continue
            tags = {t.strip() for t in row["Central banks"].split("|")}
            for bank, event_day, offset, leader in windows[day]:
                tag, bank_pattern = BANKS[bank]
                if tag not in tags:
                    continue
                name = bank_pattern.search(title) or leader.search(title)
                if not name:
                    continue
                headline_id = row["Headline ID"].strip()
                if not headline_id:
                    raise ValueError("Catalogue candidate has no headline ID")
                key = bank, event_day, publisher, headline_id
                if key in candidates:
                    continue
                status = url_status(row["Article URL"], publisher)
                counts = cells[bank, event_day, publisher]
                counts[0] += 1
                counts[1] += int(status == "original host; article unchecked")
                candidates[key] = dict(zip(QUEUE_FIELDS, (
                    bank, event_day, publisher, headline_id, day, offset, title,
                    row["Article URL"], status, row["Date evidence"], chronology(row["Date evidence"]),
                    row["Timestamp UTC if explicit"], row["Central banks"], row["Source catalogues"],
                    name.group(), policy.group(),
                ), strict=True))
    write_csv(args.counts, COUNT_FIELDS, (
        dict(zip(COUNT_FIELDS, (*key, *cells[key]), strict=True)) for key in sorted(cells)
    ))
    if args.queue:
        write_csv(args.queue, QUEUE_FIELDS, (candidates[key] for key in sorted(candidates)))
    unique_ids = {key[-1] for key in candidates}
    print(f"{len(unique_ids)} unique candidate headline IDs, {len(candidates)} event assignments, {len(cells)} decision/outlet cells.")


if __name__ == "__main__":
    main()
