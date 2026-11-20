"use strict";

const byId = id => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat("en-GB", {day:"numeric", month:"short", year:"numeric", timeZone:"UTC"});
let notes = [];
let matching = [];
let page = 0;
const perPage = 30;

function permalink(note) {
  return "research-notes.html?" + new URLSearchParams({source:note.url});
}

function node(tag, text) {
  const el = document.createElement(tag);
  el.textContent = text;
  return el;
}

let selection = 0;
const manuscripts = new Map();
const release = document.currentScript && new URL(document.currentScript.src).search;

// Verified FOMC policy-statement documents. The generic monetary press-release
// path is also used for minutes, facilities, projections and implementation notes.
const fomcStatementDates = new Set(`20080916 20110126 20110315 20110427 20110622 20110809 20110921 20111102 20111213
20120125 20120313 20120425 20120620 20120801 20120913 20121024 20121212 20130130
20130320 20130501 20130619 20130731 20130918 20131030 20131218 20140129 20140319
20140430 20140618 20140730 20140917 20141029 20141217 20150128 20150318 20150429
20150617 20150729 20150917 20151028 20151216 20160127 20160316 20160427 20160615
20160727 20160921 20161102 20161214 20170201 20170315 20170503 20170614 20170726
20170920 20171101 20171213 20180131 20180321 20180502 20180613 20180801 20180926
20181108 20181219 20190130 20190320 20190501 20190619 20190731 20190918
20191030 20191211 20200129 20200303 20200315 20200323 20200429 20200610 20200729
20200916 20201105 20201216 20210127 20210317 20210428 20210616 20210728 20210922
20211103 20211215 20220126 20220316 20220504 20220615 20220727 20220921 20221102
20221214 20230201 20230322 20230503 20230614 20230726 20230920 20231101 20231213
20240131 20240320 20240501 20240612 20240731 20240918 20241107 20241218 20250129
20250319 20250507 20250618 20250730 20250917 20251029 20251210 20260128 20260318
20260429 20260617 20260729 20260916 20261028`.split(/\s+/));
let eventBanks;

function identifyEventSource(note) {
  const source = new URL(note.url);
  const stamp = note.date.replaceAll("-", "");
  if (source.protocol !== "https:" || source.username || source.password || source.port) return;
  if (source.hostname === "www.federalreserve.gov") {
    if (fomcStatementDates.has(stamp) && source.pathname === "/newsevents/pressreleases/monetary" + stamp + "a.htm") {
      return {bank: "fed", window: "statement"};
    }
    if (source.pathname === "/monetarypolicy/fomcpresconf" + stamp + ".htm" ||
        source.pathname === "/mediacenter/files/FOMCpresconf" + stamp + ".pdf") {
      return {bank: "fed", window: "conference"};
    }
  }
  if (source.hostname !== "www.ecb.europa.eu") return;
  const conference = /^\/press\/press_conference\/monetary-policy-statement\/(\d{4})\/html\/(?:ecb\.)?is(\d{6})(?:~[a-f0-9]+)?\.[a-z]{2}\.html$/.exec(source.pathname);
  const statement = /^\/press\/pr\/date\/(\d{4})\/html\/ecb\.mp(\d{6})(?:~[a-f0-9]+)?\.[a-z]{2}\.html$/.exec(source.pathname);
  const match = conference || statement;
  if (match && match[1] === stamp.slice(0, 4) && match[2] === stamp.slice(2)) {
    return {bank: "ecb", window: conference ? "conference" : "statement"};
  }
}

async function showMarketWindow(note, revision) {
  const identity = identifyEventSource(note);
  if (!identity) return;
  eventBanks ??= fetch("data/market-events.json").then(response => {
    if (!response.ok) throw Error(response.status);
    return response.json();
  }).then(data => Array.isArray(data.banks) ? data.banks : []).catch(() => {
    eventBanks = undefined;
    return [];
  });
  const banks = await eventBanks;
  if (selection !== revision) return;
  const bank = banks.find(item => item.id === identity.bank);
  if (!Array.isArray(bank?.events) || !Array.isArray(bank.assets) || !bank.windows?.[identity.window]) return;
  const values = bank.events.find(event => event.date === note.date)?.windows?.[identity.window];
  if (!values) return;
  const instruments = bank.id === "fed" ? ["UST2Y", "UST10Y", "EURUSD", "SP500"] : ["DE2Y", "DE10Y", "EURUSD", "STOXX50"];
  const measured = instruments.map(id => bank.assets.find(asset => asset.id === id))
    .filter(asset => asset && Number.isFinite(values[asset.id]));
  if (!measured.length) return;
  const moves = document.createDocumentFragment();
  for (const asset of measured) {
    const cell = document.createElement("div");
    const figure = new Intl.NumberFormat("en-GB", {minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero"}).format(values[asset.id]);
    cell.append(node("dt", asset.label), node("dd", figure + (asset.unit === "bp" ? " bp" : "%")));
    moves.append(cell);
  }
  byId("note-moves").replaceChildren(moves);
  byId("note-window").textContent = (identity.window === "conference" ? "Press conference" : "Policy statement") + " · " + bank.windows[identity.window];
  byId("note-window-source").textContent = bank.sourceLabel;
  byId("note-window-source").href = bank.source;
  const params = new URLSearchParams({bank: bank.id, window: identity.window, date: note.date, asset: measured[0].id});
  byId("note-event-link").href = "market-reactions.html?" + params;
  byId("note-market").hidden = false;
}

async function showNote(header, unavailable = false) {
  const revision = ++selection;
  byId("note-market").hidden = true;
  const status = byId("note-status");
  const article = byId("manuscript");
  article.hidden = true;
  status.hidden = false;
  if (!header) status.textContent = unavailable ? "Research note unavailable." : "";
  byId("note-select").value = header?.url || "";
  for (const link of byId("note-index").querySelectorAll("a")) {
    if (header && link.dataset.source === header.url) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (!header) return;
  status.textContent = "Loading research note…";
  let note = manuscripts.get(header.url);
  if (!note) {
    try {
      const response = await fetch("data/notes/" + header.file + (release || ""));
      if (!response.ok) throw Error(response.status);
      note = await response.json();
      if (note.url !== header.url) throw Error("Source mismatch");
      manuscripts.set(note.url, note);
    } catch {
      if (selection === revision) status.textContent = "The research note could not be loaded.";
      return;
    }
  }
  if (selection !== revision) return;
  status.hidden = true;
  article.hidden = false;
  document.title = note.title + " · Central Bank Intelligence";
  byId("note-bank").textContent = note.bank;
  byId("note-date").dateTime = note.date;
  byId("note-date").textContent = dateFormat.format(new Date(note.date));
  byId("note-title").textContent = note.title;
  byId("note-source").href = note.url;
  byId("note-permalink").href = permalink(note);
  byId("note-summary").replaceChildren(...note.summary.map(text => node("p",text)));
  byId("note-questions").replaceChildren(...note.questions.map(item => {
    const li = document.createElement("li");
    li.append(node("h4", item.question), node("p", item.detail));
    return li;
  }));
  showMarketWindow(note, revision);
  const limitation = byId("note-limitation");
  limitation.hidden = !note.limitation;
  limitation.textContent = note.limitation ? "Coverage · " + note.limitation : "";
}

async function startNotes() {
  const response = await fetch("data/research-notes.json" + (release || ""));
  if (!response.ok) throw new Error("Notes unavailable");
  notes = (await response.json()).filter(note => {
    try {
      const url = new URL(note.url);
      return url.protocol === "https:" && !url.username && !url.password && /^[a-z0-9-]+\.json$/.test(note.file);
    } catch { return false; }
  }).sort((a,b) => b.date.localeCompare(a.date) || a.bank.localeCompare(b.bank) || a.title.localeCompare(b.title));
  for (const year of [...new Set(notes.map(note => note.date.slice(0,4)))]) {
    byId("note-year").add(new Option(year, year));
  }
  for (const bank of [...new Set(notes.map(note => note.bank))].sort((a,b) => a.localeCompare(b))) {
    byId("note-institution").add(new Option(bank, bank));
  }
  byId("note-layout").hidden = !notes.length;
  byId("note-filter").addEventListener("submit", e => e.preventDefault());
  byId("note-filter").addEventListener("input", () => {
    const params = filterParams();
    history.replaceState(null, "", location.pathname + (params.size ? "?" + params : ""));
    render();
  });
  byId("note-select").addEventListener("change", e => openNote(e.target.value));
  byId("note-prev").addEventListener("click", () => openNote(matching[(page - 1) * perPage].url));
  byId("note-next").addEventListener("click", () => openNote(matching[(page + 1) * perPage].url));
  window.addEventListener("popstate", render);
  render();
}

function filterParams() {
  const params = new URLSearchParams();
  for (const [key, id] of [["q", "note-query"], ["year", "note-year"], ["bank", "note-institution"]]) {
    const value = byId(id).value;
    if (value) params.set(key, value);
  }
  return params;
}

function readerUrl(source) {
  const params = filterParams();
  params.set("source", source);
  return "research-notes.html?" + params;
}

function openNote(url) {
  history.pushState(null, "", readerUrl(url));
  render();
}

function render() {
  const params = new URLSearchParams(location.search);
  const search = byId("note-query");
  const query = params.get("q") || "";
  if (search.value !== query) search.value = query;
  byId("note-year").value = params.get("year") || "";
  byId("note-institution").value = params.get("bank") || "";
  const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  const year = byId("note-year").value;
  const bank = byId("note-institution").value;
  matching = notes.filter(note => (!bank || note.bank === bank) && (!year || note.date.startsWith(year))
    && terms.every(term => note.title.toLocaleLowerCase().includes(term)));
  const requested = params.get("source");
  const selectedIndex = requested ? matching.findIndex(note => note.url === requested) : 0;
  page = Math.max(0, Math.floor(selectedIndex / perPage));
  const start = page * perPage;
  const visible = matching.slice(start,start + perPage);
  const total = matching.length;
  const label = total === 1 ? "note" : "notes";
  byId("note-matches").textContent = total > perPage ? (start + 1) + "–" + (start + visible.length) + " of " + total + " " + label
    : total ? total + " " + label : "No matching notes";
  const list = byId("note-index");
  const chooser = byId("note-select");
  list.replaceChildren(); chooser.replaceChildren();
  chooser.disabled = !total;
  for (const note of visible) {
    const li = document.createElement("li");
    const link = document.createElement("a");
    const date = node("time",dateFormat.format(new Date(note.date)));
    date.dateTime = note.date;
    link.href = readerUrl(note.url);
    link.dataset.source = note.url;
    link.append(date, node("span",note.title));
    li.append(link);
    list.append(li);
    chooser.add(new Option(note.date + " · " + note.title,note.url));
  }
  byId("note-pager").hidden = total <= perPage;
  byId("note-prev").disabled = page === 0;
  byId("note-next").disabled = (page + 1) * perPage >= total;
  showNote(matching[selectedIndex], Boolean(requested));
}
startNotes().catch(() => { byId("note-status").hidden = false; byId("note-status").textContent = "Research notes unavailable."; });
