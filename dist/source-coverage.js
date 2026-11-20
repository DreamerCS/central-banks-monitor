"use strict";

async function loadCoverageData(name) {
  const response = await fetch(`data/${name}.json`);
  if (!response.ok) throw new Error(`${name} returned ${response.status}`);
  return response.json();
}

async function renderCoverage() {
  const [{targets}, periods, records] = await Promise.all(
    ["coverage", "archive-periods", "research-archive"].map(loadCoverageData),
  );
  const counts = new Map();
  for (const {jurisdiction, date} of records) {
    const key = `${jurisdiction}:${date.slice(0, 7)}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const head = document.querySelector("#coverage-head");
  for (const period of periods) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = period.label;
    head.append(cell);
  }
  const body = document.querySelector("#coverage-rows");
  const sorted = [...targets].sort((a, b) => a.name.localeCompare(b.name));
  for (const target of sorted) {
    const row = body.insertRow();
    const name = document.createElement("th");
    name.scope = "row";
    name.textContent = target.name;
    row.append(name);
    row.insertCell().textContent = target.sourceCount;
    for (const period of periods) {
      const count = counts.get(`${target.name}:${period.start.slice(0, 7)}`) ?? 0;
      const link = document.createElement("a");
      const params = new URLSearchParams({month: period.id, bank: target.name});
      link.href = `research-archive.html?${params}#${period.id}`;
      link.textContent = count;
      link.setAttribute("aria-label", `${target.name}, ${period.label}: ${count} publications`);
      row.insertCell().append(link);
    }
  }
  document.querySelector(".coverage-scroll").hidden = false;
  document.querySelector("#coverage-load").hidden = true;
}

renderCoverage().catch(error => {
  document.querySelector("#coverage-load").textContent = "Could not load publication counts. Refresh the page to try again.";
  console.error(error);
});
