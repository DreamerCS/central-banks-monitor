"""Rebuild the reviewed ECB speech panel.

Usage: python scripts/build-ecb-speech-stance.py /path/to/all_ECB_speeches.csv /path/to/Dataset_EA-EMPD.xlsx
The ECB publishes the pipe-delimited full texts and the extended event workbook separately.
"""
import argparse
import bisect
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from html import escape
from pathlib import Path
from statistics import median

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
DATA = DIST / 'data'
LEADERS = [('2000-01-01', 'Duisenberg'), ('2003-11-01', 'Trichet'), ('2011-11-01', 'Draghi'), ('2019-11-01', 'Lagarde')]
LABELS = {-2:'Explicit accommodation or easing',-1:'Conditional easing',0:'Current setting appropriate',1:'Conditional tightening',2:'Explicit tightening'}
PEAK_TROUGH = [('2008Q1','2009Q2'),('2011Q3','2013Q1'),('2019Q4','2020Q2')]
WORKBOOK = 'https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx'
TEXTS = 'https://www.ecb.europa.eu/press/key/html/downloads.en.html'
CHRONOLOGY = 'https://eabcn.org/dbc/peaksandtroughs/chronology-euro-area-business-cycles'
FIELDS = ['speech_id','event_time','president','cycle','speaker','title','text_score','evidence','reason','transcript','ois_1m_bp','ois_1y_bp','de_2s10s_change_bp','conditions','earlier_scored_speech','score_change']


def norm(text):
    plain = unicodedata.normalize('NFKD',text or '').encode('ascii','ignore').decode().lower()
    return re.sub('[^a-z0-9]', '', plain)


def key(day, speaker, title):
    return day, norm(speaker), norm(title)


def phase(day):
    quarter = day[:4] + 'Q' + str((int(day[5:7]) - 1) // 3 + 1)
    return 'Dated contraction' if any(p < quarter <= t for p,t in PEAK_TROUGH) else 'Outside dated contraction'


def read_inputs(csv_path, book_path):
    with csv_path.open(encoding='utf8', newline='') as stream:
        texts = defaultdict(list)
        for row in csv.DictReader(stream,delimiter='|',quoting=csv.QUOTE_NONE):
            texts[key(row['date'],row['speakers'],row['title'])].append(row['contents'])
    book = load_workbook(book_path,read_only=True,data_only=True)
    try:
        source = book['EA-EMPD'].values
        headers = next(source)
        events = [dict(zip(headers,row)) for row in source]
    finally:
        book.close()
    return texts,events


def build(csv_path,book_path):
    texts, events = read_inputs(csv_path,book_path)
    reviews = json.loads((ROOT / 'scripts/ecb-speech-readings.json').read_text())
    review = {key(r['date'],r['speaker'],r['title']):r for r in reviews}
    observed = Counter()
    speech_events = sorted((r for r in events if r['Event_type'] in ('P','EB') and r['Date_time'].date() >= date(2000,1,1)),key=lambda r:r['Date_time'])
    times = sorted(r['Date_time'] for r in speech_events)
    meetings = {r['Date_time'].date() for r in events if str(r['Event_type']).startswith('GC_')}
    identity_counts = Counter(key(r['Date_time'].date().isoformat(),r['Speaker'],r['Title']) for r in speech_events)
    rows,previous = [],{}
    for r in speech_events:
        stamp = r['Date_time']
        day = stamp.date().isoformat()
        speaker = ' '.join(r['Speaker'].split())
        title = ' '.join((r['Title'] or '').split())
        k = key(day,speaker,title)
        corpus = texts.get(k,[])
        if len(corpus) != 1 or identity_counts[k] != 1 or not corpus[0].strip():
            continue
        leader = next(name for start,name in reversed(LEADERS) if day >= start)
        label = review.get(k,{})
        excerpt = label.get('excerpt')
        if excerpt:
            if excerpt not in ' '.join(corpus[0].split()):
                raise ValueError('The reviewed passage changed: '+day+' '+speaker)
            observed[k] += 1
        score = label.get('score')
        prior = previous.get(speaker) if score is not None else None
        dt = stamp.isoformat(timespec='minutes')
        token = hashlib.sha256((dt+'|'+speaker+'|'+title).encode()).hexdigest()[:10]
        # Two event windows can share quotes if their assumed 70-minute spans overlap.
        n = bisect.bisect_left(times,stamp+timedelta(minutes=70))-bisect.bisect_right(times,stamp-timedelta(minutes=70))
        cautions = []
        if r['Non_regular_trading_day'] or r['Outside_regular_trading_hours']:cautions.append('Outside trading session')
        if n > 1:cautions.append('Another speech window overlaps')
        if stamp.date() in meetings:cautions.append('Governing Council meeting day')
        if r['OIS_1Y'] is None:cautions.append('1Y OIS missing')
        s2,s10=r['DE2Y'],r['DE10Y']
        rows.append(dict(speech_id=token,event_time=dt,president=leader,cycle=phase(day),speaker=speaker,title=title,
                         text_score=score,evidence=excerpt,transcript=label.get('url'),ois_1m_bp=r['OIS_1M'],ois_1y_bp=r['OIS_1Y'],
                         de_2s10s_change_bp=round(s10-s2,5) if isinstance(s2,(int,float)) and isinstance(s10,(int,float)) else None,
                         conditions=' · '.join(cautions),reason=label.get('reason'),earlier_scored_speech=prior[0] if prior else None,
                         score_change=score-prior[1] if prior else None))
        if score is not None:previous[speaker]=(day,score)
    if set(observed) != set(review):
        missing=[(r['date'],r['speaker']) for r in reviews if key(r['date'],r['speaker'],r['title']) not in observed]
        raise ValueError('Unmatched reviewed cases: '+str(missing))
    with (DATA/'ecb-speech-stance.csv').open('w', newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS,extrasaction='ignore',lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    return rows,speech_events


def signed(x):
    return '—' if x is None else f'{x:+.2f}'.replace('-', '−') if x else '0.00'


def stats(rows,band=1):
    clean=[r for r in rows if r['text_score'] is not None and not r['conditions']]
    direct=[r for r in clean if r['text_score']]
    moving=[r for r in direct if abs(r['ois_1y_bp']) > band+1e-9]
    same=sum(r['text_score'] * r['ois_1y_bp']>0 for r in moving)
    return len(clean),len(direct),len(direct)-len(moving),same,len(moving)-same


def group_table(rows, keyname):
    groups=defaultdict(list)
    for r in rows:groups[r[keyname]].append(r)
    if keyname=='speaker':groups={k:v for k,v in groups.items() if any(r['text_score'] is not None for r in v)}
    body=[]
    for name,group in (sorted(groups.items()) if keyname=='speaker' else groups.items()):
        n=sum(r['text_score'] is not None for r in group)
        eligible,_,flat,same,opposite=stats(group)
        med=median(r['ois_1y_bp'] for r in group if r['text_score'] is not None and not r['conditions']) if eligible else None
        body.append('<tr><th scope="row">'+escape(name)+'</th>'+''.join(f'<td>{s}</td>' for s in [len(group),n,eligible,signed(med),flat,same,opposite])+'</tr>')
    return '<div class="es-tablewrap" tabindex="0" role="region" aria-label="Grouped speech results"><table class="es-table"><thead><tr><th>Group</th><th>Matched texts</th><th>Scored</th><th>Eligible scored</th><th>Median 1Y (bp)</th><th>Within ±1 bp</th><th>Same sign</th><th>Opposite sign</th></tr></thead><tbody>'+''.join(body)+'</tbody></table></div>'


def render(rows,events):
    reviewed=[r for r in rows if r['evidence']]
    scored=[r for r in reviewed if r['text_score'] is not None]
    eligible,directional,flat,same,opposite=stats(rows)
    sensitivity=[]
    for band in (0,1,2):
        _,_,quiet,agree,oppose=stats(rows,band)
        sensitivity.append(f'<tr><th scope="row">±{band} bp</th><td>{quiet}</td><td>{agree}</td><td>{oppose}</td></tr>')
    distributions=[]
    for s in [-2,-1,0,1,2]:
        gp=[r for r in scored if r['text_score']==s and not r['conditions']]
        med=median(r['ois_1y_bp'] for r in gp) if gp else None
        distributions.append(f'<tr><th scope="row">{s:+d} · {LABELS[s]}</th><td>{len(gp)}</td><td>{signed(med)}</td></tr>')
    by_year = defaultdict(list)
    for r in reversed(reviewed):
        score=r['text_score']; dif=r['score_change']
        status='Unscored' if score is None else f'{score:+d} · {LABELS[score]}'
        movement=('No prior scored speech in this sample.' if dif is None else f'{dif:+d} rubric steps since {r["earlier_scored_speech"]}, the previous scored speech by this speaker.')
        market = 'Excluded from group statistics · '+r['conditions'] if r['conditions'] else 'Included in regular-session comparison.'
        if score is None:market='No rate-path score for the sign comparison.'+(' '+r['conditions']+'.' if r['conditions'] else '')
        href=f'market-reactions.html?ecbSpeech={r["speech_id"]}#ecb-speech-windows'
        subtitle=' · '.join(escape(r[k]) for k in ['event_time','speaker','cycle'])
        year = r['event_time'][:4]
        eligible_case = 'yes' if score is not None and not r['conditions'] else 'no'
        by_year[year].append(f'<article class="speech-case" id="speech-{r["speech_id"]}" data-eligible="{eligible_case}" data-date="{r["event_time"][:10]}" data-leader="{escape(r["president"])}" data-speaker="{escape(r["speaker"])}" data-cycle="{escape(r["cycle"])}"><p class="meta">{subtitle}</p><h3>{escape(r["title"])}</h3><p><strong>{status}.</strong> {escape(r["reason"] or movement)}</p><blockquote>{escape(r["evidence"])}</blockquote><p><strong>1Y OIS {signed(r["ois_1y_bp"])} bp</strong> · 1M OIS {signed(r["ois_1m_bp"])} bp · German 2s10s {signed(r["de_2s10s_change_bp"])} bp</p><p class="meta">{escape(market)}</p><p><a href="{escape(r["transcript"],quote=True)}">ECB transcript</a> · <a href="{href}">Inspect the event window</a> · <a href="cross-asset-events.html?bank=ecb&amp;stage=speech&amp;event=ecb-speech-{r["speech_id"]}">Compare markets during this speech</a></p></article>')
    first_year = next(iter(by_year), None)
    shelves = ''.join(
        f'<details class="speech-year"{" open" if year == first_year else ""}><summary>{year} reviewed speeches</summary>{"".join(year_cards)}</details>'
        for year, year_cards in by_year.items()
    )
    def select(field,title,values):
        options=''.join(f'<option>{escape(x)}</option>' for x in values)
        return f'<label>{title}<select id="{field}"><option value="">All</option>{options}</select></label>'
    options=select('leader','Presidential term',[v for _,v in LEADERS])+select('speaker','Speaker',sorted({r['speaker'] for r in reviewed}))+select('cycle','Economic cycle',['Dated contraction','Outside dated contraction'])
    counts=f'{len(events):,} communication windows · {len(rows):,} matched full texts · {len(scored)} scored speeches · {len({r["speaker"] for r in scored})} speakers with a score'
    page=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ECB speeches and one-year OIS · Central Bank Intelligence</title><link rel="icon" href="favicon.svg"><link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="edition.css"><link rel="stylesheet" href="empirical-studies.css"><style>[hidden]{{display:none!important}}.speech-case{{padding:1.2rem 0;border-top:1px solid #b8beaf}}.speech-case h3{{margin-top:0}}.speech-case blockquote{{border-left:2px solid #81674e;padding-left:1rem;margin:1rem 0;font:1.16rem/1.5 var(--serif);max-width:72ch}}.meta{{color:#4f5b4f;font-size:.92rem}}.speech-columns{{display:grid;grid-template-columns:1fr 1fr;gap:2rem}}.speech-columns h3{{margin-top:0}}.es-tablewrap table{{min-width:500px}}.es-controls label{{display:grid;gap:.35rem}}.es-controls select{{max-width:100%;font:inherit;padding:.35rem}}.es-wrap section{{margin-top:2.2rem}}.speech-columns .es-tablewrap table{{min-width:320px}}@media(max-width:700px){{.speech-columns{{grid-template-columns:1fr;gap:0}}}}.review-choice {{display: grid;gap:.35rem;max-width:50rem;font-size:1rem;font-weight:600}}.review-choice select {{display:block;max-width:100%;width:100%;min-width:0;min-height:44px;padding:.4rem .7rem;font:inherit;font-weight:400;color:var(--ink);background:var(--paper);border:1px solid var(--line)}}.speech-year>summary {{cursor:pointer;padding:.65rem 0;font-weight:600}}.review-reader .speech-year>summary {{display:none}}.speech-case {{max-width:78ch}}.es-wrap #evidence .speech-case h3 {{font-size:clamp(1.65rem,3.6vw,2.6rem)}}.es-wrap #terms .es-detail {{margin-top:0;padding:.75rem 0}}.es-controls select {{min-height:42px}}.es-wrap #matches {{color:var(--muted);margin-top:.55rem}}.review-choice select:focus-visible,.speech-year>summary:focus-visible {{outline:2px solid var(--ink);outline-offset:2px}}</style><link rel="stylesheet" href="film-edition.css">
<script src="site-index.js" defer></script>
<script src="film-edition.js" defer></script>
</head><body class="es-page"><a class="skip-link" href="#main">Skip to content</a>
<header class="cbi-head film-masthead"><div class="shell cbi-bar"><a class="cbi-name" href="./"><i aria-hidden="true"></i><span>Central Bank Intelligence</span></a><nav aria-label="Primary research" class="film-primary"><a href="market-reactions.html">Market reactions</a><a href="historical-data.html">Policy history</a><a href="macro-history.html">Macro history</a></nav><a href="site-index.html" class="film-index-launch" data-index-open><span class="film-index-symbol" aria-hidden="true"></span>Site index</a></div></header>
<main id="main" class="es-wrap"><h1>ECB speeches and one-year OIS</h1><p class="es-intro">When a policymaker signals tightening, does the market raise its expected rate path? Compare what ECB presidents and Executive Board members said with the change in euro overnight index swap rates during their speaking windows. The source includes parliamentary testimony as well as addresses.</p><nav class="es-tabs" aria-label="Study sections"><a href="#findings">Market results</a><a href="#evidence">Read the speeches</a><a href="#terms">Presidents and economic cycles</a><a href="cross-asset-events.html?bank=ecb&amp;stage=speech">Cross-asset speech windows</a><a href="#method">Method and data</a></nav>
<section id="findings"><h2>How often did the two agree?</h2><p>{eligible} scored speeches had a one-year OIS quote in regular trading hours on a non-meeting day with no overlapping ECB speaker window. Of these, {directional} signalled directional policy guidance. One-year OIS moved by at most 1 bp in {flat}. Among the remaining {same+opposite}, the sign of the OIS move agreed with the text in {same} and pointed the other way in {opposite}.</p><div class="speech-columns"><div><h3>OIS moves by guidance</h3><div class="es-tablewrap"><table class="es-table"><thead><tr><th>Wording</th><th>Eligible events</th><th>Median 1Y (bp)</th></tr></thead><tbody>{''.join(distributions)}</tbody></table></div></div><div><h3>How the threshold matters</h3><div class="es-tablewrap"><table class="es-table"><thead><tr><th>1Y band</th><th>Within band</th><th>Same sign</th><th>Opposite sign</th></tr></thead><tbody>{''.join(sensitivity)}</tbody></table></div></div></div></section>
<section id="evidence"><h2>Read the speeches</h2><p>A speaker can repeat a Council position or express an individual view. The excerpt records the guidance delivered in the speech. The score change counts rubric steps since that speaker’s previous scored appearance in this sample. Intervening unscored speeches may contain additional information.</p><div id="filters" hidden><div class="es-controls">{options}</div><label class="review-choice">Reviewed speech<select id="speech-choice"></select></label></div><p id="matches" aria-live="polite"></p><div id="speech-reader">{shelves}</div></section>
<section id="terms"><h2>Presidents and economic cycles</h2><p>Each term includes the entire Executive Board. Counts show how much language and market evidence underlies each comparison. The last three columns count directional guidance only. The median uses all eligible scores, including speeches endorsing the current setting.</p><details class="es-detail"><summary>Compare presidential terms</summary>{group_table(rows,'president')}</details><details class="es-detail"><summary>Euro area business cycle</summary><p>Contractions follow the CEPR–EABCN quarterly chronology from the quarter after a peak through the trough. These retrospective dates were published with a lag. Only {sum(r["cycle"]=="Dated contraction" for r in scored)} of the {len(scored)} scores fall in a dated contraction, which limits inference about cyclical differences.</p>{group_table(rows,'cycle')}</details><details class="es-detail"><summary>Compare individual speakers</summary>{group_table(rows,'speaker')}</details></section>
<section id="method"><h2>Method and data</h2><p><strong>{counts}</strong></p><p>Coverage runs from {events[0]['Date_time'].date()} to {events[-1]['Date_time'].date()}. Dates, single-speaker names and full titles must match uniquely across the two ECB datasets after normalising case, punctuation and diacritics. The download includes every full-text match. A blank score means the record has no assigned reading. We selected and reviewed explicit policy passages before comparing their market moves. Selection favours recognisable English rate guidance, particularly the years of repeated low-rate commitments. The sample cannot establish which president was most hawkish.</p><p>+2 signals explicit tightening, +1 conditional tightening, 0 endorsement of the current setting, −1 conditional easing and −2 explicit easing or a commitment to prolonged accommodation. Hypothetical examples, past decisions and tools without a rate direction do not by themselves earn a score. Earlier scores are ordinal. They cannot be converted into basis points.</p><p>The ECB workbook compares median quotes 20–10 minutes before a speech begins with quotes 10–20 minutes after an assumed 30-minute speech ends. Positive OIS moves indicate higher market pricing at that tenor relative to the prespeech quote. One-year OIS reflects expected overnight rates over a year and a risk premium. The workbook publishes the change, so the level priced before a speech and individual-meeting probabilities remain unavailable from this source. German 2s10s is the ten-year yield minus the two-year yield. Unscheduled news can also move rates in the interval.</p><p><a href="data/ecb-speech-stance.csv" download>Download all matched speeches and market observations (CSV)</a> · <a href="{TEXTS}">ECB full texts</a> · <a href="{WORKBOOK}">ECB extended event-study workbook</a> · <a href="{CHRONOLOGY}">Euro area business-cycle chronology</a></p></section></main>
<script>
const selectors = ['leader','speaker','cycle'].map(id => document.getElementById(id));
const reader = document.getElementById('speech-reader');
const years = [...reader.querySelectorAll('.speech-year')];
const speeches = [...reader.querySelectorAll('.speech-case')];
const choice = document.getElementById('speech-choice');
const status = document.getElementById('matches');

function showSpeech(speech) {{
  for (const item of speeches) item.hidden = item !== speech;
  for (const year of years) {{
    year.hidden = !speech || !year.contains(speech);
    if (!year.hidden) year.open = true;
  }}
  choice.value = speech?.id || '';
}}

function restoreSpeeches() {{
  const url = new URL(location.href);
  for (const input of selectors) {{
    const value = url.searchParams.get(input.id);
    input.value = [...input.options].some(option => option.value === value) ? value : '';
  }}
  const matches = speeches.filter(item => selectors.every(input => !input.value || item.dataset[input.id] === input.value));
  choice.replaceChildren();
  let group;
  for (const item of matches) {{
    const year = item.dataset.date.slice(0, 4);
    if (!group || group.label !== year) {{
      group = document.createElement('optgroup');
      group.label = year;
      choice.append(group);
    }}
    group.append(new Option(item.dataset.date + ' · ' + item.dataset.speaker + ' · ' + item.querySelector('h3').textContent, item.id));
  }}
  const requested = url.hash.startsWith('#speech-') ? url.hash.slice(1) : 'speech-' + (url.searchParams.get('speech') || '');
  const selected = matches.find(item => item.id === requested) || matches.find(item => item.dataset.eligible === 'yes') || matches[0];
  choice.disabled = !matches.length;
  status.textContent = matches.length === 1 ? '1 reviewed speech' : matches.length + ' reviewed speeches';
  if (!matches.length) status.textContent = 'No reviewed speeches match these filters.';
  showSpeech(selected);
}}

for (const input of selectors) {{
  input.addEventListener('change', () => {{
    const url = new URL(location.href);
    if (input.value) url.searchParams.set(input.id, input.value);
    else url.searchParams.delete(input.id);
    url.searchParams.delete('speech');
    if (url.hash.startsWith('#speech-')) url.hash = 'evidence';
    history.replaceState(null, '', url);
    restoreSpeeches();
  }});
}}
choice.addEventListener('change', () => {{
  const url = new URL(location.href);
  url.searchParams.set('speech', choice.value.slice(7));
  if (url.hash.startsWith('#speech-')) url.hash = 'evidence';
  history.replaceState(null, '', url);
  showSpeech(document.getElementById(choice.value));
}});
window.addEventListener('popstate', restoreSpeeches);
window.addEventListener('hashchange', restoreSpeeches);
reader.classList.add('review-reader');
document.getElementById('filters').hidden = false;
restoreSpeeches();
</script></body></html>'''
    (DIST/'ecb-speech-stance.html').write_text(page)
    print(counts, '; eligible, directional, flat, same, opposite:',stats(rows))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('speeches',type=Path);parser.add_argument('workbook',type=Path)
    args=parser.parse_args()
    render(*build(args.speeches,args.workbook))
