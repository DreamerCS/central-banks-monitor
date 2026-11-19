"use strict";

const form = document.querySelector("#archive-filters");
const bankFilter = document.querySelector("#bank-filter");
const typeFilter = document.querySelector("#type-filter");
const queryFilter = document.querySelector("#query-filter");
const notesFilter = document.querySelector("#notes-filter");
const viewFilter = document.querySelector("#view-filter");
const result = document.querySelector("#archive-results");
const months = [...document.querySelectorAll(".archive-month")];
const monthLinks = [...document.querySelectorAll(".archive-nav nav a")];
const params = new URLSearchParams(location.search);
const monthParam = params.get("month");
const hashMonth = location.hash.match(/^#(oct|nov)(?:$|-)/)?.[1];
const activeMonth = ["oct", "nov"].includes(monthParam) ? monthParam : (hashMonth || "oct");

function savedView() {
  try {
    return sessionStorage.getItem("archive-view");
  } catch {
    return null;
  }
}

if ([...bankFilter.options].some((option) => option.value === params.get("bank"))) {
  bankFilter.value = params.get("bank");
}
queryFilter.value = params.get("q") || "";
const initialView = params.get("view") || (location.hash.includes("-bank-") ? "region" : savedView());
viewFilter.value = initialView === "time" ? "time" : "region";

form.hidden = false;
for (const month of months) month.hidden = month.id !== activeMonth;
const current = document.getElementById(activeMonth);
const regionView = current.querySelector(".archive-region-view");
const timeline = current.querySelector(".archive-timeline");
const groups = [...regionView.querySelectorAll(".bank-section")];
const groupRecords = new Map(groups.map((group) => [group, [...group.querySelectorAll(".research-record")]]));
const jumpItems = new Map([...regionView.querySelectorAll(".bank-jump li")].map((li) => [
  li.querySelector("a").hash.slice(1), li,
]));
const records = groups.flatMap((group) => groupRecords.get(group).map((record) => ({record, group})));
const chronological = [...records].sort((a, b) =>
  b.record.dataset.date.localeCompare(a.record.dataset.date) ||
  a.record.querySelector("h4").textContent.localeCompare(b.record.querySelector("h4").textContent)
);
let layout;

for (const link of monthLinks) {
  if (link.hash === `#${activeMonth}`) link.setAttribute("aria-current", "page");
}

function applyView() {
  const byTime = viewFilter.value === "time";
  if (layout === byTime) return;
  layout = byTime;
  regionView.hidden = byTime;
  timeline.hidden = !byTime;
  if (byTime) {
    const fragment = document.createDocumentFragment();
    let lastDay;
    for (const {record, group} of chronological) {
      const day = record.dataset.date;
      if (day !== lastDay) {
        const dayGroup = document.createElement("section");
        dayGroup.className = "archive-timeline-day";
        const header = document.createElement("h3");
        const date = document.createElement("time");
        date.dateTime = day;
        date.textContent = new Intl.DateTimeFormat("en-GB", {
          day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
        }).format(new Date(day));
        header.append(date);
        dayGroup.append(header);
        fragment.append(dayGroup);
        lastDay = day;
      }
      let bank = record.querySelector(".record-region-label");
      if (!bank) {
        bank = document.createElement("span");
        bank.className = "record-region-label";
        bank.textContent = group.dataset.bank;
        record.querySelector(".record-meta").append(bank);
      }
      fragment.lastElementChild.append(record);
    }
    timeline.replaceChildren(fragment);
  } else {
    for (const [group, entries] of groupRecords) {
      const before = group.querySelector(".register-links");
      for (const record of entries) group.insertBefore(record, before);
    }
    timeline.replaceChildren();
  }
}

function filterArchive() {
  let visibleDocuments = 0;
  let visibleBanks = 0;
  const query = queryFilter.value.trim().toLocaleLowerCase();
  const filterDocuments = typeFilter.value || query || notesFilter.checked;
  for (const group of groups) {
    const bankSelected = !bankFilter.value || group.dataset.bank === bankFilter.value;
    let matches = 0;
    for (const record of groupRecords.get(group)) {
      const show = bankSelected &&
        (!typeFilter.value || record.dataset.type === typeFilter.value) &&
        (!query || record.dataset.search.includes(query)) &&
        (!notesFilter.checked || record.dataset.analysed === "true");
      record.hidden = !show;
      if (show) matches += 1;
    }
    const showBank = bankSelected && (!filterDocuments || matches > 0) && (!layout || matches > 0);
    group.hidden = !showBank;
    jumpItems.get(group.id).hidden = !showBank;
    if (showBank) {
      visibleBanks += 1;
      visibleDocuments += matches;
    }
  }
  for (const block of regionView.querySelectorAll(".archive-region, .archive-continent")) {
    block.hidden = !block.querySelector(".bank-section:not([hidden]), .bank-jump li:not([hidden])");
  }
  for (const day of timeline.querySelectorAll(".archive-timeline-day")) {
    day.hidden = !day.querySelector(".research-record:not([hidden])");
  }
  result.textContent = `${visibleDocuments} ${visibleDocuments === 1 ? "publication" : "publications"} · ${visibleBanks} ${visibleBanks === 1 ? "jurisdiction" : "jurisdictions"} shown`;
}

form.addEventListener("input", (event) => {
  if (event.target === viewFilter) {
    try {
      sessionStorage.setItem("archive-view", viewFilter.value);
    } catch {
      // The view still works when browser storage is unavailable.
    }
    applyView();
  }
  filterArchive();
});
form.addEventListener("submit", (event) => event.preventDefault());
form.addEventListener("reset", (event) => {
  event.preventDefault();
  bankFilter.value = "";
  typeFilter.value = "";
  queryFilter.value = "";
  notesFilter.checked = false;
  filterArchive();
});
applyView();
filterArchive();
