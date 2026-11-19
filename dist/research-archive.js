"use strict";

const form = document.querySelector("#archive-filters");
const bankFilter = document.querySelector("#bank-filter");
const typeFilter = document.querySelector("#type-filter");
const queryFilter = document.querySelector("#query-filter");
const notesFilter = document.querySelector("#notes-filter");
const result = document.querySelector("#archive-results");
const months = [...document.querySelectorAll(".archive-month")];
const monthLinks = [...document.querySelectorAll(".archive-nav nav a")];
const monthParam = new URLSearchParams(location.search).get("month");
const hashMonth = location.hash.match(/^#(oct|nov)(?:$|-)/)?.[1];
const activeMonth = ["oct", "nov"].includes(monthParam) ? monthParam : (hashMonth || "oct");

form.hidden = false;
for (const month of months) month.hidden = month.id !== activeMonth;
for (const link of monthLinks) {
  if (link.hash === `#${activeMonth}`) link.setAttribute("aria-current", "page");
}

const groups = [...document.querySelectorAll(`#${activeMonth} .bank-section`)];
const jumpItems = [...document.querySelectorAll(`#${activeMonth} .bank-jump li`)];

function filterArchive() {
  let visibleDocuments = 0;
  let visibleBanks = 0;
  const query = queryFilter.value.trim().toLocaleLowerCase();
  const filterDocuments = typeFilter.value || query || notesFilter.checked;

  groups.forEach((group, index) => {
    const bankSelected = !bankFilter.value || group.dataset.bank === bankFilter.value;
    let matches = 0;
    for (const record of group.querySelectorAll(".research-record")) {
      const show = bankSelected &&
        (!typeFilter.value || record.dataset.type === typeFilter.value) &&
        (!query || record.dataset.search.includes(query)) &&
        (!notesFilter.checked || record.dataset.analysed === "true");
      record.hidden = !show;
      if (show) matches += 1;
    }
    const showBank = bankSelected && (!filterDocuments || matches > 0);
    group.hidden = !showBank;
    jumpItems[index].hidden = !showBank;
    if (showBank) {
      visibleBanks += 1;
      visibleDocuments += matches;
    }
  });
  result.textContent = `${visibleDocuments} ${visibleDocuments === 1 ? "publication" : "publications"} · ${visibleBanks} ${visibleBanks === 1 ? "jurisdiction" : "jurisdictions"} shown`;
}

form.addEventListener("input", filterArchive);
form.addEventListener("submit", (event) => event.preventDefault());
form.addEventListener("reset", () => requestAnimationFrame(filterArchive));
filterArchive();
