"""US releases listed by BLS and BEA. All dates use the agency's Eastern calendar."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


EASTERN = ZoneInfo("America/New_York")
BLS_SCHEDULE = "https://www.bls.gov/schedule/{year}/"
BEA_SCHEDULE = "https://www.bea.gov/news/schedule/"
BEA_ICAL = BEA_SCHEDULE + "ics/online-calendar-subscription.ics"
HOLIDAYS = {
    "New Year's Day", "Birthday of Martin Luther King, Jr.", "Washington's Birthday",
    "Memorial Day", "Juneteenth National Independence Day", "Independence Day",
    "Labor Day", "Columbus Day", "Veterans Day", "Thanksgiving Day", "Christmas Day",
    "Inauguration Day",
}


def download(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; The Policy Tape economic calendar)"})
    with urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8-sig")


class BLSRows(HTMLParser):
    """BLS annual pages expose each publication in a three-cell release-list row."""

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.cells = []
        self.text = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = "release-list" in dict(attrs).get("class", "").split()
        elif self.in_table:
            if tag == "tr":
                self.cells = []
            elif tag == "td":
                self.text = []

    def handle_data(self, text):
        if self.text is not None:
            self.text.append(text)

    def handle_endtag(self, tag):
        if not self.in_table:
            return
        if tag == "td":
            self.cells.append(" ".join("".join(self.text).split()))
            self.text = None
        elif tag == "tr" and self.cells:
            self.rows.append(self.cells)
        elif tag == "table":
            self.in_table = False


def bls_records(html, year):
    parser = BLSRows()
    parser.feed(html)
    parser.close()
    if parser.in_table or "</html>" not in html.lower():
        raise ValueError(f"Incomplete BLS {year} schedule")
    records = []
    for day_text, time_text, title in parser.rows:
        day = datetime.strptime(day_text, "%A, %B %d, %Y").date()
        if day.year != year or not title:
            raise ValueError(f"Unexpected BLS calendar row: {day_text} {title}")
        if not time_text and title.removesuffix(" (Observed)") in HOLIDAYS:
            continue
        key = sha256((day.isoformat() + "|" + title).encode()).hexdigest()[:20]
        record = dict(id="bls-" + key, title=title, country="US", agency="BLS",
                      source=BLS_SCHEDULE.format(year=year), date=day.isoformat())
        if time_text and time_text.upper() != "TBD":
            clock = datetime.strptime(time_text, "%I:%M %p").time()
            record["start"] = datetime.combine(day, clock, EASTERN).isoformat()
        records.append(record)
    if not records or len({r["id"] for r in records}) != len(records):
        raise ValueError(f"Empty or duplicate release entries in BLS {year} schedule")
    return records


def fetch_bls():
    today = datetime.now(EASTERN).date()
    first_year = (today - timedelta(days=7)).year
    last_year = (today + timedelta(days=90)).year
    records = []
    for year in range(first_year, last_year + 1):
        try:
            page = download(BLS_SCHEDULE.format(year=year))
        except HTTPError as exc:
            if exc.code == 404 and year > today.year:
                continue  # Next year's annual schedule can be unpublished during autumn.
            raise
        records.extend(bls_records(page, year))
    return records


def bea_records(ical, today):
    # Unfold RFC 5545 lines before decoding escaped punctuation and newlines in titles.
    content = re.sub(r"\n[ \t]", "", ical.replace("\r\n", "\n"))
    if not content.strip().startswith("BEGIN:VCALENDAR\n") or not content.strip().endswith("END:VCALENDAR"):
        raise ValueError("Invalid BEA calendar")
    events = re.findall(r"^BEGIN:VEVENT\n(.*?)^END:VEVENT$", content, re.MULTILINE | re.DOTALL)
    if len(events) != content.count("BEGIN:VEVENT"):
        raise ValueError("Incomplete BEA event")
    records = []
    seen = set()
    for event in events:
        fields = {}
        for line in event.splitlines():
            name, separator, value = line.partition(":")
            if not separator:
                raise ValueError("Invalid BEA event property")
            key, _, params = name.partition(";")
            fields[key] = (value, params)
        if fields.get("STATUS", ("",))[0] == "CANCELLED":
            continue
        if "RRULE" in fields or "RECURRENCE-ID" in fields:
            raise ValueError("Recurring BEA event needs explicit dated occurrences")
        uid = fields["UID"][0]
        summary = re.sub(r"\\([nN,;\\])", lambda m: " " if m[1].lower() == "n" else m[1], fields["SUMMARY"][0]).strip()
        raw, params = fields["DTSTART"]
        if not uid or uid in seen or not summary:
            raise ValueError("Missing or duplicate BEA event identity")
        seen.add(uid)
        stamp = None
        if params == "VALUE=DATE":
            day = datetime.strptime(raw, "%Y%m%d").date()
        elif raw.endswith("Z"):
            stamp = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(EASTERN)
            day = stamp.date()
        elif "TZID=America/New_York" in params.split(";"):
            stamp = datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=EASTERN)
            day = stamp.date()
        else:
            raise ValueError(f"BEA time without recognised timezone: {raw} {params}")
        source = BEA_SCHEDULE
        if day.year < today.year:
            source += f"full-{day.year}"
        elif day.year > today.year:
            source += "next-year"
        record = dict(id="bea-" + uid, title=summary, country="US", agency="BEA", source=source, date=day.isoformat())
        if stamp:
            record["start"] = stamp.isoformat()
        records.append(record)
    if not records:
        raise ValueError("No economic releases recognised in BEA calendar")
    return records


def fetch_bea():
    return bea_records(download(BEA_ICAL), datetime.now(EASTERN).date())


SOURCES = {"BLS": fetch_bls, "BEA": fetch_bea}
