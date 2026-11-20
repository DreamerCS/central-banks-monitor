"""Read official central bank publications and reconcile them with the research archive."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re
from threading import Semaphore
from urllib.parse import parse_qsl, quote, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

SCRIPTS = Path(__file__).resolve().parent
DATA = SCRIPTS.parent / "dist" / "data"
AUDIT_WINDOWS = {
    "aug-sep": (("aug", "sep"), "archive-review-aug-sep.json"),
    "oct-nov": (("oct", "nov"), "archive-review.json"),
}
SPANISH_MONTHS = dict(
    zip("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
        "January February March April May June July August September October November December".split())
)


def publication_day(value, date_format=None):
    value = " ".join(value.split())
    if date_format:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            return None

    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).date()
    except (ValueError, TypeError, OverflowError):
        pass

    value = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", r"\1", value)
    value = re.sub(r"^\w+[.,]? (?:the )?(?=\d{1,2}\b)", "", value)
    value = re.sub(r" (?:of|de) ", " ", value).replace(",", "")
    if re.fullmatch(r"\d{1,2} [A-Za-z]+\. \d{4}", value):
        value = value.replace(".", "")
    value = " ".join(SPANISH_MONTHS.get(word.lower(), word) for word in value.split())
    for pattern in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def hostname(url):
    return (urlsplit(url).hostname or "").removeprefix("www.")


def official_url(url, publisher):
    parsed = urlsplit(url)
    host = hostname(url)
    return (parsed.scheme == "https" and not parsed.username and not parsed.password
            and (host == publisher or host.endswith("." + publisher)))


def normal_path(path):
    return re.sub(r"/{2,}", "/", path)


def xml_entries(body, use_updated):
    root = ET.fromstring(body)
    if root.tag.split("}")[-1].lower() not in ("rss", "feed", "rdf"):
        raise ValueError("response is not RSS or Atom")
    for item in root.iter():
        if item.tag.split("}")[-1] not in ("item", "entry"):
            continue
        fields = {}
        for field in item:
            key = field.tag.split("}")[-1].lower()
            if key == "link" and field.get("rel", "alternate") != "alternate":
                continue
            fields[key] = field.get("href") or "".join(field.itertext()).strip()
        yield (
            fields.get("pubdate") or fields.get("published") or fields.get("date")
            or (fields.get("updated") if use_updated else "") or "",
            fields.get("title", ""),
            fields.get("link", ""),
        )


def listing_entries(body, spec, charset=None):
    from lxml import html
    from lxml.etree import ParserError

    def field(node, selector):
        value = node.xpath(selector)
        if isinstance(value, list):
            return next((part.strip() for part in value if part.strip()), "")
        return value.strip()

    try:
        # Some publishers serve Latin-1 bytes alongside a stale UTF-8 meta tag.
        parser = None
        if charset and not body.isascii():
            try:
                body.decode("utf-8")
            except UnicodeDecodeError:
                parser = html.HTMLParser(encoding=charset)
        doc = html.fromstring(body, parser=parser)
    except ParserError as err:
        raise ValueError("empty or unreadable listing") from err
    for node in doc.xpath(spec["entry"]):
        title = spec.get("titleText") or field(node, spec["title"])
        date_text = field(node, spec["date"])
        if "datePattern" in spec:
            match = re.search(spec["datePattern"], date_text)
            date_text = match[0] if match else ""
        yield date_text, title, field(node, spec["link"])


def collect(source, throttle):
    url = source["url"]
    publisher = source.get("host", hostname(url))
    listing = source.get("listing")
    try:
        req = Request(url, headers={"User-Agent": "CentralBankIntelligence/1.0"})
        with throttle, urlopen(req, timeout=10) as response:
            base = response.url
            if not official_url(base, publisher):
                raise ValueError("redirect outside publisher")
            charset = response.headers.get_content_charset()
            body = response.read(5_000_001)
        if len(body) > 5_000_000:
            raise ValueError("response exceeds 5 MB")
        entries = listing_entries(body, listing, charset) if listing else xml_entries(body, source.get("useUpdated", False))
        rows = {}
        for when, heading, href in entries:
            day = publication_day(when, (listing or {}).get("dateFormat"))
            title = " ".join(re.sub(r"</?(?:sup|sub|i|b|em|strong)>", "", unescape(heading)).split())[:400]
            link = urljoin(base, href) if href else ""
            if link.startswith("http://"):
                link = "https://" + link[7:]
            if not (day and title and link and official_url(link, publisher)):
                continue
            parts = urlsplit(link)
            path = normal_path(parts.path)
            if path.startswith(tuple(source.get("excludePaths", []))):
                continue
            link = urlunsplit(parts._replace(path=quote(path, safe="/%:@!$&'()*+,;=-._~")))
            kind = next((kind for prefix, kind in source.get("pathTypes", {}).items()
                         if path.lower().startswith(prefix)), source["type"])
            row = dict(bank=source["bank"], institution=source["institution"], type=kind,
                       day=day.isoformat(), title=title, url=link, source=source["id"])
            rows[identity(link)] = row
        return list(rows.values())
    except (OSError, ET.ParseError, ValueError) as err:
        print(f"{source['id']}: {err}")
        return None


def identity(url):
    parsed = urlsplit(url)
    query = tuple(sorted((k, v) for k, v in parse_qsl(parsed.query)
                         if not k.lower().startswith("utm_") and k.lower() not in
                         {"trk", "fbclid", "gclid"}))
    return hostname(url), normal_path(unquote(parsed.path)).rstrip("/"), query


def title_key(row):
    title = "".join(ch for ch in row["title"].casefold() if ch.isalnum())
    return row["bank"], row["day"], title


def write_json(target, payload):
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(target)


def review_snapshot(window, checked, checks, rows, archive):
    ids, output = AUDIT_WINDOWS[window]
    periods = json.loads((DATA / "archive-periods.json").read_text(encoding="utf-8"))
    periods = [period for period in periods if period["id"] in ids]
    start, end = periods[0]["start"], periods[-1]["end"]
    official = [r for r in rows if start <= r["day"] <= end]
    links = {identity(r["url"]) for r in archive}
    links.update(identity(link["url"]) for r in archive for link in r.get("related", []))
    titles = {title_key(r) for r in archive}
    unmatched = [r for r in official if identity(r["url"]) not in links and title_key(r) not in titles]
    monthly = {}
    for period in periods:
        monthly[period["start"][:7]] = {
            "indexed": dict(Counter(r["bank"] for r in archive if period["start"] <= r["day"] <= period["end"])),
            "review": dict(Counter(r["bank"] for r in unmatched if period["start"] <= r["day"] <= period["end"])),
        }
    write_json(SCRIPTS.parent / output, dict(
        checkedAt=checked, start=start, end=end, matched=len(official) - len(unmatched),
        inputsRead=sum(r["status"] == "Read" for r in checks), inputsChecked=len(checks),
        monthly=monthly, items=unmatched,
    ))
    print(f"Archive comparison: {len(official)} dated links, {len(unmatched)} unmatched candidates")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", nargs="?", const="oct-nov", choices=AUDIT_WINDOWS,
                        help="save a fixed historical reconciliation for the chosen 2026 window")
    parser.add_argument("--previous-archive", type=Path,
                        help="carry the previously published archive into this build")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    checked = now.isoformat(timespec="seconds")
    oldest = (now.date() - timedelta(days=21)).isoformat()
    today = now.date().isoformat()
    inputs = json.loads((SCRIPTS / "monitored-sources.json").read_text(encoding="utf-8"))
    inputs = [source for source in inputs if args.audit or not source.get("auditOnly")]
    for source in inputs:
        source["url"] = source["url"].replace("{year}", str(now.year))
    throttles = defaultdict(lambda: Semaphore(2))
    jobs = [(source, throttles[hostname(source["url"])]) for source in inputs]
    sources = defaultdict(lambda: [0, 0])
    checks = []
    collected = {}
    with ThreadPoolExecutor(max_workers=14) as pool:
        for source, rows in zip(inputs, pool.map(lambda job: collect(*job), jobs)):
            audit_only = source.get("auditOnly", False)
            if not audit_only:
                sources[source["bank"]][1] += 1
            status = "Unavailable" if rows is None else "No dated entries"
            rows = [row for row in (rows or []) if row["day"] <= today]
            check = {k: source[k] for k in ("id", "bank", "institution", "label", "url")}
            check.update(method="Listing" if "listing" in source else "RSS", status=status, count=len(rows))
            if rows:
                if not audit_only:
                    sources[source["bank"]][0] += 1
                dates = [row["day"] for row in rows]
                check.update(status="Read", first=min(dates), last=max(dates))
                for row in rows:
                    key = identity(row["url"])
                    existing = collected.get(key)
                    if existing is None or (not audit_only and existing["type"] == "Release" and row["type"] != "Release"):
                        collected[key] = row
            checks.append(check | {"auditOnly": audit_only})

    archive_path = DATA / "research-archive.json"
    records = json.loads(archive_path.read_text(encoding="utf-8"))
    ordered = sorted(collected.values(), key=lambda r: (r["day"], r["bank"], r["title"]), reverse=True)
    if args.previous_archive:
        from publication_archive import extend_periods, merge_publications

        previous = json.loads(args.previous_archive.read_text(encoding="utf-8"))
        listings = {s["id"]: s["url"] for s in inputs if not s.get("auditOnly")}
        records = merge_publications(records, previous, ordered, listings, now.date(), identity)
        periods_path = DATA / "archive-periods.json"
        periods = json.loads(periods_path.read_text(encoding="utf-8"))
        write_json(periods_path, extend_periods(periods, records, now.date()))
        write_json(archive_path, records)
        print(f"Archive: {len(records)} publications including "
              f"{sum('sourcePage' in r for r in records)} collected from official listings")

    archive = [
        dict(bank=r["jurisdiction"], type=r["type"], day=r["date"], title=r["title"], url=r["url"],
             related=r.get("related", []), archive=True)
        for r in records
        if r["date"] <= today
    ]
    if args.audit:
        review_snapshot(args.audit, checked, checks, ordered, archive)

    daily_checks = [check for check in checks if not check.pop("auditOnly")]
    daily_ids = {check["id"] for check in daily_checks}
    by_link = {identity(r["url"]): r for r in ordered if oldest <= r["day"] <= today and r["source"] in daily_ids}
    for row in archive:
        for related in row.pop("related"):
            by_link.pop(identity(related["url"]), None)
        by_link[identity(row["url"])] = row
    items = sorted(by_link.values(), key=lambda r: (r["day"], r["bank"], r["title"]), reverse=True)
    content = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    revision = sha256(content.encode("utf-8")).hexdigest()
    write_json(DATA / "world-map-activity.json", {"revision": revision, "items": items})
    print(f"Map activity: {len(items)} publications, {sum(ok for ok, _ in sources.values())}/{len(daily_checks)} sources read")


if __name__ == "__main__":
    main()
