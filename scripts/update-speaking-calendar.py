"""Refresh speaking engagements from the ECB's weekly press calendar."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from lxml import html

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
        if not speaker or not ENGAGEMENT.search(title):
            continue
        day = datetime.strptime(heading.text_content().strip(), "%A, %d %B %Y")
        entry = {"bank": "European Central Bank", "speaker": speaker, "title": title,
                 "date": day.date().isoformat(), "source": URL}
        # ECB lists Frankfurt time first and the venue's time second. Only an
        # explicitly labelled Frankfurt (summer) time can drive a countdown.
        match = re.match(r"^(\d{1,2}):(\d{2})\s*(CEST|CET)\b", info.get("Time", ""))
        if match:
            local = day.replace(hour=int(match[1]), minute=int(match[2]), tzinfo=ZoneInfo("Europe/Berlin"))
            entry["at"] = local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        events.append(entry)
    return events


def main():
    request = Request(URL, headers={"User-Agent": "Central Bank Intelligence calendar/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            events = listed_events(response.read().decode("utf-8"))
    except (ValueError, OSError) as error:
        print(f"Keeping the bundled speaking calendar ({error})")
        return
    items = [item for item in json.loads(DATA.read_text()) if item["source"] != URL]
    items.extend(events)
    DATA.write_text(json.dumps(sorted(items, key=lambda item: (item["date"], item.get("at", "~"))),
                               ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
