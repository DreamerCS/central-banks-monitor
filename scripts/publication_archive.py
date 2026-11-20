"""Carry dated official publications forward between GitHub Pages builds."""

import calendar
from datetime import date


VERIFIED_PUBLICATION_URLS = {
    'https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24100':
        'https://www.rbi.org.in/scripts/PublicationsView.aspx?Id=24100',
    'https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24099':
        'https://www.rbi.org.in/scripts/PublicationsView.aspx?Id=24099',
    'https://www.rba.gov.au/speeches/2026/sp-sp-ag-2026-11-09.html':
        'https://www.rba.gov.au/speeches/2026/sp-ag-2026-11-09.html',
}


def with_previous_urls(row):
    """Keep catalogue identifiers attached to the corrected publication."""
    url = VERIFIED_PUBLICATION_URLS.get(row["url"], row["url"])
    previous = set(row.get("previousUrls", []))
    previous.update(old for old, current in VERIFIED_PUBLICATION_URLS.items() if current == url)
    previous.discard(url)
    if previous:
        return {**row, "url": url, "previousUrls": sorted(previous)}
    return row


def merge_publications(curated, previous, harvested, listings, today, identity):
    if not isinstance(previous, list) or not previous:
        raise ValueError("Cannot restore the published archive")
    # Caller validates the complete archive before deployment. Curated rows and
    # their related links take precedence over newly discovered alternatives.
    result = [with_previous_urls(row) for row in curated]
    urls = set()
    titles = set()

    def title_key(row):
        title = "".join(c for c in row["title"].casefold() if c.isalnum())
        return row["jurisdiction"], row["institution"], row["date"], title

    for row in result:
        urls.add(identity(row["url"]))
        urls.update(identity(link["url"]) for link in row.get("related", []))
        titles.add(title_key(row))

    def add(row):
        row = with_previous_urls(row)
        url, title = identity(row["url"]), title_key(row)
        if url not in urls and title not in titles:
            result.append(row)
            titles.add(title)
        urls.add(url)

    # Only restore harvested rows. This permits editorial changes to curated
    # records, including intentional removals, without reinstating stale copies.
    for row in previous:
        if row.get("sourcePage"):
            add(row)

    for item in harvested:
        if item["source"] not in listings:
            continue
        day = date.fromisoformat(item["day"])
        if day.year < 2026 or day > today:
            continue
        add(dict(jurisdiction=item["bank"], date=item["day"], title=item["title"],
                 institution=item["institution"], type=item["type"], url=item["url"],
                 sourcePage=listings[item["source"]]))
    return sorted(result, key=lambda row: (row["date"], row["title"]), reverse=True)


def extend_periods(periods, records, today):
    periods = [dict(period) for period in periods]
    by_month = {p["start"][:7]: p for p in periods}
    for day in sorted({r["date"] for r in records}):
        month = day[:7]
        if month not in by_month:
            d = date.fromisoformat(day)
            period = {"id": calendar.month_abbr[d.month].lower() if d.year == 2026 else month,
                      "label": calendar.month_name[d.month], "start": month + "-01", "end": day}
            periods.append(period)
            by_month[month] = period
    for month, period in by_month.items():
        start = date.fromisoformat(period["start"])
        last = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        if start <= today:
            period["end"] = min(today, last).isoformat()
    return sorted(periods, key=lambda p: p["start"])
