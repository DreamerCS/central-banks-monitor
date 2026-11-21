"""Render the exchange-rate study as static, linkable HTML, including every comparison."""
from datetime import date
from html import escape

HORIZONS = ("First post-operation quote", "5 further sessions", "20 further sessions")
DISPLAY_ORDER = ("recentBuys", "latestBuys", "earlyBuys", "sells")
LABELS = {
    "recentBuys": "Yen buying, 2022–24",
    "latestBuys": "Yen buying, 2026",
    "earlyBuys": "Yen buying, 1991–98",
    "sells": "Yen selling, 1993–2011"
}


def date_label(iso):
    day = date.fromisoformat(iso)
    return f"{day.day} {day:%b %Y}"


def signed(number):
    return "—" if number is None else f"{number:+.2f}".replace("-", "−")


def cell_quote(quote):
    return f'{quote["yenPerDollar"]:.2f}<small>{date_label(quote["date"])}</small>'


def table(caption, head, body):
    columns = "".join(f'<th scope="col">{col}</th>' for col in head)
    return (f'<div class="yen-scroll" tabindex="0" role="region" aria-label="{escape(caption)}">'
            f'<table><caption>{caption}</caption><thead><tr>{columns}</tr></thead><tbody>{body}</tbody></table></div>')


def row(label, cells):
    return f'<tr><th scope="row">{label}</th>'+ "".join(f'<td>{c}</td>' for c in cells) + '</tr>'


def comparison_rows(event):
    vals = [("Operation", event)] + [(f"Comparison {n+1}", item) for n, item in enumerate(event["controls"])]
    return "".join(row(name, [cell_quote(q) for q in [v["baseline"], *v["quotes"]]]) for name,v in vals)


def details(event):
    first, last = event["first"], event["last"]
    label = date_label(first) if first == last else date_label(first) + " – " + date_label(last)
    opdates = ", ".join(f'{date_label(d)} (¥{v/10000:.4f}tn)' for d,v in event["operations"])
    moves = []
    for horizon, raw, result in zip(HORIZONS, event["moves"], event["outcomes"]):
        cells = [signed(raw), signed(result["matchedExcess"])]
        if not result["clean"]:
            cells = [f"{cell} · excluded" if cell != "—" else cell for cell in cells]
        moves.append(row(horizon, cells))
    matched = (f'{len(event["controls"])} comparison windows selected' if event["controls"]
               else 'Fewer than three suitable non-overlapping windows. No matched result.')
    return (f'<details id="episode-{first}"><summary>{label} <span>¥{event["amount100mYen"]/10000:,.4f}tn</span></summary>'
            f'<p>Tokyo operation dates and amounts were {opdates}.</p>'
            + table("Yen per dollar at New York noon", ["Window", "Baseline", "First after", "+5 sessions", "+20 sessions"], comparison_rows(event))
            + table("Direction-adjusted changes", ["Endpoint", "Observed (log %)", "Excess vs comparisons (log percentage points)"], "".join(moves))
            + f'<p class="yen-note">{matched} · <a href="#episode-{first}">Link to episode</a></p></details>')


def build_results(data):
    rows = []
    for key in DISPLAY_ORDER:
        group = data["groups"][key]
        blocks = []
        for horizon, result in zip(HORIZONS, group["results"]):
            obs, matched = result["observed"], result["matched"]
            def count(r):
                return f'{r["positive"]} / {r["ties"]} / {r["n"]-r["positive"]-r["ties"]}'
            blocks.append(row(horizon, [str(obs["n"]), signed(obs["median"]), count(obs), str(matched["n"]),
                                        signed(result["matchedObservedMedian"]), signed(matched["median"]), count(matched)]))
        rows.append(table(f'{LABELS[key]} · {group["episodes"]} episodes', [
            "Endpoint", "Clean N", "Median move<br>(log %)", "Up / tied / down¹",
            "Matched N", "Matched raw median<br>(log %)", "Median excess<br>(log pp)", "Above / tied / below²"
        ], "".join(blocks)))
    return "".join(rows)


def example(data):
    selected = [e for e in data["episodes"] if e["first"] in ("2024-04-29", "2024-07-11")]
    return table("The two 2024 yen purchases",["Operation dates", "Before", "First after", "+20 sessions",
                        "First move (log %)", "+20 move (log %)"],
                 "".join(row(f'<a href="#episode-{e["first"]}">{date_label(e["first"])} – {date_label(e["last"])}</a>',
                             [cell_quote(e["baseline"]),cell_quote(e["quotes"][0]),cell_quote(e["quotes"][2]),
                              signed(e["moves"][0]),signed(e["moves"][2])]) for e in selected))


def render(data):
    episodes = data["episodes"]
    outlines = []
    for key in DISPLAY_ORDER:
        listings = "".join(details(e) for e in reversed(episodes) if e["group"] == key)
        outlines.append(f'<section aria-labelledby="ledger-{key}"><h3 id="ledger-{key}">{LABELS[key]}</h3>{listings}</section>')
    navigation = " · ".join(f'<a href="#ledger-{k}">{LABELS[k]}</a>' for k in DISPLAY_ORDER)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Compare Japan’s yen interventions with similar periods without intervention using official operations and New York noon quotes.">
<title>What follows Japan’s yen interventions? · Central Bank Intelligence</title>
<link rel="icon" href="favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="edition.css"><link rel="stylesheet" href="yen-intervention.css">
<link rel="stylesheet" href="film-edition.css">
<script src="site-index.js" defer></script>
<script src="film-edition.js" defer></script>
</head><body><a class="skip-link" href="#main">Skip to content</a>
<header class="cbi-head film-masthead"><div class="shell cbi-bar"><a class="cbi-name" href="./"><i aria-hidden="true"></i><span>Central Bank Intelligence</span></a><nav aria-label="Primary research" class="film-primary"><a href="market-reactions.html">Market reactions</a><a href="historical-data.html">Policy history</a><a href="macro-history.html">Macro history</a></nav><a href="site-index.html" class="film-index-launch" data-index-open><span class="film-index-symbol" aria-hidden="true"></span>Site index</a></div></header>
<main class="yen-main" id="main"><a href="empirical-studies.html">← Empirical studies</a>
<h1>What follows Japan’s yen interventions?</h1>
<p class="yen-lead">Japan bought yen in four episodes in 2022–24. In each one the currency strengthened by the first New York noon quote after the final operation. The April 2024 gain almost disappeared a month later. The July gain grew.</p>
<p>From April 1991 through September 2026, Japan’s Ministry of Finance recorded {data['operations']} yen–dollar operation dates. Grouping nearby actions produces {len(episodes)} episodes. Three comparable periods without intervention were available for {sum(bool(e["controls"]) for e in episodes)} of them.</p>
<nav class="yen-jumps" aria-label="On this page"><a href="#episodes-2024">Two 2024 paths</a><a href="#results">Results by direction</a><a href="#method">Method and sources</a><a href="#ledger">All episode dates</a></nav>
<section id="episodes-2024"><h2>Two purchases, two paths</h2>
<p>The Ministry bought ¥9.7885 trillion across 29 April and 1 May. Twenty sessions after the first post-operation quote, the yen had retained only 0.27 log percentage points of its 2.47-point initial gain. In July, a smaller ¥5.5348 trillion purchase was followed by a 9.18-point gain over the longer window. Lower yen per dollar means a stronger yen.</p>
{example(data)}
</section><section id="results"><h2>What survives comparison with other periods?</h2>
<p>For 2022–24, the median first-quote appreciation was 1.86 log %. It exceeded the average change in the three matched periods by a median 1.33 log percentage points. The early sales give a different comparison. Across 51 episodes, the median first move was 0.56 log % in the intended direction. Among the 33 episodes with matches, the median observed move was +0.20 and the median excess was −0.09 log percentage points.</p>
{build_results(data)}
<p class="yen-note">¹ Up means movement in the direction of intervention. ² Above means a larger move in that direction than the mean of three comparison periods. Counts classify changes at 0.01 log percentage point precision. The observed column uses all clean episodes and the excess column uses the matched subset. A later operation removes the affected endpoint. Each median gives every included episode equal weight.</p>
</section><section id="method"><h2>How to read the comparison</h2>
<p>Does the yen keep moving in the direction of an official purchase or sale after the initial market response? Compare the first available exchange rate after each episode with later quotes and with periods that began under similar market conditions.</p>
<ol>
<li><strong>Cluster the transactions.</strong> Combine successive yen–dollar operations in the same direction when no more than five New York FX observation sessions separate them. Keep the Japanese Ministry of Finance’s original unit of ¥100 million in the downloadable data. The yen amounts on this page sum the published daily figures. The amount comparison excludes {data['otherCurrencyOperations']} other-currency records. All Ministry operations can trigger an exclusion.</li>
<li><strong>Align the two clocks.</strong> The Ministry gives Japanese operation dates. The Federal Reserve’s H.10 series gives New York noon buying rates in yen per US dollar. The baseline is the last observed noon strictly before the first operation date. The first endpoint is the first observed noon strictly after the last operation date. Count another five and twenty observed FX sessions from that endpoint. All changes start from the original baseline. The window includes other news during the episode. Intraday intervention prices are unavailable.</li>
<li><strong>Orient the sign.</strong> Calculate 100 times the natural log of the endpoint divided by the baseline. Reverse the sign for purchases of yen. Positive values therefore mean the currency moved in the announced direction. Drop a horizon from the summary whenever another Ministry action took place after the final operation and on or before that horizon’s noon quote date. The ledger retains excluded observations for inspection.</li>
<li><strong>Find comparable windows.</strong> Use the same number of FX sessions over the episode. Candidate baselines fall within 731 calendar days of the actual baseline and must have the same Bank of Japan framework at the start of the lookback, baseline, first endpoint and last follow-up. Exclude every candidate with a Ministry intervention from 20 sessions before its baseline through its final follow-up. Compare prior 20-session FX change, daily FX volatility and the US two-year Treasury yield change in basis points. For yields use the latest available observation on or before each endpoint, up to five calendar days old.</li>
<li><strong>Pick three controls.</strong> Scale each difference by its standard deviation across eligible windows for that episode. Drop candidates beyond 1.5 standard deviations on any feature. In order of smallest Euclidean distance, select three whose observation spans, including the lookback, do not overlap each other. Controls can be reused across episodes. Excess is the observed signed change less the mean signed change in that episode’s three controls. If three suitable periods cannot be found, only the observed move enters the summary.</li>
</ol>
<p>The policy-framework screen allows comparison within the same broad Japanese monetary arrangements. It does not control for contemporaneous US or Japanese announcements, volatility after intervention, changing policy settings within a framework, or the authorities’ private reasons for acting. Small cohorts, control reuse and repeated actions limit inference. A move in the intended direction cannot establish that intervention caused it.</p>
<p>Official sources include the <a href="https://www.mof.go.jp/english/policy/international_policy/reference/feio/index.html">Ministry of Finance intervention releases</a> · <a href="{escape(data['sources']['operations.csv'])}">Historical operations CSV</a> · <a href="https://fred.stlouisfed.org/series/DEXJPUS">Federal Reserve H.10 yen per dollar</a> · <a href="https://fred.stlouisfed.org/series/DGS2">Federal Reserve H.15 two-year Treasury yield</a> · <a href="https://www.boj.or.jp/en/mopo/outline/bpreview/ref.htm">Bank of Japan framework chronology</a> · <a href="https://www.boj.or.jp/en/mopo/outline/ref_qqe.htm">QQE, yield-curve control and the March 2024 transition</a>.</p>
</section><section id="ledger"><h2>Inspect the {len(episodes)} episodes</h2><p>Expand an episode for all operation dates, amounts, exact exchange-rate observations and selected comparison periods. Amounts are in trillions of yen. <a href="data/yen-intervention.json" download>Download episode data (JSON)</a>.</p>
<nav class="yen-jumps" aria-label="Episode groups">{navigation}</nav>{''.join(outlines)}
</section></main><script src="yen-intervention.js" defer></script></body></html>
"""
