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
let month, targets, monthRecords;

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
  links.append(sourceLink("Source document", record.url));
  for (const related of record.related ?? []) {
    links.append(document.createTextNode(" · "), sourceLink(related.label, related.url));
  }
  meta.append(timestamp, element("span", record.type));
  if (viewFilter.value === "time") meta.append(element("span", record.jurisdiction));
  row.append(meta, element("h4", record.title), issuer, links);
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

function render() {
  const query = queryFilter.value.trim().toLocaleLowerCase();
  const records = monthRecords.filter(record =>
    (!bankFilter.value || bankFilter.value === record.jurisdiction) &&
    (!typeFilter.value || typeFilter.value === record.type) &&
    (!query || [record.title, record.institution, record.date, record.type].some(text => text.toLocaleLowerCase().includes(query)))
  );
  const jurisdictions = new Set(records.map(record => record.jurisdiction)).size;
  const total = records.length;
  const summary = `${total} ${total === 1 ? "publication" : "publications"} · ${jurisdictions} ${jurisdictions === 1 ? "jurisdiction" : "jurisdictions"}`;
  result.textContent = total ? summary : "No matching publications";
  const title = element("div", "", "month-title");
  const heading = element("h2", `${month.label} ${month.start.slice(0, 4)}`);
  heading.id = "active-month-title";
  title.append(heading, element("p", `${month.start} to ${month.end}`));
  container.replaceChildren(title, viewFilter.value === "time" ? renderByTime(records) : renderByRegion(records));
}

async function load(name) {
  const response = await fetch(`data/${name}.json`);
  if (!response.ok) throw new Error(name + " returned " + response.status);
  return response.json();
}

async function start() {
  const [periods, map, records] = await Promise.all(["archive-periods", "world-map", "research-archive"].map(load));
  targets = map.targets;
  const hash = location.hash.slice(1);
  month = [params.get("month"), hash.split("-")[0], "oct"].map(id => periods.find(period => period.id === id)).find(Boolean) ?? periods[0];
  monthRecords = records.filter(record => month.start <= record.date && record.date <= month.end);
  for (const period of periods) {
    const link = element("a", period.label);
    link.href = `?month=${period.id}#${period.id}`;
    if (period.id === month.id) link.setAttribute("aria-current", "page");
    select("archive-months").append(link);
  }
  bankFilter.append(new Option("All jurisdictions", ""), ...targets.map(bank => new Option(bank.name, bank.name)));
  typeFilter.append(new Option("All types", ""), ...[...new Set(records.map(record => record.type))].sort().map(type => new Option(type, type)));
  const bank = params.get("bank");
  if (targets.some(target => target.name === bank)) bankFilter.value = bank;
  queryFilter.value = params.get("q") ?? "";
  let previousView;
  try { previousView = sessionStorage.getItem("archive-view"); } catch {}
  const initialView = params.get("view") ?? (hash.includes("-bank-") ? "region" : previousView);
  viewFilter.value = initialView === "time" ? "time" : "region";
  form.hidden = false;
  form.addEventListener("input", event => {
    if (event.target === viewFilter) {
      try { sessionStorage.setItem("archive-view", viewFilter.value); } catch {}
    }
    render();
  });
  form.addEventListener("reset", event => {
    event.preventDefault();
    bankFilter.value = typeFilter.value = queryFilter.value = "";
    render();
  });
  form.addEventListener("submit", event => event.preventDefault());
  render();
  if (hash.includes("-bank-")) select(hash)?.scrollIntoView();
}

start().catch(error => {
  result.textContent = "Could not load the archive. Refresh the page to try again.";
  console.error(error);
});
