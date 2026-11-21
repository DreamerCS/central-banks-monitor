"""Refresh independent official calendars, retaining other sources and dated history."""
import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from lxml import etree, html

from calendar_speeches_banks import CANADA, UK, CANCELLED, canada, england, event_type, fetch

URL = "https://www.ecb.europa.eu/press/calendars/weekly/html/index.en.html"
DATA = Path(__file__).resolve().parents[1] / "dist/data/speaking-calendar.json"
ENGAGEMENT = re.compile(r"speech|panel|lecture|conversation|remarks|interview|debate|address|discussion|hearing|presentation|keynote", re.I)


def fields(section):
    values = {}
    for label in section.xpath("./strong"):
        parts = [label.tail or ""]
        for sibling in label.itersiblings():
            if sibling.tag in {"br", "strong"}:
                break
            parts.extend([sibling.text_content(), sibling.tail or ""])
        values[label.text_content().strip(": ")] = " ".join("".join(parts).split())
    return values


def listed_events(content):
    events = []
    document = html.fromstring(content)
    entries = document.xpath("//dt[following-sibling::*[1][self::dd]]")
    if not entries:
        raise ValueError("ECB calendar entries could not be located")
    for heading in entries:
        info = fields(heading.getnext())
        speaker = info.get("Board member")
        title = info.get("Event", "")
        if not speaker or not ENGAGEMENT.search(title) or CANCELLED.search(title):
            continue
        day = datetime.strptime(heading.text_content().strip(), "%A, %d %B %Y")
        entry = {"bank": "European Central Bank", "speaker": speaker, "title": title,
                 "date": day.date().isoformat(), "source": URL, "eventType": event_type(title) or "Speaking engagement"}
        # ECB lists Frankfurt time first and the venue's time second. Only an
        # explicitly labelled Frankfurt (summer) time can drive a countdown.
        match = re.match(r"^(\d{1,2}):(\d{2})\s*(CEST|CET)\b", info.get("Time", ""))
        if match:
            local = day.replace(hour=int(match[1]), minute=int(match[2]), tzinfo=ZoneInfo("Europe/Berlin"))
            entry["at"] = local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        events.append(entry)
    return events


def ecb(content):
    events = listed_events(content)
    doc = html.fromstring(content)
    dates = [datetime.strptime(el.text_content().strip(), "%A, %d %B %Y").date().isoformat()
             for el in doc.xpath("//dt[following-sibling::*[1][self::dd]]")]
    return events, min(dates), max(dates)


SOURCES = ((URL, ecb, 'Europe/Berlin', 'European Central Bank'),
           (UK, england, 'Europe/London', 'Bank of England'),
           (CANADA, canada, 'America/Toronto', 'Bank of Canada'))


def managed_by(item, url):
    return item['source'] == url or (url == CANADA and bool(item.get('calendarEntry')))


def read_rows(path):
    rows = json.loads(path.read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError('Expected a populated speaking calendar array')
    for row in rows:
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip()
                                            for k in ('bank', 'speaker', 'title', 'date', 'source')):
            raise ValueError('Incomplete speaking calendar row')
        if date.fromisoformat(row['date']).isoformat() != row['date']:
            raise ValueError('Invalid event date')
        source = urlsplit(row['source'])
        if source.scheme != 'https' or not source.hostname or source.username or source.password:
            raise ValueError('Invalid source link')
        if row.get('sourceStatus') not in {None, 'manual', 'retained', 'verified'}:
            raise ValueError('Unexpected source status')
        for key in ('at', 'lastVerifiedAt'):
            if key in row and datetime.fromisoformat(row[key].replace('Z', '+00:00')).tzinfo is None:
                raise ValueError(f'{key} must have a UTC offset')
    return rows


def restore(bundled, previous):
    if not previous:
        return bundled
    try:
        deployed = read_rows(previous)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(f'Using bundled speaking calendar: {error}')
        return bundled
    # Never resurrect a withdrawn scheduled event from a checked-in seed. The
    # original deployed format had no verification data; keep newly introduced
    # sources from the bundled file on that first migration.
    modern = any('sourceStatus' in row for row in deployed)
    newest = max((row.get('lastVerifiedAt', '') for row in deployed), default='')
    def identity(row):
        return (row['date'], row['speaker'], row['source'], row.get('at'),
                row.get('eventType') or event_type(row['title']), None if row.get('at') else row['title'])
    positions = {identity(row): i for i, row in enumerate(deployed)}
    for row in bundled:
        position = positions.get(identity(row))
        if position is not None:
            if row.get('lastVerifiedAt', '') > deployed[position].get('lastVerifiedAt', ''):
                deployed[position] = row
            continue
        managed = any(managed_by(row, url) for url, *_ in SOURCES)
        if not managed or not modern or row.get('lastVerifiedAt', '') > newest:
            positions[identity(row)] = len(deployed)
            deployed.append(row)
    return deployed


def merge(items, url, fresh, first, last, today):
    # An unchanged advisory URL can describe several separately timed activities.
    def key(x):
        return x['date'], x['speaker'], x.get('eventType') or event_type(x['title']), x['source']

    refreshed = {key(x) for x in fresh}
    kept = []
    for item in items:
        managed = managed_by(item, url)
        in_scope = max(first, today) <= item['date'] <= last
        if key(item) in refreshed or (managed and in_scope):
            continue
        kept.append(item)
    # Unique full rows retain multiple same-speaker, same-day engagements.
    for row in fresh:
        if row not in kept:
            kept.append(row)
    return kept


def refresh(items, now):
    checked = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    for url, parse, zone, bank in SOURCES:
        today = now.astimezone(ZoneInfo(zone)).date().isoformat()
        try:
            fresh, first, last = parse(fetch(url))
        except (OSError, ValueError, IndexError, etree.ParserError) as error:
            for row in items:
                if row['bank'] == bank and row['date'] >= today:
                    row['sourceStatus'] = 'retained'
            print(f"Keeping previous speaking calendar for {url} ({error})")
            continue
        # Records outside this particular published schedule can remain visible,
        # but its successful download does not verify them again.
        for row in items:
            if managed_by(row, url) and row['date'] >= today:
                row['sourceStatus'] = 'retained'
        for row in fresh:
            row.update(sourceStatus='verified', lastVerifiedAt=checked)
        items = merge(items, url, fresh, first, last, today)
        print(f"{url}: {len(fresh)} published activities; {first} to {last}")
    items.sort(key=lambda item: (item['date'], item.get('at', '~'), item['bank'], item['speaker'], item['title']))
    return items


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--previous', type=Path, help='Last deployed speaking calendar')
    args = cli.parse_args()
    items = restore(read_rows(DATA), args.previous)
    items = refresh(items, datetime.now(timezone.utc))
    payload = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    if payload != DATA.read_text():
        with NamedTemporaryFile(mode='w', dir=DATA.parent, delete=False, encoding='utf-8') as temp:
            temp.write(payload)
        temporary = Path(temp.name)
        temporary.chmod(0o644)
        temporary.replace(DATA)


if __name__ == "__main__":
    main()
