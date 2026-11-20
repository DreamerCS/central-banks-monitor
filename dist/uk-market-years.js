(() => {
  const panel = document.getElementById("uk-market-history");
  if (!panel) return;
  const part = name => panel.querySelector("#uk-market-" + name);
  const yearField = part("year");
  const assetField = part("asset");
  const mainYear = document.getElementById("amh-year");
  const labelDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const number = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 });
  const date = iso => labelDate.format(new Date(iso + "T12:00:00Z"));
  const urlYear = () => new URLSearchParams(location.search).get("historyYear");

  function formatted(value, unit, signed) {
    const sign = signed && value > 0 ? "+" : value < 0 ? "−" : "";
    return sign + number.format(Math.abs(value)) + (unit === "bp" ? " bp" : "%");
  }

  function appendCell(row, text, header = false) {
    const cell = document.createElement(header ? "th" : "td");
    if (header) cell.scope = "row";
    cell.textContent = text;
    row.append(cell);
    return cell;
  }

  function connect(data) {
    const years = Object.keys(data.years);
    for (const year of years) yearField.add(new Option(year, year));
    for (const [id, asset] of Object.entries(data.assets)) {
      assetField.add(new Option(asset.label, id));
    }

    function show(year) {
      if (!/^\d{4}$/.test(year || "")) year = years[0];
      if (![...yearField.options].some(option => option.value === year)) yearField.add(new Option(year, year));
      yearField.value = year;
      const period = data.years[year];
      const asset = data.assets[assetField.value];
      const status = part("status");
      const rows = part("rows");
      rows.replaceChildren();
      part("results").hidden = !period;
      if (!period) {
        status.textContent = "No UK observations are available for " + year + ". The source runs through " + date(data.through) + ".";
        return;
      }
      part("caption").textContent = year + " · " + asset.label;
      status.textContent = "UK source coverage runs from " + years[0] + " through " + date(data.through) + ".";
      for (const [id, label] of [["announcement", "MPC announcement"], ["conference", "Report press conference"]]) {
        const sample = period[id];
        const result = sample.series[assetField.value];
        const row = rows.insertRow();
        appendCell(row, label, true);
        appendCell(row, result.quoted + " / " + sample.recorded);
        appendCell(row, result.quoted ? formatted(result.medianAbs, asset.unit, false) : "No quotes");
        const cell = appendCell(row, "");
        if (!result.quoted) cell.textContent = "—";
        for (const obs of result.peaks) {
          const line = document.createElement("div");
          line.textContent = formatted(obs.value, asset.unit, true) + " · " + date(obs.date);
          cell.append(line);
        }
      }
    }

    yearField.addEventListener("change", () => {
      const year = yearField.value;
      if (mainYear && [...mainYear.options].some(option => option.value === year)) {
        mainYear.value = year;
        mainYear.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        const address = new URL(location.href);
        address.searchParams.set("historyYear", year);
        history.replaceState(history.state, "", address);
      }
      show(year);
    });
    assetField.addEventListener("change", () => show(yearField.value));
    window.addEventListener("market-history-year", event => {
      const year = String(event.detail.year);
      if (yearField.value !== year) show(year);
    });
    window.addEventListener("popstate", () => show(urlYear() || mainYear?.value));
    part("controls").hidden = false;
    show(mainYear?.value || urlYear() || years[0]);
  }

  async function load() {
    try {
      const response = await fetch("data/uk-market-years.json");
      if (!response.ok) throw new Error("UK observations unavailable");
      connect(await response.json());
    } catch {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "Reload UK results";
      retry.addEventListener("click", load, { once: true });
      part("status").replaceChildren("UK results could not be loaded. ", retry);
    }
  }

  load();
})();
