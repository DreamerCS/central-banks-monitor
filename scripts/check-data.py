"""Check the requested research universe before publishing."""
import json
import math
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1] / "dist" / "data"
sources = json.loads((ROOT / "sources.json").read_text())["sources"]
coverage = json.loads((ROOT / "coverage.json").read_text())

expected = {
    "United States", "Euro area", "United Kingdom", "Sweden", "Norway",
    "Switzerland", "Canada", "Australia", "New Zealand", "Japan",
    "Mexico", "Colombia", "Brazil", "Argentina", "Peru", "Hungary",
    "Poland", "Czechia", "Türkiye", "South Africa", "China", "Taiwan",
    "South Korea", "Singapore", "India", "Indonesia", "Malaysia",
    "Philippines", "Thailand",
}
actual = {item["name"] for item in coverage["targets"]}
assert actual == expected, f"Missing: {expected - actual}; extra: {actual - expected}"
assert len(coverage["targets"]) == coverage["targetCount"] == 29
assert coverage["linkedCount"] == sum(item["sourceCount"] > 0 for item in coverage["targets"]) == 29
assert len({item["id"] for item in sources}) == len(sources)
assert len({item["institution"] for item in sources}) == 45
for item in sources:
    assert urlparse(item["url"]).scheme == "https", item["id"]
    assert not item["feed"] or urlparse(item["feed"]).scheme == "https", item["id"]
    assert item.keys() == {"id", "institution", "country", "region", "category", "sourceType", "url", "feed"}, item["id"]

periods = json.loads((ROOT / "archive-periods.json").read_text())
records = json.loads((ROOT / "research-archive.json").read_text())
from publication_archive import VERIFIED_PUBLICATION_URLS

for row in records:
    assert row.keys() <= {"jurisdiction", "date", "institution", "title", "type", "url", "related", "sourcePage", "previousUrls"}, row["url"]
    for old in row.get("previousUrls", []):
        assert VERIFIED_PUBLICATION_URLS.get(old) == row["url"], old
    assert all(link.keys() == {"label", "url"} for link in row.get("related", [])), row["url"]
assert len({period["id"] for period in periods}) == len(periods)
for period in periods:
    start, end = (date.fromisoformat(period[key]) for key in ("start", "end"))
    assert start.day == 1 and (start.year, start.month) == (end.year, end.month), period
    covered = {row["jurisdiction"] for row in records if period["start"] <= row["date"] <= period["end"]}
    assert covered and covered <= expected, period
    if "2026-06" <= period["start"][:7] <= "2026-11":
        assert covered == expected, f"{period['label']} archive is missing {', '.join(sorted(expected - covered))}"
assert all(a["end"] < b["start"] for a, b in zip(periods, periods[1:]))

history = json.loads((ROOT / "historical-series.json").read_text())
start = date.fromisoformat(history["start"])
through = date.fromisoformat(history["through"])
assert start == date(2000, 1, 1) and through >= start
assert {series["name"] for series in history["series"]} == expected
assert len({series["id"] for series in history["series"]}) == len(history["series"]) == 29
for series in history["series"]:
    assert series["metric"] == ("neer" if series["name"] == "Singapore" else "rates"), series["id"]
    assert urlparse(series["source"]).scheme == "https" and series["institution"], series["id"]
    assert series["observations"], series["id"]
    previous_end = 0
    for offset, length, value in series["observations"]:
        assert type(offset) is int and type(length) is int and length > 0, series["id"]
        assert previous_end <= offset and offset + length - 1 <= (through - start).days, series["id"]
        assert math.isfinite(value), series["id"]
        previous_end = offset + length

channels = json.loads((Path(__file__).with_name("monitored-sources.json")).read_text())
assert len({row["id"] for row in channels}) == len({row["url"] for row in channels}) == len(channels)
for row in channels:
    assert row["bank"] in expected and urlparse(row["url"]).scheme == "https", row["id"]
    if "listing" in row:
        assert {"entry", "link", "date"} <= row["listing"].keys(), row["id"]
        assert "title" in row["listing"] or "titleText" in row["listing"], row["id"]

subprocess.run([sys.executable, Path(__file__).with_name("check-news-framing.py")], check=True)

subprocess.run([sys.executable, Path(__file__).with_name("export-news-framing.py"), "--check"], check=True)

subprocess.run([sys.executable, Path(__file__).with_name("build-news-coverage-audit.py"), "--check"], check=True)

print(f"OK: {coverage['linkedCount']}/{coverage['targetCount']} targets; {len(sources)} unique HTTPS source entries; {len(history['series'])} historical series")
