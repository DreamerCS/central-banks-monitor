(() => {
  'use strict';
  const get = (id) => document.getElementById(id);
  const signed = (v) => Number.isFinite(v) ? (v > 0 ? '+' : '') + String(v).replace('-', '−') : '—';
  const bp = (v) => Number.isFinite(v) ? signed(v) + ' bp' : 'Unavailable';
  const descriptions = {
    '-2': 'Easing baseline', '-1': 'Conditional easing', '0': 'Wait / hold',
    '1': 'Conditional tightening', '2': 'Tightening baseline'
  };
  const windows = {
    'before-fixing': 'Released before the Treasury fixing', 'after-fixing': 'Released after the Treasury fixing',
    'time-unknown': 'Release time unknown on trading day', 'non-quote-day': 'No Treasury fixing on speech date',
    'at-fixing': 'Release coincides with Treasury fixing'
  };
  function node(tag, text, cls) {
    const el = document.createElement(tag);
    if (text != null) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  function link(label, url) {
    const el = node('a', label);
    el.href = url;
    return el;
  }
  function field(list, label, value) {
    list.append(node('dt', label), node('dd', value));
  }
  function median(records, key) {
    const values = records.map(r => r.market[key]).filter(Number.isFinite).sort((a,b) => a-b);
    const mid = Math.floor(values.length / 2);
    if (!values.length) return null;
    return values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
  }
  let speeches = [], visible = 20;
  let pricingSource;
  const searchParams = new URLSearchParams(location.search);
  function updateUrl() {
    const params = new URLSearchParams();
    [['chair','leader'],['year','year'],['cycle','cycle'],['status','status'],['search','date']].forEach(([id, key]) => {
      if (get(id).value) params.set(key, get(id).value);
    });
    history.replaceState(null,'', location.pathname + (params.size ? '?' + params : '') + location.hash);
  }
  function fillSummary(rows) {
    const matched = rows.filter(r => r.score !== null && r.market.eligible &&
      (get('window').value !== 'one' || r.market.overnights === 1));
    const easing = matched.filter(r=>r.score<0), tightening = matched.filter(r=>r.score>0);
    const counts = [];
    if (tightening.length) counts.push('Two-year yields rose in ' + tightening.filter(r=>r.market.close2yBp > 0).length + ' of ' + tightening.length + ' tightening readings (median ' + bp(median(tightening,'close2yBp')) + ')');
    if (easing.length) counts.push('Two-year yields fell in ' + easing.filter(r=>r.market.close2yBp < 0).length + ' of ' + easing.length + ' easing readings (median ' + bp(median(easing,'close2yBp')) + ')');
    get('finding').textContent = counts.length ? counts.join('. ') + '. Unchanged yields count in the denominators.' : '';
    const groups = [['Easing', r => r.score < 0],['Wait / hold', r => r.score === 0],['Tightening', r => r.score > 0]];
    const out = get('medians');
    out.replaceChildren();
    groups.forEach(([label, predicate]) => {
      const group = matched.filter(predicate);
      const tr = node('tr');
      const th = node('th', label); th.scope = 'row'; tr.append(th, node('td', group.length));
      if (label === 'Wait / hold' || !group.length) tr.append(node('td', '—'));
      else {
        const direction = label === 'Tightening' ? 1 : -1;
        const same = group.filter(r => Number.isFinite(r.market.close2yBp) && Math.sign(r.market.close2yBp) === direction).length;
        tr.append(node('td', same + ' / ' + group.length));
      }
      ['prior2yBp','priorSlopeBp','close2yBp','closeSlopeBp'].forEach(key => tr.append(node('td', signed(median(group, key)))));
      out.append(tr);
    });
    get('medcaption').textContent = matched.length + ' of ' + rows.filter(r=>r.score!==null).length +
      ' reviewed speeches in the selected chair, cycle and year filters have an eligible interval.';
  }
  function matches(r, mode) {
    if (mode === 'reviewed') return r.score !== null;
    if (mode === 'unscored') return r.score === null;
    if (mode === 'meeting') return !!r.market.meetingPricing;
    if (mode === 'quarter') return !!r.market.quarterPricing;
    if (mode === 'window') return Number.isFinite(r.market.marketBp);
    return true;
  }
  let eventLookup;
  function addMarketLinks(details, refs, url) {
    async function load() {
      if (!details.open) return;
      details.removeEventListener('toggle', load);
      eventLookup ??= Promise.all(['fed-speech-cross-asset-events', 'fed-speech-intraday-assets'].map(async name => {
        try {
          const response = await fetch('data/' + name + '.json');
          if (response.ok) return (await response.json()).records;
        } catch { /* Other source links remain usable. */ }
        return [];
      })).then(groups => {
        const lookup = new Map();
        for (const row of groups.flat()) {
          const key = row.documentUrl || row.sourceUrl;
          if (!lookup.has(key)) lookup.set(key, []);
          lookup.get(key).push(row);
        }
        return lookup;
      });
      for (const row of (await eventLookup).get(url) || []) {
        const q = new URLSearchParams({bank:'fed', stage:row.stage, event:row.id});
        refs.append(link(row.stage === 'speechDaily' ? 'Compare daily market moves' : 'Track intraday currency moves', 'cross-asset-events.html?' + q));
      }
    }
    details.addEventListener('toggle', load);
    if (details.open) load();
  }
  function card(r, open) {
    const m = r.market, details = node('details',null,'fed-card'), heading = node('summary');
    const label = r.score === null ? 'Unscored' : signed(r.score) + ' · ' + descriptions[r.score];
    heading.append(node('strong', r.title), node('span', label, 'sig-badge'));
    heading.append(node('span', r.date + ' · ' + r.leader + ' · ' + r.cycle, 'speech-meta'));
    details.append(heading);
    if (open) details.open = true;
    const dl = node('dl');
    if (r.evidence) details.append(node('p', r.evidence));
    if (r.score === null) field(dl,'Policy evidence',r.status);
    if (r.previousDate) field(dl,'Prior scored speech', r.previousDate + ' · ' + r.daysSincePreviousScore + ' days earlier · score change ' + signed(r.shift));
    if (Number.isFinite(m.prior2yBp)) field(dl,'Prior curve change',m.priorStart + ' → ' + m.priorEnd + ' · 2Y ' + bp(m.prior2yBp) + ' · 10Y ' + bp(m.prior10yBp) + ' · 2s10s ' + bp(m.priorSlopeBp));
    if (Number.isFinite(m.close2yBp)) field(dl,'Across the fixing interval', m.priorEnd + ' → ' + m.closeDate + ' · 2Y ' + bp(m.close2yBp) + ' · 10Y ' + bp(m.close10yBp) + ' · 2s10s ' + bp(m.closeSlopeBp));
    if (m.windowStatus) {
      const flags = [windows[m.windowStatus] || m.windowStatus];
      if (m.timeET) flags.push(m.timeET + ' ET');
      if (m.overlapCount > 1) flags.push(m.overlapCount + ' speeches share the interval');
      if (m.fomcOverlap) flags.push('FOMC decision in interval');
      if (!m.eligible) flags.push('outside median sample');
      field(dl,'Window quality',flags.join(' · '));
    }
    if (Number.isFinite(m.marketBp)) field(dl,'Published short window', bp(m.marketBp) + ' · ' + m.instrument + ' · ' + m.marketWindow);
    if (m.meetingPricing) {
      field(dl,'Meeting pricing',m.meetingPricing.beforeAndAfter);
      field(dl,'What changed',m.meetingPricing.reading);
    }
    if (m.quarterPricing) quarterlyFields(dl,m.quarterPricing);
    const refs = node('div',null,'rs-links');
    refs.append(link('Original Board speech',r.sourceUrl),link('Permalink','?date=' + r.date + '#archive'));
    if (m.timeSource) refs.append(link('FRASER release cover · page 1' + (m.timeEvidence ? ' · ' + m.timeEvidence : ''),m.timeSource));
    if (m.marketSource) refs.append(link('Window source' + (m.marketLocator ? ' · ' + m.marketLocator : ''), m.marketSource));
    if (m.meetingPricing) m.meetingPricing.sources.filter(url => url !== m.marketSource).forEach((url,i) => refs.append(link('Meeting-price source ' + (i+1),url)));
    if (m.quarterPricing && (m.quarterPricing.source || pricingSource)) refs.append(link('SOFR options source', m.quarterPricing.source || pricingSource));
    details.append(dl,refs);
    addMarketLinks(details, refs, r.sourceUrl);
    return details;
  }
  function quarterlyFields(dl, q) {
    field(dl, 'Quarterly SOFR priced before', (q.meanBp / 100).toFixed(3) + '% implied mean as of ' + q.asOf + ' · ' + bp(q.changeBp) + ' since ' + q.fromDate + ' · three-month reference period from ' + q.referenceStart);
    field(dl, 'Implied distribution', q.belowTargetPct + '% below and ' + q.aboveTargetPct + '% above the then-current target range of ' + q.targetRange.replaceAll('bps', ' bp') + '. These options price quarterly average SOFR.');
  }
  function render(reset) {
    if (reset) visible = 20;
    const base = speeches.filter(r => (!get('chair').value || r.leader === get('chair').value) &&
      (!get('cycle').value || r.cycle === get('cycle').value) &&
      (!get('year').value || r.date.startsWith(get('year').value)));
    fillSummary(base);
    const term = get('search').value.trim().toLowerCase();
    const rows = base.filter(r => matches(r, get('status').value) && (!term || (r.date+' '+r.title+' '+r.leader).toLowerCase().includes(term)));
    const events = get('events'); events.replaceChildren(...rows.slice(0,visible).map(r=>card(r,rows.length === 1)));
    get('result').textContent = rows.length ? 'Showing ' + Math.min(visible,rows.length) + ' of ' + rows.length + ' matching speeches.' : 'No speech matches these selections.';
    get('more').hidden = visible >= rows.length;
  }
  async function data(path) {
    const res = await fetch(path);
    if (!res.ok) throw Error('Could not load ' + path);
    return res.json();
  }
  async function start() {
    const [archive, prices] = await Promise.all([data('data/fed-leader-speeches.json'), data('data/fed-speech-markets.json')]);
    const markets = new Map(prices.records.map(r=>[r.url,r]));
    pricingSource = prices.sources.quarterPricing;
    speeches = archive.records.map(r => {
      const m = markets.get(r.sourceUrl);
      if (m && (m.date !== r.date || m.leader !== r.leader)) throw Error('Speech and market identifiers disagree');
      return {...r, market:m || {}};
    }).sort((a,b) => b.date.localeCompare(a.date));
    for (const year of [...new Set(speeches.map(r=>r.date.slice(0,4)))]) get('year').append(new Option(year,year));
    [['chair','leader'],['year','year'],['cycle','cycle'],['status','status'],['search','date']].forEach(([id,key]) => {
      if (searchParams.has(key)) get(id).value = searchParams.get(key);
    });
    render(true);
    for (const id of ['chair','year','cycle','status','window','search']) get(id).addEventListener(id==='search' ? 'input' : 'change',() => { updateUrl();render(true); });
    get('more').addEventListener('click',()=>{visible+=20;render(false);});
  }
  start().catch(()=>{get('result').textContent='The archive could not load. The speech and market data links below remain available.';});
})();
