"use strict";

const byId = id => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat("en-GB", {day:"numeric", month:"short", year:"numeric", timeZone:"UTC"});
let notes = [];

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

async function showNote() {
  const revision = ++selection;
  const requested = new URLSearchParams(location.search).get("source");
  const header = requested ? notes.find(item => item.url === requested) : notes[0];
  const status = byId("note-status");
  const article = byId("manuscript");
  article.hidden = true;
  status.hidden = false;
  if (!header) status.textContent = requested ? "Research note unavailable." : "No research notes available.";
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
      const response = await fetch("data/notes/" + header.file);
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
  const limitation = byId("note-limitation");
  limitation.hidden = !note.limitation;
  limitation.textContent = note.limitation ? "Coverage · " + note.limitation : "";
}

async function startNotes() {
  const response = await fetch("data/research-notes.json");
  if (!response.ok) throw new Error("Notes unavailable");
  notes = (await response.json()).filter(note => {
    try {
      const url = new URL(note.url);
      return url.protocol === "https:" && !url.username && !url.password && /^[a-z0-9-]+\.json$/.test(note.file);
    } catch { return false; }
  }).sort((a,b) => b.date.localeCompare(a.date) || a.bank.localeCompare(b.bank) || a.title.localeCompare(b.title));
  const list = byId("note-index");
  for (const note of notes) {
    const li = document.createElement("li");
    const link = document.createElement("a");
    const date = node("time",dateFormat.format(new Date(note.date)));
    date.dateTime = note.date;
    link.href = permalink(note);
    link.dataset.source = note.url;
    link.append(date, node("span",note.title));
    li.append(link);
    list.append(li);
    byId("note-select").add(new Option(note.date + " · " + note.title,note.url));
  }
  byId("note-layout").hidden = !notes.length;
  byId("note-select").addEventListener("change", event => {
    history.pushState(null,"",permalink({url:event.target.value}));
    showNote();
  });
  window.addEventListener("popstate",showNote);
  showNote();
}
startNotes().catch(() => { byId("note-status").hidden = false; byId("note-status").textContent = "Research notes unavailable."; });
