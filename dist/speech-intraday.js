(() => {
  const mount = document.querySelector("#mr-speech-intraday");
  if (!mount) return;
  const payload = new URL("data/speech-intraday.json", document.baseURI);
  let currentCurve = document.querySelector("#pre-event-curve")?.dataset;
  let syncCase;
  document.addEventListener("pre-event-date", event => {
    currentCurve = event.detail;
    syncCase?.(currentCurve);
  });

  function element(tag, label, className) {
    const node = document.createElement(tag);
    if (label) node.textContent = label;
    if (className) node.className = className;
    return node;
  }

  function link(label, href) {
    const node = element("a", label);
    node.href = href;
    return node;
  }

  function samePublication(first, second) {
    try {
      const a = new URL(first);
      const b = new URL(second);
      return a.hostname === b.hostname && a.pathname === b.pathname;
    } catch {
      return false;
    }
  }

  function curveUrl(event) {
    const url = new URL("market-reactions.html", document.baseURI);
    url.searchParams.set("curveDate", event.date);
    if (event.curveCatalogMatch) url.searchParams.set("curveEvent", event.eventUrl);
    else url.searchParams.set("curveKind", "custom");
    url.hash = "pre-event-curve";
    return url;
  }

  function change(row) {
    const prefix = row.approximate ? "≈ " : "";
    const sign = row.value > 0 ? "+" : row.value < 0 ? "−" : "";
    return prefix + sign + Math.abs(row.value) + (row.unit === "%" ? "%" : " " + row.unit);
  }

  function render({ events, studies }) {
    const section = element("section", "", "mr-analysis");
    section.setAttribute("aria-labelledby", "mr-speech-intraday-title");
    const title = element("h2", "How did markets trade around Fed speeches?");
    title.id = "mr-speech-intraday-title";
    const intro = element("p", "Explore three speeches and one congressional hearing between Fed policy meetings. Each observation links to the study that measured the move.");
    const controls = element("div", "", "mr-pair-picker");
    const label = element("label", "Speech or testimony");
    label.style.maxWidth = "100%";
    const select = element("select");
    select.id = "mr-speech-case";
    for (const event of events) {
      select.add(new Option(event.date + " · " + event.speaker + " · " + event.title, event.id));
    }
    label.append(select);
    controls.append(label);
    const result = element("div");
    result.setAttribute("aria-live", "polite");
    const scope = element("p", "The studies selected unusually large moves. A change in the 2s10s slope requires 2-year and 10-year quotes from the same window. These cases report individual instruments.", "mr-footnote");
    const download = link("Download all case observations (JSON)", payload);
    download.download = "fed-speech-intraday.json";
    const dataLink = element("p", "", "mr-method-links");
    dataLink.append(download);
    section.append(title, intro, controls, result, scope, dataLink);
    mount.replaceChildren(section);

    function show(event) {
      select.value = event.id;
      const scroll = element("div", "", "mr-table-scroll");
      scroll.tabIndex = 0;
      scroll.setAttribute("role", "region");
      scroll.setAttribute("aria-label", "Market moves around " + event.title);
      const table = element("table", "", "mr-method-table");
      table.append(element("caption", event.date + " · " + event.role + " · " + event.kind));
      const head = table.createTHead().insertRow();
      for (const field of ["Instrument", "Change", "Observation window (New York time)"]) {
        const th = element("th", field);
        th.scope = "col";
        head.append(th);
      }
      const body = table.createTBody();
      const details = element("details", "", "mr-help");
      details.append(element("summary", "Price measurements and sources"));
      for (const row of event.observations) {
        const tr = body.insertRow();
        const name = element("th", row.instrument);
        name.scope = "row";
        tr.append(name, element("td", change(row), "mr-value"), element("td", row.window));
        const source = studies[row.study];
        const note = element("p", row.instrument + ". " + row.method + " ");
        note.append(link(source.citation + " · " + row.locator, source.url + "#page=" + row.pdfPage));
        details.append(note);
      }
      scroll.append(table);
      const related = element("p", "", "mr-method-links");
      related.append(link("Federal Reserve remarks", event.eventUrl));
      if (event.overlapSource) related.append(" · ", link(event.overlapSource.label, event.overlapSource.url));
      related.append(" · ", link("Daily Treasury curve around this date", curveUrl(event)));
      result.replaceChildren(element("p", event.context), scroll, related, details);
    }

    function sync(detail) {
      if (!detail || detail.kind === "statement") return false;
      const matches = events.filter(event => event.date === detail.date &&
        (!detail.eventUrl || samePublication(event.eventUrl, detail.eventUrl)));
      if (matches.length !== 1) return false;
      show(matches[0]);
      return true;
    }

    select.addEventListener("change", () => show(events.find(event => event.id === select.value)));
    syncCase = sync;
    if (!sync(currentCurve)) show(events[0]);
  }

  async function load() {
    mount.textContent = "Loading historical Fed speech observations…";
    try {
      const response = await fetch(payload);
      if (!response.ok) throw new Error("Speech observations unavailable");
      render(await response.json());
    } catch {
      const retry = element("button", "Reload observations");
      retry.type = "button";
      retry.addEventListener("click", load);
      mount.replaceChildren(element("p", "The historical speech observations could not be loaded."), retry);
    }
  }

  load();
})();
