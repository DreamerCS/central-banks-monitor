(() => {
  "use strict";
  const get = id => document.getElementById(id);
  const formatDate = new Intl.DateTimeFormat("en-GB", {day:"numeric", month:"short", year:"numeric", timeZone:"UTC"});
  const displayDate = day => formatDate.format(new Date(day + "T12:00:00Z"));
  const number = Number.isFinite;
  const tolerance = 1e-7;
  const polarity = value => value > 0 ? "+" : value < 0 ? "−" : "";
  const signed = (value, digits=0) => polarity(value) + Math.abs(value).toFixed(digits);
  const bp = value => number(value) ? signed(Math.abs(value) < 0.005 ? 0 : value, 2) + " bp" : "Unavailable";
  const level = score => number(score) ? signed(score) + (score > 0 ? " · hawkish" : score < 0 ? " · dovish" : " · steady") : "Unscored";
  const median = values => {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  };
  function el(tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function link(label, url) {
    const a = el("a", label);
    a.href = url;
    return a;
  }
  let source, dataset, rows, byDate;
  const controls = {panel:get("panel"), sample:get("sample"), band:get("band"), meeting:get("meeting")};
  const initial = new URLSearchParams(location.search);
  const key = (initial.get("bank") || "fed") + "-" + (initial.get("stage") || "release");
  if ([...controls.panel.options].some(o => o.value === key)) controls.panel.value = key;
  for (const id of ["sample", "band"]) {
    if ([...controls[id].options].some(o => o.value === initial.get(id))) controls[id].value = initial.get(id);
  }
  function persist() {
    const params = new URLSearchParams({bank:dataset.bank, stage:dataset.stage});
    if (controls.meeting.value) params.set("date", controls.meeting.value);
    if (controls.sample.value !== "all") params.set("sample", controls.sample.value);
    if (controls.band.value !== "1") params.set("band", controls.band.value);
    history.replaceState(null, "", "?" + params.toString());
  }
  function showReader(date) {
    const out = get("reader");
    out.replaceChildren();
    const now = byDate.get(date);
    if (!now) return;
    const previous = byDate.get(now.previousDate);
    const card = el("div");
    card.className = "sx-reading";
    for (const [title, rec] of [["Previous meeting", previous], ["Selected meeting", now]]) {
      const section = el("div");
      section.append(el("h4", title));
      if (!rec) {
        section.append(el("p", "This is the first observation in this archive."));
      } else {
        section.append(el("strong", displayDate(rec.date) + " · " + level(rec.score)));
        if (rec.reading) section.append(el("p", rec.reading));
        if (rec.explanation) section.append(el("p", rec.explanation));
        if (rec.url) section.append(link("Read the official communication", rec.url));
        if (!rec.url) section.append(el("p", "No archived communication for this stage."));
      }
      card.append(section);
    }
    out.append(card);
    if (number(now.shift)) {
      const change = now.shift > 0 ? "Firmer" : now.shift < 0 ? "Softer" : "Unchanged";
      out.append(el("p", change + " guidance (" + signed(now.shift) + " score points). " + dataset.instrument + " moved " + bp(now.marketBp) + "."));
    } else {
      out.append(el("p", source.exclude[now.reason]));
      if (now.boundary) out.append(el("p", now.boundary + "."));
      if (number(now.marketBp)) out.append(el("p", dataset.instrument + " moved " + bp(now.marketBp) + "."));
    }
    if (dataset.bank === "fed" && now.date === "2012-12-12" && now.shift === 0) {
      out.append(el("p", "The October statement put the low-rate horizon at least through mid-2015. In December the Fed tied it to unemployment above 6.5%, projected inflation no higher than 2.5% one to two years ahead, and anchored longer-run inflation expectations. Both commitments score −2. The conditions changed while the next-meeting futures rate was flat."));
    }
    const context = [];
    if (now.chair) context.push(now.chair);
    if (now.cycle) context.push(now.cycle);
    if (now.window) context.push(now.window);
    if (context.length) out.append(el("p", context.join(" · ")));
    if (number(now.actionBp)) {
      const gap = number(now.gapBp) ? " Priced for this meeting " + bp(now.pricedBp) + ". Actual minus priced " + bp(now.gapBp) + "." : " Comparable actual-minus-priced gap unavailable.";
      out.append(el("p", "Policy rate change " + bp(now.actionBp) + "." + gap));
    }
    const links = el("div");
    links.className = "sx-links";
    const event = new URLSearchParams({bank:dataset.bank, stage:dataset.stage, date:now.date});
    links.append(link("Cross-asset moves at this event", "cross-asset-events.html?" + event),
      link("Meeting evidence and pricing", "stance-history.html?bank=" + dataset.bank + "&date=" + now.date));
    out.append(links);
  }
  function draw(date) {
    dataset = source.panels.find(p => p.bank + "-" + p.stage === controls.panel.value);
    byDate = new Map(dataset.records.map(r => [r.date, r]));
    const sample = controls.sample.value, band = Number(controls.band.value);
    rows = dataset.records.filter(r => r.reason !== "stage" && (sample === "all" ||
      (sample === "held" ? r.actionBp === 0 : number(r.gapBp) && Math.abs(r.gapBp) <= 1 + tolerance)));
    const comparable = rows.filter(r => number(r.shift));
    const priced = comparable.filter(r => number(r.marketBp));
    const inside = r => Math.abs(r.marketBp) <= band + tolerance;
    const changed = priced.filter(r => r.shift !== 0);
    const repeated = priced.filter(r => r.shift === 0);
    get("coverage").textContent = rows.length + " communications in this selection. " + comparable.length + " have consecutive comparable scores, and " + priced.length + " also have a quote in the event window.";
    const repeatText = repeated.length ? repeated.filter(r => !inside(r)).length + " of " + repeated.length + " windows with an unchanged score still moved by more than " + band + " bp." : "No unchanged scores have matched prices in this selection.";
    const material = changed.filter(r => !inside(r));
    const align = material.filter(r => r.shift * r.marketBp > 0).length;
    get("finding").textContent = repeatText + (material.length ? " Where the score changed and the rate moved beyond the band, the signs agreed in " + align + " of " + material.length + " windows." : " No changed scores have a rate move beyond this band.");
    get("caption").textContent = dataset.instrument + " during the selected communication.";
    const tbody = get("summary"); tbody.replaceChildren();
    for (const [direction,label] of [[1,"Firmer"],[0,"Unchanged"],[-1,"Softer"]]) {
      const group = priced.filter(r => Math.sign(r.shift) === direction);
      const tr = el("tr"), th = el("th", label); th.scope = "row"; tr.append(th);
      for (const val of [group.length,group.filter(r => r.marketBp < -band - tolerance).length,group.filter(inside).length,
        group.filter(r => r.marketBp > band + tolerance).length, bp(median(group.map(r => r.marketBp)))]) tr.append(el("td",String(val)));
      tbody.append(tr);
    }
    get("limits").textContent = "The score change uses the previous meeting as its benchmark. The rate change uses the pre-event quote. The table keeps prices inside the selected band visible.";
    const options = rows.map(r => {const o = el("option", displayDate(r.date) + (number(r.shift) ? " · " + signed(r.shift) : " · no comparison"));o.value = r.date;return o;});
    controls.meeting.replaceChildren(...options.reverse());
    const preferred = dataset.bank === "fed" ? "2023-03-22" : dataset.stage === "conference" ? "2023-03-16" : "2023-09-14";
    const choice = [date,preferred].map(d => rows.find(r => r.date === d)).find(Boolean) || changed.at(-1) || comparable.at(-1) || rows.at(-1);
    if (choice) controls.meeting.value = choice.date;
    if (date && !rows.some(r => r.date === date) && byDate.has(date) && (sample === "all" || !choice)) {
      const requested = byDate.get(date);
      const option = el("option", displayDate(date) + " · outside this sample");
      option.value = date;
      controls.meeting.append(option);
      controls.meeting.value = requested.date;
    }
    showReader(controls.meeting.value);
    const excludes = rows.length - comparable.length;
    const missing = rows.filter(r => ["current","previous"].includes(r.reason)).length;
    get("exclusions").textContent = excludes + " selected communications lack a comparable previous score. In " + missing + " of them, at least one of the two meetings lacks a scored reading for this stage.";
    const sources = get("sources"); sources.replaceChildren();
    const unique = new Map();
    for (const [day, name, url] of source.boundaries[dataset.bank]) {
      if (!unique.has(url)) unique.set(url, []);
      unique.get(url).push(day.slice(0,4));
    }
    sources.append(link("Intraday data source", dataset.marketSource), link("Download the paired data (JSON)", "data/guidance-shifts.json"));
    for (const [url, years] of unique) sources.append(link("Framework or benchmark · " + [...new Set(years)].join(" / "),url));
  }
  async function start() {
    const resp = await fetch("data/guidance-shifts.json");
    if (!resp.ok) throw new Error("data");
    source = await resp.json();
    draw(initial.get("date"));
    get("load").hidden = true; get("app").hidden = false;
    for (const id of ["panel","sample","band"]) controls[id].addEventListener("change", () => {draw(controls.meeting.value); persist();});
    controls.meeting.addEventListener("change", () => {showReader(controls.meeting.value);persist();});
  }
  start().catch(() => {get("load").textContent = "Meeting comparisons could not be loaded. Reload this page to try again.";});
})();
