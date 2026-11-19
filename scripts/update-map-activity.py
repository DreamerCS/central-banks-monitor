"""Build the map's daily publication snapshot from the archive and official feeds."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import json
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
FEEDS = {
    "United States": (
        ("Policy", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
        ("Speech or testimony", "https://www.federalreserve.gov/feeds/speeches_and_testimony.xml"),
    ),
    "Euro area": (("Release", "https://www.ecb.europa.eu/rss/press.html"),),
    "Canada": (
        ("Speech", "https://www.bankofcanada.ca/content_type/speeches/feed/"),
        ("Release", "https://www.bankofcanada.ca/content_type/press-releases/feed/"),
    ),
    "Australia": (
        ("Speech", "https://www.rba.gov.au/rss/rss-cb-speeches.xml"),
        ("Release", "https://www.rba.gov.au/rss/rss-cb-media-releases.xml"),
    ),
    "Japan": (("Release", "https://www.boj.or.jp/en/rss/whatsnew.xml"),),
    "Sweden": (
        ("Release", "https://www.riksbank.se/en-gb/rss/press-releases/"),
        ("Speech", "https://www.riksbank.se/en-gb/rss/speeches/"),
    ),
    "Norway": (
        ("Release", "https://www.norges-bank.no/en/rss-feeds/Press-releases---Norges-Bank/"),
        ("Speech", "https://www.norges-bank.no/en/rss-feeds/Speeches---Norges-Bank/"),
    ),
    "Switzerland": (
        ("Policy", "https://www.snb.ch/public/rss/en/mopo"),
        ("Speech", "https://www.snb.ch/public/rss/en/speeches"),
    ),
}


def publication_day(value):
    try:
        iso = datetime.fromisoformat(value)
    except ValueError:
        try:
            iso = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None
    return iso.astimezone(timezone.utc).date() if iso.tzinfo else iso.date()


def fetch_feed(job):
    bank, category, url = job
    try:
        req = Request(url, headers={"User-Agent": "CentralBankIntelligence/1.0"})
        with urlopen(req, timeout=9) as response:
            root = ET.fromstring(response.read(2_000_000))
        if root.tag.split("}")[-1].lower() not in ("rss", "feed", "rdf"):
            raise ValueError("not an RSS or Atom feed")
        rows = []
        for item in root.iter():
            if item.tag.split("}")[-1] not in ("item", "entry"):
                continue
            fields = {}
            for field in item:
                key = field.tag.split("}")[-1]
                if key == "link" and field.get("rel", "alternate") != "alternate":
                    continue
                fields[key] = field.get("href") or "".join(field.itertext()).strip()
            day = publication_day(fields.get("pubDate") or fields.get("published") or fields.get("date") or "")
            title = " ".join(unescape(fields.get("title", "")).split())[:400]
            link = urljoin(url, fields["link"]) if fields.get("link") else ""
            if link.startswith("http://"):
                link = "https://" + link[7:]
            parsed = urlsplit(link)
            domain = urlsplit(url).hostname.removeprefix("www.")
            if not (day and title and parsed.scheme == "https" and not parsed.username and
                    parsed.hostname and parsed.hostname.removeprefix("www.") == domain):
                continue
            if bank == "Japan" and parsed.path.startswith(("/en/statistics/", "/en/about/outline/")):
                continue
            rows.append(dict(bank=bank, type=category, day=day.isoformat(), title=title, url=link))
        return bank, True, rows
    except (OSError, ET.ParseError, ValueError) as err:
        print(f"{bank}: {url}: {err}")
        return bank, False, []


def identity(row):
    parsed = urlsplit(row["url"])
    query = tuple(sorted((k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_")
                         and k.lower() not in {"trk", "fbclid", "gclid"}))
    return row["bank"], parsed.hostname.removeprefix("www."), parsed.path.rstrip("/"), query, parsed.fragment


def main():
    now = datetime.now(timezone.utc)
    oldest = now.date() - timedelta(days=21)
    jobs = [(bank, category, url) for bank, feeds in FEEDS.items() for category, url in feeds]
    sources = {bank: [0, len(feeds)] for bank, feeds in FEEDS.items()}
    by_link = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for bank, success, rows in pool.map(fetch_feed, jobs):
            sources[bank][0] += success
            for row in rows:
                day = date.fromisoformat(row["day"])
                if oldest <= day <= now.date():
                    by_link[identity(row)] = row
    for doc in json.loads((DATA / "research-archive.json").read_text()):
        if date.fromisoformat(doc["date"]) <= now.date():
            row = dict(bank=doc["jurisdiction"], type=doc["type"], day=doc["date"],
                       title=doc["title"], url=doc["url"], archive=True)
            by_link[identity(row)] = row
    items = sorted(by_link.values(), key=lambda row: (row["day"], row["bank"], row["title"]), reverse=True)
    payload = dict(checkedAt=now.isoformat(timespec="seconds"), sources=sources, items=items)
    target = DATA / "world-map-activity.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))+"\n")
    temporary.replace(target)
    print(f"Map activity: {len(items)} releases, {sum(ok for ok, _ in sources.values())}/{len(jobs)} feeds fetched")


if __name__ == "__main__":
    main()
