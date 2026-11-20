(() => {
  const root = document.getElementById("fed-liquidity-stance");
  if (!root) return;
  const get = id => root.querySelector("#fls-" + id);
  const select = get("episode");
  const status = get("status");
  const fullDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const shortDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  const date = (stamp, formatter = fullDate) => formatter.format(new Date(stamp + "T12:00:00Z"));
  const rate = bp => bp == null ? "—" : (bp / 100).toFixed(2).replace("-", "−") + "%";
  const signed = number => (number > 0 ? "+" : number < 0 ? "−" : "") + Math.abs(number);
  const spread = (a, b) => a == null || b == null ? "—" : signed(a - b) + " bp";
  const billions = millions => (millions / 1000).toFixed(3);

  function el(tag, value, className) {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = value;
    if (className) node.className = className;
    return node;
  }

  function row(name, values) {
    const tr = el("tr");
    const th = el("th", name);
    th.scope = "row";
    tr.append(th, ...values.map(value => el("td", value)));
    return tr;
  }

  function links(list, sources) {
    list.replaceChildren(...sources.map(([label, url]) => {
      const li = el("li");
      const a = el("a", label);
      a.href = url;
      li.append(a);
      return li;
    }));
  }

  function chart(points) {
    const maximum = Math.max(...points.map(point => point.primaryMillions));
    get("bars").replaceChildren(...points.map(point => {
      const barRow = el("div", undefined, "fls-bar-row");
      const track = el("div", undefined, "fls-track");
      const bar = el("div", undefined, "fls-bar");
      bar.style.width = (100 * point.primaryMillions / maximum) + "%";
      track.append(bar);
      barRow.append(el("span", date(point.date, shortDate)), track, el("strong", billions(point.primaryMillions)));
      return barRow;
    }));
    get("figure").setAttribute("aria-label", "Primary credit in billions of US dollars: " + points.map(
      point => date(point.date) + ", " + billions(point.primaryMillions)
    ).join(". "));
  }

  function show(data, year) {
    const episode = data.episodes[year];
    const points = episode.observations;
    get("caption").textContent = episode.label;
    get("context").textContent = episode.context;
    get("reading").textContent = episode.interpretation;
    get("policy-label").textContent = year === "2008" ? "FOMC point target" : "FOMC target ceiling";
    get("rows").replaceChildren(...points.map(p => row(date(p.date), [
      billions(p.primaryMillions), rate(p.policyBp), rate(p.effectiveBp),
      rate(p.overnightPaperBp), spread(p.overnightPaperBp, p.effectiveBp),
    ])));
    get("term").replaceChildren(...points.map(p => row(date(p.date), [
      rate(p.termPaperBp), rate(p.billBp), spread(p.termPaperBp, p.billBp),
    ])));
    chart(points);
    links(get("event-sources"), episode.sources);
  }

  async function start() {
    select.disabled = true;
    try {
      const response = await fetch("data/fed-liquidity.json");
      if (!response.ok) throw new Error("Source unavailable");
      const data = await response.json();
      const episodes = Object.entries(data.episodes);
      get("summary").replaceChildren(...episodes.map(([year, episode]) => {
        const [before, stress, , later] = episode.observations;
        const amount = (stress.primaryMillions - before.primaryMillions) / 1000;
        const amountText = (amount < 0 ? "−" : amount > 0 ? "+" : "") + "$" + Math.abs(amount).toFixed(3) + "bn";
        return row(year, [amountText, spread(stress.policyBp, before.policyBp), spread(later.policyBp, before.policyBp)]);
      }));
      links(get("data-sources"), [
        ...Object.values(data.sources).map(source => [source.label, source.url]),
        ["Federal Reserve · commercial paper rate construction and missing observations", "https://www.federalreserve.gov/releases/cp/about.htm"],
        ["Federal Reserve · 2016 change to the effective federal funds rate calculation", "https://www.federalreserve.gov/Releases/H15/20160307/"],
      ]);
      const requested = new URLSearchParams(window.location.search).get("liquidityEpisode");
      if (Object.hasOwn(data.episodes, requested)) select.value = requested;
      show(data, select.value);
      get("body").hidden = false;
      status.hidden = true;
      select.disabled = false;
      select.addEventListener("change", () => {
        show(data, select.value);
        const url = new URL(window.location.href);
        url.searchParams.set("liquidityEpisode", select.value);
        window.history.replaceState(window.history.state, "", url);
      });
    } catch {
      status.textContent = "The matched observations could not be loaded. Refresh to try again.";
    }
  }
  start();
})();
