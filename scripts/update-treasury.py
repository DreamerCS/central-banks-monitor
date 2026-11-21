"""Build a dated, daily U.S. Treasury yield snapshot for the public site.

The Treasury feed is a daily close benchmark, not an intraday quote. Network
errors retain the previous snapshot; the page always shows its observation date.
"""
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "dist/data/treasury.json"
BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
SOURCE = "https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics"


def records(xml_bytes):
    root = ET.fromstring(xml_bytes)
    result = {}
    for entry in root.iter():
        if entry.tag.rsplit("}", 1)[-1] != "entry":
            continue
        fields = {child.tag.rsplit("}", 1)[-1].upper(): (child.text or "").strip()
                  for child in entry.iter()}
        raw_date = fields.get("NEW_DATE", "")
        if not raw_date:
            continue
        date = raw_date[:10]
        try:
            datetime.strptime(date, "%Y-%m-%d")
            two = float(fields["BC_2YEAR"])
            ten = float(fields["BC_10YEAR"])
        except (ValueError, KeyError):
            continue
        if 0 <= two <= 30 and 0 <= ten <= 30:
            result[date] = {"date": date, "twoYear": two, "tenYear": ten}
    return result


def main():
    year = datetime.now(timezone.utc).year
    merged = {}
    try:
        for y in (year - 1, year):
            url = f"{BASE}?data=daily_treasury_yield_curve&field_tdr_date_value={y}"
            request = urllib.request.Request(url, headers={"User-Agent": "ThePolicyTape/1.0", "Accept": "application/atom+xml, application/xml"})
            with urllib.request.urlopen(request, timeout=25) as response:
                merged.update(records(response.read(5_000_000)))
        if len(merged) < 20:
            raise ValueError(f"Only {len(merged)} valid Treasury observations")
    except Exception as exc:
        print(f"Treasury update unavailable; retaining existing snapshot: {exc}", file=sys.stderr)
        return 0 if OUT.exists() else 1
    rows = [merged[key] for key in sorted(merged)][-300:]
    snapshot = {
        "source": SOURCE,
        "feed": BASE,
        "frequency": "daily",
        "unit": "percent per annum",
        "benchmark": "U.S. Treasury daily par yield curve",
        "asOfDate": rows[-1]["date"],
        "observations": rows,
    }
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Treasury snapshot: {len(rows)} observations, latest {snapshot['asOfDate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
