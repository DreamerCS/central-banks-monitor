"""Check the curated publisher-headline study and optionally re-read its public sources.

Run python scripts/check-news-framing.py, or add --online to verify each current
headline fingerprint. A changed source is reported for editorial review. A later
version of a page never silently recodes an earlier observation.
"""
import argparse
import csv
import hashlib
import json
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from lxml import html

DATA = Path(__file__).resolve().parents[1] / "dist/data"
ACTION = {"hike", "cut", "hold", None}
PATH = {"tighter", "easier", "steady", "conditional", "mixed", None}
BASIS = {"level", "revision", "open", None}
FOCUS = {"Decision", "Forward guidance", "Market reaction", "Economic outlook", "Policy tools"}


def normalised(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def check_rows(data):
    rows = json.loads((data / "news-framing.json").read_text())["records"]
    meetings = json.loads((data / "stance-cohorts.json").read_text())["banks"]
    known = {(b["id"], r["date"], "decision", "") for b in meetings for r in b["records"]}
    us_speeches = json.loads((data / "fed-leader-speeches.json").read_text())["records"]
    for speech in us_speeches:
        known.add(("fed", speech["date"], "speech", speech["speaker"].split()[-1]))
    with (data / "ecb-speech-stance.csv").open(newline="") as f:
        for speech in csv.DictReader(f):
            known.add(("ecb", speech["event_time"][:10], "speech", speech["speaker"].split()[-1]))
    ids, urls = set(), set()
    for r in rows:
        key = (r["bank"], r["date"], r["type"], r.get("speaker", ""))
        if key not in known:
            raise ValueError(f"Unmatched central-bank event {key}")
        if r["id"] in ids or r["url"] in urls:
            raise ValueError(f"Duplicate publication {r['id']}")
        ids.add(r["id"])
        urls.add(r["url"])
        if r["focus"] not in FOCUS or r["action"] not in ACTION or r["path"] not in PATH or r["pathBasis"] not in BASIS:
            raise ValueError(f"Unknown editorial tag on {r['id']}")
        if (r["path"] is None) != (r["pathBasis"] is None):
            raise ValueError(f"Incomplete forward-path reading on {r['id']}")
        if r["coverageMode"] not in {"report", "preview"} or r["recordKind"] not in {"article", "live entry"}:
            raise ValueError(f"Missing publication context on {r['id']}")
        if urlsplit(r["url"]).scheme != "https" or not r["angle"] or not r["newsroom"] or not r["versionNote"]:
            raise ValueError(f"Missing source or interpretation on {r['id']}")
        date.fromisoformat(r["publicationDate"])
        for clock in [r["publishedAt"], r["updatedAt"]]:
            if clock:
                if not clock.endswith("Z"):
                    raise ValueError(f"Clock must be UTC on {r['id']}")
                datetime.fromisoformat(clock.replace("Z", "+00:00"))
        if r["updatedAt"] and r["publishedAt"] and r["updatedAt"] < r["publishedAt"]:
            raise ValueError(f"Update predates first posting on {r['id']}")
        if r["recordKind"] == "live entry" and not (r["publishedAt"] and urlsplit(r["url"]).fragment.startswith("block-")):
            raise ValueError(f"Live dispatch lacks a block identifier or clock on {r['id']}")
        if r["recordKind"] == "live entry":
            posted = datetime.fromisoformat(r["publishedAt"].replace("Z", "+00:00"))
            release = datetime.fromisoformat(r["decisionReleaseAt"].replace("Z", "+00:00"))
            if r["secondsFromDecision"] != (posted - release).total_seconds() or not r["decisionClockSource"].startswith("https://"):
                raise ValueError(f"Unverified offset from official decision time on {r['id']}")
        if any(x["direction"] not in {"up", "down", "volatile", "unspecified"} for x in r["markets"]):
            raise ValueError(f"Unknown market description on {r['id']}")
    return rows


def check_online(r):
    req = Request(r["url"], headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=22) as response:
            text = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        doc = html.fromstring(text)
        if r["recordKind"] == "live entry":
            block = urlsplit(r["url"]).fragment
            section = doc.xpath("//article[@id=$block]", block=block)
            if len(section) != 1:
                return f"{r['url']} — dispatch unavailable"
            matches = section[0].xpath("./header/h2")
            clocks = section[0].xpath(".//time/@datetime")
            observed = [datetime.fromisoformat(c.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") for c in clocks[:2]]
            expected = [c for c in [r["publishedAt"], r["updatedAt"]] if c]
            if observed != expected:
                return f"{r['url']} — dispatch timestamps changed"
        else:
            matches = doc.xpath("//h1")
        for el in matches:
            value = normalised(el.text_content())
            if hashlib.sha256(value.encode()).hexdigest() == r["headlineSha256"]:
                if r.get("excerpt") and normalised(r["excerpt"]) not in value:
                    return f"{r['url']} — short quote does not occur in the verified heading"
                return None
        return f"{r['url']} — visible headline differs from the reviewed version"
    except Exception as err:
        return f"{r['url']} — source unavailable ({err})"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()
    rows = check_rows(args.data)
    print(f"Checked {len(rows)} event-linked news readings.")
    if args.online:
        with ThreadPoolExecutor(max_workers=6) as executor:
            errors = [msg for msg in executor.map(check_online, rows) if msg]
        if errors:
            raise SystemExit("\n".join(errors))
        print("Every visible publisher heading matched its review fingerprint.")
