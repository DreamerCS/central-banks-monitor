"""Official Bank of England and Bank of Canada forthcoming public engagements."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from lxml import html

UK = 'https://www.bankofengland.co.uk/events/upcoming-events'
CANADA = 'https://www.bankofcanada.ca/press/upcoming-events/'
CANCELLED = re.compile(r'\b(cancelled|canceled|postponed)\b', re.I)
TYPES = [
    ('Speech text release', r'speech text release'), ('Interview', r'interview'),
    ('Hearing', r'hearing|testimony|Treasury Select Committee'),
    ('Press conference', r'press conference'), ('Briefing', r'briefing'),
    ('Speech', r'speech|address|lecture|keynote'), ('Panel', r'panel'),
    ('Discussion', r'roundtable|round table|discussion|conversation|fireside chat|debate'),
    ('Remarks', r'remarks'), ('Presentation', r'presentation'),
]


def event_type(title):
    return next((name for name, pattern in TYPES if re.search(pattern, title, re.I)), None)


def fetch(url):
    request = Request(url, headers={'User-Agent': 'ThePolicyTape/1.0'})
    with urlopen(request, timeout=15) as reply:
        return reply.read().decode('utf-8-sig')


def label(element):
    # A BR often separates the host from the city on the Canadian calendar.
    words = ' '.join(' '.join(element.itertext()).split())
    return re.sub(r'\s+([,.;!?])', r'\1', words)


def instant(day, hour, minute, zone):
    local = day.replace(hour=int(hour), minute=int(minute), tzinfo=ZoneInfo(zone) if isinstance(zone, str) else zone)
    return local.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


DAY = re.compile(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?')
UK_CLOCK = re.compile(r'\((\d{1,2})(?:[.:](\d\d))?\s*([ap]m)(?:\s+(GMT|BST|UK time))?\)\.?$', re.I)


def england(content):
    doc = html.fromstring(content)
    match = re.search(r'Upcoming events[^|]*?\b(20\d{2})\b', doc.findtext('.//title') or '', re.I)
    if not match:
        raise ValueError('Missing year on Bank of England weekly schedule')
    year = int(match[1])
    dates, rows = [], []
    for group in doc.xpath('//div[@class="page-content"]'):
        day = None
        for element in group:
            text = label(element)
            if DAY.fullmatch(text):
                # Calendar weeks can straddle New Year. Resolve against the printed weekday.
                parts = text.split()
                years = [int(parts[3])] if len(parts) == 4 else [year, year - 1, year + 1]
                day = None
                for candidate in years:
                    stamp = datetime.strptime(f'{parts[1]} {parts[2]} {candidate}', '%d %B %Y')
                    if stamp.strftime('%A') == parts[0]:
                        day = stamp
                        break
                if day is None:
                    raise ValueError(f'Unresolved Bank of England date: {text}')
                dates.append(day.date().isoformat())
                continue
            if day is None or element.tag != 'p' or ':' not in text or CANCELLED.search(text):
                continue
            speaker, title = (part.strip() for part in text.split(':', 1))
            kind = event_type(title)
            if not kind or not re.fullmatch(r"[^\W\d_][\w\s,.’'\-]{2,140}", speaker):
                continue
            row = dict(bank='Bank of England', speaker=speaker, title=title, eventType=kind,
                       date=day.date().isoformat(), source=UK)
            clock = UK_CLOCK.search(title)
            if clock:
                hour = int(clock[1]) % 12 + (12 if clock[3].lower() == 'pm' else 0)
                zone = (clock[4] or '').upper()
                # Unlabelled overseas and virtual venue times have no safe UTC conversion.
                if zone or re.search(r'\bLondon\b|Treasury Select Committee', title, re.I):
                    clock_zone = {'GMT': timezone.utc, 'BST': timezone(timedelta(hours=1))}.get(zone, 'Europe/London')
                    row['at'] = instant(day, hour, clock[2] or 0, clock_zone)
                    row['title'] = title[:clock.start()].rstrip(' .')
            rows.append(row)
    if not dates:
        raise ValueError('No dated Bank of England schedule sections')
    return rows, min(dates), max(dates)


CA_CLOCK = re.compile(r'\b(\d{1,2}):(\d{2})\s*\((?:ET|Eastern Time)\)', re.I)


def canadian_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.hostname != 'www.bankofcanada.ca':
        raise ValueError('Unexpected Canadian event link')
    return url


def canada_detail(url, day):
    doc = html.fromstring(fetch(canadian_url(url)))
    dates = doc.xpath('//main//div[@class="post-date"]')
    if not dates or datetime.strptime(label(dates[0]), '%B %d, %Y').date() != day.date():
        raise ValueError(f'Canadian detail date did not match listing: {url}')
    if not doc.xpath('//main//h1'):
        raise ValueError('Missing Canadian event heading')
    return doc


def cancelled_detail(doc):
    main = doc.xpath('//main')[0]
    return (CANCELLED.search(label(main.xpath('.//h1')[0])) or
            re.search(r'\b(?:this|the) (?:event|appearance|speech|press conference) (?:has been|is|was) (?:cancell?ed|postponed)\b', label(main), re.I))


def canada(content):
    doc = html.fromstring(content)
    articles = doc.xpath('//article[.//a[@data-content-type="Upcoming events"]]')
    dates, rows = [], []
    for article in articles:
        stamps = article.xpath('.//span[contains(@class,"media-date")]')
        if not stamps:
            raise ValueError('Canadian upcoming event is missing its date')
        day = datetime.strptime(label(stamps[0]), '%B %d, %Y')
        dates.append(day.date().isoformat())
        a = article.xpath('.//h3/a')[0]
        heading = label(a)
        activity, _, name = heading.partition(':')
        kind = event_type(activity)
        if not name or not kind or CANCELLED.search(label(article)):
            continue
        speaker = name.split(',')[0].strip()
        # Press conferences named after a report do not identify a speaker here.
        if not re.search(r',\s*(?:(?:Senior|Deputy)\s+)*Governor\b', name, re.I):
            continue
        listing = canadian_url(a.get('href', ''))
        detail = canada_detail(listing, day)
        if cancelled_detail(detail):
            continue
        excerpt = article.xpath('.//div[contains(@class,"media-excerpt")]')
        venue = label(excerpt[0]) if excerpt else ''
        row = dict(bank='Bank of Canada', speaker=speaker, title=f'{kind} · {venue}' if venue else kind,
                   date=day.date().isoformat(), source=listing, calendarEntry=listing, eventType=kind)
        links = [a.get('href') for a in detail.xpath('//main//a[@href]') if label(a).lower() == 'media advisory']
        if not links:
            clock = CA_CLOCK.match(venue)
            if clock:
                row['at'] = instant(day, *clock.groups(), 'America/Toronto')
            rows.append(row)
            continue
        advisory = canada_detail(links[0], day)
        if cancelled_detail(advisory):
            continue
        sections = {label(dt).casefold(): label(dt.getnext()) for dt in advisory.xpath('//main//dt[following-sibling::*[1][self::dd]]')}
        if 'time' not in sections:
            raise ValueError('Linked Canadian advisory has no time field')
        row.update(source=links[0], title=f'{kind} · {sections.get("topic") or venue}')
        clock = CA_CLOCK.fullmatch(sections['time'].rstrip('.'))
        if clock:
            row['at'] = instant(day, *clock.groups(), 'America/Toronto')
            row['timeQualifier'] = 'Scheduled start'
        rows.append(row)
        distribution = sections.get('distribution', '')
        text_clock = CA_CLOCK.search(distribution)
        if text_clock and re.search(r'(?:text|remarks).*?(?:website|online).*?\bat\b', distribution, re.I) and not re.search(r'approximat', distribution, re.I):
            release = dict(row, title='Speech text release · ' + (sections.get('topic') or venue),
                           eventType='Speech text release', at=instant(day, *text_clock.groups(), 'America/Toronto'))
            release.pop('timeQualifier', None)
            rows.append(release)
        media = sections.get('media availability', '')
        media_clock = CA_CLOCK.search(media)
        if media_clock and re.search(r'hold a press conference', media, re.I):
            press = dict(row, title='Press conference following the speech', eventType='Press conference')
            press.pop('at', None)
            press.pop('timeQualifier', None)
            if re.search(r'approx|around|about', media[:media_clock.start()], re.I):
                press['title'] += f' · about {media_clock[0]}'
            elif re.match(r'At\s+[0-9]', media, re.I):
                press['at'] = instant(day, *media_clock.groups(), 'America/Toronto')
            rows.append(press)
    if not dates:
        raise ValueError('No dated Bank of Canada schedule entries')
    return rows, min(dates), max(dates)
