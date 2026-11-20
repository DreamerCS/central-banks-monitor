const families = {
  "two-year": {fed:"UST2Y", ecb:"DE2Y", unit:"bp"},
  "ten-year": {fed:"UST10Y", ecb:"DE10Y", unit:"bp"},
  curve: {fed:"SLOPE", ecb:"SLOPE", unit:"bp"},
  ois: {fed:"OIS1Y", ecb:"OIS_1Y", unit:"bp"},
  eurusd: {fed:"EURUSD", ecb:"EURUSD", unit:"%"},
  equities: {fed:"SP500", ecb:"STOXX50", unit:"%"}
};
const periodNames = {statement:"Statement", conference:"Press conference", meeting:"Full event"};
const fmtDate = new Intl.DateTimeFormat("en-GB", {day:"numeric",month:"short",year:"numeric",timeZone:"UTC"});
const dateLabel = date => fmtDate.format(new Date(date+"T12:00:00Z"));

function quantile(sorted,q) {
  if (!sorted.length) return null;
  const index=(sorted.length-1)*q, lower=Math.floor(index);
  return sorted[lower]+(index-lower)*(sorted[Math.ceil(index)]-sorted[lower]);
}

function yearStats(events,windowKey,assetKey) {
  const windows=events.filter(event => Object.hasOwn(event.windows,windowKey));
  const valid=windows.filter(event => Number.isFinite(event.windows[windowKey]?.[assetKey]))
    .map(event => ({date:event.date, value:event.windows[windowKey][assetKey]}));
  const signed=valid.map(event=>event.value).sort((a,b)=>a-b);
  const size=signed.map(Math.abs).sort((a,b)=>a-b);
  const ranked=valid.sort((a,b)=>Math.abs(b.value)-Math.abs(a.value) || a.date.localeCompare(b.date));
  return {
    total:events.length, eligible:windows.length, quoted:valid.length,
    noWindow:events.length-windows.length, missing:windows.length-valid.length,
    firstWindow:windows[0]?.date, lastWindow:windows.at(-1)?.date,
    q25:quantile(signed,.25), median:quantile(signed,.5), q75:quantile(signed,.75),
    medianAbs:quantile(size,.5), ranked
  };
}

const numericFormats = Object.fromEntries([["bp",2],["%",3]].map(([unit,digits])=>
  [unit,new Intl.NumberFormat("en-GB",{minimumFractionDigits:digits,maximumFractionDigits:digits,useGrouping:false})]));

function fmt(value,unit,signed=false) {
  if (!Number.isFinite(value)) return "—";
  const magnitude=numericFormats[unit].format(Math.abs(value));
  return (Number(magnitude) && signed ? value<0?"−":"+" : "")+magnitude;
}

function svgNode(tag,attrs,text) {
  const node=document.createElementNS("http://www.w3.org/2000/svg",tag);
  for (const [key,value] of Object.entries(attrs)) node.setAttribute(key,String(value));
  if (text!==undefined) node.textContent=text;
  return node;
}

function drawChart(host,years,stats,chosen,unit) {
  const width=Math.max(245,Math.round(host.clientWidth||640));
  const height=width<550?192:220, left=53,right=width-17,top=19,bottom=height-32;
  const values=stats.flatMap(row=>[row.fed.medianAbs,row.ecb.medianAbs]).filter(Number.isFinite);
  const high=values.length?Math.max(...values):0;
  const scale=high>0 ? 10**Math.floor(Math.log10(high)) : 1;
  const cap=high>0 ? Math.ceil(high/scale*2)*scale/2 : (unit==="bp"?1:.1);
  const x=i=>left+(right-left)*i/Math.max(1,years.length-1);
  const y=v=>bottom-(bottom-top)*v/cap;
  const svg=svgNode("svg",{viewBox:`0 0 ${width} ${height}`, "aria-hidden":"true"});
  for (const magnitude of [0,cap/2,cap]) {
    svg.append(svgNode("line",{x1:left,x2:right,y1:y(magnitude),y2:y(magnitude),stroke:"#5f7262","stroke-width":.65}));
    svg.append(svgNode("text",{x:left-8,y:y(magnitude)+4,"text-anchor":"end"},Number(magnitude.toPrecision(3)).toString()));
  }
  for (const [i,year] of years.entries()) {
    if (i===0 || i===years.length-1 || (year%(width<550?10:5)===0 && years.at(-1)-year>=2)) {
      svg.append(svgNode("text",{x:x(i),y:height-6,"text-anchor":i===0?"start":i===years.length-1?"end":"middle"},String(year)));
    }
  }
  const index=years.indexOf(chosen);
  svg.append(svgNode("line",{x1:x(index),x2:x(index),y1:top,y2:bottom,stroke:"#f1daa9","stroke-dasharray":"3 4"}));
  for (const [bank,color,dash] of [["fed","#b4dcb8","none"],["ecb","#f4b38b","5 4"]]) {
    let line="";
    let previous=false;
    for (const [i,row] of stats.entries()) {
      const value=row[bank].medianAbs;
      if (value===null) {previous=false;continue;}
      line+=(previous?"L":"M")+x(i).toFixed(2)+" "+y(value).toFixed(2)+" ";
      previous=true;
    }
    svg.append(svgNode("path",{d:line.trim(),fill:"none",stroke:color,"stroke-width":2,"stroke-dasharray":dash}));
    for (const [i,row] of stats.entries()) {
      const value=row[bank].medianAbs;
      if (value===null) continue;
      const point=svgNode("circle",{cx:x(i),cy:y(value),r:i===index?4.6:2.1,fill:color,stroke:"#26342c","stroke-width":i===index?1:.45});
      point.append(svgNode("title",{},years[i]+" · "+bank.toUpperCase()+" · "+fmt(value,unit)+" "+unit));
      svg.append(point);
    }
  }
  host.replaceChildren(svg);
  return {width,left,right};
}

function cell(tag,text,scope) {
  const node=document.createElement(tag); node.textContent=text;
  if (scope) node.scope=scope;
  return node;
}

function populateSummary(host,row,unit) {
  const u=value=>fmt(value,unit,true);
  const rows=[
    ["Recorded event dates",s=>s.total],
    ["Eligible windows",s=>s.eligible],
    ["Usable quotes",s=>s.quoted],
    ["Missing quote within window",s=>s.missing],
    ["Dates without this window",s=>s.noWindow],
    ["Median signed move ("+unit+")",s=>u(s.median)],
    ["Middle 50% ("+unit+")",s=>s.q25===null?"—":u(s.q25)+" to "+u(s.q75)],
    ["Median absolute move ("+unit+")",s=>fmt(s.medianAbs,unit)]
  ];
  host.replaceChildren(...rows.map(([label,get],i)=>{
    const tr=document.createElement("tr");
    if(i===5) tr.className="amh-gap";
    tr.append(cell("th",label,"row"),cell("td",get(row.fed)),cell("td",get(row.ecb)));
    return tr;
  }));
}

function populateRanks(host,row,windowKey,asset,year) {
  host.replaceChildren();
  for (const bank of ["fed","ecb"]) {
    const block=document.createElement("div"); block.className="amh-rank";
    block.append(cell("h5",bank==="fed"?"Federal Reserve":"ECB"));
    if (!row[bank].quoted) {
      block.append(cell("p",row[bank].eligible?"No quotes for this instrument.":"No published window in this year."));
    } else {
      const list=document.createElement("ol");
      for (const item of row[bank].ranked.slice(0,3)) {
        const li=document.createElement("li");
        const link=document.createElement("a");
        const params=new URLSearchParams({bank,window:windowKey,asset:asset[bank],year:String(year),date:item.date});
        link.href="?"+params.toString()+"#mr-detail-title";
        link.append(cell("span",dateLabel(item.date)),cell("span",fmt(item.value,asset.unit,true)+" "+asset.unit));li.append(link);list.append(li);
      }
      block.append(list);
    }
    host.append(block);
  }
}

function writeCsv(years,stats,banks,windowKey,familyKey) {
  const instrument=families[familyKey];
  const rows=[["year","bank","window","instrument","unit","source_event_dates","eligible_windows","quoted_windows","missing_quotes","dates_without_window","first_window_date","last_window_date","q25_signed","median_signed","q75_signed","median_absolute","largest_move_date","largest_move_signed","window_definition","source"]];
  for (const [i,year] of years.entries()) {
    for(const bank of banks) {
      const s=stats[i][bank.id], top=s.ranked[0];
      rows.push([year,bank.name,windowKey,instrument[bank.id],instrument.unit,s.total,s.eligible,s.quoted,s.missing,s.noWindow,s.firstWindow,s.lastWindow,s.q25,s.median,s.q75,s.medianAbs,top?.date,top?.value,bank.windows[windowKey],bank.source]);
    }
  }
  const escape=v=>'"'+String(v??"").replaceAll('"','""')+'"';
  const blob=new Blob([rows.map(r=>r.map(escape).join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"});
  const url=URL.createObjectURL(blob);
  const link=document.createElement("a");link.href=url;
  link.download="annual-market-reactions-"+windowKey+"-"+familyKey+".csv";link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1500);
}

function priorMove(quotes, date, through) {
  if (date>through) return null;
  let lo=0, hi=quotes.length;
  while (lo<hi) {
    const mid=Math.floor((lo+hi)/2);
    if (quotes[mid].date<date) lo=mid+1;
    else hi=mid;
  }
  if (lo<5) return null;
  const from=quotes[lo-5], to=quotes[lo-1];
  if (Date.parse(date) - Date.parse(to.date) > 7 * 86400000) return null;
  const move=(key)=>Math.round(to[key]*100)-Math.round(from[key]*100);
  const two=move("y2"), ten=move("y10");
  return {date,from:from.date,to:to.date,two,ten,slope:ten-two};
}

function buildPrior(curve, fed) {
  const quotes=curve.observations.filter(r=>Number.isFinite(r.y2) && Number.isFinite(r.y10));
  if (!quotes.length || quotes.some((r,i)=>i && r.date<=quotes[i-1].date)) throw new Error("Invalid Treasury history");
  const through=[quotes.at(-1).date,curve.asOfDate,curve.eventsThrough].filter(Boolean).sort().at(-1);
  const speeches=curve.events.filter(e=>String(e.kind).toLowerCase()==="speech");
  const statements=fed.events.filter(e=>e.windows.statement);
  const samples={};
  const movesByDate=new Map();
  for (const [name,records] of [["speeches",speeches],["statements",statements]]) {
    const byDate=new Map();
    for (const item of records) {
      if (!byDate.has(item.date)) byDate.set(item.date,[]);
      byDate.get(item.date).push(item);
    }
    const dates=[...byDate.keys()].sort();
    const byYear=new Map();
    for (const date of dates) {
      const year=Number(date.slice(0,4));
      if (!byYear.has(year)) byYear.set(year,{records:0,dates:0,matched:[]});
      const agg=byYear.get(year), items=byDate.get(date);
      agg.records+=items.length;agg.dates++;
      if (!movesByDate.has(date)) movesByDate.set(date,priorMove(quotes,date,through));
      const move=movesByDate.get(date);
      if (move) agg.matched.push({...move,itemCount:items.length,url:items.length===1 ? items[0].url : ""});
    }
    for (const agg of byYear.values()) {
      agg.medians=Object.fromEntries(["two","ten","slope"].map(k=>[k,quantile(agg.matched.map(r=>r[k]).sort((a,b)=>a-b),.5)]));
      agg.matched.sort((a,b)=>Math.abs(b.slope)-Math.abs(a.slope)||a.date.localeCompare(b.date));
    }
    samples[name]={byYear,first:dates[0],last:dates.at(-1)};
  }
  return samples;
}

function showPrior(el,samples,year,group) {
  const coverage=el("prior-coverage"), values=el("prior-values");
  values.hidden=true;
  if (samples===undefined) {coverage.textContent="Loading pre-event Treasury data…";return;}
  if (samples===null) {coverage.textContent="Pre-event Treasury data could not be loaded.";return;}
  const series=samples[group], agg=series.byYear.get(year);
  if (!agg) {
    coverage.textContent=group==="speeches"
      ? "There is no Board speech sample for "+year+" in this catalogue."+(series.first ? " The source covers "+dateLabel(series.first)+" to "+dateLabel(series.last)+"." : "")
      : "There are no recorded Fed statement dates in "+year+".";
    return;
  }
  const groupLabel=group==="speeches"?"Board speech dates":"Fed statement dates";
  coverage.textContent=year+" · "+agg.matched.length+" matched / "+agg.dates+" distinct "+groupLabel+
    (group==="speeches"?" from "+agg.records+" speeches":"")+".";
  if (!agg.matched.length) return;
  values.hidden=false;
  el("prior-stats").replaceChildren(...[["two","Median 2Y change"],["ten","Median 10Y change"],["slope","Median 2s10s change"]].map(([k,label])=>{
    const g=document.createElement("div");g.append(cell("dt",label),cell("dd",fmt(agg.medians[k],"bp",true)+" bp"));return g;
  }));
  const top=agg.matched[0];
  const ties=agg.matched.filter(r=>Math.abs(r.slope)===Math.abs(top.slope)).length;
  const description="The largest 2s10s move was "+fmt(top.slope,"bp",true)+" bp before "+dateLabel(top.date)+
    ". The window runs from "+dateLabel(top.from)+" to "+dateLabel(top.to)+"."+
    (ties>1?" This is the earliest of "+ties+" equally large moves.":"")+
    (group==="speeches" && top.itemCount>1?" This date covers "+top.itemCount+" speeches.":"");
  const link=cell("a","Inspect the daily Treasury curve");
  const params=new URLSearchParams({curveDate:top.date});
  if (group==="speeches") {
    if(top.url) params.set("curveEvent",top.url);
    else params.set("curveKind","custom");
  }
  link.href="?"+params+"#pre-event-curve";
  el("prior-largest").replaceChildren(document.createTextNode(description+" "),link);
}

async function initialise() {
  const section=document.querySelector("#annual-market-history");
  if (!section) return;
  const el=id=>document.getElementById("amh-"+id);
  try {
    const curveRequest=fetch("data/pre-event-curve.json").then(r=>{
      if (!r.ok) throw new Error("Missing Treasury history");
      return r.json();
    }).catch(()=>null);
    const response=await fetch("data/market-events.json");
    if (!response.ok) throw new Error("Market data unavailable");
    const payload=await response.json();
    const banks=["fed","ecb"].map(id=>payload.banks.find(b=>b.id===id));
    if (banks.some(b=>!b?.events?.length)) throw new Error("Missing market history");
    const eventsByBank={};
    for (const bank of banks) {
      const byYear=new Map();
      for(const event of bank.events) {
        const year=Number(event.date.slice(0,4));
        if(!byYear.has(year)) byYear.set(year,[]);
        byYear.get(year).push(event);
      }
      for (const events of byYear.values()) events.sort((a,b)=>a.date.localeCompare(b.date));
      eventsByBank[bank.id]=byYear;
    }
    const end=Math.max(2026,...banks.map(b=>Number(b.events.at(-1).date.slice(0,4))));
    const years=Array.from({length:end-1999},(_,i)=>i+2000);
    const yearSelect=el("year"), assetSelect=el("asset"), winSelect=el("window"), chart=el("chart");
    const params=new URLSearchParams(location.search);
    const selected=Number(params.get("historyYear"));
    yearSelect.replaceChildren(...years.map(year=>new Option(String(year),String(year))));
    yearSelect.value=String(years.includes(selected)?selected:years[0]);
    if (Object.hasOwn(families,params.get("historyAsset"))) assetSelect.value=params.get("historyAsset");
    if (Object.hasOwn(periodNames,params.get("historyWindow"))) winSelect.value=params.get("historyWindow");
    const before=el("before");
    if(params.get("historyBefore")==="speeches") before.value="speeches";
    let stats=[], geometry, priorSamples;
    function pageForYear(year) {
      const address=new URL(location.href);
      address.searchParams.set("historyYear",String(year));
      address.searchParams.set("historyAsset",assetSelect.value);
      address.searchParams.set("historyWindow",winSelect.value);
      if(before.value==="speeches") address.searchParams.set("historyBefore","speeches");
      else address.searchParams.delete("historyBefore");
      address.hash="annual-market-history";
      return address;
    }
    function showYear(updateAddress) {
      const year=Number(yearSelect.value), row=stats[year-years[0]], instrument=families[assetSelect.value];
      if (updateAddress) history.replaceState(history.state,"",pageForYear(year));
      geometry=drawChart(chart,years,stats,year,instrument.unit);
      const kind=periodNames[winSelect.value];
      el("selection-title").textContent=year+" · "+kind;
      const bankAssets=banks.map(b=>b.assets.find(a=>a.id===instrument[b.id])?.label || instrument[b.id]);
      el("selection-desc").textContent="Federal Reserve · "+bankAssets[0]+" | ECB · "+bankAssets[1];
      const yearbook=el("yearbook");
      yearbook.href="yearbook.html?historyYear="+year;
      yearbook.textContent=year+" yearbook · Historical case, growth and inflation";
      populateSummary(el("summary-body"),row,instrument.unit);
      populateRanks(el("ranks"),row,winSelect.value,instrument,year);
      showPrior(el,priorSamples,year,before.value);
      for (const tr of el("grid-body").children) {
        const current=Number(tr.dataset.year)===year;
        tr.toggleAttribute("data-current",current);
        const link=tr.querySelector("a");
        if (current) link.setAttribute("aria-current","true"); else link.removeAttribute("aria-current");
      }
      window.dispatchEvent(new CustomEvent("market-history-year", {detail: {year}}));
    }
    function refresh(updateAddress) {
      const windowKey=winSelect.value,instrument=families[assetSelect.value];
      stats=years.map(year=>Object.fromEntries(banks.map(bank=>[bank.id,yearStats(eventsByBank[bank.id].get(year)||[],windowKey,instrument[bank.id])])));
      const instrumentName=assetSelect.options[assetSelect.selectedIndex].text;
      el("chart-caption").textContent=instrumentName+" · "+periodNames[windowKey]+" · "+(instrument.unit==="bp"?"basis points":"percent");
      el("latest").textContent="Latest recorded event dates · Fed "+dateLabel(banks[0].events.at(-1).date)+" · ECB "+dateLabel(banks[1].events.at(-1).date)+". Gaps indicate no usable quotes.";
      for(const bank of banks) el("def-"+bank.id).textContent=(bank.id==="fed"?"Federal Reserve":"ECB")+" · "+bank.windows[windowKey];
      el("grid-caption").textContent=periodNames[windowKey]+" · "+instrumentName+" · "+instrument.unit+". Select a year for its observations.";
      const rows=years.map((year,i)=>{
        const tr=document.createElement("tr");tr.dataset.year=String(year);
        const th=cell("th","","row"), a=document.createElement("a");a.href=pageForYear(year).href;a.textContent=String(year);
        th.append(a);tr.append(th);
        for(const bank of banks){
          const s=stats[i][bank.id];
          tr.append(cell("td",s.quoted+" / "+s.eligible),cell("td",fmt(s.median,instrument.unit,true)),cell("td",fmt(s.medianAbs,instrument.unit)));
        }
        return tr;
      });
      el("grid-body").replaceChildren(...rows);
      showYear(updateAddress);
    }
    yearSelect.addEventListener("change",()=>showYear(true));
    before.addEventListener("change",()=>{
      const year=Number(yearSelect.value);
      history.replaceState(history.state,"",pageForYear(year));
      for(const tr of el("grid-body").children) tr.querySelector("a").href=pageForYear(Number(tr.dataset.year)).href;
      showPrior(el,priorSamples,year,before.value);
    });
    for(const input of [assetSelect,winSelect]) input.addEventListener("change",()=>refresh(true));
    el("grid-body").addEventListener("click",event=>{
      const row=event.target.closest("tr[data-year]");
      if(!row || !event.target.closest("a") || event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();yearSelect.value=row.dataset.year;showYear(true);
      el("selection-title").tabIndex=-1;el("selection-title").focus();
    });
    chart.addEventListener("click",event=>{
      if(!geometry) return;
      const r=chart.getBoundingClientRect();
      const fraction=((event.clientX-r.left)*geometry.width/r.width-geometry.left)/(geometry.right-geometry.left);
      const index=Math.max(0,Math.min(years.length-1,Math.round(fraction*(years.length-1))));
      yearSelect.value=String(years[index]);showYear(true);
    });
    chart.addEventListener("keydown",event=>{
      if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key)) return;
      event.preventDefault();
      const index=years.indexOf(Number(yearSelect.value));
      const next=event.key==="Home"?0:event.key==="End"?years.length-1:index+(event.key==="ArrowLeft"?-1:1);
      yearSelect.value=String(years[Math.max(0,Math.min(years.length-1,next))]);showYear(true);
    });
    el("export").addEventListener("click",()=>writeCsv(years,stats,banks,winSelect.value,assetSelect.value));
    el("status").hidden=true;el("content").hidden=false;
    refresh(false);
    curveRequest.then(curve=>{
      try {priorSamples=curve ? buildPrior(curve,banks[0]) : null;} catch {priorSamples=null;}
      showPrior(el,priorSamples,Number(yearSelect.value),before.value);
    });
    if(typeof ResizeObserver==="function"){
      let previous=chart.clientWidth;
      new ResizeObserver(()=>{
        if(chart.clientWidth && previous!==chart.clientWidth) {
          previous=chart.clientWidth;
          geometry=drawChart(chart,years,stats,Number(yearSelect.value),families[assetSelect.value].unit);
        }
      }).observe(chart);
    }
  } catch {
    el("content").hidden=true;el("status").hidden=false;
    el("status").textContent="Annual market observations could not be loaded. Refresh to try again.";
  }
}
initialise();
