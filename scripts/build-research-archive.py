"""Validate the research records and render the public monthly archive."""
import argparse
import json
from collections import defaultdict
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dist" / "data"
ALIASES = {
    "US": "United States", "UK": "United Kingdom", "Euro-area": "Euro area",
    "Germany": "Euro area", "France": "Euro area", "Italy": "Euro area", "Spain": "Euro area",
}
MONTHS = [
    ("oct", "October 2026", "2026-10-01", "2026-10-31"),
    ("nov", "November 2026", "2026-11-01", "2026-11-19"),
]
e = escape


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def status(entries):
    analysed = sum(bool(row.get("summary")) for row in entries)
    return f"{len(entries)} sources · {analysed} notes" if entries else "Source review pending"


def render_record(row):
    title = e(row["title"])
    link = f'<a href="{e(row["url"])}" target="_blank" rel="noopener noreferrer">Official source ↗</a>'
    analysed = bool(row.get("summary"))
    label = "Analysis available" if analysed else "Analysis pending"
    locator = f'<p class="record-locator">Source sections: {e(row["locator"])}</p>' if row.get("locator") else ""
    limit = row.get("coverageNote") or row.get("coverageLimitation")
    limitation = f'<p class="record-locator"><strong>Coverage:</strong> {e(limit)}</p>' if limit else ""
    related = "".join(
        f' · <a href="{e(item["url"])}" target="_blank" rel="noopener noreferrer">{e(item["label"])} ↗</a>'
        for item in row.get("related", [])
    )
    body = '<p>The publication is indexed for this month. Its research note is pending.</p>'
    if analysed:
        paragraphs = "".join(f"<p>{e(p)}</p>" for p in row["summary"].split("\n\n") if p.strip())
        questions = "".join(
            f'<li><strong>{e(q["question"])}</strong> {e(q["evidence"])}</li>'
            for q in row["questions"]
        )
        body = f'{paragraphs}<h4>Questions for further research</h4><ol>{questions}</ol>'
    search_text = e(" ".join((row["title"], row["institution"], row["type"], row["date"])).casefold())
    return f"""
<article class="research-record" data-type="{e(row['type'])}" data-analysed="{str(analysed).lower()}" data-search="{search_text}">
  <div class="record-meta"><time datetime="{row['date']}">{row['date']}</time><span>{e(row['type'])}</span><span>{label}</span></div>
  <h4>{title}</h4><p class="record-issuer">{e(row['institution'])}</p>
  <details><summary>{"Read analysis" if analysed else "Publication details"}</summary><div class="record-body">{body}{locator}{limitation}</div></details>
  <p class="official-link">{link}{related}</p>
</article>"""


def render_sources(sources):
    grouped = defaultdict(list)
    for source in sources:
        grouped[source["institution"]].append(source)
    items = []
    for institution, links in grouped.items():
        rendered = " · ".join(
            f'<a href="{e(s["url"])}" target="_blank" rel="noopener noreferrer">{e(s["category"])}</a>'
            for s in links
        )
        items.append(f"<li><strong>{e(institution)}</strong><div>{rendered}</div></li>")
    return "<ul>" + "".join(items) + "</ul>"


def render_month(month, targets, grouped_sources, rows):
    key, label, start, end = month
    entries = [r for r in rows if start <= r["date"] <= end]
    by_bank = defaultdict(list)
    for row in entries:
        by_bank[row["jurisdiction"]].append(row)
    jump = []
    groups = []
    for index, bank in enumerate(targets, 1):
        items = by_bank[bank]
        anchor = f"{key}-bank-{index}"
        jump.append(f'<li><a href="#{anchor}">{e(bank)}<span>{e(status(items))}</span></a></li>')
        cards = "".join(render_record(r) for r in items)
        no_items = "" if items else "<p class='missing'>No dated publication verified here yet. Use the official register links to continue the review.</p>"
        groups.append(f"""
<section class="bank-section" id="{anchor}" data-bank="{e(bank)}">
  <div class="bank-title"><h3>{e(bank)}</h3><span>{e(status(items))}</span></div>
  {cards}{no_items}
  <details class="register-links"><summary>Official register sources</summary>{render_sources(grouped_sources[bank])}</details>
</section>""")
    notes = sum(bool(row.get("summary")) for row in entries)
    institutions = len({row["institution"] for row in entries})
    covered = sum(bool(items) for items in by_bank.values())
    return f"""
<section class="archive-month" id="{key}" aria-labelledby="{key}-title">
  <div class="month-title"><h2 id="{key}-title">{label}</h2><p>{start} to {end} · {covered}/29 jurisdictions · {institutions} institutions · {len(entries)} publications · {notes} research notes</p></div>
  <ul class="bank-jump" aria-label="{label} jurisdiction shortcuts">{''.join(jump)}</ul>
  {''.join(groups)}
</section>"""


def load_records(path):
    return read_json(path) if path.is_file() else [
        row for source in sorted(path.glob("*.json")) for row in read_json(source)
    ]


def build(records):
    targets = [x["name"] for x in read_json(DATA / "coverage.json")["targets"]]
    sources = read_json(DATA / "sources.json")["sources"]
    grouped_sources = defaultdict(list)
    for source in sources:
        country = ALIASES.get(source["country"], source["country"])
        if country in targets:
            grouped_sources[country].append(source)
    assert len(targets) == len(set(targets)) == len(grouped_sources) == 29
    assert sum(map(len, grouped_sources.values())) == len(sources)
    assert len({r["institution"] for src in grouped_sources.values() for r in src}) == 45
    assert records, "No archive records"
    seen = set()
    allowed_types = {"Decision", "Minutes", "Forecast", "Speech", "Research", "Testimony", "Statement"}
    for r in records:
        assert r["jurisdiction"] in targets, r
        assert r["type"] in allowed_types, r
        assert all(isinstance(r[k], str) and r[k].strip() for k in ("date", "institution", "title", "url")), r
        assert date.fromisoformat(r["date"]).isoformat() == r["date"]
        assert any(start <= r["date"] <= end for _, _, start, end in MONTHS), r
        url = urlsplit(r["url"])
        assert url.scheme == "https" and url.hostname and not url.username, r
        identity = (url.hostname, url.path.rstrip("/"), url.query, url.fragment)
        assert identity not in seen, f"Duplicate source: {r['url']}"
        seen.add(identity)
        for item in r.get("related", []):
            linked = urlsplit(item["url"])
            assert linked.scheme == "https" and linked.hostname and not linked.username, item
        if r.get("summary"):
            assert isinstance(r["summary"], str) and 3 <= len(r["questions"]) <= 5, r
            assert all(q["question"].strip() and q["evidence"].strip() for q in r["questions"]), r
    rows = sorted(records, key=lambda r: (r["date"], r["title"]), reverse=True)
    month_html = "".join(render_month(month, targets, grouped_sources, rows) for month in MONTHS)
    types = "".join(f'<option value="{e(t)}">{e(t)}</option>' for t in sorted(allowed_types))
    banks = "".join(f'<option value="{e(b)}">{e(b)}</option>' for b in targets)
    template = (ROOT / "scripts" / "research-archive.html").read_text(encoding="utf-8")
    page = template.replace("{{MONTHS}}", month_html).replace("{{BANKS}}", banks).replace("{{TYPES}}", types)
    for label, prefix in (("October", "2026-10"), ("November", "2026-11")):
        month = [r for r in rows if r["date"].startswith(prefix)]
        notes = [r for r in month if r.get("summary")]
        dated_banks = {r["jurisdiction"] for r in month}
        print(f"{label}: {len(month)} documents, {len(notes)} notes, {len(dated_banks)}/29 jurisdictions with dated sources")
        print(f"  Pending dated sources: {', '.join(b for b in targets if b not in dated_banks) or 'none'}")
    return rows, page


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fragments", type=Path, help="Directory of individual research batches")
    args = parser.parse_args()
    archive = DATA / "research-archive.json"
    rows, page = build(load_records(args.fragments or archive))
    archive.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "dist" / "research-archive.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
