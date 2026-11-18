"use strict";

const state = { sources: [], region: "All", category: "All", query: "", sort: "institution" };
const $ = (selector) => document.querySelector(selector);
const categories = ["All", "Policy", "Speeches", "Research", "Models"];
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
      state[key] = choice;
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
  const badge = document.createElement("span");
  badge.className = `badge ${source.status === "Proposed" ? "proposed" : ""}`;
  badge.textContent = `${source.status} link · verify at source`;
  content.append(meta, name, type, badge);

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
    for (const source of filtered) fragment.append(sourceCard(source));
    list.append(fragment);
  }
}

async function start() {
  filterButtons("#region-filters", regions, "region");
  filterButtons("#category-filters", categories, "category");
  $("#search").addEventListener("input", (event) => { state.query = event.target.value; render(); });
  $("#sort").addEventListener("change", (event) => { state.sort = event.target.value; render(); });
  $("#reset").addEventListener("click", () => {
    state.region = "All"; state.category = "All"; state.query = "";
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
    $("#atlas .section-number").textContent = `${data.sources.length} / SOURCES`;
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
    $("#coverage .section-number").textContent = `${coverage.linkedCount} LINKED / ${coverage.targetCount} TARGETS`;
    $(".coverage-intro strong").textContent = String(coverage.linkedCount);
    const fragment = document.createDocumentFragment();
    for (const target of coverage.targets) {
      const card = document.createElement("div");
      card.className = `coverage-card ${target.sourceCount ? "linked" : "pending"}`;
      const name = document.createElement("strong"); name.textContent = target.name;
      const status = document.createElement("small");
      status.textContent = target.sourceCount ? `${target.sourceCount} source link${target.sourceCount === 1 ? "" : "s"} · ${target.status}` : "TO BE CATALOGUED";
      card.append(name, status); fragment.append(card);
    }
    $("#coverage-grid").append(fragment);
  } catch (error) {
    $("#coverage-grid").textContent = "Coverage map unavailable.";
    console.error("Coverage map failed to load", error);
  }
}

start();

function parseCsvLine(line) {
  const fields = []; let value = "", quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"' && quoted && line[i+1] === '"') { value += '"'; i++; }
    else if (ch === '"') quoted = !quoted;
    else if (ch === ',' && !quoted) { fields.push(value); value = ""; }
    else value += ch;
  }
  fields.push(value); return fields.map((item) => item.trim());
}

async function runEvent() {
  const output = $("#event-result"); output.className = "";
  const file = $("#market-file").files?.[0];
  const event = $("#event-time").value;
  const asset = $("#asset-filter").value.trim();
  if (!file || !event || !asset) { output.textContent = "Select a CSV, UTC event time and asset name."; output.className = "error"; return; }
  if (file.size > 2_000_000) { output.textContent = "Choose a CSV smaller than 2 MB."; output.className = "error"; return; }
  const lines = (await file.text()).replace(/^\uFEFF/, "").split(/\r?\n/).filter(Boolean);
  if (lines[0]?.toLowerCase() !== "timestamp_utc,asset,value") { output.textContent = "The CSV header must be timestamp_utc,asset,value."; output.className = "error"; return; }
  const observations = [];
  for (const line of lines.slice(1)) {
    const [stamp, label, raw] = parseCsvLine(line);
    if (label?.toLowerCase() !== asset.toLowerCase() || !/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?Z$/.test(stamp || "")) continue;
    const time = Date.parse(stamp), value = Number(raw);
    if (Number.isFinite(time) && raw !== "" && Number.isFinite(value)) observations.push({time,value,stamp});
  }
  const eventTime = Date.parse(`${event}Z`), windowMs = Number($("#event-window").value) * 60_000;
  const before = observations.filter((item) => item.time < eventTime && eventTime - item.time <= windowMs).sort((a,b) => b.time-a.time)[0];
  const after = observations.filter((item) => item.time > eventTime && item.time - eventTime <= windowMs).sort((a,b) => a.time-b.time)[0];
  if (!before || !after) { output.textContent = `No observation on both sides of the event within the chosen window (${observations.length} valid matching rows). Check UTC timestamps and asset name.`; output.className = "error"; return; }
  const delta = after.value - before.value;
  const yieldNote = /yield|rate/i.test(asset) ? ` (${(delta*100).toFixed(2)} bp if values are percentage points)` : "";
  output.replaceChildren();
  const headline = document.createElement("strong"); headline.textContent = `${asset}: ${delta >= 0 ? "+" : ""}${delta.toFixed(4)}${yieldNote}`;
  const detail = document.createElement("span"); detail.textContent = ` · ${before.value} at ${before.stamp} → ${after.value} at ${after.stamp}. Descriptive change only; no causal attribution.`;
  output.append(headline, detail);
}

$("#run-event").addEventListener("click", runEvent);
