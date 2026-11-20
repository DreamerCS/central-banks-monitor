const root = document.querySelector("#study");
const params = new URLSearchParams(location.search);
const cache = new Map();
const num = (x, decimals = 1) => Number.isFinite(x) ? x.toFixed(decimals) : "—";
const colours = {line:"#e8c198", shade:"#596b58", point:"#fff8db"};

function read(file) {
  if (!cache.has(file)) {
    const request = fetch("data/" + file + ".json").then(response => {
      if (!response.ok) throw Error(file);
      return response.json();
    }).catch(error => { cache.delete(file); throw error; });
    cache.set(file, request);
  }
  return cache.get(file);
}
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function link(text, url) {
  const a = el("a",text);
  a.href = url;
  return a;
}
function local(view, entries = {}) {
  return "macro-history.html?" + new URLSearchParams({view, ...entries});
}
function select(label, options, value, onChange) {
  const field = el("label",label,"hs-control");
  const input = el("select");
  for (const [id, text] of options) input.add(new Option(text, id));
  input.value = value;
  input.addEventListener("change",() => onChange(input.value));
  field.append(input);
  return field;
}
function table(headers, rows, caption) {
  const wrap = el("div",undefined,"hs-scroll");
  const t = el("table",undefined,"hs-table");
  if (caption) t.setAttribute("aria-label",caption);
  const h = t.createTHead().insertRow();
  for (const label of headers) { const cell=el("th",label); cell.scope="col";h.append(cell); }
  const body = t.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const value of row) {const td=tr.insertCell();if(value instanceof Node)td.append(value);else td.textContent=value;}
  }
  wrap.append(t);
  return wrap;
}
function sourceList(sources) {
  const details = el("details",undefined,"hs-sources");
  const list = el("ul",undefined,"hs-links");
  for (const s of sources) {const item=el("li");item.append(link(s.label,s.url));list.append(item);}
  details.append(el("summary","Sources"),list);
  return details;
}
function navItem(title,subtitle,url,current) {
  const a=link("",url);
  a.append(el("small",subtitle),document.createTextNode(title));
  if(current)a.setAttribute("aria-current","page");
  return a;
}
function layout() {
  const grid=el("div",undefined,"hs-grid"), nav=el("nav",undefined,"hs-list"), article=el("article",undefined,"hs-article");
  grid.append(nav,article);
  return {grid,nav,article};
}
function svgNode(tag,attributes={}) {
  const n=document.createElementNS("http://www.w3.org/2000/svg",tag);
  for (const [k,v] of Object.entries(attributes)) n.setAttribute(k,v);
  return n;
}
function chart(rows, series, anchor, geography, recessions, options = {}) {
  const figure=el("figure",undefined,"hs-figure"), heading=el("figcaption"), controls=el("div",undefined,"hs-bars");
  const graphic=svgNode("svg",{viewBox:"0 0 760 190","aria-hidden":"true"}),slider=el("input",undefined,"hs-slider"),output=el("output");
  const names=options.names || {cpiYoY:"Consumer price inflation · year on year",unemployment:"Unemployment rate",industrialProductionYoY:"Industrial production · year on year"};
  let key=Object.keys(names)[0], index=Math.max(0,rows.findIndex(d=>d.month===anchor));
  if(!rows.length)return el("p","No published monthly observations in this period.");
  slider.type="range";slider.min=0;slider.max=rows.length-1;slider.step=1;slider.value=index;
  slider.setAttribute("aria-label","Observation month");
  controls.append(select("Indicator",Object.entries(names),key,value=>{key=value;draw();}));
  const hint=el("div",options.hint || (recessions?"Shading indicates US recession months, dated retrospectively.":"Euro area · fixed EA21 membership."),"hs-legend");
  const credits=el("p",undefined,"hs-legend");
  figure.append(el("div",geography+" · monthly observations","hs-kicker"),heading,controls,graphic,slider,output,hint,credits);
  function draw() {
    heading.textContent=names[key];
    const width=760,left=43,right=12,top=12,bottom=158;
    const values=rows.map(r=>r[key]).filter(Number.isFinite);
    const low=Math.min(0,...values),high=Math.max(0,...values),step=Math.max(1,high-low)/4;
    const ymin=low-step*.22,ymax=high+step*.22;
    const x=i=>left+i*(width-left-right)/Math.max(1,rows.length-1),y=v=>bottom-(v-ymin)*(bottom-top)/(ymax-ymin);
    graphic.replaceChildren();
    if (recessions) {
      for(let i=0;i<rows.length;i++){
        if(rows[i].recession!==1)continue;
        const first=i;while(i+1<rows.length&&rows[i+1].recession===1)i++;
        const x1=Math.max(left,x(first-.5)),x2=Math.min(width-right,x(i+.5));
        graphic.append(svgNode("rect",{x:x1,y:top,width:x2-x1,height:bottom-top,fill:colours.shade,opacity:.63}));
      }
    }
    for(const val of [...new Set([low,high,0])]){
      graphic.append(svgNode("line",{x1:left,x2:width-right,y1:y(val),y2:y(val),class:"tick"}));
      const tick=svgNode("text",{x:left-5,y:y(val)+4,"text-anchor":"end"});tick.textContent=num(val)+"%";graphic.append(tick);
    }
    let d="",connect=false;
    rows.forEach((r,i)=>{
      if(!Number.isFinite(r[key])) {connect=false;return;}
      d+=(connect?"L":"M")+x(i).toFixed(2)+" "+y(r[key]).toFixed(2)+" ";connect=true;
    });
    graphic.append(svgNode("path",{d,stroke:colours.line,fill:"none","stroke-width":2.5}));
    for(const i of new Set([0,Math.floor((rows.length-1)/2),rows.length-1])){
      const txt=svgNode("text",{x:x(i),y:184,"text-anchor":i===0?"start":i===rows.length-1?"end":"middle"});txt.textContent=rows[i].month;graphic.append(txt);
    }
    graphic.append(svgNode("line",{x1:x(index),x2:x(index),y1:top,y2:bottom,stroke:colours.point,"stroke-dasharray":"3 4",opacity:.7}));
    const value=rows[index][key];
    if(Number.isFinite(value)) graphic.append(svgNode("circle",{cx:x(index),cy:y(value),r:4,fill:colours.point}));
    output.textContent=rows[index].month+"  ·  "+(Number.isFinite(value)?num(value,2)+"%":"No observation");
    if (Number.isInteger(rows[index].n)) output.textContent += "  ·  " + rows[index].n + " matched daily returns";
    slider.setAttribute("aria-valuetext",output.textContent);
    const s=series[key];credits.replaceChildren(link(s.source,s.sourceUrl));
    credits.firstChild.style.color="inherit";
  }
  slider.addEventListener("input",()=>{index=Number(slider.value);draw();});
  draw();return figure;
}
const idOf = profile=>profile.name.split(" ").at(-1).toLowerCase();
function dateTitle(date) {
  return new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}).format(new Date(date+"T00:00:00Z"));
}

function testSection(results) {
  const block=el("section",undefined,"hs-wide");
  block.append(el("p","Historical forecast test · United States","hs-kicker"),el("h2","Which decade travels best?"),
    el("p","Each model predicts US year-on-year CPI inflation six months ahead using the inflation rate and the twelve-month change in unemployment at the forecast origin. Only the historical training sample changes. The benchmark carries current inflation forward."));
  const controls=el("div",undefined,"hs-bars"),target=el("div");
  function show(period) {
    const t=results.tests.find(x=>x.period===period);
    target.replaceChildren(el("p",t.n+" matched target months · "+t.firstTarget+" to "+t.lastTarget+". Errors are in percentage points; smaller values indicate closer forecasts.","hs-byline"),
      table(["Training sample","Mean absolute error","Root mean squared error"],t.scores.map(r=>[r.name,num(r.mae,2),num(r.rmse,2)]),"Six-month inflation forecast errors"));
  }
  const last=results.tests.at(-1);
  controls.append(select("Evaluation targets",results.tests.map(x=>[x.period,x.period]),last.period,show));show(last.period);
  const details=el("details",undefined,"hs-details");
  details.append(el("summary","Specification and interpretation"),el("p","Direct OLS with an intercept, one equation per training sample. Both the forecast origin and its six-month outcome fall within training dates. Evaluation origins start in January 2020. Each model uses the same non-missing evaluation months. Six-month-ahead year-on-year inflation shares six underlying price months with today’s year-on-year reading."),
    el("p","Inputs are a November 2026 historical vintage. Earlier policymakers saw different releases and revisions. Monthly errors overlap, the crisis years influence the coefficients, and the evaluation covers few independent shocks. These are retrospective forecasting comparisons. A finding for inflation does not establish the best period for an FX, growth or rates forecast."),
    table(["Training sample","Fitted months","Intercept","Inflation","Change in unemployment"],results.models.filter(x=>x.n).map(m=>[m.name,m.n,...m.coefficients.map(x=>num(x,3))]),"Fitted coefficients"));
  block.append(controls,target,el("p","Including 2008 improves the pre-crisis model’s 2022–26 mean absolute error from 1.05 to 0.81 percentage points. In the pandemic evaluation, unchanged inflation outperforms every fitted model. The preferred comparison changes with the period being forecast."),details);
  block.append(link("Compare rolling and real-time forecasts","empirical-studies.html?study=inflation#vintage-check"));
  return block;
}
async function cycles() {
  const [history,episodes,tests]=await Promise.all([read("cycle-context"),read("history-episodes"),read("regime-test")]);
  const item=episodes.find(x=>x.id===params.get("episode"))||episodes.find(x=>x.id==="volcker");
  const {grid,nav,article}=layout();nav.setAttribute("aria-label","Historical episodes");
  for(const ep of episodes) nav.append(navItem(ep.name,ep.period,local("cycles",{episode:ep.id}),item.id===ep.id));
  article.append(el("p",(item.geography || "United States")+" · "+item.period,"hs-kicker"),el("h2",item.name),el("p",item.headline,"hs-deck"));
  if (item.id === "bretton-woods-floats") {
    const fx = await read("historical-fx");
    article.append(chart(fx.rows, fx.series, item.anchor, item.geography, false, {
      names: {dem:"Deutsche mark · mean absolute daily move", gbp:"Sterling · mean absolute daily move"},
      hint:"Daily log changes against the US dollar, averaged by calendar month on common observation dates."
    }));
    const rows = fx.windows.slice(0, 3).map(({label, main}) => [
      label, main.firstReturnEnd + " to " + main.lastReturnEnd, main.n,
      num(main.currency.gbp.meanAbsolutePct, 3) + "%", num(main.currency.dem.meanAbsolutePct, 3) + "%"
    ]);
    article.append(el("h3","How much did each currency move?"),
      table(["Exchange-rate arrangement","Return dates","Days","Sterling · mean absolute move","Mark · mean absolute move"],rows,"Mean absolute daily log returns against the dollar"));
  } else {
    article.append(chart(history.rows.filter(r=>r.month>=item.start&&r.month<=item.end),history.series,item.anchor,history.geography,true));
  }
  article.append(el("p",item.analysis));
  for(const part of item.details || []) article.append(el("h3",part.heading),el("p",part.text));
  if (item.balanceSheet) {
    const {title, note, rows} = item.balanceSheet;
    article.append(el("h3", title), el("p", note),
      table(["Wednesday observation", "Reserve Bank credit", "Securities held outright", "Term auction credit"],
        rows.map(row => [link(row.date, row.url), num(row.credit, 2), num(row.outright, 2),
          row.auction === null ? "Before launch" : num(row.auction, 2)]), title));
  }
  if (item.studyLink) article.append(link(item.studyLink.label, item.studyLink.url));
  article.append(el("h3","What would test the analogy?"),el("p",item.test),sourceList(item.sources));
  if (item.id !== "bretton-woods-floats") article.append(testSection(tests));
  return grid;
}
const signalLabels = {
  tightening: "Tightening bias",
  easing: "Easing bias",
  balanced: "Hold or two-sided guidance",
  unclear: "No explicit rate direction"
};
function policyAction(o) {
  const verb = {hold:"Hold",raise:"Increase",cut:"Cut",lower:"Cut"}[o.action] || o.action;
  if (o.rateChangeBps === 0 || !Number.isFinite(o.rateChangeBps)) return verb;
  return verb + " · " + Math.abs(o.rateChangeBps) + " bp";
}
function releaseWindow(observation) {
  return observation.sourceType === "press-conference" ? "conference" : "statement";
}
function marketSection(events, bankId, observation) {
  const section=el("section");
  const bank=events?.banks.find(b=>b.id===bankId);
  const windowId=releaseWindow(observation);
  const change=bank?.events.find(e=>e.date===observation.date)?.windows[windowId];
  section.append(el("h3","What moved in the release window?"));
  if (!change) {
    section.append(el("p","A matched intraday observation is unavailable for this release window.","hs-byline"));
    return section;
  }
  const ids=bankId==="fed"?["MP1","MP2","UST2Y","EURUSD","SP500"]:["OIS_1M","OIS_1Y","DE2Y","EURUSD","STOXX50"];
  const rows=bank.assets.filter(a=>ids.includes(a.id)&&Number.isFinite(change[a.id])).map(a=>[a.label,(change[a.id]>0?"+":"")+num(change[a.id],2)+" "+a.unit]);
  section.append(el("p",bank.windows[windowId],"hs-byline"),table(["Instrument","Observed change"],rows,"Price changes in the matched release window"));
  const links=el("p",undefined,"hs-byline");
  links.append(link(bank.sourceLabel,bank.source)," · ",link("Open this market event","market-reactions.html?"+new URLSearchParams({bank:bankId,year:observation.date.slice(0,4),date:observation.date,window:windowId})));
  section.append(links);
  return section;
}
async function guidance() {
  const bankId=params.get("bank")==="ecb"?"ecb":"fed";
  const [panel,market,notes]=await Promise.all([read(bankId==="fed"?"policy-guidance":"ecb-guidance"),read("market-events").catch(()=>null),read("research-notes").catch(()=>[])]);
  const sorted=[...panel.observations].sort((a,b)=>b.date.localeCompare(a.date));
  const years=[...new Set(sorted.map(o=>o.date.slice(0,4)))];
  const requested=sorted.find(o=>o.date===params.get("date")&&(!params.has("window")||params.get("window")===releaseWindow(o)));
  const year=["all",...years].includes(params.get("year"))?params.get("year"):requested?.date.slice(0,4)||years[0];
  const state=Object.hasOwn(signalLabels,params.get("signal"))?params.get("signal"):"all";
  const subset=sorted.filter(o=>(year==="all"||o.date.startsWith(year))&&(state==="all"||state===o.state));
  const chosen=subset.find(o=>o===requested)||subset[0];
  const page=el("article",undefined,"hs-article hs-wide"),controls=el("div",undefined,"hs-bars");
  page.append(el("p","2000–2026 · Selected policy meetings","hs-kicker"),el("h2","Reading the policy signal"),
    el("p","Did policymakers signal a change in the next rate decision? Read the guidance alongside the rate action they took and what markets priced in the same release window."));
  const address=(y,s,o)=>local("guidance",{bank:bankId,year:y,signal:s,...(o?{date:o.date,window:releaseWindow(o)}:{})});
  controls.append(select("Institution",[["fed","Federal Reserve"],["ecb","European Central Bank"]],bankId,b=>location.assign(local("guidance",{bank:b}))),
    select("Year",[["all","All years"],...years.map(y=>[y,y])],year,y=>location.assign(address(y,state))),
    select("Guidance",[["all","All signals"],...Object.entries(signalLabels)],state,s=>location.assign(address(year,s))));
  page.append(controls,el("p",subset.length+" of "+sorted.length+" documented releases in this selection.","hs-byline"));
  if(chosen) {
    const detail=el("section"),label=chosen.sourceType==="press-conference"?"Press conference":"Decision statement";
    const original=el("p");original.append(link("Read the official "+label.toLowerCase(),chosen.url));
    const note=notes.find(n=>n.url===chosen.url || n.publication?.aliases?.includes(chosen.url));
    if(note) original.append(" · ",link("Read the archive analysis","research-archive.html?analysis="+encodeURIComponent(note.file.replace(/\.json$/,""))));
    detail.append(el("p",dateTitle(chosen.date)+" · "+label,"hs-kicker"),el("h3",signalLabels[chosen.state]),el("p",policyAction(chosen)+" on the day · "+(chosen.voice||"Federal Open Market Committee"),"hs-byline"),el("p",chosen.evidence,"hs-deck"),el("p",chosen.analysis));
    if(chosen.balanceSheet) detail.append(el("p",chosen.balanceSheet));
    if(chosen.priorDate) {
      const prior=sorted.find(o=>o.date===chosen.priorDate&&releaseWindow(o)===releaseWindow(chosen));
      if(prior){
        const p=el("p",undefined,"hs-byline");
        p.append("Previous meeting · ",link(dateTitle(prior.date),address(prior.date.slice(0,4),"all",prior))," · "+signalLabels[prior.state]);
        if(chosen.shift) p.append(chosen.shift.kind==="explicitness"?" · Change in explicitness":" · Change in rate guidance");
        detail.append(p);
      }
    }
    detail.append(original,marketSection(market,bankId,chosen));
    page.append(detail,el("h3","Release record"),table(["Date","Communication","Rate action","Forward guidance"],subset.map(o=>[link(o.date,address(year,state,o)),releaseWindow(o)==="conference"?"Press conference":"Decision statement",policyAction(o),signalLabels[o.state]]),"Selected policy releases"));
  } else page.append(el("p","No documented release matches this selection."));
  const definitions=el("details",undefined,"hs-details");
  definitions.append(el("summary","How to read the four signals"));
  for(const [key,value] of Object.entries(panel.definitions)) definitions.append(el("h4",signalLabels[key]),el("p",value));
  definitions.append(el("p",panel.methodology.find(m=>m.includes("selected")||m.includes("interpolated"))||panel.methodology[0]),link("Official meeting archive",panel.calendarUrl));
  page.append(definitions,link("Compare market responses by guidance signal","empirical-studies.html?study=guidance"));
  return page;
}
async function main(){
  const views={cycles,leaders,guidance};
  const view=Object.hasOwn(views,params.get("view"))?params.get("view"):"cycles";
  document.querySelector('[data-view="'+view+'"]').setAttribute("aria-current","page");
  try {
    root.replaceChildren(await views[view]());
  } catch(error) {
    console.error(error);
    const p=el("p","Research data could not be loaded. ");
    p.setAttribute("role","alert");p.append(link("Reload this page",location.href));root.replaceChildren(p);
  } finally {root.setAttribute("aria-busy","false");}
}
async function leaders() {
  const [fed, ecb, fiscal, notes] = await Promise.all([
    read("fed-leadership"), read("ecb-leadership"), read("fiscal-history"), read("research-notes")
  ]);
  const banks = [
    {id:"fed", name:"Federal Reserve", area:"United States", history:"cycle-context", fiscal:"us", profiles:fed.profiles},
    {id:"ecb", name:"European Central Bank", area:"Euro area", history:"euro-cycle-context", fiscal:"ea", profiles:ecb.profiles}
  ];
  const requested = params.get("leader");
  const bank = banks.find(b => b.id === params.get("bank"))
    || banks.find(b => b.profiles.some(p => idOf(p) === requested)) || banks[0];
  const profile = bank.profiles.find(p => idOf(p) === requested) || bank.profiles.at(-1);
  const panel = await read(bank.history);
  const budget = fiscal.series.find(s => s.id === bank.fiscal);
  const cutoff = profile.end || panel.asOf;
  const rows = panel.rows.filter(row =>
    row.month >= profile.start.slice(0,7) && row.month <= cutoff.slice(0,7)
  );
  const {grid, nav, article} = layout();
  nav.setAttribute("aria-label", "Central bank leaders");

  function tenure(p) {
    return dateTitle(p.start) + " – " + (p.end ? dateTitle(p.end) : "present");
  }
  function archiveUrl(year, note) {
    const query = new URLSearchParams({scope:"all", bank:bank.area});
    if (year) query.set("month", year === "2026" ? "year" : year);
    if (note) query.set("analysis", note.file.replace(/\.json$/, ""));
    return "research-archive.html?" + query;
  }
  function sourceKey(value) {
    const url = new URL(value);
    return url.origin + url.pathname.replace(/\/$/, "") + url.search + url.hash;
  }
  function monthlySummary(key) {
    const meta = panel.series[key];
    const valid = rows.filter(row => Number.isFinite(row[key]));
    const reading = row => row ? num(row[key], 2) + "% · " + row.month : "—";
    return [meta.label, reading(valid[0]), reading(valid.at(-1))];
  }
  for (const group of banks) {
    nav.append(el("span", group.name, "hs-group"));
    for (const p of [...group.profiles].reverse()) {
      const years = p.start.slice(0,4) + "–" + (p.end ? p.end.slice(0,4) : "present");
      nav.append(navItem(p.name, years, local("leaders", {bank:group.id, leader:idOf(p)}), p === profile));
    }
  }
  article.append(
    el("p", bank.name + " · " + tenure(profile), "hs-kicker"),
    el("h2", profile.name), el("p", profile.role, "hs-byline"),
    el("p", profile.headline, "hs-deck"), el("p", profile.context)
  );

  if (rows.length) {
    const anchor = rows.findLast(row => Number.isFinite(row.cpiYoY))?.month || rows.at(-1).month;
    article.append(
      chart(rows, panel.series, anchor, bank.area, bank.id === "fed"),
      table(["Indicator", "First observation", "Last observation"],
        ["cpiYoY", "unemployment", "industrialProductionYoY"].map(monthlySummary),
        "Available monthly readings overlapping the term")
    );
    const overlaps = bank.profiles.filter(p => p !== profile).flatMap(p => {
      const first = [p.start.slice(0,7), rows[0].month].sort().at(-1);
      const last = [(p.end || panel.asOf).slice(0,7), rows.at(-1).month].sort()[0];
      return first <= last ? [first + " also overlaps " + p.name + "’s term."] : [];
    });
    let dates = "Each reading covers a full calendar month. " + overlaps.join(" ");
    if (rows[0].month > profile.start.slice(0,7)) {
      dates += " The available series begin in " + rows[0].month + ".";
    }
    article.append(el("p", dates.trim(), "hs-byline"));
  }
  article.append(el("h3", "Monetary policy"), el("p", profile.monetary),
    el("h3", "Fiscal setting"), el("p", profile.fiscal));
  const year = Number(cutoff.slice(0,4)) - Number(cutoff.slice(5) !== "12-31");
  const fiscalRow = budget?.observations.filter(r =>
    Number.isFinite(r.value) && r.year <= year && r.year <= budget.latestActualYear
  ).sort((a,b) => b.year - a.year)[0];
  if (fiscalRow) {
    const fiscalSource = fiscalRow.sourceId && fiscalRow.sourceId === budget.supplement?.sourceId
      ? budget.supplement : budget;
    const preceding = String(fiscalRow.year) + "-12-31" < profile.start;
    const fiscalLabel = preceding ? "Last completed year · before this term" : "Last completed calendar year";
    article.append(table(["Fiscal measure", fiscalLabel, "Balance"],
      [[link("General government net lending / borrowing", fiscalSource.sourceUrl),
        String(fiscalRow.year), num(fiscalRow.value, 2) + "% of GDP"]], "Annual fiscal context"),
      el("p", budget.label + " general government, calendar-year accrual balance. Negative values indicate borrowing. The annual figure reflects government finances and the economic cycle.", "hs-byline"));
  }
  article.append(el("h3", "Communication"), el("p", profile.communication),
    el("h3", "What the market data can test"), el("p", profile.test),
    link("Explore "+bank.name+" guidance and market repricing","empirical-studies.html?study=guidance&bank="+bank.id));

  const noteBySource = new Map();
  for (const note of notes) {
    for (const url of [note.url, ...(note.publication?.aliases || [])]) {
      noteBySource.set(sourceKey(url), note);
    }
  }
  const events = [...profile.episodes].sort((a,b) => a.date.localeCompare(b.date));
  article.append(el("h3", "Policy chronology"), table(["Date", "Policy record"], events.map(event => {
    const note = noteBySource.get(sourceKey(event.url));
    const cell = el("div");
    cell.append(link(event.title, event.url));
    if (note) cell.append(document.createTextNode(" · "), link("Read analysis", archiveUrl(event.date.slice(0,4), note)));
    return [dateTitle(event.date), cell];
  }), "Dated policy records"));
  const archive = el("p");
  archive.append(link("Browse the " + bank.name + " archive", archiveUrl()));
  const sources = [...profile.sources, ...["cpiYoY", "unemployment", "industrialProductionYoY"].map(key => ({
    label:panel.series[key].source + " · " + panel.series[key].label, url:panel.series[key].sourceUrl
  }))];
  if (panel.series.recession) sources.push({label:"NBER · US business-cycle turning points", url:panel.series.recession.sourceUrl});
  if (budget) sources.push({label:budget.source, url:budget.sourceUrl});
  article.append(archive, sourceList([...new Map(sources.map(s => [s.url, s])).values()]));
  return grid;
}
main();
