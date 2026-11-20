"""Reconcile official archive entries and editorial reviews in a private state file.

Initialise once with --init --from-date YYYY-MM-DD. Retain the same state across
updates. --reviewed accepts exact manuscript filenames after editorial review.
No public build step uses this file.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
import json
import os
import re
from pathlib import Path
import tempfile
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree
from zipfile import ZipFile

import fcntl

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKOUT = SCRIPT_ROOT if (SCRIPT_ROOT / "dist/data").is_dir() else Path.cwd()
DATA = DEFAULT_CHECKOUT / "dist" / "data"


def digest(value):
    serialised = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(serialised.encode()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def key(raw):
    url = urlsplit(raw)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError(f"Invalid publication URL: {raw}")
    return urlunsplit((url.scheme, url.netloc.lower(), url.path.rstrip("/"), url.query, url.fragment))


def prompt_digest(path):
    if path.suffix.lower() == ".docx":
        with ZipFile(path) as document:
            root = ElementTree.fromstring(document.read("word/document.xml"))
        word = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        text = "\n".join("".join(p.itertext()) for p in root.iter(word + "p"))
    else:
        text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("The private instructions are empty")
    return sha256(text.strip().encode()).hexdigest()


def catalogue(archive, index, notes_dir):
    """Match the archive reader's canonical URLs, explicit aliases and note-only entries."""
    if not archive or not index:
        raise ValueError("Archive and manuscript index must both be supplied")
    notes = {}
    editions = {}
    for note in index:
        canonical = key(note["url"])
        if canonical in notes:
            raise ValueError(f"Duplicate manuscript: {canonical}")
        notes[canonical] = note
        for url in [canonical, *note.get("publication", {}).get("aliases", [])]:
            alias = key(url)
            if alias in editions and editions[alias] != canonical:
                raise ValueError(f"Overlapping official source alias: {alias}")
            editions[alias] = canonical

    groups = defaultdict(list)
    for row in archive:
        url = key(row["url"])
        groups[editions.get(url, url)].append(row)
    for canonical in notes:
        groups.setdefault(canonical, [])

    result = {}
    for url, rows in groups.items():
        note = notes.get(url)
        meta = (note or {}).get("publication", {})
        row = next((r for r in rows if key(r["url"]) == url), rows[0] if rows else {})
        day = note["date"] if note else row["date"]
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError(f"Invalid publication date: {day}")
        official = {
            "date": day, "url": url, "title": meta.get("title") or row["title"],
            "jurisdiction": meta.get("jurisdiction") or row["jurisdiction"],
            "institution": row.get("institution") or note["bank"],
            "type": meta.get("type") or row["type"]
        }
        aliases = sorted(({key(r["url"]) for r in rows} | {key(a) for a in meta.get("aliases", [])}) - {url})
        related = sorted({key(link["url"]) for r in rows for link in r.get("related", [])})
        name = None
        text_digest = None
        if note:
            name = note["file"]
            if Path(name).name != name:
                raise ValueError(f"Invalid manuscript path: {name}")
            manuscript = read(notes_dir / name)
            if key(manuscript["url"]) != url or manuscript["date"] != day:
                raise ValueError(f"Manuscript and index disagree: {name}")
            text_digest = digest(manuscript)
        # Include the archived titles and editions even when metadata is overridden
        # by the manuscript. Ordering and changes to discovery pages are immaterial.
        rows_digest = sorted({digest({k: r[k] for k in ("title","date","institution","type","jurisdiction")}) for r in rows})
        revision = digest([official, aliases, related, rows_digest, text_digest])
        result[url] = dict(official, aliases=aliases, revision=revision, noteFile=name, inPublicArchive=True)
    return result


def include_supplements(publications, supplements):
    # Explicit official aliases can connect a landing page and its document.
    # Identical titles alone cannot establish that two publications are the same.
    editions = {a: url for url, item in publications.items() for a in [url, *item["aliases"]]}
    for record in supplements.values():
        url = key(record["url"])
        candidates = {url, *(key(a) for a in record.get("aliases", []))}
        matches = {editions[a] for a in candidates if a in editions}
        if len(matches) > 1:
            raise ValueError(f"Ambiguous supplemental source aliases: {url}")
        if matches:
            canonical = matches.pop()
            item = publications[canonical]
            item["aliases"] = sorted((set(item["aliases"]) | candidates) - {canonical})
        else:
            canonical = url
            official = {k: record[k] for k in ("jurisdiction","date","institution","type","title")}
            if not all(isinstance(v, str) and v.strip() for v in official.values()):
                raise ValueError(f"Missing official source metadata: {url}")
            date.fromisoformat(official["date"])
            item = dict(official, url=url, aliases=sorted(candidates - {url}), noteFile=None,
                        revision=digest(record), inPublicArchive=False)
            publications[url] = item
        # Keep the canonical publication identity when an additional edition is
        # processed later. A dated original outranks an undated catalogue copy.
        primary = supplements.get(canonical, {})
        for field in ("workId", "candidateDate"):
            if field in record:
                item[field] = primary.get(field, record[field])
        date_record = primary if primary.get("confirmedDate") else record
        if date_record.get("confirmedDate") or not item.get("confirmedDate"):
            for field in ("dateStatus", "confirmedDate", "dateEvidence"):
                if field in date_record:
                    item[field] = date_record[field]
        if record.get("sourceUrls"):
            item["sourceUrls"] = sorted(set(item.get("sourceUrls", [])) |
                                        {key(a) for a in record["sourceUrls"]})
        editions.update({a: canonical for a in candidates})
    return editions


def apply_source_versions(publications, editions, hashes):
    owners = defaultdict(set)
    for official, canonical in editions.items():
        owners[official].add(canonical)
    for canonical, item in publications.items():
        for document in item.get("sourceUrls", []):
            owners[document].add(canonical)
    versions = defaultdict(list)
    for url, checksum in hashes.items():
        if not isinstance(checksum, str) or not re.fullmatch("[0-9a-f]{64}", checksum):
            raise ValueError(f"Invalid source SHA-256: {url}")
        for owner in owners.get(url, []):
            versions[owner].append((url, checksum))
    for url, pairs in versions.items():
        item = publications[url]
        item["revision"] = digest([item["revision"], sorted(pairs)])


def source_only_decisions(raw, editions):
    decisions = {}
    for decision in raw:
        url = key(decision["url"])
        if url not in editions:
            raise ValueError(f"Unknown source-only decision: {url}")
        if not all(isinstance(decision.get(k), str) and decision[k].strip() for k in ("locator","evidence")):
            raise ValueError(f"Provide a specific source locator and editorial evidence for {url}")
        decisions[editions[url]] = {k: decision[k] for k in ("locator","evidence")}
    return decisions


def reconcile(catalogue, previous, from_date, prompt_hash, reviewed, dispositions):
    ledger = dict(previous.get("ledger", {}))
    prior_editions = {a: state for url, state in ledger.items() for a in [url, *state.get("aliases", [])]}
    files = {item["noteFile"] for item in catalogue.values() if item["noteFile"]}
    if set(reviewed) - files:
        raise ValueError("Unknown manuscript(s): " + ", ".join(sorted(set(reviewed) - files)))
    work = []
    totals = Counter()
    public = Counter()
    months = defaultdict(Counter)
    public_months = defaultdict(Counter)
    retired = set(ledger)
    missing_public = []
    prior_public_urls = {i["url"] for i in previous.get("items", []) if i.get("inPublicArchive")}
    for url, item in catalogue.items():
        prior = next((prior_editions[a] for a in (url, *item["aliases"]) if a in prior_editions), None)
        changed = prior is None or prior["revision"] != item["revision"]
        assigned = bool(item["date"] >= from_date or (prior and prior["assigned"]) or (previous and changed))
        receipt = digest([prompt_hash, item["revision"]])
        accepted = (prior or {}).get("reviewReceipt")
        decision = (prior or {}).get("disposition") if (prior or {}).get("decisionReceipt") == receipt else None
        if url in dispositions and item["noteFile"]:
            raise ValueError(f"Source-only decision resolves to published manuscript {item['noteFile']}: {url}")
        if url in dispositions:
            assigned = True
            decision = dispositions[url]
        if item["noteFile"] in reviewed:
            if url in dispositions:
                raise ValueError(f"Conflicting editorial decisions: {url}")
            assigned = True
            accepted = receipt
            decision = None
        was_public = bool((prior or {}).get("everInPublicArchive") or url in prior_public_urls)
        state = {"revision": item["revision"], "assigned": assigned,
                 "everInPublicArchive": item["inPublicArchive"] or was_public}
        if was_public and not item["inPublicArchive"]:
            missing_public.append(url)
        if item["aliases"]:
            state["aliases"] = item["aliases"]
        if decision:
            state.update(disposition=decision, decisionReceipt=receipt)
        elif accepted == receipt and item["noteFile"]:
            state["reviewReceipt"] = receipt
        ledger[url] = state
        retired.discard(url)
        # If a published notice has acquired its canonical manuscript URL, it
        # is still the same publication and should not appear as a withdrawal.
        for alias in item["aliases"]:
            if alias != url and alias not in catalogue:
                ledger.pop(alias, None)
                retired.discard(alias)
        if not assigned:
            continue
        if decision:
            status = "source-only"
        elif not item["noteFile"]:
            status = "needs-analysis"
        else:
            status = "reviewed" if state.get("reviewReceipt") else "needs-review"
        output = {k: v for k, v in item.items() if k not in ("revision", "aliases")}
        work.append(output | {"status": status})
        groups = [totals, months[item["date"][:7]]]
        if item["inPublicArchive"]:
            groups.extend([public, public_months[item["date"][:7]]])
        for group in groups:
            group[status] += 1
            group["withManuscript"] += int(bool(item["noteFile"]))
    for url in retired:
        ledger[url]["absentFromIndex"] = True
    work.sort(key=lambda r: (r["date"], r["url"]), reverse=True)

    def counts(values):
        statuses = ("needs-analysis", "needs-review", "reviewed", "source-only")
        return {"assigned": sum(values[s] for s in statuses), "withManuscript": values["withManuscript"],
                **{s: values[s] for s in statuses}}
    prior_absent = previous.get("absentItems", []) + previous.get("items", [])
    return {"schemaVersion": 1, "fromDate": from_date, "promptSha256": prompt_hash,
            "counts": counts(totals), "months": {m: counts(c) for m, c in sorted(months.items())},
            "publicCounts": counts(public), "publicMonths": {m: counts(c) for m,c in sorted(public_months.items())},
            "absentFromPublicIndex": sorted(set(missing_public) | {u for u in retired if ledger[u].get("everInPublicArchive") or u in prior_public_urls}),
            "absentFromIndex": sorted(retired), "absentItems": [i for i in prior_absent if i["url"] in retired],
            "items": work, "ledger": ledger}



def save_private(path, result):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".publication-work-", delete=False) as out:
        temp = Path(out.name)
        try:
            json.dump(result, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
            out.close()
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DATA / "research-archive.json")
    parser.add_argument("--index", type=Path, default=DATA / "research-notes.json")
    parser.add_argument("--notes-dir", type=Path, default=DATA / "notes")
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--from-date", type=date.fromisoformat, help="required for the first run")
    parser.add_argument("--supplement", type=Path, help="private JSON array of additional official archive records")
    parser.add_argument("--source-fingerprints", type=Path, help="private JSON object mapping source URLs to content SHA-256")
    parser.add_argument("--dispositions", type=Path, help="source-only editorial decisions with url, locator and evidence")
    parser.add_argument("--reviewed", nargs="+", metavar="NOTE_FILENAME", default=[])
    args = parser.parse_args()
    state = args.state.resolve()
    private_inputs = [p for p in (args.prompt,args.supplement,args.source_fingerprints,args.dispositions) if p]
    private_paths = [state, *(p.resolve() for p in private_inputs)]
    for location in [DEFAULT_CHECKOUT, *args.notes_dir.resolve().parents]:
        if (location / "dist/data").is_dir() and (location / "scripts/build-research-notes.py").is_file():
            if any(p.is_relative_to(location) for p in private_paths):
                parser.error("Keep editorial inputs and state outside the public checkout")
    if state in {p.resolve() for p in (*private_inputs, args.archive, args.index)}:
        parser.error("The state path must differ from all inputs")
    if args.init != bool(args.from_date):
        parser.error("Use --init and --from-date together only when starting a new ledger")
    state.parent.mkdir(parents=True, exist_ok=True)
    # Lock a separate inode so replacing the ledger atomically preserves the lock.
    with os.fdopen(os.open(str(state) + ".lock", os.O_CREAT | os.O_RDWR, 0o600), "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.init == state.exists():
            parser.error("Initialisation requires an unused path; subsequent runs require the saved private ledger")
        previous = {} if args.init else read(state)
        if not args.init and (previous.get("schemaVersion") != 1 or not previous.get("ledger")):
            parser.error("Invalid or empty private ledger")
        publications = catalogue(read(args.archive), read(args.index), args.notes_dir)
        start = args.from_date.isoformat() if args.init else previous["fromDate"]
        supplement = previous.get("supplement", {})
        if args.supplement:
            supplement.update({key(row["url"]): row for row in read(args.supplement)})
        editions = include_supplements(publications, supplement)
        hashes = previous.get("sourceFingerprints", {})
        if args.source_fingerprints:
            hashes.update({key(url): value for url,value in read(args.source_fingerprints).items()})
        apply_source_versions(publications, editions, hashes)
        decisions = source_only_decisions(read(args.dispositions) if args.dispositions else [], editions)
        result = reconcile(publications, previous, start, prompt_digest(args.prompt), set(args.reviewed), decisions)
        result.update(supplement=supplement, sourceFingerprints=hashes)
        save_private(state, result)
    print(json.dumps(result["counts"], sort_keys=True))
    if result["absentFromPublicIndex"]:
        print(f"{len(result['absentFromPublicIndex'])} prior public works are missing from this public archive and index.")
    if result["absentFromIndex"]:
        print(f"{len(result['absentFromIndex'])} prior source identities are absent from the supplied index; see private state.")


if __name__ == "__main__":
    main()
