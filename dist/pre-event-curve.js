const scopes = [1, 5, 20];
const shortDate = new Intl.DateTimeFormat("en-GB", {day:"numeric", month:"short", timeZone:"UTC"});
const fullDate = new Intl.DateTimeFormat("en-GB", {day:"numeric", month:"short", year:"numeric", timeZone:"UTC"});
const dateString = (date, short = false) => (short ? shortDate : fullDate).format(new Date(date + "T12:00:00Z"));
const bp = value => value > 0 ? "+" + value : value < 0 ? "−" + Math.abs(value) : "0";

function validDate(value) {
  if (!/^\d{4}-\d\d-\d\d$/.test(value)) return false;
  const date = new Date(value + "T12:00:00Z");
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

// Official par rates are quoted to two decimal places in percent.
function moves(from, to) {
  const two = Math.round((to.y2 - from.y2) * 100);
  const ten = Math.round((to.y10 - from.y10) * 100);
  return {two, ten, slope:ten - two};
}

function frameForDate(quotes, date) {
  let low = 0, high = quotes.length;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (quotes[mid].date < date) low = mid + 1;
    else high = mid;
  }
  const prior = low - 1;
  const same = quotes[low]?.date === date ? quotes[low] : null;
  return {
    prior: quotes[prior],
    before: scopes.map(n => [n, quotes[prior - n], quotes[prior]]),
    path: quotes.slice(Math.max(0, prior - 20), prior + 1),
    same,
    next: quotes[low + (same ? 1 : 0)]
  };
}

function normaliseUrl(raw) {
  try {
    const url = new URL(raw);
    if (url.hostname === "federalreserve.gov") url.hostname = "www.federalreserve.gov";
    if (url.hostname === "www.federalreserve.gov" && url.protocol === "http:") url.protocol = "https:";
    if (url.protocol !== "https:") return "";
    url.hash = "";
    return url.href.replace(/\/$/, "");
  } catch {
    return "";
  }
}

function combineEvents(primary, policy, eventStudy) {
  const result = [];
  const statements = new Map();
  const seenSpeeches = new Set();
  for (const item of primary) {
    if (!validDate(item.date) || !item.title) continue;
    if (/decision|statement|meeting/i.test(item.kind) && !/speech/i.test(item.kind)) {
      statements.set(item.date, {...item, group:"statement"});
      continue;
    }
    const key = [item.date, item.url, item.title].join("|");
    if (!seenSpeeches.has(key)) result.push({...item, group:"speech"});
    seenSpeeches.add(key);
  }
  for (const item of policy?.observations || []) {
    if (validDate(item.date) && !statements.has(item.date)) statements.set(item.date, {...item, group:"statement", speaker:"FOMC"});
  }
  const fed = eventStudy?.banks?.find(bank => bank.id === "fed");
  for (const item of fed?.events || []) {
    if (item.windows?.statement && validDate(item.date) && !statements.has(item.date)) {
      statements.set(item.date, {date:item.date, group:"statement", title:"FOMC statement", speaker:"FOMC", sourceUrl:fed.source});
    }
  }
  result.push(...statements.values());
  return result.sort((a,b) => b.date.localeCompare(a.date) || (b.time || "").localeCompare(a.time || "") || a.title.localeCompare(b.title));
}

function description(change) {
  const {two, ten, slope} = change;
  const shape = slope > 0 ? "steepened by " + slope + " bp" : slope < 0 ? "flattened by " + -slope + " bp" : "was unchanged";
  const direction = move => move > 0 ? "rose" : move < 0 ? "fell" : "was unchanged";
  const legs = two > 0 && ten > 0 ? "Both yields rose" : two < 0 && ten < 0 ? "Both yields fell"
    : "The two-year yield " + direction(two) + " and the ten-year yield " + direction(ten);
  return legs + ". The 2s10s curve " + shape + ".";
}

function svgEl(name, attributes, content) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key,value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  if (content !== undefined) node.textContent = content;
  return node;
}

function drawPath(host, path) {
  if (!path.length) { host.replaceChildren(); return; }
  const width = Math.max(240, Math.floor(host.clientWidth || 600));
  const height = width < 520 ? 164 : 182;
  const x0 = 53, x1 = width - 8, y0 = 15, y1 = height - 30;
  const values = path.flatMap(r => [r.y2,r.y10]);
  const lo = Math.floor(Math.min(...values) * 10) / 10;
  const hi = Math.max(Math.ceil(Math.max(...values) * 10) / 10, lo + .1);
  const x = i => path.length === 1 ? (x0+x1)/2 : x0 + (x1-x0)*i/(path.length-1);
  const y = v => y1 - (y1-y0)*(v-lo)/(hi-lo);
  const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":`Two- and ten-year Treasury yields over ${path.length} quoted closes from ${dateString(path[0].date)} to ${dateString(path.at(-1).date)}.`});
  for (const level of [lo,(hi+lo)/2,hi]) {
    svg.append(svgEl("line",{x1:x0,x2:x1,y1:y(level),y2:y(level),stroke:"#657467","stroke-width":.6}));
    svg.append(svgEl("text",{x:x0-5,y:y(level)+4,"text-anchor":"end"},level.toFixed(2)+"%"));
  }
  for (const [key,colour,dash] of [["y2","#b9debd","none"],["y10","#f4b589","6 4"]]) {
    const points = path.map((r,i) => x(i).toFixed(1)+","+y(r[key]).toFixed(1)).join(" ");
    svg.append(svgEl("polyline",{points,fill:"none",stroke:colour,"stroke-width":2.2,"stroke-dasharray":dash}));
    svg.append(svgEl("circle",{cx:x(path.length-1),cy:y(path.at(-1)[key]),r:3,fill:colour}));
  }
  svg.append(svgEl("text",{x:x0,y:height-7},dateString(path[0].date,true)));
  if (path.length>1) svg.append(svgEl("text",{x:x1,y:height-7,"text-anchor":"end"},dateString(path.at(-1).date,true)));
  host.replaceChildren(svg);
}

function row(label, from, to) {
  const tr = document.createElement("tr");
  const th = document.createElement("th");
  th.scope="row"; th.textContent=label; tr.append(th);
  const dates = document.createElement("td");
  dates.textContent = from && to ? dateString(from.date,from.date.slice(0,4)===to.date.slice(0,4))+" – "+dateString(to.date) : "—";
  tr.append(dates);
  const change = from && to ? moves(from,to) : null;
  for (const key of ["two","ten","slope"]) {
    const td = document.createElement("td");
    td.textContent = change ? bp(change[key]) : "—";
    tr.append(td);
  }
  return tr;
}

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error("Data unavailable");
  return response.json();
}

async function start() {
  const section = document.getElementById("pre-event-curve");
  if (!section) return;
  const el = name => document.getElementById("pc-"+name);
  const parameters = new URLSearchParams(location.search);
  try {
    const [data, policy, market] = await Promise.all([
      getJson("data/pre-event-curve.json"),
      getJson("data/policy-guidance.json").catch(() => null),
      getJson("data/market-events.json").catch(() => null)
    ]);
    const quotes = data.observations.filter(r => validDate(r.date) && Number.isFinite(r.y2) && Number.isFinite(r.y10));
    if (!quotes.length || quotes.some((r,i) => i && r.date <= quotes[i-1].date)) throw new Error("Invalid curve data");
    const events = combineEvents(data.events || [],policy,market);
    const first = quotes[0].date, last = quotes.at(-1).date;
    const through = [last,data.asOfDate,data.eventsThrough].filter(validDate).sort().at(-1);
    const dateInput=el("date"), kind=el("kind"), year=el("year"), event=el("event");
    el("content").hidden=false; el("status").hidden=true;
    dateInput.min=first; dateInput.max=through;
    const sources = [...(data.market?.sources || []),{label:"US Treasury quotation methodology",url:"https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology"}];
    const usedUrls = new Set();
    for (const source of sources) {
      const url=normaliseUrl(source.url);
      if (!url || usedUrls.has(url)) continue;
      const a=document.createElement("a"); a.href=source.url; a.textContent=source.label || "Official source"; el("sources").append(a);
      usedUrls.add(url);
    }
    let current = null;
    let path = [];

    function yearsInGroup() {
      return [...new Set(events.filter(item => item.group===kind.value).map(item => item.date.slice(0,4)))];
    }
    function eventOptions(preferred) {
      const term=kind.value==="speech" ? el("search").value.trim().toLowerCase() : "";
      const choices=events.filter(item => item.group===kind.value && item.date.startsWith(year.value) && (!term || [item.speaker,item.title].join(" ").toLowerCase().includes(term)));
      event.replaceChildren(...choices.map(item => new Option(dateString(item.date,true)+" · "+(item.group==="speech" && item.speaker ? item.speaker+" · " : "")+item.title,String(events.indexOf(item)))));
      if (preferred && choices.includes(preferred)) event.value=String(events.indexOf(preferred));
      current=event.value ? events[Number(event.value)] : null;
    }
    function setGroup(group, preferred) {
      kind.value=group;
      const custom=group==="custom";
      el("year-field").hidden=custom; el("event-field").hidden=custom; el("date-field").hidden=!custom; el("search-field").hidden=group!=="speech";
      if (custom) { current=null; return; }
      const years=yearsInGroup();
      year.replaceChildren(...years.map(value => new Option(value,value)));
      if (preferred) year.value=preferred.date.slice(0,4);
      eventOptions(preferred);
    }
    function saveDate(date) {
      const url=new URL(location.href);
      url.searchParams.set("curveDate",date);
      if (current?.url) url.searchParams.set("curveEvent",current.url);
      else url.searchParams.delete("curveEvent");
      if (!current) url.searchParams.set("curveKind","custom");
      else url.searchParams.delete("curveKind");
      history.replaceState(history.state,"",url);
    }
    function render(updateUrl) {
      const date = current?.date || (kind.value === "custom" ? dateInput.value : "");
      if (current) dateInput.value=date;
      const note=el("event-note"); note.replaceChildren();
      el("results").hidden=true;
      path=[];
      section.dataset.date=date;
      section.dataset.kind=current?.group || "custom";
      section.dataset.eventUrl=current?.url || "";
      section.dispatchEvent(new CustomEvent("pre-event-date",{bubbles:true,detail:{date,kind:section.dataset.kind,eventUrl:current?.url || ""}}));
      if (!validDate(date)) {
        note.textContent=kind.value==="speech" && el("search").value.trim() ? "No matching speech in this year. Change the year or search terms." : "Choose an event or enter a valid date.";
        return;
      }
      if (updateUrl) saveDate(date);
      if (date<first || date>through) { note.textContent="Choose a date between "+dateString(first)+" and "+dateString(through)+"."; return; }
      const prefix=current?.speaker && current.group==="speech" ? current.speaker+" · " : "";
      const fact=dateString(date)+(current?.time?" · "+current.time+(current.group==="speech" ? " ET · Board-listed release time" : " ET · release time"):"");
      if (current) {
        const cited=normaliseUrl(current.url);
        const name=document.createElement(cited?"a":"strong");
        name.textContent=prefix+current.title;
        if (cited) name.href=current.url;
        note.append(name,document.createTextNode(" · "+fact));
        if (!cited && current.sourceUrl) {
          const source=document.createElement("a"); source.href=current.sourceUrl; source.textContent="USMPD source";
          note.append(document.createTextNode(" · "),source);
        }
      } else note.textContent="Custom date · "+fact;
      const frame=frameForDate(quotes,date);
      if (!frame.prior) {note.append(document.createTextNode(" · No earlier paired quote is available."));return;}
      if (date > last && (Date.parse(date)-Date.parse(last))/86400000 > 7) {
        note.append(document.createTextNode(" · The latest paired quote is "+dateString(last)+". There is insufficient recent coverage for this window.")); return;
      }
      el("results").hidden=false;
      path=frame.path;
      el("period").textContent=dateString(path[0].date)+" – "+dateString(frame.prior.date)+" · "+path.length+" quoted closes";
      drawPath(el("chart"),path);
      el("levels").textContent="Last pre-event quote · 2Y "+frame.prior.y2.toFixed(2)+"% · 10Y "+frame.prior.y10.toFixed(2)+"% · 2s10s "+bp(Math.round((frame.prior.y10-frame.prior.y2)*100))+" bp";
      el("before").replaceChildren(...frame.before.map(([n,a,b]) => row(n+" session"+(n===1?"":"s")+" before",a,b)));
      el("after").replaceChildren(row("Event-date close",frame.prior,frame.same),row("First later close",frame.same || frame.prior,frame.next));
      const [n,from,to]=frame.before.filter(([,a])=>a).at(-1) || [];
      if (from) {
        const reading=description(moves(from,to));
        el("reading").textContent="Over the "+n+"-session pre-event window, "+reading.charAt(0).toLowerCase()+reading.slice(1);
      } else el("reading").textContent="";
      let timing;
      if (date>last) timing="Daily observations currently end on "+dateString(last)+".";
      else if (!frame.same) timing="There is no joint quote on the event date. The first later close is compared with the final pre-event close.";
      else if (current?.time && current.time >= "15:30") timing="The listed release time is at or after the Treasury’s usual sampling time. The event-date close can precede the release.";
      else if (current && !current.time) timing="The event’s intraday timing is unverified here, so the event-date close may precede or follow it.";
      else timing="The event-date row covers the full close-to-close interval.";
      el("timing").textContent=timing+" The chart uses only closes strictly before the selected date.";
    }
    const requested=parameters.get("curveDate") || (parameters.get("bank")==="fed" ? parameters.get("date") : null);
    const wantedUrl=normaliseUrl(parameters.get("curveEvent"));
    const matches=events.filter(item => item.date===requested);
    let chosen = wantedUrl ? matches.find(item => normaliseUrl(item.url)===wantedUrl) : matches.find(item => item.group==="statement") || (matches.length===1 ? matches[0] : null);
    if (parameters.get("curveKind")==="custom") chosen=null;
    if (!requested) chosen=events.find(item => item.group==="speech" && item.date<=through && item.date>=first) || events[0];
    setGroup(chosen?.group || "custom",chosen);
    dateInput.value=validDate(requested)?requested:(chosen?.date || last);
    kind.addEventListener("change",() => {setGroup(kind.value); render(true);});
    year.addEventListener("change",() => {eventOptions(); render(true);});
    event.addEventListener("change",() => {current=events[Number(event.value)]; render(true);});
    el("search").addEventListener("input",() => {eventOptions(current); render(true);});
    dateInput.addEventListener("change",() => render(true));
    render(false);
    if (typeof ResizeObserver==="function") {
      let chartWidth=el("chart").clientWidth;
      new ResizeObserver(() => {
        const w=el("chart").clientWidth;
        if (w && w!==chartWidth && path.length) drawPath(el("chart"),path);
        chartWidth=w;
      }).observe(el("chart"));
    }
  } catch {
    el("content").hidden=true;
    el("status").hidden=false;
    el("status").textContent="Treasury history could not be loaded. Refresh to try again.";
  }
}

start();
