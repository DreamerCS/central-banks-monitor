"""Selected UK and euro-area releases from the agencies' own upcoming calendars.

The ONS selection takes confirmed statistical bulletins and omits companion time
series, methodology notes and revisions notices. Eurostat's Euro indicators calendar
also lists national, ECB and Commission products. We select headline euro-area
releases, crediting the Commission survey to its producer. We do not treat an
all-day calendar placeholder or a provisional date as a confirmed release time.
"""
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ONS = "https://www.ons.gov.uk"
EUROSTAT = "https://ec.europa.eu/eurostat/news/euro-indicators/release-calendar"
EUROSTAT_FEED = "https://ec.europa.eu/eurostat/o/calendars/eventsJson"
ECFIN = ("https://economy-finance.ec.europa.eu/economic-forecast-and-surveys/"
         "business-and-consumer-surveys/latest-business-and-consumer-surveys_en")
LONDON = ZoneInfo("Europe/London")
LUXEMBOURG = ZoneInfo("Europe/Luxembourg")
UTC = timezone.utc

# Match series names, not arbitrary references to trade, GDP or prices.
ONS_SERIES = re.compile(
    r"^(?:GDP (?:monthly estimate|first quarterly estimate|quarterly national accounts)|"
    r"consumer price inflation, UK|producer price inflation, UK|household costs indices for UK household groups|"
    r"(?:UK labour market|labour market overview, UK)|average weekly earnings in Great Britain|"
    r"earnings and employment from pay as you earn real time information, UK|"
    r"retail sales[,;] Great Britain|UK trade(?:\s*(?=[:,])| in services by industry)|"
    r"index of (?:production|services), UK|construction output in Great Britain|"
    r"public sector finances, UK|balance of payments, UK|business investment in the UK)(?=\W|$)",
    re.I,
)
ONS_SUPPLEMENTS = re.compile(r"\b(?:time\s*series|methodolog\w*|revisions? (?:notice|analysis|policy))\b", re.I)
EURO_SERIES = re.compile(
    r"^(?:flash estimate (?:inflation euro area|GDP)|(?:preliminary )?flash (?:estimate of )?GDP|"
    r"GDP(?: and employment| main aggregates)|inflation \(HICP\)|unemployment|retail trade|"
    r"industrial (?:production|producer prices)|services production|production in construction|"
    r"international trade in goods|labour cost index|job vacancy|house price index|"
    r"government (?:debt|deficit))(?=\W|$)", re.I,
)


def coverage(as_of: date):
    """Inclusive window guaranteed by each successful adapter call."""
    return as_of, as_of + timedelta(days=35)


def _read(url):
    request = Request(url, headers={"User-Agent": "ThePolicyTape/1.0 (public economic release calendar)"})
    with urlopen(request, timeout=25) as response:
        data = response.read(4_000_001)
    if not data or len(data) > 4_000_000:
        raise ValueError("Official calendar returned an empty or unexpectedly large response")
    return data.decode("utf-8-sig")


def _ical_entries(text):
    lines = re.sub(r"\r?\n[ \t]", "", text).splitlines()
    if not lines or lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR":
        raise ValueError("Incomplete ONS iCalendar")
    event = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            if event is not None:
                raise ValueError("Unexpected nested ONS event")
            event = {}
        elif line == "END:VEVENT":
            if event is None:
                raise ValueError("Unexpected ONS event terminator")
            yield event
            event = None
        elif event is not None:
            head, sep, value = line.partition(":")
            key, _, params = head.partition(";")
            if sep and key in {"DTSTAMP", "DTSTART", "STATUS", "SUMMARY", "UID"}:
                event[key] = (params, value)
    if event is not None:
        raise ValueError("Incomplete ONS event")


def _ons_start(params, value):
    if "VALUE=DATE" in params.split(";") or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").date(), None
    fmt = "%Y%m%dT%H%M%S"
    if value.endswith("Z"):
        moment = datetime.strptime(value[:-1], fmt).replace(tzinfo=UTC)
    else:
        tzid = next((p.split("=", 1)[1].strip('"') for p in params.split(";") if p.startswith("TZID=")), None)
        moment = datetime.strptime(value, fmt).replace(tzinfo=ZoneInfo(tzid) if tzid else LONDON)
    return moment.astimezone(LONDON).date(), moment.isoformat()


def _calendar_text(value):
    return re.sub(r"\\([,;\\nN])", lambda m: " " if m[1].lower() == "n" else m[1], value).strip()


def ons():
    lower, upper = coverage(datetime.now(UTC).date())
    dates, stamps, releases = [], [], {}
    for event in _ical_entries(_read(ONS + "/calendar/releasecalendar")):
        if not {"STATUS", "DTSTAMP"} <= event.keys():
            raise ValueError("Unrecognised ONS event metadata")
        stamps.append(datetime.strptime(event["DTSTAMP"][1], "%Y%m%dT%H%M%SZ").date())
        if event["STATUS"][1].lower() != "confirmed":
            continue
        when, start = _ons_start(*event["DTSTART"])
        dates.append(when)
        title = _calendar_text(event["SUMMARY"][1])
        if not lower <= when <= upper or not ONS_SERIES.match(title) or ONS_SUPPLEMENTS.search(title):
            continue
        uid = event["UID"][1]
        if not re.fullmatch(r"/releases/[\w%-]+", uid):
            raise ValueError("Unrecognised ONS release permalink")
        row = {"id": "ons-" + uid.rsplit("/", 1)[1], "title": title, "country": "UK",
               "agency": "ONS", "source": ONS + uid, "date": when.isoformat()}
        if start:
            row["start"] = start
        releases[uid] = row
    if not stamps or not lower - timedelta(days=3) <= max(stamps) <= lower + timedelta(days=1):
        raise ValueError("ONS calendar timestamp is stale or invalid")
    if not dates or min(dates) > lower + timedelta(days=10) or max(dates) < upper:
        raise ValueError("ONS upcoming calendar does not cover the requested window")
    return sorted(releases.values(), key=lambda row: (row["date"], row["id"]))


def eurostat():
    lower, upper = coverage(datetime.now(UTC).date())
    # This is the request made by the public FullCalendar widget. Use complete
    # months and require actual calendar observations before and beyond our window.
    first = (lower - timedelta(days=35)).replace(day=1)
    last = (upper + timedelta(days=63)).replace(day=1)
    def midnight(day):
        return datetime.combine(day, time.min, tzinfo=LUXEMBOURG)
    query = urlencode({"theme": "", "category": "", "keywords": "", "isEuroindicator": "true",
                       "authorInclude": "", "authorExclude": "", "start": midnight(first).isoformat(),
                       "end": midnight(last).isoformat(), "timeZone": "Europe/Luxembourg"})
    entries = json.loads(_read(EUROSTAT_FEED + "?" + query))
    if not isinstance(entries, list) or not entries:
        raise ValueError("Unrecognised Eurostat calendar response")
    dates, releases = [], {}
    for event in entries:
        if not isinstance(event.get("allDay"), bool) or not isinstance(event.get("preliminary"), bool):
            raise ValueError("Unrecognised Eurostat scheduling flags")
        raw = event["start"]
        if event["allDay"]:
            # The publisher supplies a dummy clock even on flagged all-day records.
            when, start = date.fromisoformat(raw[:10]), None
        else:
            published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if published.tzinfo is None:
                raise ValueError("Eurostat timed event lacks a time-zone offset")
            when, start = published.astimezone(LUXEMBOURG).date(), published.isoformat()
        dates.append(when)
        if not lower <= when <= upper or event["preliminary"] or not event.get("euroind"):
            continue
        if "Euro indicators release" not in {t["label"] for t in event["types"]}:
            continue
        title = event["title"].strip()
        producer = event["euroindAuthor"].lower()
        sentiment = producer == "ecfin" and title.startswith("Economic Sentiment Indicator")
        if not sentiment and (producer != "estat" or not EURO_SERIES.match(title)):
            continue
        if sentiment:
            title = "European Commission (DG ECFIN) · " + title
        period = event.get("period")
        if period:
            title += ", " + period
        record_id = str(event["recordid"])
        if not record_id.isdigit():
            raise ValueError("Unrecognised Eurostat record identifier")
        source = ECFIN if sentiment else EUROSTAT + "?" + urlencode(
            {"type": "listMonth", "start": int(midnight(when).timestamp() * 1000)})
        row = {"id": "eurostat-" + record_id, "title": title, "country": "Euro area",
               "agency": "Eurostat", "source": source, "date": when.isoformat()}
        if start:
            row["start"] = start
        releases[record_id] = row
    if min(dates) > lower or max(dates) < upper:
        raise ValueError("Eurostat release calendar does not cover the requested window")
    return sorted(releases.values(), key=lambda row: (row["date"], row["id"]))


SOURCES = {"ONS": ons, "Eurostat": eurostat}
COVERAGE = dict.fromkeys(SOURCES, coverage)
