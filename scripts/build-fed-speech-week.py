"""Render the Fed speech review from the same source-keyed records used in the archive."""
import csv
import json
from decimal import Decimal
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlencode

DIST = Path(__file__).resolve().parents[1] / "dist"
study = json.loads((DIST / "data/fed-speech-week.json").read_text())
notes = {row["url"]: row for row in json.loads((DIST / "data/research-notes.json").read_text())}
# Both readers use the same figures and copy calculated from the settlement file.
pricing = study["pricing"]
with (DIST / pricing["settlementsCsv"]).open() as handle:
    quotes = {row["trade_date"]: row for row in csv.DictReader(handle) if row["contract"] == pricing["contract"]}
for day, window in pricing["windows"].items():
    prior = quotes[window["priorDate"]]
    after = quotes.get(day)
    prior_level = Decimal(prior["implied_step_bp"])
    window["priorPrice"] = prior["settlement_price"]
    window["priorStepBp"] = float(prior_level)
    window["priorSource"] = prior["cme_source"]
    window["afterPrice"] = after["settlement_price"] if after else None
    after_level = Decimal(after["implied_step_bp"]) if after else None
    window["afterStepBp"] = float(after_level) if after else None
    window["changeBp"] = float(after_level - prior_level) if after else None
    day_us = date.fromisoformat(day).strftime("%m/%d/%Y")
    window["afterSource"] = after["cme_source"] if after else prior["cme_source"].replace(date.fromisoformat(window["priorDate"]).strftime("%m/%d/%Y"), day_us)
    before_date = date.fromisoformat(window["priorDate"]).strftime("%d %b")
    after_date = date.fromisoformat(day).strftime("%d %b")
    summary = f"{before_date} settlement {window['priorPrice']} implied {prior_level:+.2f} bp at the 9 December decision. "
    if after:
        change = after_level - prior_level
        delta = f"{change:+.2f}" if change else "0.00"
        summary += f"{after_date} settlement {window['afterPrice']} implied {after_level:+.2f} bp. Daily change {delta} bp."
    else:
        summary += f"Post-speech quote unavailable. CME’s final report for {after_date} supplied no settlement to compute the change."
    window["summary"] = summary
(DIST / "data/fed-speech-week.json").write_text(json.dumps(study, indent=2, ensure_ascii=False) + "\n")
articles = []
for source, case in study["cases"].items():
    note = notes[source]
    assert note["date"] == case["date"]
    archive = "research-archive.html?" + urlencode({"month": case["date"][:7], "analysis": note["file"][:-5]})
    score = case["score"]
    label = escape(case["label"]) if score is None else f'{score:+d} · {escape(case["label"])}'
    heading = date.fromisoformat(case["date"]).strftime("%d %B")
    window = pricing["windows"][case["date"]]
    context = escape(window["context"])
    if window.get("contextSource"):
        context += f' <a href="{escape(window["contextSource"])}">Release record</a>.'
    comparison = ""
    if prior_outlook := case.get("priorOutlook"):
        comparison = (f'<h4>Change from the earlier outlook</h4><p>{escape(prior_outlook["comparison"])}</p>'
                      f'<p><a href="{escape(prior_outlook["url"])}">{escape(prior_outlook["label"])}</a></p>')
    market = f'''<h4>Pricing for the December meeting</h4>
<p>Remarks at <a href="{escape(case["releaseTimeSource"])}">{escape(case["releaseTimeET"])} ET</a>. {escape(window["summary"])}</p>
<p>{context}</p>
<p class="rs-links"><a href="{escape(window["priorSource"])}">Previous CME settlement</a> <a href="{escape(window["afterSource"])}">Speech-day CME report</a> <a href="{escape(pricing["methodUrl"])}">Pricing calculation</a></p>'''
    articles.append(f'''<article id="{escape(case["id"])}" class="rs-pending">
<h3>{escape(case["speaker"])} · <time datetime="{case["date"]}">{heading}</time></h3>
<p><strong>{label}</strong></p>
<p>{escape(case["rationale"])}</p>
<blockquote>“{escape(case["evidence"])}”</blockquote>
<p class="rs-links"><a href="{escape(source)}">{escape(case["title"])}</a> <a href="{escape(archive)}">Read the dated archive note</a></p>
{comparison}{market}</article>''')
page = '''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Read the evidence behind the policy-direction scores for Federal Reserve Board speeches, 16–20 November 2026.">
<title>Did Fed speakers signal a rate move? · Central Bank Intelligence</title>
<link rel="icon" href="favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="edition.css"><link rel="stylesheet" href="macro-studies.css">
<link rel="stylesheet" href="film-edition.css">
<script src="site-index.js" defer></script>
<script src="film-edition.js" defer></script>
</head><body><a class="skip-link" href="#main">Skip to content</a>
<header class="cbi-head film-masthead"><div class="shell cbi-bar"><a class="cbi-name" href="./"><i aria-hidden="true"></i><span>Central Bank Intelligence</span></a><nav aria-label="Primary research" class="film-primary"><a href="market-reactions.html">Market reactions</a><a href="historical-data.html">Policy history</a><a href="macro-history.html">Macro history</a></nav><a href="site-index.html" class="film-index-launch" data-index-open><span class="film-index-symbol" aria-hidden="true"></span>Site index</a></div></header>
<main id="main" class="rs-wrap">
<header class="rs-head"><p class="eyeline">Federal Reserve Board · 16–20 November 2026</p><h1>Did Fed speakers signal a rate move?</h1>
<p>Two speakers favoured further tightening. One described conditions that could pull policy in either direction. Four speeches gave no current rate guidance.</p></header>
<section class="rs-study" aria-labelledby="method"><h2 id="method">How to read a score</h2>
<p>Read each speaker’s stated preference for the current or prospective US policy rate. The unit is one set of prepared remarks. A speaker can discuss inflation, payments or financial risks without taking a position on rates.</p>
<p>On this editorial scale, +2 and −2 denote an advocated tightening or easing, respectively. +1 and −1 denote a directional lean conditional on the speaker’s baseline. Zero is reserved for an explicit preference to maintain the current rate. Two-sided conditions without a preferred direction and speeches without guidance both receive a blank numeric score.</p>
<p>These seven readings use the official speech texts available through 20 November. The scores describe individuals’ views. Market expectations, changes from a previous speech and the size of any likely rate move require separate evidence.</p>
<p>The same December fed funds futures contract (ZQZ6) trades throughout the week. Its final settlement at 3 p.m. ET implies a change from the 3.88% effective rate assuming one move effective 10 December. Daily changes use unrounded inputs and include other news. Speakers on the same day share one pair of settlements.</p>
<p class="rs-links"><a href="policy-stance.html">Explore policy statement scores</a> <a href="data/fed-speech-week.json" download>Download speech evidence (JSON)</a></p></section>
<section class="rs-study" aria-labelledby="records"><h2 id="records">Seven speeches</h2>
''' + "\n".join(articles) + f'''
<p><a href="{escape(study["catalogue"])}">Federal Reserve Board speech catalogue</a></p>
</section></main></body></html>
'''
(DIST / "fed-speech-week.html").write_text(page)
