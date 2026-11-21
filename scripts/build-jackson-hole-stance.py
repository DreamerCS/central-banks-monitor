"""Build the Jackson Hole speech comparison from reviewed texts and Treasury quotes."""
import csv
import json
from datetime import date
from decimal import Decimal
from html import escape
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DATA = DIST / "data"
# Speech evidence was coded separately from futures and Treasury observations.
CASES = [
    ("2021-08-27", -2, "Low-rate commitment", "Powell reaffirmed a near-zero policy rate until employment and inflation met explicit conditions. He separately opened the door to slowing asset purchases that year.", "continue to hold the target range for the federal funds rate at its current level until the economy reaches conditions consistent with maximum employment"),
    ("2022-08-26", 2, "Further tightening", "Powell described further restraint as necessary even if growth slowed. The size of the September increase still depended on the data.", "as the stance of monetary policy tightens further"),
    ("2023-08-25", 1, "Conditional tightening", "Inflation had fallen but remained too high. Powell kept a further increase available and said the Committee could proceed carefully.", "prepared to raise rates further if appropriate"),
    ("2024-08-23", -2, "Easing signalled", "With disinflation and a cooler labour market, Powell identified cuts as the direction of travel and left their speed and size open.", "the timing and pace of rate cuts will depend on incoming data"),
    ("2025-08-22", -1, "Conditional easing", "Powell saw greater downside employment risks and room to ease restrictive policy. Tariff-related inflation risks limited his commitment.", "the baseline outlook and the shifting balance of risks may warrant adjusting our policy stance"),
]
MARKET = {
    "2021": ("September meeting odds unavailable for this comparison.", "", []),
    "2022": ("75 bp hike probability, 56.5% before and 60.5% afterwards.", "With 50 and 75 bp as the two outcomes, implied tightening rose from 64.13 to 65.13 bp. The source gives no quote times, so other news could enter the 1.00 bp change.", [("Contemporaneous futures comparison, figure 2", "https://blog.bitfinex.com/wp-content/uploads/2022/08/Bitfinex-Alpha-19.pdf#page=9")]),
    "2023": ("25 bp hike probability, 19.5% at 10:00 and 21.5% at 10:20 ET.", "Powell spoke at 10:05. Across this 20-minute window the expected move rose from +4.88 to +5.38 bp. By 15:00 it was back to +4.88 bp. The initial repricing was half a basis point and had unwound by mid-afternoon.", [("Bespoke market report, p. 16", "https://media.bespokepremium.com/uploads/2023/08/Bespoke-Report-082523-osdurh54f.pdf#page=16")]),
    "2024": ("The reported probability of a 25 bp cut fell 0.5 percentage points before the speech, from 76.5% on 16 August to 76% on 22 August.", "Market participants were already choosing between a 25 and 50 bp cut. Thursday’s probabilities implied 31.00 bp of easing. By Friday afternoon the reported probability of 50 bp was 36.5%, equivalent to 34.13 bp of easing. The additional 3.13 bp spans a prior-day to afternoon interval.", [("16 August futures reading", "https://www.interactivebrokers.com/campus/?p=210471"), ("22 August futures reading", "https://www.interactivebrokers.com/campus/traders-insight/securities/macro/markets-cry-wolf-ahead-of-jackson-hole-powell/"), ("23 August market report", "https://www.marketwatch.com/story/bond-yields-steady-before-pivotal-powell-remarks-297be706")]),
    "2025": ("September cut probability, 75% the day before and 91.5% after the speech.", "The reported probability rose 16.5 percentage points. The report gives the chance of a cut without a complete distribution by size, so the change is displayed in probability points. The interval includes overnight news.", [("Contemporaneous FedWatch reading", "https://www.investopedia.com/fed-chair-powell-keeps-september-rate-cut-on-the-table-11795858")]),
}

def link(label, url):
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'

def signed(number):
    return str(number) if not number else f"{number:+}".replace("-", "−")

def bp(series, key):
    return int((Decimal(str(series[-1][key])) - Decimal(str(series[0][key]))) * 100)

def build():
    curve = json.loads((DATA / "pre-event-curve.json").read_text())
    quotes = [r for r in curve["observations"] if r.get("y2") is not None and r.get("y10") is not None]
    events = {e["url"]: e for e in curve["events"]}
    rows, cards, exported = [], [], []
    previous = None
    for day, score, label, reading, evidence in CASES:
        year = day[:4]
        url = "https://www.federalreserve.gov/newsevents/speech/powell" + day.replace("-", "") + "a.htm"
        event = events[url]
        window = [r for r in quotes if r["date"] < day][-5:]
        assert len(window) == 5 and event["date"] == day
        two, ten = bp(window, "y2"), bp(window, "y10")
        spread = ten - two
        move = None if previous is None else score - previous
        title = date.fromisoformat(day).strftime("%d %b %Y")
        first, last = window[0]["date"], window[-1]["date"]
        prices, interpretation, sources = MARKET[year]
        rows.append(f'<tr><th scope="row">{link(title, "#y" + year)}</th><td>{signed(score)} · {label}</td><td>{signed(move) if move is not None else "—"}</td><td>{signed(two)}</td><td>{signed(ten)}</td><td>{signed(spread)}</td></tr>')
        href = "market-reactions.html?" + urlencode({"curveDate":day, "curveEvent":url}) + "#pre-event-curve"
        links = [link("Federal Reserve transcript", url), link("Inspect daily Treasury observations", href)] + [link(*s) for s in sources]
        price_detail = f"<p>{escape(interpretation)}</p>" if interpretation else ""
        cards.append(f'<section class="es-release" id="y{year}"><div><h3>{year} · {escape(event["title"])}</h3><p><strong>{label} ({signed(score)}).</strong> {escape(reading)}</p><p><q>{escape(evidence)}</q> — Jerome Powell</p><p>{" · ".join(links)}</p></div><div><h4>September meeting pricing</h4><p>{escape(prices)}</p>{price_detail}<small>Prior Treasury closes, {first} to {last}. Speech at {event["time"]} ET.</small></div></section>')
        exported.append([day, event["time"], score, move, label, evidence, url, first, last, window[0]["y2"], window[-1]["y2"], window[0]["y10"], window[-1]["y10"], two, ten, spread, prices, interpretation, " | ".join(x[1] for x in sources)])
        previous = score
    with (DATA / "jackson-hole-stance.csv").open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["speech_date","release_time_ET","speech_score","change_since_prior_symposium","label","evidence","official_speech","prior_window_start","prior_window_end","start_2y_pct","end_2y_pct","start_10y_pct","end_10y_pct","delta_2y_bp","delta_10y_bp","delta_2s10s_bp","next_meeting_pricing","pricing_interpretation","pricing_sources"])
        writer.writerows(exported)
    html = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Powell at Jackson Hole · Central Bank Intelligence</title><meta name="description" content="Five Jackson Hole speeches compared with prior Treasury yields and September meeting pricing."><link rel="icon" href="favicon.svg"><link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="edition.css"><link rel="stylesheet" href="empirical-studies.css"><style>.es-release{grid-template-columns:1.1fr 1fr}.es-release h4{margin:0;font:600 1rem/1.4 Arial,sans-serif}.es-release small{color:#4b5d50}.es-release q{font-family:var(--serif);font-size:1.18rem}.es-wrap article{padding-top:24px}.es-tablewrap table{min-width:630px}@media(max-width:720px){.es-release{grid-template-columns:1fr;gap:8px}}</style><link rel="stylesheet" href="film-edition.css">
<script src="site-index.js" defer></script>
<script src="film-edition.js" defer></script>
</head>
<body class="es-page"><a class="skip-link" href="#main">Skip to content</a><header class="cbi-head film-masthead"><div class="shell cbi-bar"><a class="cbi-name" href="./"><i aria-hidden="true"></i><span>Central Bank Intelligence</span></a><nav aria-label="Primary research" class="film-primary"><a href="market-reactions.html">Market reactions</a><a href="historical-data.html">Policy history</a><a href="macro-history.html">Macro history</a></nav><a href="site-index.html" class="film-index-launch" data-index-open><span class="film-index-symbol" aria-hidden="true"></span>Site index</a></div></header>
<main class="es-wrap" id="main"><h1>Powell at Jackson Hole</h1><p class="es-intro">How much did the next meeting’s price move when the Fed Chair signalled tighter or easier policy? Compare five annual speeches by the same speaker, with dated quotes for the September meeting where available.</p>
<article><h2>Guidance and the curve before the speech</h2><p>The score records Powell’s guidance on interest rates. The change compares consecutive annual symposium speeches. The Treasury columns show moves from the fifth prior close to the last prior close, in basis points. 2s10s is the 10-year yield minus the 2-year yield. A positive change means the curve steepened.</p>
<div class="es-tablewrap" tabindex="0" role="region" aria-label="Speech scores and Treasury curve changes"><table class="es-table"><thead><tr><th scope="col">Speech</th><th scope="col">Rate guidance</th><th scope="col">Annual score change</th><th scope="col">2Y Δ bp</th><th scope="col">10Y Δ bp</th><th scope="col">2s10s Δ bp</th></tr></thead><tbody>""" + "".join(rows) + """</tbody></table></div>
<p><a download href="data/jackson-hole-stance.csv">Download scores, price observations and sources (CSV)</a></p>
<details class="es-detail"><summary>Scoring and pricing conventions</summary><p>These editorial readings use +2 for a clear tightening direction, +1 for conditional tightening, 0 for an explicit wait without a directional commitment, −1 for conditional easing and −2 for a clear easing direction or an explicit commitment to keep rates exceptionally low. A numerical gap counts steps on this ordinal scale. The 2021 score reflects the promised low-rate horizon. The taper discussion concerned a different instrument. Annual comparisons cannot capture intervening speeches.</p><p>September pricing identifies one meeting and one instrument. Where two outcomes exhaust the quoted distribution, their probability-weighted average gives the futures-implied change from the prevailing target. Implied basis points are approximate because reported probabilities are rounded. A rise in the expected rate is hawkish relative to prior pricing. A fall is dovish. Source timestamps determine how closely a move can be associated with the speech. Treasury yields incorporate a wider rate path and term premia.</p><p><a href="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve">US Treasury par yields</a> · <a href="https://www.cmegroup.com/tools-information/quikstrike/cme-fedwatch-tool-user-guide.html">FedWatch methodology</a></p></details></article>
<article><h2>What changed in September pricing?</h2>""" + "".join(cards) + """</article><p><a href="policy-stance.html">Compare FOMC statement scores and meeting surprises</a> · <a href="market-reactions.html#speech-futures">Open the futures comparisons</a></p></main></body></html>"""
    (DIST / "jackson-hole-stance.html").write_text(html)

if __name__ == "__main__":
    build()
