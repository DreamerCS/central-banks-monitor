"use strict";

const select = id => document.getElementById(id);
const form = select("archive-filters");
const bankFilter = select("bank-filter");
const typeFilter = select("type-filter");
const queryFilter = select("query-filter");
const viewFilter = select("view-filter");
const container = select("archive-month");
const result = select("archive-results");
const params = new URLSearchParams(location.search);
const regions = ["North America", "South America", "Europe", "Africa", "Asia", "Oceania"];
const dateLabel = new Intl.DateTimeFormat("en-GB", {day: "numeric", month: "long", year: "numeric", timeZone: "UTC"});
const yearFilter = select("year-filter");
const dialog = select("archive-reader");
const notesByUrl = new Map();
const notesById = new Map();
let records, targets, periods, month, scope, opener;
let visibleCount = 60;
let readRevision = 0;

function sourceKey(raw) {
  const url = new URL(raw);
  // Some official HTML pages are indexed both with and without a trailing slash.
  return url.origin + url.pathname.replace(/\/$/, "") + url.search + url.hash;
}

function noteFor(url) {
  return notesByUrl.get(sourceKey(url));
}

function matchingNotes(record) {
  const matches = [noteFor(record.url), ...(record.related || []).map(link => noteFor(link.url))];
  return [...new Set(matches.filter(Boolean))];
}

function mergeEditions(publications) {
  const seen = new Map();
  for (const row of publications) {
    const note = noteFor(row.url);
    const key = note?.url || sourceKey(row.url);
    const previous = seen.get(key);
    if (!previous) {
      seen.set(key, row);
      continue;
    }
    const canonical = row.url === note?.url ? row : previous;
    const other = canonical === row ? previous : row;
    const links = new Map();
    for (const link of [...(canonical.related || []), ...(other.related || []),
      {label: "Publication notice", url: other.url}]) {
      if (sourceKey(link.url) !== sourceKey(canonical.url)) links.set(sourceKey(link.url),link);
    }
    seen.set(key, {...canonical, related:[...links.values()]});
  }
  return [...seen.values()];
}

function element(name, text, cssClass) {
  const node = document.createElement(name);
  if (text) node.textContent = text;
  if (cssClass) node.className = cssClass;
  return node;
}

function sourceLink(text, url) {
  const href = new URL(url);
  if (href.protocol !== "https:" || href.username || href.password) throw new Error("Invalid publication URL");
  const link = element("a", text);
  link.href = href.href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function card(record) {
  const row = element("article", "", "research-record");
  const meta = element("div", "", "record-meta");
  const timestamp = element("time", record.date);
  timestamp.dateTime = record.date;
  const issuer = element("p", record.institution, "record-issuer");
  const links = element("p", "", "official-link");
  const direct = noteFor(record.url);
  if (direct) links.append(analysisLink(direct, "Read analysis"));
  links.append(sourceLink("Source document", record.url));
  for (const related of record.related || []) {
    const relatedNote = noteFor(related.url);
    if (relatedNote && relatedNote !== direct) {
      links.append(analysisLink(relatedNote, related.label + " analysis"));
    }
    links.append(sourceLink(related.label, related.url));
  }
  meta.append(timestamp, element("span", record.type));
  if (viewFilter.value === "time") meta.append(element("span", record.jurisdiction));
  const heading = element("h4");
  if (direct) {
    heading.append(analysisLink(direct, record.title, "record-title-link"));
  } else {
    heading.textContent = record.title;
  }
  row.append(meta, heading, issuer);
  if (direct?.excerpt) row.append(element("p", direct.excerpt, "record-excerpt"));
  row.append(links);
  return row;
}

function renderByRegion(records) {
  const wrapper = element("div", "", "archive-region-view");
  const locations = targets.filter(({name}) => records.some(record => record.jurisdiction === name));
  for (const region of regions) {
    const banks = locations.filter(bank => bank.region === region);
    if (!banks.length) continue;
    const block = element("section", "", "archive-region");
    block.append(element("h3", region, "archive-region-title"));
    const jump = element("ul", "", "bank-jump");
    for (const bank of banks) {
      const entries = records.filter(record => record.jurisdiction === bank.name);
      const anchor = `${month.id}-bank-${bank.index}`;
      const link = element("a", bank.name);
      link.href = "#" + anchor;
      link.append(element("span", String(entries.length)));
      const listItem = element("li");
      listItem.append(link);
      jump.append(listItem);
      const section = element("section", "", "bank-section");
      section.id = anchor;
      const title = element("div", "", "bank-title");
      title.append(element("h3", bank.name));
      section.append(title, ...entries.map(card));
      block.append(section);
    }
    block.insertBefore(jump, block.children[1]);
    wrapper.append(block);
  }
  return wrapper;
}

function renderByTime(records) {
  const wrapper = element("div", "", "archive-timeline");
  let day;
  for (const record of records) {
    if (record.date !== day) {
      day = record.date;
      const group = element("section", "", "archive-timeline-day");
      const title = element("h3", dateLabel.format(new Date(day)));
      group.append(title);
      wrapper.append(group);
    }
    wrapper.lastElementChild.append(card(record));
  }
  return wrapper;
}

function stateUrl() {
  const url = new URL(location.href);
  url.searchParams.delete("analysis");
  url.searchParams.set("month", month.id);
  url.searchParams.set("scope", scope);
  for (const [key, input] of [["bank", bankFilter], ["type", typeFilter], ["q", queryFilter], ["view", viewFilter]]) {
    if (input.value) url.searchParams.set(key, input.value);
    else url.searchParams.delete(key);
  }
  return url;
}

function analysisLink(header, label, style = "analysis-action") {
  const link = element("a", label, style);
  const id = header.file.slice(0, -5);
  const url = stateUrl();
  url.searchParams.set("analysis", id);
  link.href = url.href;
  link.dataset.analysis = id;
  link.setAttribute("aria-haspopup", "dialog");
  return link;
}

async function readAnalysis(header) {
  const revision = ++readRevision;
  const article = select("manuscript");
  const status = select("reader-status");
  article.hidden = true;
  status.hidden = false;
  status.textContent = "Loading analysis…";
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
  select("close-analysis").focus({preventScroll:true});
  try {
    const note = await PublicationReader.load(header);
    if (revision !== readRevision || !dialog.open) return;
    PublicationReader.render(article, note, location.href);
    article.hidden = false;
    status.hidden = true;
  } catch {
    if (revision !== readRevision || !dialog.open) return;
    const retry = element("button", "Try again");
    retry.type = "button";
    retry.addEventListener("click", () => readAnalysis(header));
    status.replaceChildren(document.createTextNode("Analysis could not be loaded. "), retry);
  }
}

function dismissReader() {
  ++readRevision;
  if (dialog.open) dialog.close();
  if (opener?.isConnected) opener.focus({preventScroll:true});
}

function closeReader() {
  if (history.state?.archiveOverlay) {
    history.back();
  } else {
    const url = new URL(location.href);
    url.searchParams.delete("analysis");
    history.replaceState(null, "", url);
    dismissReader();
  }
}

container.addEventListener("click", event => {
  const link = event.target.closest("a[data-analysis]");
  if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
  const header = notesById.get(link.dataset.analysis);
  if (!header) return;
  event.preventDefault();
  opener = link;
  history.pushState({archiveOverlay:true}, "", link.href);
  readAnalysis(header);
});
dialog.addEventListener("cancel", event => { event.preventDefault(); closeReader(); });
dialog.addEventListener("click", event => { if (event.target === dialog) closeReader(); });
select("close-analysis").addEventListener("click", closeReader);

function render() {
  const query = queryFilter.value.trim().toLocaleLowerCase();
  const filtered = records.filter(record => {
    if (month.start > record.date || month.end < record.date ||
      (bankFilter.value && bankFilter.value !== record.jurisdiction) ||
      (typeFilter.value && typeFilter.value !== record.type)) return false;
    const matches = matchingNotes(record);
    if (scope === "analysis" && !noteFor(record.url)) return false;
    return !query || [record.title, record.institution, record.date, record.type,
      ...(record.related || []).map(link => link.label),
      ...matches.flatMap(note => [note.title, note.publication?.title || "", note.excerpt || ""])]
      .some(text => text.toLocaleLowerCase().includes(query));
  });
  const jurisdictions = new Set(filtered.map(record => record.jurisdiction)).size;
  result.textContent = filtered.length ? filtered.length + (filtered.length === 1 ? " publication" : " publications") +
    " · " + jurisdictions + (jurisdictions === 1 ? " jurisdiction" : " jurisdictions") : "No matching publications";
  const title = element("div", "", "month-title");
  const heading = element("h2", month.annual ? month.label : month.label + " " + month.start.slice(0,4));
  heading.id = "active-month-title";
  title.append(heading);
  const timeline = viewFilter.value === "time";
  select("archive-more").hidden = !timeline || visibleCount >= filtered.length;
  container.replaceChildren(title, timeline ? renderByTime(filtered.slice(0, visibleCount)) : renderByRegion(filtered));
  for (const button of select("archive-scope").querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.scope === scope));
  }
}

async function load(name) {
  const response = await fetch("data/" + name + ".json");
  if (!response.ok) throw new Error(name + " returned " + response.status);
  return response.json();
}

let ranges;
function setPeriod(period) {
  month = period;
  const year = month.id === "all" ? "all" : month.start.slice(0,4);
  yearFilter.value = year;
  const nav = select("archive-months");
  nav.replaceChildren();
  nav.hidden = year === "all";
  if (!nav.hidden) {
    for (const item of ranges.filter(x => x.start.startsWith(year) && x.id !== "all")) {
      const link = element("a", item.annual ? "Full year" : item.label.slice(0,3));
      link.setAttribute("aria-label", item.annual ? "All of " + year : item.label + " " + year);
      const url = stateUrl();
      url.searchParams.set("month", item.id);
      url.hash = "";
      link.href = url;
      if (item.id === month.id) link.setAttribute("aria-current", "page");
      nav.append(link);
    }
  }
}

function filtersChanged() {
  visibleCount = 60;
  setPeriod(month);
  const url = stateUrl();
  url.hash = "";
  history.replaceState(null,"",url);
  render();
}

async function start() {
  const [calendar, map, publications, notes] = await Promise.all([
    load("archive-periods"), load("world-map"), load("research-archive"), PublicationReader.index().catch(() => null)
  ]);
  targets = map.targets;
  const primaryUrls = new Set(publications.map(row => sourceKey(row.url)));
  const additional = [];
  for (const note of notes || []) {
    const key = sourceKey(note.url);
    const editions = [key,...(note.publication?.aliases || []).map(sourceKey)];
    for (const edition of editions) notesByUrl.set(edition, note);
    notesById.set(note.file.slice(0,-5), note);
    if (note.publication && !editions.some(edition => primaryUrls.has(edition))) {
      additional.push({...note.publication, url:note.url, date:note.date, institution:note.bank});
    }
  }
  records = publications.map(row => {
    const note = noteFor(row.url);
    if (!note) return row;
    const publication = note.publication;
    if (publication && publication.type !== row.type) {
      return {...row, date:note.date, type:publication.type, title:publication.title};
    }
    return row.date !== note.date ? {...row, date:note.date} : row;
  });
  records.push(...additional);
  records = mergeEditions(records);
  records.sort((a,b) => b.date.localeCompare(a.date) || a.title.localeCompare(b.title));
  const periodsByYear = new Map(calendar.map(item => [item.start.slice(0,7), item]));
  for (const record of records) {
    const key = record.date.slice(0,7);
    if (periodsByYear.has(key)) continue;
    const label = new Intl.DateTimeFormat("en-GB",{month:"long", timeZone:"UTC"}).format(new Date(record.date));
    const [year, number] = key.split("-").map(Number);
    const end = new Date(Date.UTC(year,number,0)).toISOString().slice(0,10);
    periodsByYear.set(key,{id:key,label,start:key+"-01",end});
  }
  periods = [...periodsByYear.values()].sort((a,b) => a.start.localeCompare(b.start));
  const years = [...new Set(periods.map(p => p.start.slice(0,4)))].sort().reverse();
  const annual = years.map(year => ({id:year === "2026" ? "year" : year, label:year, start:year+"-01-01",end:year+"-12-31",annual:true}));
  const all = {id:"all",label:"All years",start:"0000",end:"9999",annual:true};
  ranges = [all,...annual,...periods];
  yearFilter.append(new Option("All years","all"),...years.map(year => new Option(year,year)));
  bankFilter.append(new Option("All jurisdictions",""),...targets.map(bank => new Option(bank.name,bank.name)));
  typeFilter.append(new Option("All types",""),...[...new Set(records.map(r => r.type))].sort().map(type => new Option(type,type)));
  const hash = location.hash.slice(1);
  const id = params.get("month") || hash.split("-bank-")[0];
  scope = params.get("scope") === "all" || (!params.has("scope") && (id || params.has("bank") || params.has("q"))) || !notes ? "all" : "analysis";
  const requested = notesById.get(params.get("analysis"));
  const initial = ranges.find(period => period.id === id) || all;
  bankFilter.value = targets.some(x => x.name === params.get("bank")) ? params.get("bank") : "";
  typeFilter.value = [...typeFilter.options].some(o => o.value === params.get("type")) ? params.get("type") : "";
  queryFilter.value = params.get("q") || "";
  let saved;
  try { saved = sessionStorage.getItem("archive-view"); } catch {}
  const view = params.get("view") || (hash.includes("-bank-") ? "region" : saved);
  viewFilter.value = view === "region" ? "region" : "time";
  setPeriod(initial);
  form.hidden = false;
  select("archive-scope").hidden = !notes;
  select("archive-scope").addEventListener("click", event => {
    const button = event.target.closest("button");
    if (button) { scope=button.dataset.scope; filtersChanged(); }
  });
  form.addEventListener("input", event => {
    if (event.target === yearFilter) {
      month = yearFilter.value === "all" ? all : annual.find(p => p.label === yearFilter.value);
    }
    if (event.target === viewFilter) {
      try { sessionStorage.setItem("archive-view",viewFilter.value); } catch {}
    }
    filtersChanged();
  });
  form.addEventListener("reset", event => {
    event.preventDefault();
    bankFilter.value = typeFilter.value = queryFilter.value = "";
    month = all;
    filtersChanged();
  });
  form.addEventListener("submit", e => e.preventDefault());
  select("archive-more").addEventListener("click", () => {visibleCount += 60; render();});
  window.addEventListener("popstate", () => {
    const header = notesById.get(new URLSearchParams(location.search).get("analysis"));
    if (header) readAnalysis(header);
    else dismissReader();
  });
  render();
  if (hash.includes("-bank-")) select(hash)?.scrollIntoView();
  if (requested) readAnalysis(requested);
}

start().catch(error => {
  result.textContent = "Could not load the archive. Refresh the page to try again.";
  console.error(error);
});
