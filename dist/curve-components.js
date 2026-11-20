const controls = Object.fromEntries(['group','instrument','window','era','spacing','date'].map(k => [k, document.querySelector('#cc-' + k)]));
const node = (tag, label) => {
  const x = document.createElement(tag);
  if (label !== undefined) x.textContent = label;
  return x;
};
const byId = id => document.querySelector('#cc-' + id);
const dates = new Intl.DateTimeFormat('en-GB', {day:'numeric', month:'short', year:'numeric', timeZone:'UTC'});
const displayDate = date => dates.format(new Date(date + 'T12:00:00Z'));
const signed = x => (x < -0.05 ? '−' : x >= 0.05 ? '+' : '') + Math.abs(x).toFixed(1);
const median = values => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a-b);
  return (sorted[Math.floor((sorted.length-1)/2)] + sorted[Math.floor(sorted.length/2)]) / 2;
};

function correlation(x, y) {
  if (x.length < 2) return null;
  const mean = a => a.reduce((sum, v) => sum + v, 0) / a.length;
  const mx = mean(x), my = mean(y);
  let xy = 0, xx = 0, yy = 0;
  for (let i = 0; i < x.length; i++) {
    const dx = x[i]-mx, dy = y[i]-my;
    xx += dx*dx; yy += dy*dy; xy += dx*dy;
  }
  return xx && yy ? xy / Math.sqrt(xx*yy) : null;
}

function components(window, instrument) {
  const [, , y2, y10, e2, e10, p2, p10] = window;
  const leg = (two, ten) => instrument === 'two' ? two : instrument === 'ten' ? ten : ten - two;
  const observed = leg(y2,y10), expected = leg(e2,e10), premium = leg(p2,p10);
  return {observed, expected, premium, fitted:expected + premium, residual:observed - expected - premium};
}

function initialise(data) {
  const options = ['group','instrument','window','era','spacing'];
  const query = new URLSearchParams(location.search);
  let preferred = query.get('date') || '2023-08-25';
  for (const key of options) {
    if ([...controls[key].options].some(option => option.value === query.get(key))) controls[key].value = query.get(key);
  }
  byId('vintage').textContent = 'Source cutoffs · ACM ' + displayDate(data.modelThrough) + ', Treasury ' + displayDate(data.treasuryThrough) + ', Board speech catalogue ' + displayDate(data.speechesThrough) + '. Site calculations using Adrian, Crump and Moench, “Pricing the Term Structure with Linear Regressions”, Federal Reserve Bank of New York. The model estimates may change with subsequent releases.';
  let use = [];
  function writeURL() {
    const url = new URL(location.href);
    for (const key of options) url.searchParams.set(key, controls[key].value);
    if (controls.date.value) url.searchParams.set('date', controls.date.value);
    url.hash = 'curve-components';
    history.replaceState(history.state, '', url);
  }
  function example() {
    const box = byId('event');
    box.replaceChildren();
    const row = use.find(item => item.r.date === controls.date.value);
    if (!row) return;
    const {r, w, c} = row;
    const name = controls.group.value === 'speeches' ? r.speeches + (r.speeches === 1 ? ' Board speech' : ' Board speeches') : 'FOMC statement';
    const caption = node('p', displayDate(r.date) + ' · ' + name + '. The two closes were ' + displayDate(w[0]) + ' and ' + displayDate(w[1]) + '.');
    caption.className = 'rs-event-label';
    const bars = node('ul');
    bars.className = 'rs-bars';
    const measurements = [['Observed par move',c.observed],['Expected short rates',c.expected],['Term premium',c.premium]];
    const scale = Math.max(1, ...measurements.map(([label, value]) => Math.abs(value)));
    for (const [label, value] of measurements) {
      const li = node('li'), plot = node('div'), bar = node('i');
      plot.className = 'rs-bar';
      plot.setAttribute('aria-hidden','true');
      const width = 50*Math.abs(value)/scale;
      bar.style.width = width + '%';
      bar.style.left = (value < 0 ? 50-width : 50) + '%';
      plot.append(bar);
      li.append(node('span',label), plot, node('output',signed(value) + ' bp'));
      bars.append(li);
    }
    const fit = node('p','The model components sum to ' + signed(c.fitted) + ' bp. The observed move less the fitted move is ' + signed(c.residual) + ' bp. Values are rounded after calculation.');
    const datesLink = node('a','Inspect both Treasury legs for this date');
    datesLink.href = 'market-reactions.html?curveDate=' + r.date + '#pre-event-curve';
    box.append(caption, bars, fit, datesLink);
  }
  function refresh(update) {
    const windowKey = controls.window.value, instr = controls.instrument.value, era = controls.era.value;
    const eligible = data.events.filter(r => {
      const inGroup = controls.group.value === 'speeches' ? r.speeches > 0 : r.statement;
      const year = Number(r.date.slice(0,4));
      return inGroup && (era === 'all' || (year >= Number(era) && year <= Math.min(2026, Number(era) + 9)));
    });
    const matched = eligible.filter(r => r.windows[windowKey]);
    use = [];
    let last = '';
    for (const r of matched) {
      const w = r.windows[windowKey];
      if (controls.spacing.value === 'spaced' && w[0] <= last) continue;
      use.push({r, w, c:components(w,instr)});
      last = w[1];
    }
    const sample = controls.group.value === 'speeches' ? 'distinct Board speech dates' : 'FOMC statement dates';
    const opposing = use.filter(({c}) => c.premium * c.expected < 0).length;
    byId('opposition').textContent = use.length ? 'Expected rates and the term premium moved in opposite directions on ' + opposing + ' of these ' + use.length.toLocaleString('en-GB') + ' dates. On those dates the two components partly offset each other in the fitted change.' : '';
    const coverage = eligible.length ? ' Catalogue range ' + displayDate(eligible[0].date) + ' to ' + displayDate(eligible.at(-1).date) + '.' : '';
    byId('count').textContent = 'Using ' + use.length.toLocaleString('en-GB') + ' of ' + eligible.length.toLocaleString('en-GB') + ' ' + sample + ' · ' + (eligible.length - matched.length) + ' lack matched quote endpoints, ' + (matched.length - use.length) + ' excluded for overlap.' + coverage;
    const values = k => use.map(item => item.c[k]);
    const observed = values('observed'), corr = key => correlation(observed, values(key));
    const larger = use.filter(({c}) => Math.abs(c.premium) > Math.abs(c.expected)).length;
    const metrics = [
      [corr('premium')?.toFixed(2) ?? '—','Correlation of observed changes with the term-premium component'],
      [corr('expected')?.toFixed(2) ?? '—','Correlation of observed changes with the expected-rate component'],
      [use.length ? (100 * larger / use.length).toFixed(1) + '%' : '—','Dates when the term premium moved more than expected rates, in absolute terms']
    ];
    byId('summary').replaceChildren(...metrics.map(([value,label]) => {
      const div = node('div'); div.append(node('strong', value), node('small',label)); return div;
    }));
    const body = byId('distribution');
    body.replaceChildren();
    for (const [key, label] of [['observed','Observed par yield or slope'],['expected','Expected-rate component'],['premium','Term-premium component'],['fitted','ACM fitted move'],['residual','Observed less fitted']]) {
      const vals = values(key), med = median(vals.map(Math.abs));
      const valid = vals.filter((v, i) => v !== 0 && observed[i] !== 0).length;
      const opposite = vals.filter((v, i) => v * observed[i] < 0).length;
      const tr = node('tr'), heading = node('th',label); heading.scope = 'row';
      tr.append(heading, node('td',med === null ? '—' : med.toFixed(2) + ' bp'), node('td',key === 'observed' || key === 'residual' || !valid ? '—' : opposite + ' of ' + valid));
      body.append(tr);
    }
    const previous = preferred;
    controls.date.replaceChildren(...use.slice().reverse().map(({r}) => new Option(displayDate(r.date),r.date)));
    if (use.some(({r}) => r.date === previous)) controls.date.value = previous;
    controls.date.disabled = !use.length;
    preferred = controls.date.value;
    example();
    if (update) writeURL();
  }
  for (const key of options) controls[key].addEventListener('change', () => refresh(true));
  controls.date.addEventListener('change', () => {preferred = controls.date.value; example(); writeURL();});
  refresh(false);
  byId('content').hidden = false;
  byId('status').hidden = true;
}

fetch('data/curve-components.json').then(response => {
  if (!response.ok) throw new Error('data unavailable');
  return response.json();
}).then(initialise).catch(() => {
  byId('status').textContent = 'The Treasury observations could not be loaded. Reload to try again.';
});
