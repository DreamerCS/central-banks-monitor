const id = (name) => document.getElementById(name);
const banks = ["US", "GB", "EA"];
const names = { US: "United States", GB: "United Kingdom", EA: "Euro area" };
const calendar = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const number = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 });
const displayDate = (day) => calendar.format(new Date(day + "T12:00:00Z"));
const signed = (value) => (value > 0 ? "+" : "") + number.format(value).replace("-", "−");
const rate = (value) => number.format(value).replace("-", "−") + "%";
const selectedYear = () => {
  const query = new URLSearchParams(location.search);
  return query.get("historyYear") || query.get("year");
};

function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}

function rowWithHeading(heading, cells) {
  const tr = document.createElement("tr");
  const th = element("th", typeof heading === "string" ? heading : "");
  th.scope = "row";
  if (typeof heading !== "string") th.append(heading);
  tr.append(th, ...cells.map((value) => element("td", value)));
  return tr;
}

function yearUrl(year) {
  const url = new URL(location.href);
  url.searchParams.set("historyYear", year);
  url.searchParams.delete("year");
  return url;
}

async function initialize() {
  const response = await fetch("data/policy-year-ledger.json");
  if (!response.ok) throw new Error("Could not load rate history");
  const data = await response.json();
  const years = Object.keys(data.years).sort().reverse();
  const chooser = id("ledger-year");
  const yearLinks = new Map();

  for (const year of years) {
    const option = element("option", year);
    option.value = year;
    chooser.append(option);

    const link = element("a", year);
    const url = yearUrl(year);
    url.hash = "annual-policy-ledger";
    link.href = url.href;
    link.addEventListener("click", (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      select(year);
      chooser.focus();
    });
    const series = data.years[year].banks;
    const values = banks.map((bank) => signed(series[bank].net));
    id("ledger-matrix").append(rowWithHeading(link, values));
    yearLinks.set(year, link);
  }
  for (const bank of banks) {
    const meta = data.banks[bank];
    const link = element("a", meta.bank + " · " + meta.instrument);
    link.href = meta.url;
    id("ledger-sources").append(link);
    if (meta.dataUrl) {
      const series = element("a", (bank === "US" ? "FRED" : "ECB") + " daily observations (CSV)");
      series.href = meta.dataUrl;
      id("ledger-sources").append(series);
    }
  }

  function select(year) {
    render(year);
    history.replaceState(history.state, "", yearUrl(year));
    window.dispatchEvent(new CustomEvent("historyyearchange", { detail: { year } }));
  }

  function render(requested) {
    const year = Object.hasOwn(data.years, requested) ? String(requested) : years[0];
    const series = data.years[year].banks;
    const record = data.years[year].record;
    const until = year === data.through.slice(0, 4) ? data.through : year + "-12-31";
    chooser.value = year;
    for (const [value, link] of yearLinks) {
      if (value === year) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
    id("ledger-status").textContent = year + " · " + (until.endsWith("-12-31") ? "Full calendar year" : "Year to date") + " through " + displayDate(until);
    id("ledger-totals").replaceChildren(...banks.map((bank) => {
      const values = series[bank];
      return rowWithHeading(names[bank], [rate(values.open), number.format(values.hikes), number.format(values.cuts), signed(values.net), rate(values.close)]);
    }));
    const moves = banks.flatMap((bank) => series[bank].moves.map((m) => ({ bank, day: m[0], from: m[1], to: m[2], change: m[3] })));
    moves.sort((a, b) => a.day.localeCompare(b.day));
    id("ledger-moves-title").textContent = "Dated rate changes (" + moves.length + ")";
    if (moves.length) {
      const table = document.createElement("table");
      table.className = "policy-path-table ledger-grid";
      const header = table.createTHead().insertRow();
      for (const cell of ["Date in series", "Jurisdiction", "From", "To", "Move · bp"]) {
        const th = element("th", cell);
        th.scope = "col";
        header.append(th);
      }
      const body = table.createTBody();
      for (const move of moves) {
        body.append(rowWithHeading(displayDate(move.day), [names[move.bank], rate(move.from), rate(move.to), signed(move.change)]));
      }
      const panel = id("ledger-moves");
      panel.className = "policy-table-scroll";
      panel.tabIndex = 0;
      panel.setAttribute("role", "region");
      panel.setAttribute("aria-label", year + " effective rate changes");
      panel.replaceChildren(table);
    } else {
      const panel = id("ledger-moves");
      panel.removeAttribute("tabindex");
      panel.removeAttribute("role");
      panel.removeAttribute("aria-label");
      panel.replaceChildren(element("p", "No changes in these three published rates during " + year + "."));
    }
    const article = id("ledger-record-title").closest("article");
    article.hidden = !record;
    if (record) {
      id("ledger-record-date").textContent = displayDate(record.date) + " · " + record.instrument;
      id("ledger-record-title").textContent = record.title;
      id("ledger-record-analysis").textContent = record.analysis;
      const source = id("ledger-record-source");
      source.textContent = data.banks[record.bank].bank + " · original decision ↗";
      source.href = record.url;
    }
    const book = id("ledger-yearbook");
    book.href = "yearbook.html?historyYear=" + year;
    book.textContent = "Read the " + year + " historical case and compare growth and inflation →";
  }

  render(selectedYear());
  chooser.disabled = false;
  id("ledger-body").hidden = false;
  chooser.addEventListener("change", () => select(chooser.value));
  window.addEventListener("historyyearchange", (event) => {
    if (Object.hasOwn(data.years, event.detail?.year) && String(event.detail.year) !== chooser.value) render(event.detail.year);
  });
  window.addEventListener("popstate", () => render(selectedYear()));
}

initialize().catch(() => {
  id("ledger-status").textContent = "The policy ledger could not load. ";
  const link = element("a", "Open the annual data file");
  link.href = "data/policy-year-ledger.json";
  id("ledger-status").append(link);
});
