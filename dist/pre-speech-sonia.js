const dateFormat = new Intl.DateTimeFormat("en-GB", {day:"numeric", month:"short", year:"numeric", timeZone:"UTC"});
const formatDay = day => dateFormat.format(new Date(day + "T12:00:00Z"));
const windows = [1, 5, 20];
const cutoffs = [1, 2];

function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function link(text, url) {
  const item = node("a", text);
  item.href = url;
  return item;
}

function selectField(id, label, options) {
  const container = node("label", label);
  const select = node("select");
  select.id = id;
  for (const [value, title] of options) {
    const option = node("option", title);
    option.value = value;
    select.appendChild(option);
  }
  container.appendChild(select);
  return [container, select];
}

function basisPoints(value) {
  if (!Number.isFinite(value)) return "Unavailable";
  const fixed = Math.abs(value).toFixed(1);
  return (Number(fixed) === 0 ? "0.0" : (value < 0 ? "−" : "+") + fixed) + " bp";
}

function rate(value) {
  return Number.isFinite(value) ? value.toFixed(3).replace("-", "−") + "%" : "Unavailable";
}

function plotRates(first, last, months) {
  const svgNS = "http://www.w3.org/2000/svg";
  function shape(tag, attrs, text) {
    const element = document.createElementNS(svgNS, tag);
    for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
    if (text) element.textContent = text;
    return element;
  }
  const chart = shape("svg", {viewBox:"0 0 580 158", "aria-hidden":"true", focusable:"false"});
  const finite = [...first, ...last].filter(Number.isFinite);
  if (!finite.length) return chart;
  const bottom = Math.floor((Math.min(...finite) - 0.015) * 10) / 10;
  const top = Math.max(bottom + 0.2, Math.ceil((Math.max(...finite) + 0.015) * 10) / 10);
  const xpos = m => 58 + (m - 3) * 54;
  const ypos = r => 118 - (r - bottom) * 98 / (top - bottom);
  for (const mark of [bottom, (bottom + top) / 2, top]) {
    const y = ypos(mark);
    chart.append(shape("line", {x1:50,x2:552,y1:y,y2:y,stroke:"currentColor",opacity:".16"}),
      shape("text", {x:45,y:y + 4,"text-anchor":"end",fill:"currentColor"}, mark.toFixed(2) + "%"));
  }
  for (const month of months) chart.append(shape("text", {x:xpos(month),y:146,"text-anchor":"middle",fill:"currentColor"}, month + "m"));
  for (const [values, cls] of [[first, "ss-earlier"], [last, "ss-later"]]) {
    values.forEach((value, i) => {
      if (!Number.isFinite(value)) return;
      const x = xpos(months[i]), y = ypos(value);
      if (i && Number.isFinite(values[i - 1])) {
        chart.append(shape("line", {x1:xpos(months[i - 1]),y1:ypos(values[i - 1]),x2:x,y2:y,class:cls}));
      }
      chart.append(shape("circle", {cx:x,cy:y,r:3.5,class:cls}));
    });
  }
  return chart;
}

function observationTable(data, event, from, to) {
  const table = node("table");
  const caption = node("caption", "Estimated SONIA forward rates for the same future dates");
  const header = node("thead"), top = node("tr");
  for (const label of ["Fixed target",formatDay(from.date),formatDay(to.date),"Change"]) {
    const cell = node("th", label);
    cell.scope = "col";
    top.appendChild(cell);
  }
  const body = node("tbody");
  for (const [i, target] of event.targets.entries()) {
    const row = node("tr"), title = node("th", data.months[i] + " months");
    title.scope = "row";
    title.appendChild(node("small", formatDay(target)));
    const a = from.rates[i], b = to.rates[i];
    row.append(title, node("td", rate(a)), node("td", rate(b)),
      node("td", basisPoints(Number.isFinite(a) && Number.isFinite(b) ? 100 * (b - a) : NaN)));
    body.appendChild(row);
  }
  header.appendChild(top);
  table.append(caption, header, body);
  return table;
}

function mount(host, data) {
  const heading = node("h2", "Sterling pricing before a speech");
  const intro = node("p", "Compare where sterling overnight index swaps placed SONIA on three future dates. Each date stays fixed as you move between earlier and later market closes.");
  const controls = node("div", undefined, "ss-controls");
  const [eventField, speak] = selectField("ss-speech","Speech", data.events.map(e => [e.date, formatDay(e.date) + " · " + e.speaker]));
  const [rangeField, range] = selectField("ss-window","Trading interval", windows.map(n => [n, n + (n === 1 ? " session" : " sessions")]));
  const [cutField, end] = selectField("ss-cutoff", "End of comparison", [[1,"Last close before the speech"],[2,"One close earlier · publication buffer"]]);
  controls.append(eventField, rangeField, cutField);
  const result = node("div"), announcement = node("p", undefined, "ss-announcement");
  announcement.setAttribute("aria-live","polite");
  const method = node("details"), src = node("p", undefined, "ss-links");
  method.append(node("summary","How the rates and dates are calculated"),
    node("p","The Bank of England fits a daily sterling overnight index swap (OIS) curve. Its short-end spreadsheet gives annualised, continuously compounded instantaneous forwards at monthly tenors. A forward is the fitted rate at a future point in time. SONIA is an overnight unsecured sterling rate and can differ from Bank Rate. Risk premiums and market conditions also affect the curve."),
    node("p","Targets are three, six and twelve calendar months from the speech, including weekends. For each earlier close, we convert the remaining days to years using Actual/365 and interpolate linearly between the two neighbouring monthly forward rates. The Bank publishes those tenor points. The values at our fixed dates are estimates. A missing neighbouring rate leaves that target unavailable."),
    node("p","Session counts follow dates with valid daily curve observations. A five-session change compares two closes five observations apart. The Bank aims to publish each day’s curve by noon on the next business day. The last close predates the speech, but the Bank’s fitted figures may first have appeared after the speaker began. The extra-session buffer allows one more publication day. Historical files can be revised and individual release timestamps are unavailable."),
    node("p","All quoted closes precede the speech date. The changes include other news during the interval. These estimates do not measure the speech’s effect or the probability of a particular MPC decision. Levels are shown to three decimal places and changes to one tenth of a basis point, calculated before display rounding."));
  src.append(link("Bank methodology",data.curveSource),link("Daily OIS archive (ZIP)",data.dailyArchive),
    link("Latest daily curves (ZIP)",data.latestMonth),link("Source tenor values (CSV)","data/pre-speech-sonia-grid.csv"));
  method.appendChild(src);
  host.replaceChildren(heading, intro, controls, announcement, result, method);

  function currentUrl() {
    const url = new URL(location.href);
    url.searchParams.set("ukSpeech", speak.value);
    url.searchParams.set("ukWindow", range.value);
    url.searchParams.set("ukCutoff", end.value);
    url.hash = host.id;
    return url;
  }
  function restore() {
    const params = new URL(location.href).searchParams;
    speak.value = data.events.some(e => e.date === params.get("ukSpeech")) ? params.get("ukSpeech") : data.events[0].date;
    range.value = windows.includes(Number(params.get("ukWindow"))) ? params.get("ukWindow") : "5";
    end.value = cutoffs.includes(Number(params.get("ukCutoff"))) ? params.get("ukCutoff") : "1";
  }
  function paint() {
    const event = data.events.find(e => e.date === speak.value);
    const to = event.observations.find(o => o.sessionsBefore === Number(end.value));
    const from = event.observations.find(o => o.sessionsBefore === Number(end.value) + Number(range.value));
    announcement.textContent = "Market closes from " + formatDay(from.date) + " to " + formatDay(to.date) +
      " for " + event.speaker + "’s speech on " + formatDay(event.date) + ".";
    const info = node("p", event.context);
    const legend = node("div", undefined, "ss-legend");
    legend.append(node("span", formatDay(from.date), "ss-early-key"),node("span", formatDay(to.date), "ss-late-key"));
    const figure = node("div", undefined, "ss-figure");
    figure.append(legend, plotRates(from.rates, to.rates, data.months));
    const timeline = node("div");
    for (const item of event.policyDates.filter(i => from.date < i.date && i.date <= to.date)) {
      const annotation = node("p", undefined, "ss-timing");
      annotation.append(link(formatDay(item.date),item.url), " · " + item.text + " This announcement fell within the pricing interval.");
      timeline.appendChild(annotation);
    }
    const urls = node("p", undefined, "ss-links");
    urls.append(link("Official speech",event.url));
    if (event.note) urls.append(link("Read the archive analysis","research-archive.html?analysis=" + event.note));
    urls.append(link("Link to this comparison",currentUrl().href));
    const tableWrap = node("div", undefined, "ss-table");
    tableWrap.appendChild(observationTable(data, event, from, to));
    result.replaceChildren(node("h3", event.title),info,figure,tableWrap,timeline,urls);
  }
  restore();
  paint();
  controls.addEventListener("change", () => {
    const url = currentUrl();
    const current = new URL(location.href);
    current.search = url.search;
    history.replaceState(history.state, "", current);
    paint();
  });
  window.addEventListener("popstate", () => { restore(); paint(); });
}

const host = document.getElementById("pre-speech-sonia");
if (host) {
  fetch("data/pre-speech-sonia.json").then(response => {
    if (!response.ok) throw new Error("SONIA data unavailable");
    return response.json();
  }).then(data => mount(host, data)).catch(() => {
    const status = node("p", "The speech comparison could not load. ");
    status.append(link("Open the Bank of England yield curves","https://www.bankofengland.co.uk/statistics/yield-curves"));
    host.replaceChildren(status);
  });
}
