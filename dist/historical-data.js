const DAY = 86_400_000;
const colours = ["#1b6156", "#a04d2a", "#3d6794", "#75568d", "#a32e61", "#5d6a1c", "#3b427e", "#7b5741"];
const defaults = ["US", "XM", "GB", "JP"];
const ui = Object.fromEntries([...document.querySelectorAll("[id]")].map(node => [node.id, node]));
const metricButtons = [...document.querySelectorAll("[data-metric]")];
const grainButtons = [...document.querySelectorAll("[data-grain]")];
const viewButtons = [...document.querySelectorAll("[data-view]")];
const rangeButtons = [...document.querySelectorAll("[data-range]")];
const metrics = {
  rates: {
    title: "Policy rates", unit: "Percent per year · last available observation in each period",
    method: "Bank for International Settlements, Central bank policy rates (WS_CBPOL), with national central banks as the underlying sources. Historical series can splice different instruments. Taiwan uses its central bank’s effective-date discount rate schedule.",
  },
  publications: {
    title: "Archived publications", unit: "Documents indexed · total in each period",
    method: "Counts come from the dated documents in the monthly research archive and include all publication types. Counts describe the reviewed archive and depend on the available sources and selection of documents.",
  },
  neer: {
    title: "Singapore nominal effective exchange rate", unit: "BIS broad index · 2020 = 100 · last available observation in each period",
    method: "The Monetary Authority of Singapore implements policy through the exchange rate. The BIS broad NEER measures the Singapore dollar against a trade-weighted basket. A rise indicates appreciation. MAS uses its own basket and policy band.",
  },
};

const toDay = iso => Date.parse(`${iso}T00:00:00Z`) / DAY;
const toDate = day => new Date(day * DAY);
const iso = day => toDate(day).toISOString().slice(0, 10);
const longDate = new Intl.DateTimeFormat("en-GB", {day: "numeric", month: "short", year: "numeric", timeZone: "UTC"});
const monthDate = new Intl.DateTimeFormat("en-GB", {month: "short", year: "numeric", timeZone: "UTC"});
const shortDate = new Intl.DateTimeFormat("en-GB", {day: "numeric", month: "short", timeZone: "UTC"});
const valueFormat = new Intl.NumberFormat("en-GB", {maximumFractionDigits: 4});
const dayLabel = day => longDate.format(toDate(day));
const canvas = ui["history-canvas"];
const ctx = canvas.getContext("2d");

let firstDay, lastDay, archiveStart, archiveEnd, banks;
let view = "level";
let metric = "rates", grain = "year", from, to, frame, hover = -1;
const selected = {rates: [...defaults], publications: [...defaults], neer: ["SG"]};

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function addSource(label, url) {
  const link = element("a", label);
  link.href = url;
  if (url.startsWith("https://")) {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }
  ui["history-sources"].append(link);
}

function blankSeries() {
  return new Float64Array(Math.max(lastDay, archiveEnd) - firstDay + 1).fill(NaN);
}

function initData(snapshot, archive, archivePeriods) {
  firstDay = toDay(snapshot.start);
  lastDay = toDay(snapshot.through);
  archiveStart = toDay(archivePeriods[0].start);
  archiveEnd = toDay(archivePeriods.at(-1).end);
  banks = new Map(snapshot.series.map(({observations, ...bank}) => {
    const values = blankSeries();
    for (const [offset, size, value] of observations) values.fill(value, offset, offset + size);
    const publications = blankSeries();
    for (const period of archivePeriods) publications.fill(0, toDay(period.start) - firstDay, toDay(period.end) - firstDay + 1);
    return [bank.id, {...bank, values, publications, latest: firstDay + values.findLastIndex(Number.isFinite)}];
  }));
  const byName = new Map([...banks.values()].map(bank => [bank.name, bank]));
  for (const record of archive) {
    const index = toDay(record.date) - firstDay;
    byName.get(record.jurisdiction).publications[index] += 1;
  }
}

function periodBounds(day) {
  const date = toDate(day);
  const year = date.getUTCFullYear(), month = date.getUTCMonth();
  if (grain === "year") return [Date.UTC(year, 0, 1) / DAY, Date.UTC(year + 1, 0, 1) / DAY - 1];
  if (grain === "month") return [Date.UTC(year, month, 1) / DAY, Date.UTC(year, month + 1, 1) / DAY - 1];
  if (grain === "week") {
    const monday = day - (date.getUTCDay() + 6) % 7;
    return [monday, monday + 6];
  }
  return [day, day];
}

function periodsInRange() {
  const periods = [];
  for (let day = from; day <= to;) {
    const [start, end] = periodBounds(day);
    periods.push({start: day, end: Math.min(end, to), anchor: start});
    day = end + 1;
  }
  return periods;
}

function pointFor(bank, period) {
  if (metric === "publications") {
    const start = Math.max(period.start, archiveStart), end = Math.min(period.end, archiveEnd);
    let total = 0, latest;
    for (let day = start; day <= end; day++) {
      const count = bank.publications[day - firstDay];
      if (!Number.isFinite(count)) continue;
      total += count;
      latest = day;
    }
    return latest === undefined ? null : {value: total, day: latest};
  }
  for (let day = period.end; day >= period.start; day--) {
    const value = bank.values[day - firstDay];
    if (Number.isFinite(value)) return {value, day};
  }
  return null;
}

function seriesPoint(bank, period) {
  const current = pointFor(bank, period);
  if (!current || view === "level" || metric === "publications") return current;
  // Use the final observed close before this visible interval, including bank holidays.
  const earliest = Math.max(firstDay, period.start - 7);
  for (let day = period.start - 1; day >= earliest; day--) {
    const baseline = bank.values[day - firstDay];
    if (!Number.isFinite(baseline)) continue;
    const change = metric === "rates"
      ? (current.value - baseline) * 100
      : 100 * (current.value / baseline - 1);
    return {value: Number(change.toFixed(8)), day: current.day, baselineDay: day};
  }
  return null;
}

function availableRange() {
  return metric === "publications" ? [archiveStart, archiveEnd] : [firstDay, lastDay];
}

function shortcut(name) {
  const [start, end] = availableRange();
  if (name === "ytd") return [Math.max(start, toDay("2026-01-01")), end];
  if (name === "recent") return [Math.max(start, toDay("2026-06-01")), Math.min(end, toDay("2026-07-31"))];
  if (name === "five") {
    const date = toDate(end);
    date.setUTCFullYear(date.getUTCFullYear() - 5);
    return [Math.max(start, date.getTime() / DAY), end];
  }
  return [start, end];
}

function setRange(start, end) {
  const [min, max] = availableRange();
  from = Math.max(min, Math.min(max, start));
  to = Math.max(from, Math.min(max, end));
  const startField = ui["history-from"], endField = ui["history-to"];
  startField.min = iso(min);
  startField.max = iso(to);
  endField.min = iso(from);
  endField.max = iso(max);
  startField.value = iso(from);
  endField.value = iso(to);
  for (const button of rangeButtons) {
    const [a, b] = shortcut(button.dataset.range);
    button.disabled = ["five", "ytd"].includes(button.dataset.range) && min === a;
    const chosen = !button.disabled && a === from && b === to;
    button.setAttribute("aria-pressed", chosen);
  }
}

function tickLabel(period) {
  if (grain === "year") return iso(period.anchor).slice(0, 4);
  if (grain === "month" || to - from > 365) return monthDate.format(toDate(period.anchor));
  return shortDate.format(toDate(period.anchor));
}

function draw() {
  if (!frame || !ctx) return;
  const {periods, lines} = frame;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return;
  const scale = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  ctx.scale(scale, scale);
  ctx.font = '11px "IBM Plex Mono", ui-monospace, monospace';
  const left = 48, right = width - 15, top = 12, bottom = height - 33;
  const x = index => periods.length === 1 ? (left + right) / 2 : left + index * (right - left) / (periods.length - 1);
  frame.bounds = {left, right, x};
  let low = Infinity, high = -Infinity;
  for (const line of lines) for (const point of line.points) {
    if (!point) continue;
    low = Math.min(low, point.value);
    high = Math.max(high, point.value);
  }
  if (!Number.isFinite(low)) {
    showCursor();
    return;
  }
  if (metric === "publications") low = 0;
  if (view === "change") {
    low = Math.min(0, low);
    high = Math.max(0, high);
  }
  high = Math.max(high, low + (metric === "rates" ? 0.1 : 1));
  const approx = (high - low) / 5;
  const magnitude = 10 ** Math.floor(Math.log10(approx));
  const step = Math.max(metric === "publications" ? 1 : 0,
    magnitude * ([1, 2, 2.5, 5, 10].find(value => value * magnitude >= approx) ?? 10));
  const floor = Math.floor(low / step) * step, ceil = Math.ceil(high / step) * step;
  const y = value => bottom - (value - floor) * (bottom - top) / (ceil - floor);

  ctx.lineWidth = 1;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#5b665d";
  for (let i = 0; i <= Math.round((ceil - floor) / step); i++) {
    const value = floor + step * i;
    ctx.strokeStyle = Math.abs(value) < 1e-9 ? "#93988a" : "#dcdcd1";
    ctx.beginPath();
    ctx.moveTo(left, y(value));
    ctx.lineTo(right, y(value));
    ctx.stroke();
    ctx.fillText(valueFormat.format(Math.abs(value) < 1e-9 ? 0 : value), left - 8, y(value));
  }
  const ticks = Math.min(periods.length, Math.max(2, Math.floor((right - left) / 86) + 1));
  ctx.textBaseline = "top";
  for (let i = 0; i < ticks; i++) {
    const index = ticks === 1 ? 0 : Math.round(i * (periods.length - 1) / (ticks - 1));
    ctx.textAlign = index === 0 && ticks > 1 ? "left" : index === periods.length - 1 && ticks > 1 ? "right" : "center";
    ctx.fillText(tickLabel(periods[index]), x(index), bottom + 10);
  }

  for (const line of lines) {
    ctx.beginPath();
    ctx.strokeStyle = line.colour;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    const markers = [];
    let previous = -1;
    for (const [i, point] of line.points.entries()) {
      if (!point) continue;
      const gap = i - previous;
      const connected = previous >= 0 && gap <= (grain === "day" ? 4 : 1);
      if (!connected) ctx.moveTo(x(i), y(point.value));
      else {
        if (grain === "day" && metric === "rates" && view === "level") ctx.lineTo(x(i), y(line.points[previous].value));
        ctx.lineTo(x(i), y(point.value));
      }
      if (periods.length < 42 || (!connected && !line.points.slice(i + 1, i + (grain === "day" ? 5 : 2)).some(Boolean))) markers.push([x(i), y(point.value)]);
      previous = i;
    }
    ctx.stroke();
    ctx.fillStyle = line.colour;
    for (const [px, py] of markers) {
      ctx.beginPath();
      ctx.arc(px, py, 2.7, 0, 2 * Math.PI);
      ctx.fill();
    }
  }
  showCursor();
}

function showCursor() {
  const cursor = ui["history-cursor"];
  cursor.hidden = hover < 0 || !frame.bounds;
  if (!cursor.hidden) cursor.style.left = `${frame.bounds.x(hover)}px`;
}

function inspect(index, interactive = false) {
  const period = frame.periods[index];
  if (!period) return;
  hover = interactive ? index : -1;
  frame.inspected = index;
  ui["inspector-period"].textContent = period.start === period.end ? dayLabel(period.end) : `${dayLabel(period.start)} – ${dayLabel(period.end)}`;
  ui["inspector-label"].textContent = metric === "publications" ? "Indexed in period" : view === "change" ? "Period change" : "Latest in period";
  const cards = frame.lines.map(line => {
    const point = line.points[index];
    const card = element("div", "", "history-value");
    card.style.setProperty("--series-colour", line.colour);
    const suffix = view === "change" ? (metric === "rates" ? " bp" : "%") : metric === "rates" ? "%" : "";
    const prefix = view === "change" && point?.value > 0 ? "+" : "";
    const reading = point ? `${prefix}${valueFormat.format(point.value)}${suffix}` : "—";
    const detail = !point ? "No observation" : metric === "publications" ? "Documents" : view === "change"
      ? `${dayLabel(point.baselineDay)} – ${dayLabel(point.day)}`
      : dayLabel(point.day);
    card.append(element("small", line.bank.name), element("strong", reading), element("small", detail));
    return card;
  });
  ui["inspector-values"].replaceChildren(...cards);
  showCursor();
}

function compare(lines) {
  ui["history-compare"].hidden = metric === "neer";
  const enabled = [...banks.values()].filter(bank => (metric === "publications" || bank.metric === metric) && !selected[metric].includes(bank.id));
  enabled.sort((a, b) => a.name.localeCompare(b.name));
  const select = ui["bank-select"];
  select.replaceChildren(new Option("Select a jurisdiction", ""), ...enabled.map(bank => new Option(bank.name, bank.id)));
  select.disabled = lines.length >= colours.length || !enabled.length;
  if (select.disabled) select.options[0].textContent = "Comparison limit reached";
  const entries = lines.map(({bank, colour}) => {
    const row = element("li");
    const dot = element("span", "", "history-dot");
    dot.style.setProperty("--series-colour", colour);
    const remove = element("button", "×", "history-remove");
    remove.type = "button";
    remove.dataset.removeBank = bank.id;
    remove.setAttribute("aria-label", `Remove ${bank.name}`);
    remove.hidden = lines.length === 1;
    row.append(dot, element("strong", bank.name), remove);
    if (metric === "rates") row.append(element("span", `Through ${dayLabel(bank.latest)}`, "history-series-date"));
    return row;
  });
  ui["history-legend"].replaceChildren(...entries);
}

function sources(lines) {
  ui["history-method-note"].textContent = metrics[metric].method + (view === "change"
    ? " Changes use the last observation before the selected period and the last within it. A baseline must fall within the previous seven calendar days." : "");
  ui["history-sources"].replaceChildren();
  let note = "";
  if (metric === "rates") {
    note = "Observation dates vary by jurisdiction.";
    if (selected.rates.includes("AR")) note += " The BIS Argentina series ends on 10 July 2025.";
    if (selected.rates.includes("CN")) note += " The BIS China series uses the one-year loan prime rate in recent years.";
    addSource("BIS instrument definitions and series breaks", "https://www.bis.org/pages/statistics/cbpol-doc.pdf");
    for (const {bank} of lines) addSource(bank.id === "TW" ? "Taiwan CBC discount rate schedule" : `${bank.name} · ${bank.institution} via BIS`, bank.source);
  } else if (metric === "publications") {
    note = `Archive dates ${dayLabel(archiveStart)} – ${dayLabel(archiveEnd)}.`;
    addSource("Monthly research archive and original publications", "research-archive.html");
  } else {
    note = `Data through ${dayLabel(lines[0].bank.latest)}.`;
    addSource("BIS daily Singapore broad NEER", lines[0].bank.source);
    addSource("MAS monetary policy statements", "https://www.mas.gov.sg/monetary-policy/monetary-policy-statements");
  }
  ui["history-series-note"].textContent = note;
}

function render() {
  ui["chart-title"].textContent = metrics[metric].title;
  ui["chart-unit"].textContent = view === "change"
    ? (metric === "rates" ? "Period change · basis points" : "Period return · percent")
    : metrics[metric].unit;
  ui["history-view-field"].hidden = metric === "publications";
  for (const button of viewButtons) button.setAttribute("aria-pressed", view === button.dataset.view);
  for (const button of metricButtons) button.setAttribute("aria-pressed", metric === button.dataset.metric);
  for (const button of grainButtons) button.setAttribute("aria-pressed", grain === button.dataset.grain);
  const periods = periodsInRange();
  const lines = selected[metric].map((id, index) => {
    const bank = banks.get(id);
    return {bank, colour: colours[index], points: periods.map(period => seriesPoint(bank, period))};
  });
  frame = {periods, lines, inspected: periods.length - 1};
  const lastObserved = Math.max(...lines.map(line => line.points.findLastIndex(Boolean)));
  const hasValues = lastObserved >= 0;
  ui["chart-status"].textContent = hasValues ? "" : "The selected series have no observations in this date range.";
  ui["history-export"].disabled = !hasValues;
  compare(lines);
  sources(lines);
  inspect(hasValues ? lastObserved : periods.length - 1);
  draw();
}

function selectMetric(value) {
  metric = value;
  view = "level";
  grain = metric === "publications" ? "month" : "year";
  setRange(...shortcut("all"));
  render();
}

function exportCsv() {
  const output = ["metric,jurisdiction,frequency,period_start,period_end,observation_date,value,unit,source_url,measure,baseline_date"];
  const unit = view === "change" ? (metric === "rates" ? "bp" : "percent_return") : {rates: "percent", publications: "documents", neer: "index_2020_100"}[metric];
  const archiveUrl = new URL("research-archive.html", location.href).href;
  for (const [i, period] of frame.periods.entries()) {
    for (const {bank, points} of frame.lines) {
      const point = points[i];
      const fields = [metric, bank.name, grain, iso(period.start), iso(period.end),
        point && metric !== "publications" ? iso(point.day) : "", point?.value ?? "", unit,
        metric === "publications" ? archiveUrl : bank.source, metric === "publications" ? "count" : view,
        point?.baselineDay !== undefined ? iso(point.baselineDay) : ""];
      output.push(fields.map(value => `"${String(value).replaceAll('"', '""')}"`).join(","));
    }
  }
  const url = URL.createObjectURL(new Blob([output.join("\r\n") + "\r\n"], {type: "text/csv;charset=utf-8"}));
  const link = element("a");
  link.href = url;
  link.download = `central-banks-${metric}-${view}-${grain}-${iso(from)}-${iso(to)}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function load(file) {
  const response = await fetch(file);
  if (!response.ok) throw new Error(`${file} returned ${response.status}`);
  return response.json();
}

async function start() {
  initData(...await Promise.all([load("data/historical-series.json"), load("data/research-archive.json"), load("data/archive-periods.json")]));
  ui["history-explorer"].hidden = false;
  ui["history-load"].hidden = true;
  const requestedMetric = new URLSearchParams(location.search).get("metric");
  selectMetric(Object.hasOwn(metrics, requestedMetric) ? requestedMetric : "rates");
  new ResizeObserver(draw).observe(canvas);
  for (const button of metricButtons) button.addEventListener("click", () => selectMetric(button.dataset.metric));
  for (const button of viewButtons) button.addEventListener("click", () => {
    view = button.dataset.view;
    render();
  });
  for (const button of grainButtons) button.addEventListener("click", () => {
    grain = button.dataset.grain;
    render();
  });
  for (const button of rangeButtons) button.addEventListener("click", () => {
    setRange(...shortcut(button.dataset.range));
    render();
  });
  for (const id of ["history-from", "history-to"]) ui[id].addEventListener("change", event => {
    const day = toDay(event.target.value);
    const start = id === "history-from" && Number.isFinite(day) ? day : from;
    const end = id === "history-to" && Number.isFinite(day) ? day : to;
    setRange(start, end);
    render();
  });
  ui["bank-select"].addEventListener("change", event => {
    if (!event.target.value) return;
    selected[metric].push(event.target.value);
    render();
  });
  ui["history-legend"].addEventListener("click", event => {
    const remove = event.target.closest("[data-remove-bank]");
    if (!remove || selected[metric].length <= 1) return;
    selected[metric] = selected[metric].filter(id => id !== remove.dataset.removeBank);
    render();
    ui["bank-select"].focus();
  });
  const move = event => {
    if (!frame.bounds) return;
    const {left, right} = frame.bounds;
    const plotX = event.clientX - canvas.getBoundingClientRect().left;
    const fraction = Math.min(1, Math.max(0, (plotX - left) / (right - left)));
    const index = Math.round(fraction * (frame.periods.length - 1));
    if (index !== hover) inspect(index, true);
  };
  canvas.addEventListener("pointermove", move);
  canvas.addEventListener("pointerdown", move);
  canvas.addEventListener("keydown", event => {
    const last = frame.periods.length - 1;
    const next = {ArrowLeft: frame.inspected - 1, ArrowRight: frame.inspected + 1, Home: 0, End: last}[event.key];
    if (next === undefined) return;
    event.preventDefault();
    inspect(Math.min(last, Math.max(0, next)), true);
  });
  ui["history-export"].addEventListener("click", exportCsv);
}

start().catch(error => {
  ui["history-explorer"].hidden = true;
  ui["history-load"].hidden = false;
  ui["history-load"].textContent = "Historical data could not be loaded. Refresh the page to try again.";
  console.error(error);
});
