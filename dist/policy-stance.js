"use strict";

(() => {
  const byId = id => document.getElementById(id);
  const dateFormat = new Intl.DateTimeFormat("en-GB", {day:"numeric", month:"short", year:"numeric", timeZone:"UTC"});
  const dateText = date => dateFormat.format(new Date(date + "T12:00:00Z"));
  function signed(n, places = 0) {
    const magnitude = Math.abs(n).toFixed(places);
    return Number(magnitude) === 0 ? magnitude : (n < 0 ? "−" : "+") + magnitude;
  }
  const isNumber = Number.isFinite;
  const pageSize = 12;
  const filters = {year:byId("year-filter"), guidance:byId("score-filter"), decision:byId("action-filter"), pricing:byId("pricing-filter")};
  let data, records = [], matching = [], selected, offset = 0, marketRows = new Map(), marketObs = new Map();
  let marketLoaded = false, expectationRows = new Map();
  const bpText = n => isNumber(n) ? signed(n,2) + " bp" : "Unavailable";
  const marketSource = "https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/";
  function mixedSignal(row) {
    const quote = expectationRows.get(row.date);
    return isNumber(row.score) && isNumber(quote?.marketDirection) && row.score * quote.marketDirection < 0;
  }

  function node(tag, text, cls) {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  }
  function link(label, href) {
    const a = node("a", label);
    a.href = href;
    return a;
  }
  function option(label, value) {
    const el = node("option", label);
    el.value = value;
    return el;
  }
  function point(value, name) {
    if (!isNumber(value)) return name ? "Unscored" : "Unavailable";
    return signed(value);
  }
  function action(n) {
    if (!isNumber(n)) return "Unavailable";
    return n === 0 ? "Hold" : (n > 0 ? "Increase " : "Cut ") + Math.abs(n) + " bp";
  }
  function group(score) {
    if (!isNumber(score)) return "unscored";
    if (score > 0) return "hawkish";
    return score < 0 ? "dovish" : "steady";
  }
  function actionGroup(n) {
    if (!isNumber(n)) return "unknown";
    return n === 0 ? "hold" : n > 0 ? "hike" : "cut";
  }
  function metric(label, value, detail, cls) {
    const wrap = node("div", undefined, cls);
    const dd = node("dd", value);
    if (detail) dd.append(node("small", detail));
    wrap.append(node("dt", label), dd);
    return wrap;
  }
  async function readJson(path) {
    const response = await fetch("data/" + path);
    if (!response.ok) throw new Error("Unavailable dataset");
    return response.json();
  }
  function dateUrl(date) {
    const url = new URL(location.href);
    for (const [name, input] of Object.entries(filters)) {
      if (input.value) url.searchParams.set(name, input.value);
      else url.searchParams.delete(name);
    }
    if (date) url.searchParams.set("date", date);
    else url.searchParams.delete("date");
    return url;
  }
  function setUrl() {
    const url = dateUrl(selected?.date);
    history.replaceState(null, "", url);
  }
  function svgElement(tag, attrs, text) {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) n.setAttribute(key, value);
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function plot() {
    const svg = svgElement("svg", {width:"100%", role:"img", "aria-label":"Statement scores by date. The selected statement is outlined. Individual observations are available in the meeting ledger."});
    const palette = {hawkish:"#e8aa81", dovish:"#82c6c4", steady:"#c8d3ac", unscored:"#20372d"};
    const yPos = value => (isNumber(value) ? 10 + 13 * (2 - value) : 77) + "%";
    for (const value of [2,1,0,-1,-2,null]) {
      const y = yPos(value);
      svg.append(svgElement("line", {x1:"12%", x2:"94%", y1:y, y2:y, class:value === 0 ? "plot-zero" : "plot-grid"}));
      svg.append(svgElement("text", {x:"9%", y, dy:".33em", "text-anchor":"end"}, isNumber(value) ? signed(value) : "N/A"));
    }
    const ts = date => Date.parse(date + "T12:00:00Z");
    const first = ts(matching.at(-1).date), last = ts(matching[0].date);
    const xPos = millis => (first === last ? 53 : 13 + 80 * (millis - first) / (last - first)) + "%";
    for (const row of matching) {
      const missing = !isNumber(row.score);
      svg.append(svgElement("circle", {cx:xPos(ts(row.date)), cy:yPos(row.score), r:3.3, fill:palette[group(row.score)], stroke:missing ? "#b9c5b9" : "none"}));
    }
    svg.append(svgElement("circle", {cx:xPos(ts(selected.date)), cy:yPos(selected.score), r:6.3, fill:"none", stroke:"#fff6d6", "stroke-width":1.7}));
    const label = (date, align, str) => svg.append(svgElement("text", {x:xPos(ts(date)), y:"95%", "text-anchor":align}, str));
    if (first === last) label(selected.date, "middle", dateText(selected.date));
    else {
      const start = matching.at(-1).date, end = matching[0].date;
      const short = (last - first) < 750 * 86400000;
      label(start,"start", short ? dateText(start) : start.slice(0,4));
      label(end,"end", short ? dateText(end) : end.slice(0,4));
    }
    byId("time-plot").replaceChildren(svg);
    const list = byId("distribution-list");
    list.replaceChildren();
    for (const score of [2,1,0,-1,-2,null]) {
      const n = matching.filter(row => row.score === score).length;
      const row = node("div", undefined, "dist-row");
      const bar = node("span", undefined, "dist-track");
      bar.setAttribute("aria-hidden","true");
      const fill = node("i", undefined, "dist-fill " + group(score));
      fill.style.width = 100 * n / matching.length + "%";
      bar.append(fill);
      row.append(node("span", isNumber(score) ? "Score " + signed(score) : "Unscored"), bar, node("strong", String(n)));
      list.append(row);
    }
  }
  function pricingDetail(row) {
    const quote = expectationRows.get(row.date);
    const result = node("aside", undefined, "pricing-inset");
    result.append(node("h4", "What was priced in?"));
    if (!quote) {
      result.append(node("p", "Comparable fed funds futures pricing is unavailable for this statement in the scheduled-meeting sample.","evidence-note"));
      return result;
    }
    const current = node("dl", undefined, "pricing-figures");
    current.append(metric("Expected move",bpText(quote.impliedPriorMoveBp),"Reconstructed before release","market-metric"),
      metric("Announced move",bpText(quote.actionBp),"Current meeting","market-metric"),
      metric("Surprise (MP1)",bpText(quote.currentSurpriseBp),"Window change","market-metric"));
    result.append(node("p","Current meeting","pricing-horizon"),current);
    const path = node("p", undefined, "path-quote");
    path.append(node("strong", bpText(quote.nextRepricingBp)),document.createTextNode(" · " + (quote.marketLabel || "Unavailable")));
    result.append(node("p","Next meeting · futures repricing (MP2)","pricing-horizon"),path);
    if (mixedSignal(row)) result.append(node("p",row.score > 0 ? "The wording signalled tightening, while futures marked the next meeting lower." : "The wording signalled easing, while futures marked the next meeting higher.","evidence-note"));
    const explanation = node("details",undefined,"pricing-explanation");
    explanation.append(node("summary","Calculation and source"),
      node("p","The pre-release expected move is reconstructed as the announced step minus the current-meeting surprise, assuming a stable effective-rate spread and full resolution of the decision. Both futures surprises measure changes across the statement window. MP2 describes the change in next-meeting pricing. Positive values mean higher implied rates. Values within ±1 bp are labelled close to prior pricing."),
      link("San Francisco Fed futures data",marketSource));
    result.append(explanation);
    return result;
  }
  function marketDetail(row) {
    const aside = node("details", undefined, "market-details");
    aside.append(node("summary", "Treasury yield evidence"));
    const match = marketRows.get(row.date);
    if (!match) {
      aside.append(node("p", marketLoaded ? "No paired pre-release and announcement-window yields are available for this meeting." : "Loading the matched yield observations…"));
      return aside;
    }
    const obs = expectationRows.get(row.date) || marketObs.get(row.date);
    const figures = node("dl", undefined, "yield-figures");
    const bp = n => isNumber(n) ? signed(n, Math.round(n) === n ? 0 : 1) + " bp" : "Unavailable";
    figures.append(metric("Prior 2Y", bp(match.priorBp), "", "market-metric"));
    if (isNumber(obs?.prior2s10sBp)) figures.append(metric("Prior 2s10s", bp(obs.prior2s10sBp), "", "market-metric"));
    figures.append(metric("Release 2Y", bp(match.statementBp), "", "market-metric"));
    aside.append(figures, node("p", "The pre-release change runs from the close on " + dateText(match.start) + " to " + dateText(match.end) + ". The release change uses the published statement window."));
    if (isNumber(obs?.prior2s10sBp)) aside.append(node("p","The 2s10s spread is the ten-year yield minus the two-year yield. A positive change means the curve steepened."));
    const links = node("p", undefined, "case-links");
    links.append(link("Pre-release yield curve", "market-reactions.html?curveDate=" + row.date + "#pre-event-curve"), link("Statement window", "market-reactions.html?" + new URLSearchParams({bank:"fed", year:row.date.slice(0,4), date:row.date, window:"statement", asset:"UST2Y"}) + "#mr-detail-title"));
    aside.append(links);
    return aside;
  }
  function detail() {
    if (!selected) return;
    const row = selected, main = node("div",undefined,"case-summary"), evidence = node("div",undefined,"case-evidence"), card = byId("statement-card");
    main.append(node("h4", dateText(row.date), "case-date"));
    const facts = node("dl", undefined, "case-facts");
    const shiftNote = row.previousDate ? "From " + dateText(row.previousDate) : "No preceding statement";
    const range = isNumber(row.targetUpper) && isNumber(row.targetLower) ? (row.targetLower === row.targetUpper ? row.targetUpper : row.targetLower + "–" + row.targetUpper) + "% target" : "";
    facts.append(metric("Guidance", point(row.score,true), data.scale[row.score] || "No directional score"), metric("Score change", point(row.shift,false), shiftNote), metric("Rate decision", action(row.actionBp), range));
    main.append(facts);
    if (row.evidence) evidence.append(node("blockquote", row.evidence));
    if (row.rationale) evidence.append(node("p", row.rationale, "evidence-note"));
    const links = node("p", undefined, "case-links");
    links.append(link("Federal Reserve statement", row.url));
    const previous = records.find(r => r.date === row.previousDate);
    if (previous) links.append(link("Previous statement (" + dateText(previous.date) + ")", previous.url));
    evidence.append(links);
    if (row.riskSignal || row.riskEvidence) {
      const risk = node("details", undefined, "case-risk");
      risk.append(node("summary","Economic risks in the statement"));
      if (row.riskSignal) risk.append(node("p", row.riskSignal));
      if (row.riskEvidence) risk.append(node("blockquote", row.riskEvidence));
      evidence.append(risk);
    }
    const market = node("div",undefined,"inset");
    market.append(pricingDetail(row),marketDetail(row));
    card.replaceChildren(main,market,evidence);
  }
  function examples() {
    const links = byId("example-links");
    links.replaceChildren();
    const examples = [
      ["Hawkish words, lower futures", r => r.score > 0 && mixedSignal(r)],
      ["Dovish words, higher futures", r => r.score < 0 && mixedSignal(r)],
      ["Hawkish shift on a hold", r => r.actionBp === 0 && isNumber(r.shift) && r.shift > 0],
      ["Dovish shift on a hold", r => r.actionBp === 0 && isNumber(r.shift) && r.shift < 0]
    ];
    for (const [label, test] of examples) {
      const row = matching.find(test);
      if (!row) continue;
      const button = node("button", label + " · " + dateText(row.date), "example-button");
      button.type = "button";
      button.addEventListener("click", () => selectRow(row));
      links.append(button);
    }
  }
  function selectRow(row) {
    selected = row;
    byId("case-select").value = row.date;
    offset = Math.floor(matching.indexOf(row) / pageSize) * pageSize;
    ledger();
    plot();
    detail();
    setUrl();
  }
  function ledger() {
    const body = byId("meeting-rows");
    body.replaceChildren();
    const rows = matching.slice(offset, offset + pageSize);
    for (const row of rows) {
      const tr = node("tr"), th = node("th");
      const quote = expectationRows.get(row.date);
      th.scope = "row";
      const url = dateUrl(row.date);
      url.hash = "statement-evidence";
      const a = link(dateText(row.date),url);
      a.className = "meeting-button";
      if (row === selected) a.setAttribute("aria-current","true");
      a.addEventListener("click", event => {
        if (event.ctrlKey || event.shiftKey || event.metaKey || event.altKey) return;
        event.preventDefault();
        selectRow(row);
        byId("case-select").focus({preventScroll:true});
        byId("statement-evidence").scrollIntoView?.({block:"start"});
      });
      th.append(a);
      tr.append(th,node("td",isNumber(row.score) ? signed(row.score) + " · " + data.scale[row.score] : "Unscored"),node("td",point(row.shift,false)),node("td",action(row.actionBp)),node("td",bpText(quote?.impliedPriorMoveBp)),node("td",bpText(quote?.nextRepricingBp)));
      body.append(tr);
    }
    byId("recent-rows").disabled = offset === 0;
    byId("older-rows").disabled = offset + rows.length >= matching.length;
    byId("page-range").textContent = (offset + 1) + "–" + (offset + rows.length) + " of " + matching.length;
  }
  function applyFilters(preferredDate, initial = false) {
    matching = records.filter(row =>
      (!filters.year.value || row.date.slice(0,4) === filters.year.value) &&
      (!filters.guidance.value || group(row.score) === filters.guidance.value) &&
      (!filters.decision.value || actionGroup(row.actionBp) === filters.decision.value) &&
      (!filters.pricing.value || String(expectationRows.get(row.date)?.marketDirection ?? "unknown") === filters.pricing.value)
    );
    const hasFilters = Object.values(filters).some(input => input.value);
    byId("reset-filters").hidden = !hasFilters;
    byId("matched-content").hidden = matching.length === 0;
    if (!matching.length) {
      selected = undefined;
      byId("filter-count").textContent = "No statements match these filters. Change a selection to see more meetings.";
      setUrl();
      return;
    }
    const n = matching.filter(row => isNumber(row.score)).length;
    byId("filter-count").textContent = matching.length + (matching.length === 1 ? " statement" : " statements") + " · " + n + " scored · " + (matching.length - n) + " unscored";
    byId("case-select").replaceChildren(...matching.map(row => option(dateText(row.date),row.date)));
    selected = matching.find(row => row.date === preferredDate) ||
      (initial && !hasFilters && matching.find(row => row.date === "2022-11-02" && mixedSignal(row))) ||
      (initial && !hasFilters && matching.find(mixedSignal)) || matching[0];
    examples();
    selectRow(selected);
  }
  function method() {
    const method = byId("score-method"), scale = byId("score-scale");
    const details = node("details", undefined, "meeting-table");
    details.append(node("summary", "Scope and scoring rules"));
    const list = node("ul");
    for (const note of data.method) list.append(node("li", note));
    details.append(list);
    const appendix = node("details", undefined, "meeting-table");
    appendix.append(node("summary","Individual wording rules"));
    const rules = node("ul");
    for (const rule of Object.values(data.rules)) {
      const entry = node("li");
      entry.append(node("strong",rule.label + " (" + point(rule.score,true) + "). "),document.createTextNode(rule.rationale));
      rules.append(entry);
    }
    appendix.append(rules);
    const sources = node("p",undefined,"case-links");
    sources.append(link("Fed meeting calendars",data.coverage.source),link("Fed historical releases",data.coverage.historicalArchive));
    method.replaceChildren(node("p",data.coverage.scope),node("p","Only an explicit wait-or-hold signal earns zero. Statements that leave the direction open are unscored. This historical rubric uses the committee’s own wording and was developed after the events."),details,appendix,sources);
    const table = node("table",undefined,"scale-table");
    table.append(node("caption","Forward-guidance rubric"));
    const body = node("tbody");
    for (const score of [2,1,0,-1,-2]) {
      const tr = node("tr"), th = node("th",signed(score));
      th.scope = "row";
      tr.append(th,node("td",data.scale[score]));
      body.append(tr);
    }
    scale.replaceChildren(table);
    table.append(body);
  }
  function validation(v) {
    const host = byId("validation-result");
    host.className = "market-result";
    const c = v.coverage, changed = v.groups.filter(g => g.name !== "Unchanged").reduce((n,g) => n + g.n, 0);
    const stats = node("dl",undefined,"market-metrics");
    const rho = n => isNumber(n) ? signed(n,2) : "Unavailable";
    stats.append(metric("Scheduled meetings",String(v.all.n),changed + " with a change in guidance","market-metric"),metric("Rank correlation",rho(v.all.rho),"All matched meetings","market-metric"),metric("Rank correlation, holds",rho(v.hold.rho),v.hold.n + " meetings","market-metric"));
    const scroll = node("div",undefined,"table-scroll");
    scroll.tabIndex = 0;
    scroll.setAttribute("role","region");
    scroll.setAttribute("aria-label","Median yield changes, by direction of the change in guidance");
    const table = node("table",undefined,"es-table"), head = node("thead"), header = node("tr");
    const caption = node("caption","Median yield changes in basis points");
    for (const title of ["Change in guidance","Meetings","Prior 2Y","Prior 2s10s","Release 2Y"]) {
      const th = node("th",title);
      th.scope = "col";
      header.append(th);
    }
    head.append(header);
    const body = node("tbody");
    const median = n => isNumber(n) ? signed(n,2) : "Unavailable";
    for (const g of v.groups) {
      const tr = node("tr"), bucket = node("th", g.name);
      bucket.scope = "row";
      tr.append(bucket,node("td",String(g.n)),node("td",median(g.medianPrior2yBp)),node("td",median(g.medianPrior2s10sBp)),node("td",median(g.medianBp)));
      body.append(tr);
    }
    table.append(caption,head,body);
    scroll.append(table);
    const notes = node("details",undefined,"meeting-table");
    notes.append(node("summary","Market sample and calculations"));
    const list = node("ul");
    for (const note of v.method) list.append(node("li",note));
    notes.append(node("p",c.records + " statements in the corpus. Exclusions in order: " + c.unscored + " unscored, " + c.noPriorScore + " without a comparable preceding score, " + c.noMarket + " without a matched release quote and " + c.unscheduled + " unscheduled releases."),list);
    const links = node("p",undefined,"case-links");
    links.append(link("San Francisco Fed event data",v.sourceUrl),link("U.S. Treasury daily quotes",v.treasuryUrl),link("Download matched observations (JSON)","data/stance-validation.json"));
    const range = v.firstDate && v.lastDate ? dateText(v.firstDate) + " to " + dateText(v.lastDate) : "No matched dates";
    const signAgreement = v.all.comparable ? v.all.sameSign + " of " + v.all.comparable + " pairs moved in the same direction when both the score and the yield changed. " : "";
    const marketComparison = node("div",undefined,"pricing-sample");
    const e = v.expectations;
    if (e) {
      marketComparison.append(node("h3","Wording versus futures pricing"));
      const figure = node("p");
      figure.append(node("strong",e.opposite + " of " + e.comparable),document.createTextNode(" directional comparisons had opposite signs. These meetings had hawkish or dovish wording and next-meeting futures repricing outside ±1 bp."));
      const futuresMethod = node("details",undefined,"meeting-table");
      futuresMethod.append(node("summary","Futures reconstruction and coverage"));
      const notes = node("ul");
      for (const note of e.method) notes.append(node("li",note));
      futuresMethod.append(node("p", e.priorMoveAvailable + " meetings have an implied current action. Market quotes run from " + dateText(e.firstDate) + " to " + dateText(e.lastDate) + "."),notes);
      marketComparison.append(figure,node("p",e.matched + " scheduled statements matched the futures sample. Of " + e.directionalText + " with directional wording, " + e.flatMarket + " had next-meeting repricing within ±1 bp. The signs agreed on " + e.same + " of the remaining " + e.comparable + ". This comparison uses the level of the text score.","market-coverage"),futuresMethod);
    }
    host.replaceChildren(marketComparison,node("h3","Changes in guidance and two-year yields"),node("p","Full matched sample · " + range + ". The explorer filters apply only to the statement selection.","market-coverage"),
      stats,scroll,node("p","Prior changes run from the fifth to the last daily quote before release. A rising 2s10s means the curve steepened. The release comparison uses the two-year move from ten minutes before the statement to twenty minutes after it.","market-coverage"),
      node("p",signAgreement + "Only " + changed + " matched statements changed guidance category. The group medians describe a small number of shifts. Expectations, the decision and any projections released simultaneously can also affect the yield."),
      notes,links);
  }
  async function load() {
    const marketTask = readJson("fed-direction-study.json").then(raw => {
      marketRows = new Map(raw.rows.map(values => {
        const row = Object.fromEntries(raw.fields.map((key,i) => [key,values[i]]));
        return [row.date,row];
      }));
    }).catch(() => {}).finally(() => { marketLoaded = true; detail(); });
    const validationTask = readJson("stance-validation.json").then(v => {
      marketObs = new Map(v.observations.map(row => [row.date,row]));
      expectationRows = new Map((v.expectations?.observations || []).map(row => [row.date,row]));
      validation(v);
      detail();
    }).catch(() => {
      byId("validation-result").textContent = "The matched market data could not be loaded.";
    });
    try {
      data = await readJson("fed-statement-stance.json");
      records = [...data.records].sort((a,b) => b.date.localeCompare(a.date));
      if (!records.length) throw new Error("No statements");
      for (const year of new Set(records.map(r => r.date.slice(0,4)))) filters.year.append(option(year,year));
      const params = new URLSearchParams(location.search);
      for (const [name,input] of Object.entries(filters)) {
        if ([...input.options].some(o => o.value === params.get(name))) input.value = params.get(name);
        input.addEventListener("change", () => applyFilters(selected?.date));
      }
      byId("reset-filters").addEventListener("click",() => {
        for (const input of Object.values(filters)) input.value = "";
        applyFilters(selected?.date);
      });
      byId("case-select").addEventListener("change",e => selectRow(matching.find(row => row.date === e.target.value)));
      byId("older-rows").addEventListener("click",() => { offset += pageSize; ledger(); });
      byId("recent-rows").addEventListener("click",() => { offset = Math.max(0,offset - pageSize); ledger(); });
      const c = data.coverage;
      byId("score-coverage").textContent = dateText(c.start) + " to " + dateText(c.end) + " · " + c.documents + " decision statements · " + c.comparableShifts + " comparable changes";
      method();
      await validationTask;
      applyFilters(params.get("date"),true);
      byId("score-status").hidden = true;
      byId("score-explorer").hidden = false;
    } catch (error) {
      byId("score-status").textContent = "The statement dataset could not be loaded. Refresh this page to try again.";
    }
    await Promise.all([marketTask,validationTask]);
  }
  load();
})();
