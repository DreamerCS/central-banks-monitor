"use strict";

const state = { sources: [], limit: 10, region: "All", category: "All", query: "", sort: "institution" };
const $ = (selector) => document.querySelector(selector);
const categories = ["All", "Policy", "Speeches", "Research"];
const regions = ["All", "Europe", "Americas", "Asia-Pacific", "Africa"];

function groupFor(category) {
  if (category.startsWith("Research")) return "Research";
  if (category.startsWith("Policy")) return "Policy";
  if (category.startsWith("Speeches")) return "Speeches";
  return category;
}

function filterButtons(container, choices, key) {
  const parent = $(container);
  for (const choice of choices) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = choice;
    button.dataset.value = choice;
    button.setAttribute("aria-pressed", String(state[key] === choice));
    button.addEventListener("click", () => {
      state[key] = choice; state.limit = 10;
      for (const item of parent.children) item.setAttribute("aria-pressed", String(item === button));
      render();
    });
    parent.append(button);
  }
}

function sourceCard(source) {
  const article = document.createElement("article");
  article.className = "source-card";
  const content = document.createElement("div");
  const meta = document.createElement("div");
  meta.className = "source-meta";
  meta.textContent = `${source.region} / ${source.country} / ${source.category}`;
  const name = document.createElement("h3");
  name.textContent = source.institution;
  const type = document.createElement("p");
  type.textContent = source.sourceType;
  content.append(meta, name, type);

  const links = document.createElement("div");
  links.className = "source-links";
  const official = document.createElement("a");
  official.href = source.url;
  official.target = "_blank";
  official.rel = "noopener noreferrer";
  official.textContent = "Official page ↗";
  official.setAttribute("aria-label", `Open ${source.institution} ${source.category} official page`);
  links.append(official);
  if (source.feed) {
    const feed = document.createElement("a");
    feed.href = source.feed;
    feed.target = "_blank";
    feed.rel = "noopener noreferrer";
    feed.textContent = "RSS / Atom ↗";
    feed.setAttribute("aria-label", `Open ${source.institution} ${source.category} feed`);
    links.append(feed);
  }
  article.append(content, links);
  return article;
}

function render() {
  const query = state.query.trim().toLocaleLowerCase();
  const filtered = state.sources.filter((source) =>
    (state.region === "All" || state.region === source.region) &&
    (state.category === "All" || state.category === groupFor(source.category)) &&
    (!query || [source.institution, source.country, source.category, source.sourceType].some((value) => value.toLocaleLowerCase().includes(query)))
  );
  const key = state.sort;
  filtered.sort((a, b) => a[key].localeCompare(b[key]) || a.institution.localeCompare(b.institution) || a.id.localeCompare(b.id));
  $("#results-count").textContent = `${filtered.length} of ${state.sources.length} source pages`;
  const list = $("#results-list");
  list.replaceChildren();
  $("#more-sources").hidden = filtered.length <= state.limit;
  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    const heading = document.createElement("h3");
    heading.textContent = "No matching sources";
    const note = document.createElement("p");
    note.textContent = "Try another bank, country or publication type.";
    empty.append(heading, note);
    list.append(empty);
  } else {
    const fragment = document.createDocumentFragment();
    for (const source of filtered.slice(0, state.limit)) fragment.append(sourceCard(source));
    list.append(fragment);
  }
}

async function start() {
  $("#more-sources").addEventListener("click", () => { state.limit += 20; render(); });
  filterButtons("#region-filters", regions, "region");
  filterButtons("#category-filters", categories, "category");
  $("#search").addEventListener("input", (event) => { state.limit = 10; state.query = event.target.value; render(); });
  $("#sort").addEventListener("change", (event) => { state.sort = event.target.value; render(); });
  $("#reset").addEventListener("click", () => {
    state.limit = 10; state.region = "All"; state.category = "All"; state.query = "";
    $("#search").value = "";
    for (const container of ["#region-filters", "#category-filters"]) {
      for (const item of $(container).children) item.setAttribute("aria-pressed", String(item.dataset.value === "All"));
    }
    render();
    $("#search").focus();
  });
  try {
    const response = await fetch("data/sources.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data.sources)) throw new Error("Invalid source data");
    state.sources = data.sources;
    $("#source-total").textContent = String(data.sources.length);
    $("#bank-total").textContent = String(new Set(data.sources.map((item) => item.institution)).size);
    render();
  } catch (error) {
    $("#results-count").textContent = "Directory unavailable";
    $("#load-error").hidden = false;
    console.error("Source atlas failed to load", error);
  }
  try {
    const response = await fetch("data/coverage.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const coverage = await response.json();
    const fragment = document.createDocumentFragment();
    for (const target of coverage.targets) {
      const card = document.createElement("div");
      card.className = "coverage-card linked";
      const name = document.createElement("strong"); name.textContent = target.name;
      const status = document.createElement("small");
      status.textContent = `${target.sourceCount} source ${target.sourceCount === 1 ? "page" : "pages"}`;
      card.append(name, status); fragment.append(card);
    }
    $("#coverage-grid").append(fragment);
    $("#jurisdiction-total").textContent = String(coverage.targets.length);
  } catch (error) {
    $("#coverage-grid").textContent = "Coverage map unavailable.";
    console.error("Coverage map failed to load", error);
  }
}

start();

async function loadTreasury() {
  const status = $("#treasury-asof"), chart = $("#treasury-chart");
  try {
    const response = await fetch("data/treasury.json", {cache: "no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const rows = data.observations;
    if (!Array.isArray(rows) || !rows.length) throw new Error("No verified observations yet");
    if (data.frequency !== "daily" || data.unit !== "percent per annum" || rows.length > 300 ||
        rows.some((r) => !/^\d{4}-\d\d-\d\d$/.test(r.date) || !Number.isFinite(r.twoYear) || !Number.isFinite(r.tenYear) || r.twoYear < 0 || r.tenYear < 0)) {
      throw new Error("Invalid Treasury snapshot");
    }
    const latest = rows[rows.length - 1];
    if (latest.date !== data.asOfDate) throw new Error("Inconsistent observation date");
    $("#yield-2y").textContent = `${latest.twoYear.toFixed(2)}%`;
    $("#yield-10y").textContent = `${latest.tenYear.toFixed(2)}%`;
    $("#yield-spread").textContent = `${((latest.tenYear - latest.twoYear) * 100).toFixed(0)} bp`;
    status.textContent = `Observation date ${latest.date} · U.S. Treasury daily par yield curve`;
    const recent = rows.slice(-90);
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 860 280");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");
    const values = recent.flatMap((r) => [r.twoYear, r.tenYear]);
    const lo = Math.floor((Math.min(...values) - .1) * 4) / 4;
    const hi = Math.ceil((Math.max(...values) + .1) * 4) / 4;
    const x = (i) => 48 + (i / Math.max(recent.length - 1, 1)) * 790;
    const y = (v) => 225 - ((v - lo) / Math.max(hi - lo, .1)) * 190;
    for (let i = 0; i <= 4; i++) {
      const value = lo + (hi - lo) * i / 4;
      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", "48"); line.setAttribute("x2", "838");
      line.setAttribute("y1", String(y(value))); line.setAttribute("y2", String(y(value)));
      line.setAttribute("stroke", "#d8e3e1"); svg.append(line);
      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", "4"); label.setAttribute("y", String(y(value) + 4));
      label.textContent = `${value.toFixed(2)}%`; svg.append(label);
    }
    for (const [key, colour] of [["twoYear", "#24516b"], ["tenYear", "#b49566"]]) {
      const line = document.createElementNS(ns, "polyline");
      line.setAttribute("points", recent.map((r, i) => `${x(i).toFixed(1)},${y(r[key]).toFixed(1)}`).join(" "));
      line.setAttribute("fill", "none"); line.setAttribute("stroke", colour);
      line.setAttribute("stroke-width", "3"); line.setAttribute("vector-effect", "non-scaling-stroke");
      svg.append(line);
    }
    for (const [i, anchor] of [[0, "start"], [recent.length - 1, "end"]]) {
      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", String(x(i))); label.setAttribute("y", "260");
      label.setAttribute("text-anchor", anchor); label.textContent = recent[i].date;
      svg.append(label);
    }
    chart.replaceChildren(svg);
    chart.setAttribute("aria-label", `Daily U.S. Treasury par yields from ${recent[0].date} to ${latest.date}. Latest two-year ${latest.twoYear.toFixed(2)} percent, ten-year ${latest.tenYear.toFixed(2)} percent.`);
  } catch (error) {
    status.textContent = "Daily Treasury series unavailable. Check the official source; no value has been inferred.";
    chart.textContent = "No verified observations to display.";
    console.warn("Treasury snapshot failed to load", error);
  }
}

loadTreasury();

function parseCsvLine(line) {
  const fields = []; let value = "", quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"' && quoted && line[i+1] === '"') { value += '"'; i++; }
    else if (ch === '"') quoted = !quoted;
    else if (ch === ',' && !quoted) { fields.push(value); value = ""; }
    else value += ch;
  }
  if (quoted) return [];
  fields.push(value);
  return fields.map((item) => item.trim());
}

const minuteMs = 60_000;
const quoteTolerance = 2 * minuteMs;

function parseUtcTimestamp(stamp) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?Z$/.test(stamp)) return NaN;
  const time = Date.parse(stamp);
  if (!Number.isFinite(time)) return NaN;
  return new Date(time).toISOString().slice(0, 16) === stamp.slice(0, 16) ? time : NaN;
}

function eventObservations(csv, asset) {
  const lines = csv.trim().split(/\r?\n/);
  if (parseCsvLine(lines[0]).join(",").toLowerCase() !== "timestamp_utc,asset,value") {
    throw new Error("The CSV header must be timestamp_utc,asset,value.");
  }
  const quotes = new Map();
  for (const line of lines.slice(1)) {
    const fields = parseCsvLine(line);
    if (fields.length !== 3) continue;
    const [stamp, name, raw] = fields;
    if (name.toLowerCase() !== asset.toLowerCase() || !/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(raw)) continue;
    const time = parseUtcTimestamp(stamp);
    const value = Number(raw);
    if (!Number.isFinite(time) || !Number.isFinite(value)) continue;
    const existing = quotes.get(time);
    if (!existing) quotes.set(time, { time, value, stamp });
    else if (existing.value !== value) existing.conflict = true;
  }
  return Array.from(quotes.values()).sort((first, second) => first.time - second.time);
}

function eventWindow(quotes, eventTime, horizon, nearestMinutes) {
  if (quotes.length === 0) throw new Error("No matching quotes. Check the asset name, numeric values and UTC timestamps ending in Z.");
  const nearest = horizon === "nearest";
  const gap = nearest ? nearestMinutes * minuteMs : quoteTolerance;
  const before = quotes.filter(quote => quote.time < eventTime && quote.time >= eventTime - gap).at(-1);
  if (!before) throw new Error(`Missing baseline. Supply a quote strictly before the announcement, within ${gap / minuteMs} minutes.`);
  let after;
  if (nearest) {
    after = quotes.find(quote => quote.time > eventTime && quote.time <= eventTime + gap);
    if (!after) throw new Error(`Missing post-announcement quote within ${nearestMinutes} minutes.`);
  } else {
    const target = eventTime + Number(horizon) * minuteMs;
    after = quotes.filter(quote => quote.time > eventTime && quote.time <= target && quote.time >= target - gap).at(-1);
    if (!after) throw new Error(`No quote at +${horizon} minutes or in the preceding two minutes. Supply a quote for that window.`);
  }
  for (const quote of [before, after]) {
    if (quote.conflict) throw new Error(`The CSV has conflicting prices for the selected asset at ${quote.stamp}. Keep one value for that time.`);
  }
  return { before, after };
}

function eventChange(before, after, measure) {
  let value = after - before;
  let digits = 4;
  let suffix = " units";
  if (measure === "yield") {
    value *= 100;
    digits = 2;
    suffix = " bp";
  } else if (measure === "return") {
    if (before <= 0 || after <= 0) throw new Error("FX or price returns require positive quotes. Choose original units for a series that crosses zero.");
    value = (after - before) / before * 100;
    digits = 3;
    suffix = "%";
  }
  if (!Number.isFinite(value)) throw new Error("The change exceeds the supported numeric range.");
  return new Intl.NumberFormat("en-GB", {
    signDisplay: "exceptZero", minimumFractionDigits: digits, maximumFractionDigits: digits
  }).format(value) + suffix;
}

let eventRequest = 0;

function clearEventResult() {
  eventRequest++;
  const output = $("#event-result");
  output.className = "";
  output.textContent = "Select Calculate change to see the result.";
}

function updateWindowFields() {
  const nearest = $("#event-horizon").value === "nearest";
  $("#nearest-window").hidden = !nearest;
  $("#window-method").textContent = nearest
    ? "Uses the last quote strictly before the announcement and the first quote strictly after it, within the maximum gap on each side."
    : "Uses the last quote strictly before the announcement and the last quote at or before the target. Each quote can be up to two minutes old.";
}

async function runEvent() {
  const request = ++eventRequest;
  const output = $("#event-result");
  const file = $("#market-file").files?.[0];
  const eventTime = parseUtcTimestamp(`${$("#event-time").value}Z`);
  const asset = $("#asset-filter").value.trim();
  const horizon = $("#event-horizon").value;
  const measure = $("#event-measure").value;
  const nearestMinutes = Number($("#event-window").value);
  output.className = "";
  try {
    if (!file || !Number.isFinite(eventTime) || !asset) throw new Error("Select a CSV, UTC announcement time and asset name.");
    if (file.size > 2_000_000) throw new Error("Choose a CSV of 2 MB or less.");
    output.textContent = "Reading quotes…";
    const csv = await file.text().catch(() => { throw new Error("Could not read this file. Select it again."); });
    if (request !== eventRequest) return;
    const quotes = eventObservations(csv, asset);
    const { before, after } = eventWindow(quotes, eventTime, horizon, nearestMinutes);
    const headline = document.createElement("strong");
    const windowLabel = horizon === "nearest" ? "Nearest quotes" : `+${horizon} min`;
    headline.textContent = `${asset} · ${windowLabel} · ${eventChange(before.value, after.value, measure)}`;
    const detail = document.createElement("span");
    detail.textContent = ` · ${before.value} at ${before.stamp} to ${after.value} at ${after.stamp}.`;
    output.replaceChildren(headline, detail);
  } catch (error) {
    if (request !== eventRequest) return;
    output.className = "error";
    output.textContent = error.message;
  }
}

$("#event-form").addEventListener("input", clearEventResult);
$("#event-horizon").addEventListener("change", updateWindowFields);
$("#run-event").addEventListener("click", runEvent);
updateWindowFields();

function openLinkedCalculator() {
  if (location.hash === "#event-calculator") $("#event-calculator").open = true;
}
openLinkedCalculator();
window.addEventListener("hashchange", openLinkedCalculator);
