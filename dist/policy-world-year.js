const DAY = 86_400_000;
const MAX_AGE = 10;
const asDay = iso => Date.parse(iso + "T00:00:00Z") / DAY;
const dateFmt = new Intl.DateTimeFormat("en-GB", {day:"numeric",month:"short",year:"numeric",timeZone:"UTC"});
const numberFmt = new Intl.NumberFormat("en-GB", {maximumFractionDigits:4});
const bpFmt = new Intl.NumberFormat("en-GB", {maximumFractionDigits:2});
const displayDate = day => dateFmt.format(day * DAY);
const yearAt = day => new Date(day * DAY).getUTCFullYear();
const yearEnd = year => Date.UTC(year, 11, 31) / DAY;

function lastAtOrBefore(runs, offset) {
  let start = 0, end = runs.length;
  while (start < end) {
    const middle = Math.floor((start + end) / 2);
    if (runs[middle][0] <= offset) start = middle + 1;
    else end = middle;
  }
  if (start === 0) return null;
  const [first, length, value] = runs[start - 1];
  return {offset:Math.min(first + length - 1, offset),value};
}

function endpoint(series, startDay, boundary) {
  const observation = lastAtOrBefore(series.observations, boundary - startDay);
  if (!observation) return null;
  const day = startDay + observation.offset;
  if (yearAt(day) !== yearAt(boundary)) return null;
  return {day,value:observation.value,fresh:boundary - day <= MAX_AGE};
}

function assess(series, year, base, through) {
  const before = endpoint(series, base, yearEnd(year - 1));
  const after = endpoint(series, base, Math.min(yearEnd(year), through));
  const runs = series.observations;
  const first = runs.length ? base + runs[0][0] : null;
  const tail = runs.at(-1);
  const last = tail ? base + tail[0] + tail[1] - 1 : null;
  const neer = series.metric === "neer";
  if (before?.fresh && after?.fresh && (!neer || before.value > 0)) {
    const delta = neer ? 100 * (after.value / before.value - 1) : 100 * (after.value - before.value);
    return {before,after,delta:Math.round(delta * 100) / 100};
  }
  let reason = "No comparable pair";
  if (first === null) reason = "No source observations";
  else if (year < yearAt(first)) reason = "Coverage begins " + displayDate(first);
  else if (year > yearAt(last)) reason = "Last observed " + displayDate(last);
  else if (after && !after.fresh) reason = "Closing observation is too old";
  else if (!after) reason = "No closing observation";
  else if (year === yearAt(first)) reason = "Coverage begins " + displayDate(first);
  else if (before && !before.fresh) reason = "Previous December unavailable";
  else if (!before) reason = "Previous December unavailable";
  return {before,after,delta:null,reason};
}

function make(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}

function formatChange(n, unit) {
  const prefix = n > 0 ? "+" : n < 0 ? "−" : "";
  return prefix + bpFmt.format(Math.abs(n)) + unit;
}

function level(cell, obs, isRate) {
  if (!obs) { cell.append("—"); return; }
  const amount = numberFmt.format(obs.value) + (isRate ? "%" : "");
  if (obs.fresh) cell.append(amount, make("small",displayDate(obs.day)));
  else cell.append("—",make("small","Last: " + amount + " · " + displayDate(obs.day),"pw-muted"));
}

function sourceAnchor(series) {
  const a = make("a",series.name);
  a.href = series.source;
  a.setAttribute("aria-label",series.name + " · " + (series.id === "TW" ? "central bank discount rate schedule" : "BIS source series"));
  return a;
}

function addRate(row, series, data) {
  const country = make("th");
  country.scope = "row";
  country.append(sourceAnchor(series));
  const previous = make("td"), last = make("td"), change = make("td");
  level(previous,data.before,true);
  level(last,data.after,true);
  if (data.delta === null) change.append("—",make("small",data.reason));
  else change.textContent = formatChange(data.delta," bp");
  row.append(country,previous,last,change);
}

function displayNeer(container, series, data, endLabel) {
  const dl = make("dl");
  for (const [label,obs] of [["Previous December",data.before],[endLabel,data.after]]) {
    const group = make("div"), value = make("dd");
    level(value,obs,false);
    group.append(make("dt",label),value);
    dl.append(group);
  }
  const group = make("div");
  group.append(make("dt","Index change"),make("dd",data.delta === null ? "—" : formatChange(data.delta,"%")));
  if (data.delta === null) group.append(make("small",data.reason));
  dl.append(group);
  const source = make("a","BIS Singapore broad NEER series");
  source.href = series.source;
  container.replaceChildren(dl,source);
}

async function mount(host) {
  const byId = id => host.querySelector("#pw-" + id);
  const years = byId("year"), regions = byId("region"), status = byId("status");
  let requestedYear = null;
  // A year may change while the compressed observations are still loading.
  window.addEventListener("historyyearchange", event => {
    requestedYear = String(event.detail?.year ?? "");
    if ([...years.options].some(o => o.value === requestedYear) && years.value !== requestedYear) {
      years.value = requestedYear;
      draw();
    }
  });
  const response = await fetch("data/historical-series.json");
  if (!response.ok) throw new Error("Could not fetch source observations");
  const snapshot = await response.json();
  const base = asDay(snapshot.start), through = asDay(snapshot.through);
  const firstYear = yearAt(base), finalYear = yearAt(through);
  const economies = snapshot.series.slice().sort((a,b) => a.name.localeCompare(b.name,"en"));
  const availableRegions = [...new Set(economies.map(s => s.region))].sort();
  for (let y = finalYear; y >= firstYear; y--) years.add(new Option(String(y),String(y)));
  for (const region of availableRegions) regions.add(new Option(region,region));
  function restore() {
    const params = new URLSearchParams(location.search);
    const choice = requestedYear || params.get("historyYear") || params.get("year") || document.querySelector("#ledger-year")?.value;
    years.value = [...years.options].some(o => o.value === choice) ? choice : String(finalYear);
    const region = params.get("policyRegion") || "";
    regions.value = availableRegions.includes(region) ? region : "";
  }
  function comparisonUrl() {
    const url = new URL(location.href);
    url.searchParams.set("historyYear",years.value);
    if (regions.value) url.searchParams.set("policyRegion",regions.value);
    else url.searchParams.delete("policyRegion");
    return url;
  }
  function draw() {
    const year = Number(years.value);
    const partial = year === finalYear && through < yearEnd(year);
    const endLabel = partial ? "Year to date" : "Year-end";
    byId("before").textContent = "December " + (year - 1);
    byId("after").textContent = endLabel + " " + year;
    const shown = economies.filter(s => !regions.value || s.region === regions.value);
    const rates = shown.filter(s => s.metric === "rates");
    const results = rates.map(series => assess(series,year,base,through));
    const counts = {up:0,down:0,flat:0,missing:0};
    const rows = rates.map((series,i) => {
      const r = results[i], tr = make("tr");
      const key = r.delta === null ? "missing" : r.delta > 0 ? "up" : r.delta < 0 ? "down" : "flat";
      counts[key]++;
      addRate(tr,series,r);
      return tr;
    });
    byId("rates").replaceChildren(...rows);
    byId("caption").textContent = (regions.value || "All regions") + " · " + year + " policy rate levels";
    const coverage = partial ? "Reporting cutoff " + displayDate(through) + ". " : "";
    status.textContent = coverage + rates.length + " rate series · " + counts.up + " higher · " + counts.down +
      " lower · " + counts.flat + " unchanged · " + counts.missing + " without a comparable pair.";
    const sg = shown.find(s => s.metric === "neer");
    byId("singapore").hidden = !sg;
    if (sg) displayNeer(byId("sg-reading"),sg,assess(sg,year,base,through),endLabel);
    const share = comparisonUrl();
    share.hash = host.id;
    byId("permalink").href = share.href;
  }
  restore();
  draw();
  years.disabled = regions.disabled = false;
  byId("results").hidden = false;
  for (const control of [years,regions]) {
    control.addEventListener("change", () => {
      requestedYear = years.value;
      history.replaceState(history.state,"",comparisonUrl());
      draw();
      if (control === years) window.dispatchEvent(new CustomEvent("historyyearchange",{detail:{year:years.value}}));
    });
  }
  window.addEventListener("popstate", () => { requestedYear = null; restore(); draw(); });
}

const host = document.getElementById("policy-world-year");
if (host) mount(host).catch(() => {
  const status = host.querySelector("#pw-status");
  const a = make("a","Open the dated series directly");
  a.href = "data/historical-series.json";
  status.replaceChildren("The annual comparisons could not load. ",a);
});
