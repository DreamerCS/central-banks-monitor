"""Refresh the official economic release calendar, retaining verified schedules through outages."""
import argparse
import importlib
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parents[1] / "dist/data/economic-calendar.json"
# The agencies maintain separate releases even when they have the same date and clock.
AGENCIES = {
    "BLS": ("calendar_us", "US", "U.S. Bureau of Labor Statistics",
            "https://www.bls.gov/schedule/", "America/New_York"),
    "BEA": ("calendar_us", "US", "U.S. Bureau of Economic Analysis",
            "https://www.bea.gov/news/schedule", "America/New_York"),
    "Eurostat": ("calendar_europe", "Euro area", "Eurostat euro indicators",
                 "https://ec.europa.eu/eurostat/news/euro-indicators/release-calendar", "Europe/Luxembourg"),
    "ONS": ("calendar_europe", "UK", "UK Office for National Statistics",
            "https://www.ons.gov.uk/releasecalendar", "Europe/London"),
}
SCOPES = {
    "BLS": "Selected statistical releases on the BLS annual schedule.",
    "BEA": "Releases listed on the official BEA economic accounts calendar.",
    "Eurostat": "Confirmed euro indicators for growth, employment, prices, output, trade, retail and public finances, plus European Commission business and consumer surveys.",
    "ONS": "Confirmed UK releases on growth, output, retail, trade, labour, earnings, prices, household costs, public finances, balance of payments and investment.",
}


def day(value):
    parsed = date.fromisoformat(value)
    if value != parsed.isoformat():
        raise ValueError(f"Expected calendar date, got {value!r}")
    return parsed


def instant(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp has no UTC offset")
    return parsed


def clean_rows(rows, agency):
    _, country, _, _, tz = AGENCIES[agency]
    by_id = {}
    for raw in rows:
        row = {k: raw[k] for k in ("id", "agency", "country", "title", "date", "source")}
        if row["agency"] != agency or row["country"] != country:
            raise ValueError("Unexpected agency or geography")
        if any(not isinstance(v, str) or not v.strip() for v in row.values()):
            raise ValueError("Incomplete release")
        address = urlsplit(row["source"])
        if address.scheme != "https" or not address.hostname or address.username or address.password:
            raise ValueError("Invalid source URL")
        scheduled = day(row["date"])
        if "start" in raw:
            if instant(raw["start"]).astimezone(ZoneInfo(tz)).date() != scheduled:
                raise ValueError("The published local date and timestamp disagree")
            row["start"] = raw["start"]
        if row["id"] in by_id and by_id[row["id"]] != row:
            raise ValueError(f'Conflicting release ID: {row["id"]}')
        by_id[row["id"]] = row
    return by_id


def read_snapshot(path):
    if not path or not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text())
        if not isinstance(document.get("sources"), list) or not isinstance(document.get("events"), list):
            raise ValueError("Missing calendar arrays")
        return document
    except (OSError, ValueError, AttributeError) as error:
        print(f"Ignoring unreadable previous calendar {path.name}: {error}")
        return {}


def previous_schedule(agency, snapshots):
    newest = None
    result = {}, {}
    for snapshot in snapshots:
        source = next((s for s in snapshot.get("sources", []) if isinstance(s, dict) and s.get("agency") == agency), {})
        if not source.get("lastVerifiedAt"):
            continue
        try:
            verified = instant(source["lastVerifiedAt"])
            first, last = day(source["verifiedFrom"]), day(source["verifiedThrough"])
            if first > last:
                raise ValueError("Invalid previous coverage interval")
            rows = clean_rows((r for r in snapshot["events"] if r.get("agency") == agency), agency)
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            print(f"Ignoring invalid previous {agency} schedule: {error}")
            continue
        if newest is None or verified > newest:
            newest, result = verified, (source, rows)
    return result


def agency_schedule(agency, snapshots, today, first, last, checked):
    module_name, country, label, url, _ = AGENCIES[agency]
    prior, cached = previous_schedule(agency, snapshots)
    source = dict(agency=agency, country=country, label=label, url=url, scope=SCOPES[agency])
    try:
        module = importlib.import_module(module_name)
        observed = clean_rows(module.SOURCES[agency](), agency)
        coverage = getattr(module, "COVERAGE", {}).get(agency)
        if coverage:
            covered_from, covered_to = coverage(today)
        else:
            dates = [day(row["date"]) for row in observed.values()]
            if not dates:
                raise ValueError("No published interval could be verified")
            covered_from, covered_to = min(dates), max(dates)
        if covered_from > last or covered_to < today or covered_from > covered_to:
            raise ValueError("Source schedule does not establish current coverage")
        start, end = max(first, covered_from).isoformat(), min(last, covered_to).isoformat()
        # Within a complete verified interval a withdrawal or rescheduling supersedes the
        # previous entry. Newer observations always supersede the same stable ID.
        merged = {k: v for k, v in cached.items() if not start <= v["date"] <= end}
        merged.update(observed)
        source.update(status="verified", lastVerifiedAt=checked, verifiedFrom=start, verifiedThrough=end)
    except Exception as error:
        print(f"{agency} schedule unavailable for this refresh: {type(error).__name__}: {error}")
        merged = cached
        source.update(status="stale" if prior else "unavailable", lastVerifiedAt=prior.get("lastVerifiedAt"),
                      verifiedFrom=prior.get("verifiedFrom"), verifiedThrough=prior.get("verifiedThrough"))
    rows = [r for r in merged.values() if first.isoformat() <= r["date"] <= last.isoformat()]
    source["eventCount"] = len(rows)
    print(f'{agency}: {source["status"]}, {len(rows)} releases')
    return source, rows


def build(snapshots, now):
    today = now.date()
    first, last = today - timedelta(days=7), today + timedelta(days=90)
    checked = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    sources, all_rows = [], []
    with ThreadPoolExecutor(max_workers=len(AGENCIES)) as pool:
        tasks = [pool.submit(agency_schedule, agency, snapshots, today, first, last, checked) for agency in AGENCIES]
        for task in tasks:
            source, rows = task.result()
            sources.append(source)
            all_rows.extend(rows)
    def order(row):
        clock = instant(row["start"]).astimezone(timezone.utc).isoformat() if "start" in row else "~"
        return row["date"], clock, row["agency"], row["title"], row["id"]
    return {"asOf": today.isoformat(), "from": first.isoformat(), "through": last.isoformat(), "updatedAt": checked,
            "sources": sources, "events": sorted(all_rows, key=order)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, help="Last published calendar, if available")
    parser.add_argument("--output", type=Path, default=DATA)
    args = parser.parse_args()
    snapshots = [read_snapshot(args.previous), read_snapshot(args.output)]
    result = build(snapshots, datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent, delete=False) as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary = Path(stream.name)
    temporary.chmod(0o644)
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
