const get = id => document.getElementById(id);
const make = (tag, text) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  return element;
};
const anchor = (label, url) => {
  const link = make('a', label);
  link.href = url;
  return link;
};
const readJSON = async file => {
  const response = await fetch('data/' + file);
  if (!response.ok) throw new Error('Data unavailable');
  return response.json();
};
const niceDate = iso => new Date(iso + 'T12:00:00Z').toLocaleDateString('en-GB',
  {year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC'});
const areaName = name => name === 'Czech Republic' ? 'Czechia' : name;
const caseKey = item => item.date + '-' + areaName(item.area).toLowerCase().replace(/[^a-z0-9]+/g, '-');
const number = new Intl.NumberFormat('en-GB', {maximumFractionDigits: 2, minimumFractionDigits: 2});
const signed = value => (value > 0 ? '+' : '') + number.format(value);
const fmt = (value, change) => value == null ? '—' : change ? signed(value) : number.format(value);
const regionSelect = get('yb-region');
const indexSelect = get('yb-case-index');
let cases, data, selected, years, mainCase;
function yearURL(year, item) {
  const url = new URL(location.href);
  url.searchParams.set('historyYear', year);
  if (item) url.searchParams.set('case', item);
  else url.searchParams.delete('case');
  url.hash = '';
  return url;
}
function card(record) {
  const article = make('article');
  article.className = 'yb-card';
  article.id = caseKey(record);
  const meta = make('p', areaName(record.area) + '  ·  ' + niceDate(record.date));
  meta.className = 'yb-meta';
  const title = make('h3', record.title);
  const columns = make('div');
  columns.className = 'yb-columns';
  const follow = make('div');
  follow.className = 'yb-follow';
  follow.append(make('h4', 'Evidence and interpretation'), make('p', record.test));
  columns.append(make('p', record.analysis), follow);
  const sources = make('div');
  sources.className = 'yb-sources';
  for (const source of record.sources) sources.append(anchor(source.label, source.url));
  article.append(meta, title, columns, sources);
  return article;
}
function studies(year) {
  const nav = get('yb-studies');
  nav.replaceChildren();
  const paths = [
    ['Market reactions', 'Fed, ECB and UK event windows', 'market-reactions.html?historyYear=' + year + '#annual-market-history'],
    ['Policy history', 'Effective rate changes and policy decisions', 'historical-data.html?historyYear=' + year + '#annual-policy-ledger'],
    ['Macro history', 'Monthly prices, unemployment and output', 'macro-history.html?view=yearbook&historyYear=' + year]
  ];
  for (const [title, description, url] of paths) {
    const link = anchor('', url);
    link.append(make('strong', title + ' ↗'), make('span', description));
    nav.append(link);
  }
}
function macroTable() {
  const container = get('yb-matrix');
  container.replaceChildren();
  const filtered = data.economies.filter(row => regionSelect.value === 'All regions' || row.region === regionSelect.value);
  const count = column => filtered.filter(row => row.years[selected]?.[column] != null).length;
  if (selected > data.through) {
    regionSelect.disabled = true;
    get('yb-sample').textContent = '2026 is in progress. The annual comparison runs through ' + data.through + '. The monthly study above shows the available 2026 observations and their individual cutoffs.';
    return;
  }
  regionSelect.disabled = false;
  get('yb-sample').textContent = selected + ' · Real GDP growth is available for ' + count(0) + ' of ' + filtered.length + ' economies and consumer price inflation for ' + count(1) + '. Changes compare each growth or inflation rate with its own previous year, in percentage points.';
  const table = make('table');
  table.setAttribute('aria-label', selected + ' annual real GDP growth and consumer price inflation');
  const head = table.createTHead().insertRow();
  for (const label of ['Economy', 'Real GDP growth (%)', 'Change (pp)', 'CPI inflation (%)', 'Change (pp)']) {
    const th = make('th', label);
    th.scope = 'col';
    head.append(th);
  }
  const body = table.createTBody();
  for (const row of filtered) {
    const tr = body.insertRow();
    const th = make('th', row.name);
    th.scope = 'row';
    tr.append(th);
    const now = row.years[selected] || [], before = row.years[selected - 1] || [];
    for (let column = 0; column < 2; column++) {
      const level = now[column], previous = before[column];
      const delta = level == null || previous == null ? null : level - previous;
      for (const [value, isChange] of [[level, false], [delta, true]]) {
        const td = tr.insertCell();
        td.textContent = fmt(value, isChange);
        if (value == null) {
          td.className = 'yb-na';
          td.setAttribute('aria-label', 'Unavailable');
        }
      }
    }
  }
  const wrap = make('div');
  wrap.className = 'yb-scroll';
  wrap.append(table);
  container.append(wrap);
}
function peerPath() {
  const focal = data.economies.find(row => row.name === areaName(mainCase.area));
  const benchmark = get('yb-benchmark');
  const regional = data.economies.filter(row => row.region === focal.region && row.id !== focal.id);
  benchmark.querySelector('[value="regional"]').disabled = !regional.length;
  if (!regional.length && benchmark.value === 'regional') benchmark.value = 'all';
  const peers = benchmark.value === 'regional' ? regional : data.economies.filter(row => row.id !== focal.id);
  const measure = Number(get('yb-measure').value);
  const label = measure === 0 ? 'Real GDP growth' : 'CPI inflation';
  get('yb-peer-title').textContent = focal.name + ' and its peers';
  get('yb-peer-caption').textContent = 'Compare the year before the ' + niceDate(mainCase.date) + ' decision with the decision year and the next two years. The benchmark gives each reporting economy equal weight. Later data incorporate other policy decisions and shocks.';
  const table = make('table');
  table.setAttribute('aria-label', focal.name + ' and peer ' + label.toLowerCase() + ' before and after the decision');
  const head = table.createTHead().insertRow();
  for (const title of ['Year', focal.name + ' (%)', 'Peer median (%)', 'Gap (pp)', 'Peer count']) {
    const th = make('th', title);
    th.scope = 'col';
    head.append(th);
  }
  const body = table.createTBody();
  for (let y = selected - 1; y <= Math.min(selected + 2, data.through); y++) {
    const own = focal.years[y]?.[measure];
    const values = peers.map(row => row.years[y]?.[measure]).filter(Number.isFinite).sort((a, b) => a - b);
    const n = values.length;
    const midpoint = n ? (values[Math.floor((n - 1) / 2)] + values[Math.floor(n / 2)]) / 2 : null;
    const tr = body.insertRow();
    const th = make('th', String(y));
    th.scope = 'row';
    tr.append(th);
    for (const text of [fmt(own), fmt(midpoint), fmt(own == null || midpoint == null ? null : own - midpoint, true), String(n)]) tr.insertCell().textContent = text;
  }
  const nodes = [table];
  if (selected + 2 > data.through) nodes.push(make('p', 'Full-year outcomes after ' + data.through + ' are unavailable in this annual dataset.'));
  get('yb-peer-grid').replaceChildren(...nodes);
}
function draw() {
  const params = new URLSearchParams(location.search);
  const year = Number(params.get('historyYear'));
  selected = years.includes(year) ? year : years[0];
  get('yb-heading').textContent = selected;
  for (const link of get('yb-years').querySelectorAll('a')) {
    if (Number(link.textContent) === selected) link.setAttribute('aria-current', 'date');
    else link.removeAttribute('aria-current');
  }
  const records = cases.filter(record => record.year === selected);
  const picked = records.find(record => caseKey(record) === params.get('case')) || records[0];
  indexSelect.value = caseKey(picked);
  mainCase = picked;
  const sorted = picked === records[0] ? records : [picked, ...records.filter(record => record !== picked)];
  get('yb-cases').replaceChildren(...sorted.map(card));
  studies(selected);
  peerPath();
  macroTable();
}
function setYear(url) {
  if (url.href !== location.href) history.pushState(null, '', url);
  draw();
}
function note() {
  const box = get('yb-source-note');
  const sources = make('p', 'World Development Indicators · ');
  sources.append(anchor('Real GDP growth', 'https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG'), ' · ',
    anchor('Consumer price inflation', 'https://data.worldbank.org/indicator/FP.CPI.TOTL.ZG'));
  box.append(sources, make('p', 'Real GDP growth measures the annual change in output at constant prices. CPI inflation measures the annual change in consumer prices. Reporting calendars, CPI baskets and revisions can differ by economy. The euro area is the World Bank aggregate. An em dash marks an unpublished figure or a missing input for the change.'),
    make('p', 'World Bank source updates · GDP ' + niceDate(data.vintages.gdp) + ' · CPI ' + niceDate(data.vintages.inflation) + '. These are revised historical observations. Each event’s source links preserve what policymakers actually announced at the time.'));
  const taiwan = data.economies.find(row => row.id === 'TW');
  if (taiwan?.sources) {
    const local = make('p', 'Taiwan · Directorate-General of Budget, Accounting and Statistics. ');
    local.append(anchor('Real GDP growth', taiwan.sources.gdp), ' · ', anchor('Annual CPI inflation', taiwan.sources.inflation), '. ' + taiwan.note);
    box.append(local);
  }
}
async function init() {
  [cases, data] = await Promise.all([readJSON('yearbook-cases.json'), readJSON('yearbook-economies.json')]);
  cases.sort((a, b) => a.date.localeCompare(b.date));
  years = [...new Set(cases.map(record => record.year))];
  const economies = new Set(cases.map(record => areaName(record.area)));
  get('yb-coverage').textContent = cases.length + ' dated cases across ' + economies.size + ' economies. Every year has a case. Source coverage differs across the market and macro studies.';
  for (const y of years) {
    const link = anchor(y, yearURL(y));
    link.addEventListener('click', e => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      setYear(new URL(link.href));
    });
    get('yb-years').append(link);
  }
  const byEconomy = [...cases].sort((a, b) => areaName(a.area).localeCompare(areaName(b.area)) || a.year - b.year);
  for (const record of byEconomy) indexSelect.add(new Option(areaName(record.area) + ' · ' + record.year + ' · ' + record.title, caseKey(record)));
  for (const region of [...new Set(data.economies.map(row => row.region))].sort()) regionSelect.add(new Option(region));
  indexSelect.addEventListener('change', () => {
    const choice = cases.find(record => caseKey(record) === indexSelect.value);
    setYear(yearURL(choice.year, caseKey(choice)));
  });
  regionSelect.addEventListener('change', macroTable);
  for (const id of ['yb-measure', 'yb-benchmark']) get(id).addEventListener('change', peerPath);
  window.addEventListener('popstate', draw);
  note();
  draw();
  get('yb-status').hidden = true;
  get('yb-content').hidden = false;
}
init().catch(() => {
  get('yb-status').textContent = 'The historical data could not be loaded. Reload the page to try again.';
});
