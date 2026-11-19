"use strict";

const select = (id) => document.getElementById(id);
const params = new URLSearchParams(window.location.search);

function node(tag, value) {
  const element = document.createElement(tag);
  if (value) element.textContent = value;
  return element;
}

function primaryLink(url, label) {
  const link = node("a", label);
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

async function readData(path) {
  const response = await fetch(`data/${path}.json`, {cache: "no-cache"});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function table(headers, rows) {
  const container = node("div");
  container.className = "check-table";
  const grid = node("table");
  const heading = grid.createTHead().insertRow();
  for (const text of headers) {
    const header = node("th", text);
    header.scope = "col";
    heading.append(header);
  }
  const body = grid.createTBody();
  for (const values of rows) {
    const row = body.insertRow();
    for (const value of values) row.insertCell().append(value);
  }
  container.append(grid);
  return container;
}

function renderChecks(targets, checks, review) {
  const container = select("source-checks");
  for (const bank of targets) {
    const channels = checks.filter((channel) => channel.bank === bank);
    const read = channels.filter((channel) => channel.status === "Read").length;
    const details = node("details");
    const summary = node("summary", bank);
    summary.append(node("span", channels.length
      ? `${read}/${channels.length} channels read`
      : "Directory links and archive only"));
    details.append(summary);
    details.open = bank === params.get("bank");
    if (channels.length) {
      const rows = channels.map((channel) => {
        const name = node("div");
        name.append(primaryLink(channel.url, channel.label), node("small", channel.institution));
        return [name, channel.method, channel.status, channel.last ?? "—"];
      });
      details.append(table(["Official channel", "Method", "Last check", "Latest item returned"], rows));
    }
    if (review) {
      const count = (month, key) => review.monthly[month][key][bank] ?? 0;
      const october = `October ${count("2026-10", "indexed")} indexed · ${count("2026-10", "review")} to review`;
      const november = `November ${count("2026-11", "indexed")} indexed · ${count("2026-11", "review")} to review`;
      details.append(node("small", `${october}  /  ${november}`));
    }
    container.append(details);
  }
}

function renderEurope(sources, checks) {
  const channels = new Map(checks.map((channel) => [channel.url, channel]));
  const entries = sources.filter((source) => source.workbook?.includes("Europe Policies & Models"));
  const rows = entries.map((source) => {
    const channel = channels.get(source.feed) ?? channels.get(source.url);
    const status = channel ? `${channel.method} · ${channel.status}` : "Directory link";
    const name = primaryLink(source.url, source.institution);
    return [name, source.category, source.sourceType, status];
  });
  select("europe-register").append(table(["Institution", "Category", "Register entry", "Monitoring"], rows));
}

function renderReview(review, targets) {
  const indexed = Object.values(review.monthly).reduce(
    (total, month) => total + Object.values(month.indexed).reduce((sum, count) => sum + count, 0), 0);
  select("review-count").textContent = `${indexed} indexed publications · ${review.items.length} unmatched official links to review.`;
  const month = select("review-month");
  const bank = select("review-bank");
  const type = select("review-type");
  const entries = select("review-entries");
  for (const name of targets) bank.add(new Option(name, name));
  for (const kind of [...new Set(review.items.map((item) => item.type))].sort()) {
    type.add(new Option(kind, kind));
  }
  if (targets.includes(params.get("bank"))) bank.value = params.get("bank");
  month.value = params.get("month") === "2026-10" ? "2026-10" : "2026-11";
  const update = () => {
    const filtered = review.items.filter((item) => item.day.startsWith(month.value) &&
      (!bank.value || item.bank === bank.value) && (!type.value || item.type === type.value));
    select("review-selection").textContent = filtered.length
      ? `${filtered.length} unmatched links in this view.`
      : "This check found no unmatched links for the selected filters.";
    entries.replaceChildren(...filtered.map((item) => {
      const li = node("li");
      li.append(primaryLink(item.url, item.title), node("small",
        `${item.day} · ${item.bank} · ${item.institution} · ${item.type}`));
      return li;
    }));
  };
  select("review-filters").addEventListener("change", update);
  select("review-filters").hidden = false;
  update();
}

async function start() {
  const results = await Promise.allSettled([
    readData("coverage"), readData("sources"), readData("world-map-activity"), readData("archive-review"),
  ]);
  const [coverage, directory, snapshot, review] = results.map((result) => result.value);
  const targets = (coverage?.targets ?? []).map((target) => target.name);
  const checks = snapshot?.checks ?? [];
  if (checks.length) {
    const rss = checks.filter((channel) => channel.method === "RSS");
    const pages = checks.filter((channel) => channel.method === "Listing");
    const count = (set) => set.filter((channel) => channel.status === "Read").length;
    const active = new Set(checks.filter((channel) => channel.status === "Read").map((channel) => channel.bank));
    select("coverage-check").textContent = `${count(rss)}/${rss.length} RSS feeds and ${count(pages)}/${pages.length} official listings read across ${active.size}/29 jurisdictions on ${snapshot.checkedAt.slice(0, 10)} UTC.`;
    if (targets.length) renderChecks(targets, checks, review);
  } else {
    select("coverage-check").textContent = "Daily check results are unavailable.";
  }
  if (review && targets.length) renderReview(review, targets);
  else select("review-count").textContent = "The archive comparison is unavailable.";
  if (directory) renderEurope(directory.sources, checks);
  else select("europe-register").textContent = "Register entries are unavailable.";
}

start();
