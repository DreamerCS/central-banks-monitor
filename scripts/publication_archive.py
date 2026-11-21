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


# These corrections identify one dated feed entry. Annual catalogues may be
# reused for later releases, so they must never become permanent URL aliases.
DATED_PUBLICATIONS = {
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24117"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/07APPENDIXI19112026A198F390DF914F41AEC15D77C81602D3.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24116"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/06APPENDIXI191120263A7F124B464D4834966F1A0B2B409D46.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24115"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/05APPENDIXI191120265A109F9F1A3B48ABB08CDECD240A1F99.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24105"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/01OVERVIEW19112026B29D00152F5C424E98C9CF7ABB3E9557.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24106"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/02FISCAL191120269B012BB5588F48B39FE0A962780E515A.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24107"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/03LOCAL191120265BBFAFED86484060B06DAFC552D4FEC4.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24108"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/04WAYFORWARD191120266F83311EA41848B6B6A7A180A1319705.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24109"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/05REFERENCES19112026A0E48A583FC24D618DBB90A8DE2D6E50.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24110"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/06EXPLANATORYNOTE19112026038321D1CFB740BF98DA947E68A07C29.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24111"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/01APPENDIXI191120264D4476F5212A45829E5DA48AE330FA2B.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24112"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/02APPENDIXI191120261E194DEF33394A5D93FE7E5F03469987.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24113"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/03APPENDIXI191120263665E038E1684A78BE0E477CC21EC2A2.PDF",
    },
    ("2026-11-19", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24114"): {
        "url": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/04APPENDIXI19112026FD548FAFF0074FC6B25C99E346850603.PDF",
    },
    ("2026-11-06", "https://www.boj.or.jp/en/research/imes/dps/dps26.htm"): {
        "url": "https://www.imes.boj.or.jp/research/abstracts/english/26-E-14.html",
        "title": "Generative AI for Economic Simulation: Heterogeneity in Subjective Models of Inflation",
        "type": "Research",
    },
    ("2026-11-06", "https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=24098"): {
        "url": "https://www.rbi.org.in/scripts/PublicationsView.aspx?id=24098",
    },
    ("2026-11-03", "https://www.snb.ch/en/publications/research/working-papers/2026/working_paper_2026_14"): {
        "date": "2026-11-04",
        "title": "Forecasting the post-COVID inflation surge in Switzerland",
    },
}


def correct_dated_publication(row):
    """Normalize the official item before any feed or archive deduplication."""
    day_key = "day" if "day" in row else "date"
    correction = DATED_PUBLICATIONS.get((row.get(day_key), row["url"]))
    if not correction:
        return row
    return {**row, **{day_key if key == "date" else key: value
                      for key, value in correction.items()}}


def with_previous_urls(row):
    """Keep catalogue identifiers attached to the corrected publication."""
    row = correct_dated_publication(row)
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
