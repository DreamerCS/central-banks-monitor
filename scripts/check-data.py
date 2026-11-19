"""Check the requested research universe before publishing."""
import json
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
assert sum("Europe Policies & Models" in item.get("workbook", []) for item in sources) == 69

periods = json.loads((ROOT / "archive-periods.json").read_text())
assert len({period["id"] for period in periods}) == len(periods)
for period in periods:
    start, end = (date.fromisoformat(period[key]) for key in ("start", "end"))
    assert start.day == 1 and (start.year, start.month) == (end.year, end.month), period
assert all(a["end"] < b["start"] for a, b in zip(periods, periods[1:]))

channels = json.loads((Path(__file__).with_name("monitored-sources.json")).read_text())
assert len({row["id"] for row in channels}) == len({row["url"] for row in channels}) == len(channels)
for row in channels:
    assert row["bank"] in expected and urlparse(row["url"]).scheme == "https", row["id"]
    if "listing" in row:
        assert {"entry", "link", "date"} <= row["listing"].keys(), row["id"]
        assert "title" in row["listing"] or "titleText" in row["listing"], row["id"]

print(f"OK: {coverage['linkedCount']}/{coverage['targetCount']} targets; {len(sources)} unique HTTPS source entries")
