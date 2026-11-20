"""Validate published manuscripts and build the lightweight research reader index."""
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
FIELDS = {"title", "bank", "date", "url", "summary", "questions", "limitation"}


def filled(value):
    return isinstance(value, str) and bool(value.strip())


def build():
    index = []
    urls = set()
    for file in sorted((DATA / "notes").glob("*.json")):
        note = json.loads(file.read_text())
        if set(note) != FIELDS or not all(filled(note[k]) for k in ("title", "bank", "url", "date")):
            raise ValueError(f"Incomplete manuscript: {file.name}")
        url = urlsplit(note["url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password or note["url"] in urls:
            raise ValueError(f"Invalid or duplicate source: {file.name}")
        urls.add(note["url"])
        if not re.fullmatch(r"[a-z0-9-]+\.json", file.name) or date.fromisoformat(note["date"]).isoformat() != note["date"]:
            raise ValueError(f"Invalid manuscript name or date: {file.name}")
        if not isinstance(note["summary"], list) or not note["summary"] or not all(map(filled, note["summary"])):
            raise ValueError(f"Missing summary: {file.name}")
        if not isinstance(note["limitation"], str) or not 3 <= len(note["questions"]) <= 5 or not all(
            set(q) == {"question", "detail"} and all(map(filled, q.values())) for q in note["questions"]
        ):
            raise ValueError(f"Invalid research questions or coverage: {file.name}")
        header = {key: note[key] for key in ("title", "bank", "date", "url")}
        index.append({**header, "file": file.name})
    if not index:
        raise ValueError("Empty research index")
    index.sort(key=lambda n: (n["date"], n["title"]), reverse=True)
    (DATA / "research-notes.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    print(f"Indexed {len(index)} full research notes")


if __name__ == "__main__":
    build()
