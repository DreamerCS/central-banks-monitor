"""Apply the shared masthead and rebuild the static directory from dist/site-index.js."""
import json
import re
from html import escape
from itertools import groupby
from operator import itemgetter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TEMPLATES = (
    "build-ecb-speech-stance.py",
    "build-fed-speech-week.py",
    "build-jackson-hole-stance.py",
    "yen_intervention_page.py",
)
PRIMARY = (
    ("Market reactions", "market-reactions.html"),
    ("Policy history", "historical-data.html"),
    ("Macro history", "macro-history.html"),
    ("Research library", "research-library.html"),
)
ASSETS = """<link rel="stylesheet" href="film-edition.css">
<script src="site-index.js" defer></script>
<script src="film-edition.js" defer></script>"""
OLD_HEADER = re.compile(r'<header\b[^>]*\bclass="(?:masthead|cbi-head(?: [^"]*)?)"[^>]*>.*?</header>', re.DOTALL)
SHARED_ASSET = re.compile(
    r"""[ \t]*(?:<link\b[^>]*\bhref=["'](?:\./)?film-edition\.css(?:[?#][^"']*)?["'][^>]*>"""
    r"""|<script\b[^>]*\bsrc=["'](?:\./)?(?:site-index|film-edition)\.js(?:[?#][^"']*)?["'][^>]*>\s*</script\s*>)[ \t]*\n?""",
    re.IGNORECASE,
)


def masthead(page):
    links = []
    for label, href in PRIMARY:
        current = ' aria-current="page"' if page == href else ""
        links.append(f'<a href="{href}"{current}>{label}</a>')
    return (
        '<header class="cbi-head film-masthead"><div class="shell cbi-bar">'
        '<a class="cbi-name" href="./"><i aria-hidden="true"></i><span>Central Bank Intelligence</span></a>'
        '<nav aria-label="Primary research" class="film-primary">' + "".join(links) + '</nav>'
        '<a href="site-index.html" class="film-index-launch" data-index-open>'
        '<span class="film-index-symbol" aria-hidden="true"></span>Site index</a></div></header>'
    )


def apply_navigation(markup, page):
    markup, count = OLD_HEADER.subn(masthead(page), markup)
    if count != 1 or markup.count("</head>") != 1:
        raise ValueError(f"Expected one masthead and HTML head in {page}")
    # Move the edition assets to the end if an individual page adds styles on regeneration.
    markup = SHARED_ASSET.sub("", markup)
    return markup.replace("</head>", ASSETS + "\n</head>")


def render_index():
    script = (DIST / "site-index.js").read_text()
    entries = json.loads(script.split("window.CBI_SITE_INDEX = ", 1)[1].strip().removesuffix(";"))
    sections = []
    for section in entries:
        title = escape(section["label"])
        subsections = []
        for name, items in groupby(section["items"], key=itemgetter("section")):
            links = [
                f'<li><a href="{escape(item["href"], quote=True)}">{escape(item["label"])}</a></li>'
                for item in items
            ]
            subsections.append(
                f'<div class="film-index-subsection"><h3>{escape(name)}</h3>\n<ul>\n'
                + "\n".join(links) + "\n</ul></div>"
            )
        sections.append(f'<section class="film-index-section"><h2>{title}</h2>\n'
                        + "\n".join(subsections) + "\n</section>")
    return """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Site index · Central Bank Intelligence</title>
<meta name="description" content="Browse the market studies, policy history, macro history, publications and data tools in Central Bank Intelligence.">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="edition.css">
""" + ASSETS + """
</head><body>
<a href="#main" class="skip-link">Skip to content</a>
""" + masthead("site-index.html") + """
<main id="main" class="shell film-index-page"><h1>Site index</h1>
<div class="film-index-groups">
""" + "\n".join(sections) + """
</div></main>
</body></html>
"""


def write_if_changed(path, content):
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


def main():
    write_if_changed(DIST / "site-index.html", render_index())
    for page in sorted(DIST.glob("*.html")):
        if page.name == "reading-studies.html":  # Legacy redirect to macro-studies.html.
            continue
        write_if_changed(page, apply_navigation(page.read_text(), page.name))
    for name in TEMPLATES:
        source = ROOT / "scripts" / name
        write_if_changed(source, apply_navigation(source.read_text(), name))


if __name__ == "__main__":
    main()
