"use strict";

const PublicationReader = (() => {
  const release = new URL(document.currentScript.src).search;
  const manuscripts = new Map();
  const dateFormat = new Intl.DateTimeFormat("en-GB", {day: "numeric", month: "long", year: "numeric", timeZone: "UTC"});

  function node(tag, text) {
    const el = document.createElement(tag);
    el.textContent = text;
    return el;
  }

  async function index() {
    const response = await fetch("data/research-notes.json" + release);
    if (!response.ok) throw Error("Research notes unavailable");
    const notes = await response.json();
    return notes.filter(note => {
      try {
        const url = new URL(note.url);
        return url.protocol === "https:" && !url.username && !url.password && /^[a-z0-9-]+\.json$/.test(note.file);
      } catch { return false; }
    });
  }

  async function load(header) {
    if (manuscripts.has(header.url)) return manuscripts.get(header.url);
    const response = await fetch("data/notes/" + header.file + release);
    if (!response.ok) throw Error("Could not load analysis");
    const note = await response.json();
    if (note.url !== header.url || note.date !== header.date) throw Error("Source mismatch");
    manuscripts.set(note.url, note);
    return note;
  }

  // Verified FOMC policy-statement documents. The generic monetary press-release
  // path is also used for minutes, facilities, projections and implementation notes.
  const fomcStatementDates = new Set(`20080916 20110126 20110315 20110427 20110622 20110809 20110921 20111102 20111213
  20120125 20120313 20120425 20120620 20120801 20120913 20121024 20121212 20130130
  20130320 20130501 20130619 20130731 20130918 20131030 20131218 20140129 20140319
  20140430 20140618 20140730 20140917 20141029 20141217 20150128 20150318 20150429
  20150617 20150729 20150917 20151028 20151216 20160127 20160316 20160427 20160615
  20160727 20160921 20161102 20161214 20170201 20170315 20170503 20170614 20170726
  20170920 20171101 20171213 20180131 20180321 20180502 20180613 20180801 20180926
  20181108 20181219 20190130 20190320 20190501 20190619 20190731 20190918
  20191030 20191211 20200129 20200303 20200315 20200323 20200429 20200610 20200729
  20200916 20201105 20201216 20210127 20210317 20210428 20210616 20210728 20210922
  20211103 20211215 20220126 20220316 20220504 20220615 20220727 20220921 20221102
  20221214 20230201 20230322 20230503 20230614 20230726 20230920 20231101 20231213
  20240131 20240320 20240501 20240612 20240731 20240918 20241107 20241218 20250129
  20250319 20250507 20250618 20250730 20250917 20251029 20251210 20260128 20260318
  20260429 20260617 20260729 20260916 20261028`.split(/\s+/));
  const archivedFomcStatements = new Set();
  for (const [directory, dates] of [
    ["general", "20000202 20000321 20000516 20000628 20000822 20001003 20001115 20001219 20010103 20010131 20010320 20010418 20010515 20010627 20010821 20010917 20011002 20011106 20011211 20020130 20020319"],
    ["monetary", "20020507 20020626 20020813 20020924 20021106 20021210"]
  ]) {
    for (const date of dates.split(" ")) {
      archivedFomcStatements.add("/boarddocs/press/" + directory + "/" + date.slice(0,4) + "/" + date + "/");
    }
  }
  let eventBanks;

  function identifyEventSource(note) {
    const source = new URL(note.url);
    const stamp = note.date.replaceAll("-", "");
    if (source.protocol !== "https:" || source.username || source.password || source.port) return;
    if (source.hostname === "www.federalreserve.gov") {
      const archivedPath = source.pathname.replace(/\/default\.htm$/, "/");
      if (archivedFomcStatements.has(archivedPath) && archivedPath.endsWith("/" + stamp + "/")) {
        return {bank: "fed", window: "statement"};
      }
      if (fomcStatementDates.has(stamp) && source.pathname === "/newsevents/pressreleases/monetary" + stamp + "a.htm") {
        return {bank: "fed", window: "statement"};
      }
      if (source.pathname === "/monetarypolicy/fomcpresconf" + stamp + ".htm" ||
          source.pathname === "/mediacenter/files/FOMCpresconf" + stamp + ".pdf") {
        return {bank: "fed", window: "conference"};
      }
    }
    if (source.hostname !== "www.ecb.europa.eu") return;
    const conference = /^\/press\/press_conference\/monetary-policy-statement\/(\d{4})\/html\/(?:ecb\.)?is(\d{6})(?:~[a-f0-9]+)?\.[a-z]{2}\.html$/.exec(source.pathname);
    const statement = /^\/press\/pr\/date\/(\d{4})\/html\/ecb\.mp(\d{6})(?:~[a-f0-9]+)?\.[a-z]{2}\.html$/.exec(source.pathname);
    const match = conference || statement;
    if (match && match[1] === stamp.slice(0, 4) && match[2] === stamp.slice(2)) {
      return {bank: "ecb", window: conference ? "conference" : "statement"};
    }
  }

  async function showMarketWindow(note, article) {
    const identity = identifyEventSource(note);
    if (!identity) return;
    eventBanks ??= fetch("data/market-events.json").then(response => {
      if (!response.ok) throw Error(response.status);
      return response.json();
    }).then(data => Array.isArray(data.banks) ? data.banks : []).catch(() => {
      eventBanks = undefined;
      return [];
    });
    const banks = await eventBanks;
    if (article.dataset.note !== note.url) return;
    const bank = banks.find(item => item.id === identity.bank);
    if (!Array.isArray(bank?.events) || !Array.isArray(bank.assets) || !bank.windows?.[identity.window]) return;
    const values = bank.events.find(event => event.date === note.date)?.windows?.[identity.window];
    if (!values) return;
    const instruments = bank.id === "fed" ? ["UST2Y", "UST10Y", "EURUSD", "SP500"] : ["DE2Y", "DE10Y", "EURUSD", "STOXX50"];
    const measured = instruments.map(id => bank.assets.find(asset => asset.id === id))
      .filter(asset => asset && Number.isFinite(values[asset.id]));
    if (!measured.length) return;
    const moves = document.createDocumentFragment();
    for (const asset of measured) {
      const cell = document.createElement("div");
      const figure = new Intl.NumberFormat("en-GB", {minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero"}).format(values[asset.id]);
      cell.append(node("dt", asset.label), node("dd", figure + (asset.unit === "bp" ? " bp" : "%")));
      moves.append(cell);
    }
    article.querySelector("#note-moves").replaceChildren(moves);
    article.querySelector("#note-window").textContent = (identity.window === "conference" ? "Press conference" : "Policy statement") + " · " + bank.windows[identity.window];
    article.querySelector("#note-window-source").textContent = bank.sourceLabel;
    article.querySelector("#note-window-source").href = bank.source;
    const params = new URLSearchParams({bank: bank.id, window: identity.window, date: note.date, asset: measured[0].id});
    article.querySelector("#note-event-link").href = "market-reactions.html?" + params;
    article.querySelector("#note-market").hidden = false;
  }

  const workedCases = [
    ["https://www.snb.ch/public/asset/en/www-snb-ch/publications/research/working-papers/2026/working_paper_2026_14/publications0_en/working_paper_2026_14.pdf","swiss-inflation-horizons-2026","Swiss inflation forecasts against a seasonal benchmark"],
    ["https://www.snb.ch/en/publications/research/working-papers/2026/working_paper_2026_14","swiss-inflation-horizons-2026","Swiss inflation forecasts against a seasonal benchmark"],
    ["https://www.boj.or.jp/en/mopo/outlook/gor2610b.pdf","japan-investment-adoption-2026","Japan’s investment plans and the cost of delay"],
    ["https://www.dallasfed.org/news/speeches/logan/2026/lkl261113", "tips-liquidity-2008-2020", "When ten-year breakevens fall in a Treasury sell-off"],
    ["https://www.bancaditalia.it/pubblicazioni/rapporto-stabilita/2026-2/index.html?com.dotmarketing.htmlpage.language=1", "italian-btp-repo-2026", "Italian BTP repo and rollover funding"],
    ["https://www.bundesbank.de/en/press/speeches/statement-on-the-publication-of-the-financial-stability-review-2026-of-the-deutsche-bundesbank-1014858", "italian-btp-repo-2026", "Italian BTP repo and rollover funding"],
    ["https://www.cnb.cz/en/monetary-policy/monetary-policy-reports/Monetary-Policy-Report-Autumn-2026", "czech-inflation-forecast-2026", "Czech inflation, growth and the policy path"],
    ["https://www.cnb.cz/en/monetary-policy/bank-board-decisions/CNB-Board-decisions-1793865600000/?tab=record", "czech-inflation-forecast-2026", "Czech inflation, growth and the policy path"],
    ["https://www.boj.or.jp/en/research/research_data/cai/index.htm", "japan-consumption-2026", "How much of Japan’s spending decline reversed?"],
    ["https://www.federalreserve.gov/newsevents/pressreleases/monetary20130918a.htm", "fed-cut-september-2024", "A Fed cut and a steeper Treasury curve"],
    ["https://www.federalreserve.gov/newsevents/pressreleases/monetary20240918a.htm", "fed-cut-september-2024", "A Fed cut and a steeper Treasury curve"]
  ];

  function addWorkedCase(article, url) {
    const match = workedCases.find(([source]) => source === url);
    if (!match) return;
    const [, id, label] = match;
    const link = node("a", "Worked case · " + label);
    link.className = "note-source";
    link.href = "casebook.html#" + id;
    const paragraph = node("p", "");
    paragraph.append(link);
    article.querySelector("#note-source").after(paragraph);
  }

  function render(article, note, link) {
    article.dataset.note = note.url;
    article.innerHTML = `
      <div class="note-byline"><span id="note-bank"></span><time id="note-date"></time></div>
      <h2 id="note-title"></h2>
      <a id="note-source" class="note-source" target="_blank" rel="noopener noreferrer">Source document</a>
      <section class="note-summary" aria-labelledby="note-summary-title">
        <h3 id="note-summary-title">Summary</h3><div id="note-summary"></div>
      </section>
      <section class="note-questions"><h3>Questions for further research</h3><ol id="note-questions"></ol></section>
      <p class="note-limitation" id="note-limitation" hidden></p>
      <aside id="note-market" class="note-market" aria-labelledby="note-market-title" hidden>
        <h3 id="note-market-title">Observed market moves</h3>
        <p id="note-window"></p>
        <dl id="note-moves"></dl>
        <p>Other news during the window may also affect prices.</p>
        <div><a id="note-window-source">Data source</a><a id="note-event-link">Open this event</a></div>
      </aside>
      <a class="note-permalink" id="note-permalink">Permalink</a>
    `;
    article.querySelector("#note-bank").textContent = note.bank;
    article.querySelector("#note-date").dateTime = note.date;
    article.querySelector("#note-date").textContent = dateFormat.format(new Date(note.date));
    article.querySelector("#note-title").textContent = note.title;
    article.querySelector("#note-source").href = note.url;
    addWorkedCase(article, note.url);
    article.querySelector("#note-permalink").href = link;
    article.querySelector("#note-summary").replaceChildren(...note.summary.map(text => node("p",text)));
    article.querySelector("#note-questions").replaceChildren(...note.questions.map(item => {
      const li = document.createElement("li");
      li.append(node("h4", item.question), node("p", item.detail));
      return li;
    }));
    showMarketWindow(note, article);
    const limitation = article.querySelector("#note-limitation");
    limitation.hidden = !note.limitation;
    limitation.textContent = note.limitation ? "Coverage · " + note.limitation : "";
  }

  return {index, load, render};
})();
