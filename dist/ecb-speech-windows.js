// Each event is selected by release, since several speakers can share a date.
const panel = document.querySelector('#ecb-speech-windows');
const field = name => panel.querySelector('[data-es="' + name + '"]');
const params = new URLSearchParams(location.search);
const fmt = (n, unit) => Number.isFinite(n) ? new Intl.NumberFormat('en-GB', {
  signDisplay: 'exceptZero', minimumFractionDigits: 2, maximumFractionDigits: 2
}).format(n) + (unit === 'bp' ? ' bp' : '%') : '—';
const diff = (a, b) => Number.isFinite(a) && Number.isFinite(b) ? a - b : null;

async function start() {
  const response = await fetch('data/ecb-speech-windows.json');
  if (!response.ok) throw Error('Data unavailable');
  const {fields, events} = await response.json();
  const [year, speaker, select] = ['year','speaker','event'].map(field);
  const rows = events.map(([id,time,name,title,closed,off,values]) => ({
    id,time,name,title,closed,off, moves:Object.fromEntries(fields.map((key,i) => [key,values[i]]))
  }));
  const first = rows.find(r => r.id === params.get('ecbSpeech')) ||
    rows.find(r => r.id === '7837548756') || rows.at(-1);
  const options = (control, values) => control.replaceChildren(...values.map(([id,label]) => new Option(label,id)));
  const years = [...new Set(rows.map(r => r.time.slice(0,4)))].reverse();
  options(year, years.map(y => [y,y]));
  year.value = first.time.slice(0,4);
  field('scope').textContent = rows.length.toLocaleString('en-GB') + ' communications · ' + rows[0].time.slice(0,10) + ' – ' + rows.at(-1).time.slice(0,10) + ' · ECB extended event-study database';
  function updateSpeakers(selectedId) {
    const dated = rows.filter(r => r.time.startsWith(year.value));
    const names = [...new Set(dated.map(r => r.name))].sort();
    const saved = speaker.value;
    options(speaker, [['','All speakers'],...names.map(n => [n,n])]);
    if (names.includes(saved)) speaker.value = saved;
    updateEvents(selectedId);
  }
  function updateEvents(selectedId) {
    const relevant = rows.filter(r => r.time.startsWith(year.value) && (!speaker.value || r.name === speaker.value)).reverse();
    options(select,relevant.map(r => [r.id,r.time.replace('T',' ') + ' · ' + r.name + ' · ' + r.title]));
    select.value = relevant.some(r => r.id === selectedId) ? selectedId : relevant[0].id;
    show();
  }
  function show() {
    const r = rows.find(x => x.id === select.value);
    field('title').textContent = r.title;
    const moves = r.moves;
    field('release').textContent = r.name + ' · ' + r.time.replace('T',' at ') + ' Frankfurt local time' +
      (r.closed ? ' · non-trading day' : r.off ? ' · outside regular hours' : ' · regular trading session');
    const values = [
      ['1M euro OIS', moves.OIS_1M,'bp'],['1Y euro OIS',moves.OIS_1Y,'bp'],['German 2Y yield',moves.DE2Y,'bp'],
      ['German 10Y yield',moves.DE10Y,'bp'],['German 2s10s',diff(moves.DE10Y,moves.DE2Y),'bp'],
      ['Italian 10Y yield',moves.IT10Y,'bp'],['Italy–Germany 10Y spread',diff(moves.IT10Y,moves.DE10Y),'bp'],
      ['EUR/USD', moves.EURUSD,'%'],['Euro Stoxx 50',moves.STOXX50E,'%']
    ];
    field('results').replaceChildren(...values.map(([label,value,unit]) => {
      const cell=document.createElement('div'); const key=document.createElement('dt'); const val=document.createElement('dd');
      key.textContent=label; val.textContent=fmt(value,unit); cell.append(key,val); return cell;
    }));
    const note = field('reading');
    const other = rows.filter(q => q.id !== r.id && q.time.slice(0,10) === r.time.slice(0,10) &&
      Math.abs(Date.parse(q.time+'Z') - Date.parse(r.time+'Z')) < 70 * 60_000);
    const context = r.id === '7837548756' ? 'Italian yields fell while German yields rose. The narrowing sovereign spread and the small change in one-year OIS point to distinct credit, redenomination and policy-rate channels. ' : '';
    note.textContent = context + (other.length ? 'The source also lists ' + other.length + ' other communication' + (other.length===1 ? '' : 's') + ' with an overlapping measurement window. ' : '') + (r.closed || r.off ? 'Trading was outside regular hours, so sparse quotes and wider spreads can distort comparisons. ' : '') + (values.every(v => !Number.isFinite(v[1])) ? 'No selected instrument has a reported quote in this window.' : 'A dash marks a missing quote.');
    const url = new URL(location.href); url.searchParams.set('ecbSpeech',r.id); url.hash = 'ecb-speech-windows';
    field('link').href = url.href;
  }
  year.addEventListener('change',() => updateSpeakers());
  speaker.addEventListener('change',() => updateEvents());
  select.addEventListener('change',show);
  updateSpeakers(first.id);
  field('controls').hidden=false;
}
if (panel) start().catch(() => {field('scope').textContent='ECB speech prices could not be loaded. The original workbook is linked below.';});
