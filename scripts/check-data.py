"""Check the requested research universe before publishing."""
import json
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

print(f"OK: {coverage['linkedCount']}/{coverage['targetCount']} targets; {len(sources)} unique HTTPS source entries")
