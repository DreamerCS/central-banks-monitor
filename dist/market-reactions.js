const el = id => document.getElementById('mr-' + id);
const controls = Object.fromEntries(['bank','window','asset','year','date'].map(id => [id, el(id)]));
const names = {statement:'Statement', conference:'Press conference', meeting:'Full event'};
const dateLabel = date => new Intl.DateTimeFormat('en-GB', {
  year:'numeric', month:'short', day:'numeric', timeZone:'UTC'
}).format(new Date(date + 'T12:00:00Z'));
const formatted = (value, unit) => {
  if (!Number.isFinite(value)) return '—';
  const magnitude = Math.abs(value).toFixed(unit === 'bp' ? 1 : 2);
  const sign = Number(magnitude) === 0 ? '' : value < 0 ? '−' : '+';
  return sign + magnitude + (unit === 'bp' ? ' bp' : '%');
};

let banks, bank, asset, sample, history, selectedDate;
const params = new URLSearchParams(location.search);
function options(select, choices, preferred) {
  select.replaceChildren(...choices.map(([key,label]) => new Option(label,key)));
  if (choices.some(([key]) => key === preferred)) select.value = preferred;
}
function chooseBank() {
  bank = banks.find(b => b.id === controls.bank.value);
  options(controls.window, Object.keys(bank.windows).map(id => [id,names[id]]), controls.window.value || params.get('window') || 'statement');
  options(controls.asset, bank.assets.map(a => [a.id,a.label]),controls.asset.value || params.get('asset'));
  const years = [...new Set(bank.events.map(e => e.date.slice(0,4)))].reverse();
  options(controls.year,[['all','All years'], ...years.map(y => [y,y])],controls.year.value || params.get('year'));
  update();
}
function update() {
  const year = controls.year.value;
  const window = controls.window.value;
  asset = bank.assets.find(a => a.id === controls.asset.value);
  sample = bank.events.filter(e => (year === 'all' || e.date.startsWith(year)) && e.windows[window]);
  history = sample.filter(e => Number.isFinite(e.windows[window][asset.id]));
  const previous = selectedDate || params.get('date');
  const date = sample.find(e => e.date === previous)?.date || history.at(-1)?.date || sample.at(-1)?.date;
  options(controls.date,[...sample].reverse().map(e => [e.date,dateLabel(e.date)]), date);
  selectedDate = controls.date.value;
  el('title').textContent = asset.label;
  el('unit').textContent = asset.unit === 'bp' ? 'Change in basis points' : 'Return in per cent';
  el('window-note').textContent = bank.windows[window];
  el('series-period').textContent = history.length
    ? bank.name + '   /   ' + dateLabel(history[0].date) + ' – ' + dateLabel(history.at(-1).date)
    : bank.name;
  const source = el('source');
  source.href = bank.source;
  source.textContent = bank.sourceLabel + ' ↗';
  el('credit').textContent = bank.id === 'fed' ? 'Acosta et al. (2025). Yields converted to basis points. Curve slope is the 10Y change minus the 2Y change.' : 'Altavilla et al. Curve slope is the 10Y change minus the 2Y change.';
  const sorted = history.map(e => e.windows[window][asset.id]).sort((a,b) => a-b);
  const quantile = q => {
    if (!sorted.length) return NaN;
    const i = q * (sorted.length-1);
    return sorted[Math.floor(i)] + (sorted[Math.ceil(i)] - sorted[Math.floor(i)]) * (i % 1);
  };
  const metrics = [
    ['Observations', sorted.length], ['Median move', formatted(quantile(.5),asset.unit)],
    ['Middle 50%', sorted.length ? formatted(quantile(.25),asset.unit) + ' to ' + formatted(quantile(.75),asset.unit) : '—']
  ];
  el('metrics').replaceChildren(...metrics.map(([label,value]) => {
    const div = document.createElement('div');
    div.className = 'mr-metric';
    const caption = document.createElement('small');
    const number = document.createElement('strong');
    caption.textContent = label;
    number.textContent = value;
    div.append(caption,number);
    return div;
  }));
  controls.date.disabled = !sample.length;
  el('export').disabled = !sample.length;
  selectEvent();
}
function selectEvent() {
  selectedDate = controls.date.value;
  const event = sample.find(e => e.date === selectedDate);
  const record = event?.windows[controls.window.value] || {};
  el('selected').textContent = event ? dateLabel(event.date) + '   ·   ' + formatted(record[asset.id],asset.unit) : '';
  el('detail-bank').textContent = bank.name + '   /   ' + names[controls.window.value];
  const panels = el('panels');
  panels.replaceChildren();
  for (const group of new Set(bank.assets.map(a => a.class))) {
    const section = document.createElement('div');
    const title = document.createElement('h3');
    title.textContent = group;
    section.append(title);
    for (const item of bank.assets.filter(a => a.class === group)) {
      const value = record[item.id];
      const row = document.createElement('div');
      const label = document.createElement('span');
      const number = document.createElement('span');
      label.textContent = item.label;
      number.textContent = formatted(value,item.unit);
      row.className = 'mr-asset-row';
      number.className = 'mr-value ' + (value > 0 ? 'mr-pos' : value < 0 ? 'mr-neg' : '');
      row.append(label,number);
      section.append(row);
    }
    panels.append(section);
  }
  el('detail-note').textContent = event ? dateLabel(event.date) + ' · ' + names[controls.window.value] + (bank.assets.some(a => !Number.isFinite(record[a.id])) ? ' · — indicates no observation.' : '') : 'No observations in this sample.';
  renderWindowComparison(event);
  drawChart();
}

function renderWindowComparison(event) {
  const section = el('windows');
  section.hidden = !event;
  if (!event) return;
  el('compare-date').textContent = bank.name + ' · ' + dateLabel(event.date);
  const periodKeys = ['statement', 'conference', 'meeting'];
  const fed = bank.id === 'fed';
  const rowIds = fed
    ? ['MP1', 'MP2', 'OIS1Y', 'UST2Y', 'UST10Y', 'EURUSD', 'SP500']
    : ['OIS_1M', 'OIS_1Y', 'DE2Y', 'DE10Y', 'EURUSD', 'STOXX50'];
  if (!rowIds.includes(asset.id)) rowIds.push(asset.id);
  const rows = rowIds.map(id => {
    const item = bank.assets.find(candidate => candidate.id === id);
    if (!item) return null;
    const tr = document.createElement('tr');
    const label = document.createElement('th');
    label.scope = 'row';
    label.textContent = item.label;
    tr.append(label);
    for (const key of periodKeys) {
      const cell = document.createElement('td');
      cell.textContent = formatted(event.windows[key]?.[id], item.unit);
      tr.append(cell);
    }
    return tr;
  }).filter(Boolean);
  el('compare-rows').replaceChildren(...rows);

  const decision = fed && document.querySelector('[data-mr-meeting="' + event.date + '"]');
  const surprise = event.windows.statement?.MP1;
  const intro = el('window-context');
  if (decision && Number.isFinite(surprise)) {
    const action = Number(decision.dataset.action);
    const daily = Number(decision.dataset.daily);
    intro.textContent = 'The Fed ' + (action === 0 ? 'held its target range' : 'moved its target range by ' + formatted(action, 'bp')) +
      '. Current-meeting futures repriced by ' + formatted(surprise, 'bp') +
      ' around the statement. Subtracting that surprise from the decision gives approximately ' +
      formatted(action - surprise, 'bp') + ' priced in beforehand, assuming a stable futures basis. The daily two-year Treasury move was ' + formatted(daily, 'bp') + '.';
  } else {
    intro.textContent = fed
      ? 'Current-meeting futures measure the unexpected part of the announcement. Next-meeting futures and one-year swaps show how pricing farther ahead changed. Longer yields can also reflect inflation compensation and term premia.'
      : 'The one-month euro overnight index swap reflects near-term overnight-rate pricing, including days outside this meeting. It is a proxy for short-rate expectations. The one-year swap captures pricing farther ahead, while German government yields also contain risk premia.';
  }

  const definitions = periodKeys.flatMap(key => {
    const term = document.createElement('dt');
    const definition = document.createElement('dd');
    term.textContent = names[key];
    definition.textContent = bank.windows[key] || 'Window unavailable.';
    return [term, definition];
  });
  el('window-definitions').replaceChildren(...definitions);
  const period = controls.year.value;
  const events = bank.events.filter(candidate => period === 'all' || candidate.date.startsWith(period));
  const direction = value => {
    if (!Number.isFinite(value)) return null;
    const displayed = Math.abs(value).toFixed(asset.unit === 'bp' ? 1 : 2);
    return Number(displayed) === 0 ? 0 : Math.sign(value);
  };
  let pairs = 0;
  let reversals = 0;
  for (const candidate of events) {
    const first = direction(candidate.windows.statement?.[asset.id]);
    const second = direction(candidate.windows.conference?.[asset.id]);
    if (!first || !second) continue;
    pairs++;
    if (first !== second) reversals++;
  }
  const first = direction(event.windows.statement?.[asset.id]);
  const second = direction(event.windows.conference?.[asset.id]);
  const label = asset.label;
  let reading;
  if (first === null || second === null) reading = label + ' has no comparable pair of quoted moves for this meeting. A dash marks an unavailable observation.';
  else if (!first || !second) reading = label + ' was flat at displayed precision in at least one of the two windows.';
  else reading = label + (first !== second
    ? ' moved in opposite directions around the statement and the conference.'
    : ' moved in the same direction around the statement and the conference.');
  const scope = period === 'all' ? 'over the available sample' : 'in ' + period;
  el('window-pattern').textContent = reading + (pairs
    ? ' For this instrument ' + scope + ', ' + reversals + ' of ' + pairs + ' meetings with two nonzero reported moves had opposite signs.'
    : ' There are no meetings with two nonzero reported moves for this instrument ' + scope + '.');
}

function drawChart() {
  const box = el('chart');
  box.replaceChildren();
  if (!history.length) {
    const empty = document.createElement('p');
    empty.className = 'mr-empty';
    empty.textContent = 'No observations for this instrument and period.';
    box.append(empty);
    return;
  }
  const window = controls.window.value;
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS,'svg');
  const width = Math.max(230,box.clientWidth);
  const height = width < 600 ? 222 : 264;
  const left = 49, right = width - 14, top = 16, bottom = height - 34;
  svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
  svg.setAttribute('role','group');
  svg.setAttribute('tabindex','0');
  svg.setAttribute('aria-label', asset.label + ' event changes. Select a meeting with the left and right arrow keys or the meeting list below.');
  const element = (tag, attributes, text) => {
    const node = document.createElementNS(svgNS,tag);
    Object.entries(attributes).forEach(([key,val]) => node.setAttribute(key,val));
    if (text !== undefined) node.textContent = text;
    svg.append(node);
    return node;
  };
  const points = history.map(e => ({date:e.date,time:Date.parse(e.date),value:e.windows[window][asset.id]}));
  const lo = points[0].time, hi = points.at(-1).time;
  const x = time => hi === lo ? (left + right)/2 : left + (right-left)*(time-lo)/(hi-lo);
  const max = Math.max(asset.unit === 'bp' ? 1 : .05,...points.map(p => Math.abs(p.value)));
  const step = 10 ** Math.floor(Math.log10(max));
  const cap = Math.ceil(max / step) * step;
  const y = value => (top+bottom)/2 - value / cap * (bottom-top)/2;
  for (const level of [-cap,0,cap]) {
    element('line',{x1:left,y1:y(level),x2:right,y2:y(level),stroke:level ? '#53645b' : '#a2b2a2','stroke-width':level ? .6 : 1});
    element('text',{x:left-7,y:y(level)+4,'text-anchor':'end'},String(+level.toPrecision(3)));
  }
  const activeIndex = points.findIndex(p => p.date === selectedDate);
  for (const point of points) {
    const colour = point.value >= 0 ? '#b8d4bc' : '#e0a485';
    element('line',{x1:x(point.time),x2:x(point.time),y1:y(0),y2:y(point.value),stroke:colour,'stroke-width':points.length < 40 ? 2 : 1.2});
    element('circle',{cx:x(point.time),cy:y(point.value),r:points.length < 40 ? 3 : 1.7,fill:colour});
  }
  if (activeIndex >= 0) {
    const current = points[activeIndex];
    element('line',{x1:x(current.time),x2:x(current.time),y1:top,y2:bottom,stroke:'#f2d49e','stroke-dasharray':'2 4'});
    element('circle',{cx:x(current.time),cy:y(current.value),r:4.8,fill:'#eadbbd',stroke:'#25332d','stroke-width':1.3});
  }
  const ticks = width < 550 ? 3 : 5;
  const useYear = hi-lo > 2*365*86400000;
  const n = hi === lo ? 1 : ticks;
  for(let i=0; i<n; i++) {
    const when = lo+(hi-lo)*i/Math.max(1,n-1);
    const label = new Date(when).toLocaleDateString('en-GB',useYear ? {timeZone:'UTC',year:'numeric'} : {timeZone:'UTC',month:'short',day:'numeric'});
    element('text',{x:x(when),y:height-8,'text-anchor':i === 0 ? 'start' : i === n-1 ? 'end' : 'middle'},label);
  }
  svg.addEventListener('click',event => {
    const rect = svg.getBoundingClientRect();
    const clickX = (event.clientX-rect.left) / rect.width * width;
    const nearest = points.reduce((a,b) => Math.abs(x(a.time)-clickX) <= Math.abs(x(b.time)-clickX) ? a : b);
    controls.date.value = nearest.date;
    selectEvent();
  });
  svg.addEventListener('keydown',event => {
    if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const i = event.key === 'Home' ? 0 : event.key === 'End' ? points.length-1 : Math.min(points.length-1,Math.max(0,activeIndex+(event.key === 'ArrowLeft' ? -1 : 1)));
    controls.date.value = points[i].date;
    selectEvent();
    el('chart').querySelector('svg').focus({preventScroll:true});
  });
  box.append(svg);
}
function download() {
  const escape = cell => '"' + String(cell ?? '').replaceAll('"','""') + '"';
  const period = controls.window.value;
  const rows = [['bank','event_date','window','window_definition',...bank.assets.map(a => a.label + ' (' + a.unit + ')')],
    ...sample.map(e => [bank.name,e.date,names[period],bank.windows[period],...bank.assets.map(a => e.windows[period][a.id])])];
  const blob = new Blob([rows.map(row => row.map(escape).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = bank.id + '-' + period + '-' + controls.year.value + '.csv';
  a.click();
  setTimeout(() => URL.revokeObjectURL(href),1500);
}
async function init() {
  try {
    const res = await fetch('data/market-events.json');
    if (!res.ok) throw new Error('Data unavailable');
    banks = (await res.json()).banks;
    options(controls.bank,banks.map(b => [b.id,b.name]),params.get('bank'));
    el('load').hidden = true;
    el('explorer').hidden = false;
    chooseBank();
    controls.bank.addEventListener('change',chooseBank);
    for (const id of ['window','asset','year']) controls[id].addEventListener('change',update);
    controls.date.addEventListener('change',selectEvent);
    el('export').addEventListener('click',download);
    let cachedWidth = el('chart').clientWidth;
    new ResizeObserver(() => {
      const newWidth = el('chart').clientWidth;
      if (newWidth === cachedWidth) return;
      cachedWidth = newWidth;
      drawChart();
    }).observe(el('chart'));
  } catch {
    el('explorer').hidden = true;
    el('load').hidden = false;
    el('load').textContent = 'The event data could not be loaded. Refresh to try again.';
  }
}
init();
