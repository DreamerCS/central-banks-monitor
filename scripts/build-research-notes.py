"""Validate published manuscripts and build the lightweight research reader index."""
import json
import re
from datetime import date
from hashlib import sha256
from pathlib import Path
from textwrap import shorten
from urllib.parse import urlsplit

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
FIELDS = {"title", "bank", "date", "url", "summary", "questions", "limitation"}


def filled(value):
    return isinstance(value, str) and bool(value.strip())


def source_key(raw):
    url = urlsplit(raw)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError(f"Invalid publication URL: {raw}")
    return (url.netloc.lower(), url.path.rstrip("/"), url.query, url.fragment)


def opening_sentence(paragraph):
    for stop in re.finditer(r'[.!?][”’"]?(?=\s|$)', paragraph):
        lead = paragraph[:stop.end()]
        if re.search(r'\b(?:[A-Za-z]|Mr|Mrs|Ms|Dr|Prof|pp|vs)\.$', lead):
            continue
        return shorten(lead, width=325, placeholder="…")
    return shorten(paragraph, width=325, placeholder="…")


def build():
    index = []
    urls = set()
    revision = sha256()
    publications = json.loads(Path(__file__).with_name("note-publications.json").read_text())
    archive = json.loads((DATA / "research-archive.json").read_text())
    archived = {source_key(row["url"]) for row in archive}
    jurisdictions = {item["name"] for item in json.loads((DATA / "coverage.json").read_text())["targets"]}
    for file in sorted((DATA / "notes").glob("*.json")):
        manuscript = file.read_bytes()
        revision.update(sha256(manuscript).digest())
        note = json.loads(manuscript)
        if set(note) != FIELDS or not all(filled(note[k]) for k in ("title", "bank", "url", "date")):
            raise ValueError(f"Incomplete manuscript: {file.name}")
        publication = publications.get(file.name)
        key = source_key(note["url"])
        if publication:
            if (publication.get("jurisdiction") not in jurisdictions or
                    not all(filled(publication.get(k)) for k in ("title", "type"))):
                raise ValueError(f"Invalid archive publication metadata: {file.name}")
        elif key not in archived:
            raise ValueError(f"Add this item's official metadata to note-publications.json: {file.name}")
        editions = {key, *(source_key(u) for u in (publication or {}).get("aliases", []))}
        if editions & urls:
            raise ValueError(f"Duplicate manuscript or official source alias: {file.name}")
        urls.update(editions)
        name = note["date"] + "-" + sha256(note["url"].encode()).hexdigest()[:10] + ".json"
        if file.name != name or date.fromisoformat(note["date"]).isoformat() != note["date"]:
            raise ValueError(f"Invalid manuscript name or date: {file.name}")
        if not isinstance(note["summary"], list) or not note["summary"] or not all(map(filled, note["summary"])):
            raise ValueError(f"Missing summary: {file.name}")
        if not isinstance(note["limitation"], str) or not 3 <= len(note["questions"]) <= 5 or not all(
            set(q) == {"question", "detail"} and all(map(filled, q.values())) for q in note["questions"]
        ):
            raise ValueError(f"Invalid research questions or coverage: {file.name}")
        header = {key: note[key] for key in ("title", "bank", "date", "url")}
        header["excerpt"] = opening_sentence(note["summary"][0])
        header["file"] = file.name
        if file.name in publications:
            header["publication"] = publications[file.name]
        index.append(header)
    if not index:
        raise ValueError("Empty research index")
    index.sort(key=lambda n: (n["date"], n["title"]), reverse=True)
    catalogue = json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    (DATA / "research-notes.json").write_text(catalogue)
    revision.update(catalogue.encode())
    # Keep the reader, its index and the manuscripts on the same release on Pages.
    site = DATA.parent
    for asset in ("research-notes.js", "research-notes.css", "publication-reader.js",
                  "research-archive.js", "research-archive.css"):
        revision.update(sha256((site / asset).read_bytes()).digest())
    for page in ("research-notes.html", "research-archive.html"):
        reader = site / page
        asset_pattern = r'((?:research-notes|research-archive|publication-reader)\.(?:js|css))(?:\?v=[0-9a-f]+)?(?=")'
        reader.write_text(re.sub(asset_pattern, r'\g<1>?v=' + revision.hexdigest()[:12], reader.read_text()))
    print(f"Indexed {len(index)} full research notes")


if __name__ == "__main__":
    build()
