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
async function showNote(header, unavailable = false) {
  const revision = ++selection;
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
  let note;
  try {
    note = await PublicationReader.load(header);
  } catch {
    if (selection === revision) status.textContent = "The research note could not be loaded.";
    return;
  }
  if (selection !== revision) return;
  status.hidden = true;
  article.hidden = false;
  document.title = note.title + " · Central Bank Intelligence";
  PublicationReader.render(article, note, permalink(note));
}

async function startNotes() {
  notes = (await PublicationReader.index()).sort((a,b) => b.date.localeCompare(a.date) || a.bank.localeCompare(b.bank) || a.title.localeCompare(b.title));
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
