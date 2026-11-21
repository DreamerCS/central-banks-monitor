"""Census of the discovery CSV, with conservative links to the event study.

python scripts/audit-news-catalogue.py /path/to/news.csv [--site news-framing.json] [--output summary.json]
"""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

DATA = Path(__file__).resolve().parents[1] / "dist/data"
DOMAINS = {"Bloomberg": "bloomberg.com", "Financial Times": "ft.com",
           "Reuters": "reuters.com", "The Wall Street Journal": "wsj.com"}
SCOPE = ("fedOnly", "ecbOnly", "both", "otherTagged", "untagged")
EXPECTED = {"Bloomberg": 30148, "Financial Times": 6471, "Reuters": 116505, "The Wall Street Journal": 2783}


def scope(jurisdictions):
    tags = {t.strip() for t in jurisdictions.split("|") if t.strip()}
    fed, ecb = "United States" in tags, "Euro area" in tags
    if fed and ecb:
        return "both"
    if fed:
        return "fedOnly"
    if ecb:
        return "ecbOnly"
    return "otherTagged" if tags else "untagged"


def original_key(url, publisher):
    u = urlsplit(url)
    base = DOMAINS.get(publisher)
    if not base or u.scheme not in {"http", "https"} or u.username or u.password or u.port:
        return "", ""
    host = u.hostname or ""
    if host in {base, "www." + base}:
        bucket = "directRows"
    elif host.endswith("." + base):
        bucket = "publisherSubdomainRows"
    else:
        return "", ""
    # Keep meaningful query strings (including wire/story IDs) and edition-specific paths.
    path = u.path.rstrip("/")
    query = urlencode([(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
                       if not k.startswith(("utm_", "syn-")) and k not in {"mod", "shareType"}])
    canonical_host = base if bucket == "directRows" else host
    if base == "wsj.com" and host in {base, "www." + base, "online.wsj.com"}:
        match = re.fullmatch(r"/articles?/(SB[0-9]+)(?:\.html)?", path)
        if match:
            path = "/articles/" + match[1]
            canonical_host = base
    if base == "ft.com" and canonical_host == base:
        match = re.fullmatch(r"/cms/s/[0-9]+/([a-f0-9-]{36})\.html", path)
        if match:
            path = "/content/" + match[1]
    return bucket, canonical_host + path + ("?" + query if query else "") + ("#" + u.fragment if u.fragment else "")


def basis(label):
    s = label.lower()
    if "gdelt" in s or "cc-news" in s:
        return "News corpus observation"
    if "wire" in s or "reuters" in s:
        return "Wire edition or archive"
    if "rss" in s or "feed" in s:
        return "Feed or RSS record"
    if any(x in s for x in ("publisher", "guardian", "nyt", "central banking publisher")) and "unverified" not in s:
        return "Publisher date, listing or timestamp"
    return "Other archive, index or catalogue date"


def empty_scope():
    return dict.fromkeys(SCOPE, 0)


def new_stats():
    return {"rows": 0, "directRows": 0, "publisherSubdomainRows": 0, "scope": empty_scope(),
            "directScope": empty_scope(), "byYear": {}}


def census(source, site):
    ids = set()
    by_url, by_id = defaultdict(set), defaultdict(set)
    overlap = {"id": set(), "url": set(), "archive": set()}
    for s in site:
        _, key = original_key(s["url"], s["publisher"])
        if key:
            by_url[key].add(s["id"])
        if s.get("workbookHeadlineId"):
            by_id[s["workbookHeadlineId"]].add(s["id"])
    outlets = {k: new_stats() for k in DOMAINS}
    all_scope, four_scope, direct_scope = empty_scope(), empty_scope(), empty_scope()
    dates, sources, four_dates, four_bases, all_bases = Counter(), Counter(), Counter(), Counter(), Counter()
    years = {}
    n = 0
    with source.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            n += 1
            ident = r["Headline ID"]
            if not ident or ident in ids:
                raise ValueError(f"Blank or repeated archive ID at row {n}")
            ids.add(ident)
            dates[r["Date evidence"]] += 1
            all_bases[basis(r["Date evidence"])] += 1
            group = scope(r["Jurisdictions"])
            all_scope[group] += 1
            pub = r["Publisher"]
            yr = r["Recorded date"][:4]
            years[yr] = years.get(yr, 0) + 1
            sources[r["Event link status"]] += 1
            if pub not in outlets:
                continue
            item = outlets[pub]
            year = item["byYear"].setdefault(yr, {"rows": 0, "directRows": 0, "publisherSubdomainRows": 0, **empty_scope()})
            item["rows"] += 1
            year["rows"] += 1
            year[group] += 1
            item["scope"][group] += 1
            four_scope[group] += 1
            four_dates[r["Date evidence"]] += 1
            four_bases[basis(r["Date evidence"])] += 1
            bucket, key = original_key(r["Article URL"], pub)
            if bucket:
                item[bucket] += 1
                year[bucket] += 1
            if bucket == "directRows":
                item["directScope"][group] += 1
                direct_scope[group] += 1
            im = by_id.get(ident, ())
            um = by_url.get(key, ())
            overlap["id"].update(im)
            overlap["url"].update(um)
            if im or um:
                overlap["archive"].add(ident)
    matches = overlap["id"] | overlap["url"]
    matched_ids = overlap["id"] & overlap["url"]
    return {
        "allRows": n, "uniqueIds": len(ids), "allScope": all_scope, "allRowsByYear": dict(sorted(years.items())),
        "fourOutletRows": sum(four_scope.values()), "fourOutletScope": four_scope,
        "fourOutletDirectRows": sum(direct_scope.values()), "fourOutletDirectScope": direct_scope,
        "fourOutletPublisherSubdomainRows": sum(p["publisherSubdomainRows"] for p in outlets.values()),
        "publishers": outlets, "dateEvidence": dict(dates.most_common()), "fourOutletDateEvidence": dict(four_dates.most_common()),
        "dateBasis": dict(all_bases), "fourOutletDateBasis": dict(four_bases), "archiveEventLinkStatus": dict(sources),
        "siteOverlap": {"curatedRows": len(site), "matchedSiteRows": len(matches), "byId": len(overlap["id"]),
                        "byUrl": len(overlap["url"]), "both": len(matched_ids), "matchedArchiveRows": len(overlap["archive"])},
        "notes": [
            "Counts refer to unique archive headline identifiers. Two records can refer to successive versions of one story. Archive scope uses the jurisdiction tags present in the file.",
            "Fed only and ECB only refer to the two study jurisdictions. A row can mention other countries. Both is counted once. An untagged row has no jurisdiction assigned.",
            "Direct-host counts require a web URL on the publisher’s main domain or its www alias. Other publisher subdomains are counted separately. The link can lead to an index, an unavailable page or a different edition. The hostname alone cannot establish an original article or an event match.",
            "Years use the archive’s recorded date. Wire and feed dates can identify an edition. News-corpus observations can postdate publication. Date labels describe archive evidence and cannot timestamp the first appearance of a headline.",
            "Overlap uses a shared archive ID or a conservative publisher URL match with common tracking parameters removed. WSJ legacy article IDs and FT legacy content IDs are normalised. Related press coverage on another URL may remain unmatched. Each study record and each archive row are counted once in their respective unions.",
        ],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("--site", type=Path, default=DATA / "news-framing.json")
    ap.add_argument("--output", type=Path, default=DATA / "news-catalogue-summary.json")
    ap.add_argument("--check-original", action="store_true", help="Require the original 253,188-record snapshot.")
    args = ap.parse_args()
    result = census(args.input, json.loads(args.site.read_text())["records"])
    if args.check_original and (result["allRows"] != 253188 or {k: v["rows"] for k, v in result["publishers"].items()} != EXPECTED):
        raise SystemExit("Original snapshot counts do not match.")
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
