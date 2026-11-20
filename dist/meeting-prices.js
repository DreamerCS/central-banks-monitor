"use strict";

const assets={
  fed:{near:"MP1",ois1y:"OIS1Y",twoYear:"UST2Y",tenYear:"UST10Y",fx:"EURUSD",equity:"SP500"},
  ecb:{near:"OIS_1M",ois1y:"OIS_1Y",twoYear:"DE2Y",tenYear:"DE10Y",fx:"EURUSD",equity:"STOXX50"}
};
const actions={hold:"Hold",raise:"Rate increase",cut:"Rate cut"};
const stages=[{id:"statement",label:"Statement"},{id:"conference",label:"Press conference"}];
function value(n,unit) {
  return Number.isFinite(n)?signed(n,unit==="%"?3:2)+" "+unit:"No published quote";
}
function marketLink(bank,date,window,asset) {
  return "market-reactions.html?"+new URLSearchParams({bank,date,window,year:date.slice(0,4),asset:assets[bank][asset]});
}
function bars(bank,event,asset) {
  const changes=stages.map(s=>event[s.id][asset.id]);
  const label=asset.label+" · "+event.date;
  const description=stages.map((s,i)=>s.label+" "+value(changes[i],asset.unit)).join(". ")+". Each bar is the price change within its own published window.";
  const g=priceFigure(label,asset.unit,bank.timezone,changes,description);
  const width=(g.right-g.left)*.19;
  for(const [i,n] of changes.entries()){
    const x=g.x(i);
    if(Number.isFinite(n)){
      const y=g.y(n),base=g.y(0);
      g.chart.append(svg("rect",{x:x-width/2,y:Math.min(y,base),width,height:Math.max(2,Math.abs(base-y)),fill:i===0?ink.gold:ink.blue}));
    }
    const stamp=svg("text",{x,y:g.bottom+38,"text-anchor":"middle"});stamp.textContent=event[stages[i].id+"Time"]||"";
    g.chart.append(stamp);
  }

  const labels=el("dl",undefined,"es-price-values");
  for(const [i,stage] of stages.entries()){
    const item=el("div");item.append(el("dt",stage.label),el("dd",value(changes[i],asset.unit)));labels.append(item);
  }
  g.f.append(labels);
  return g.f;
}
function publishedDecision(event){
  if(!event.announcedAction)return null;
  const wording=actions[event.announcedAction]||event.announcedAction;
  return Number.isFinite(event.announcedChangeBp)?wording+" · "+signed(event.announcedChangeBp,0)+" bp":wording;
}
function render(data) {
  const q=new URLSearchParams(location.search),page=el("div");
  const bankId=pick("bank",data.banks,data.banks.find(b=>b.events.some(e=>e.date===q.get("date")))?.id||"fed");
  const bank=data.banks.find(b=>b.id===bankId);
  const instruments=[{id:"near",label:bank.nearLabel,unit:"bp"},...bank.assets];
  const assetId=pick("asset",instruments,"ois1y"),asset=instruments.find(a=>a.id===assetId);
  const dates=bank.events.slice().reverse().map(e=>({id:e.date,label:e.date}));
  const date=pick("date",dates,bank.id==="fed"?"2022-11-02":"2023-09-14");
  const event=bank.events.find(e=>e.date===date);
  page.append(el("h2","Statement and press conference"),
    el("p","Market prices during two parts of the same policy meeting, as reported by the Federal Reserve Bank of San Francisco and the European Central Bank.","es-intro"));
  addInputs(page,select("bank","Institution",data.banks,bank.id,["date","asset"]),
    select("asset","Instrument",instruments,asset.id),select("date","Meeting date",dates,date));
  if(!event){page.append(el("p","No paired price observations are available."));return page;}
  if(q.get("date")&&q.get("date")!==date)page.append(el("p","The source has no pair of windows for "+q.get("date")+" at this institution. Showing "+date+".","es-note"));
  const selected=el("section");selected.id="meeting";
  const facts=[["Meeting date",event.date],["Statement",event.statementTime+" · "+bank.timezone],
    ["Press conference",event.conferenceTime+" · "+bank.timezone]];
  const decision=publishedDecision(event);
  if(decision)facts.splice(1,0,["Announced decision",decision]);
  const side=summaryFacts(bank.label,facts);
  const links=el("p",undefined,"es-links");
  for(const stage of stages){
    const url=event.guidance?.[stage.id];
    if(url)links.append(anchor("Official "+stage.label.toLowerCase(),url));
  }
  links.append(anchor("Link to this meeting","meeting-prices.html?"+new URLSearchParams({bank:bank.id,asset:assetId,date})+"#meeting"));
  side.append(links);selected.append(resultPair(bars(bank,event,asset),side));
  page.append(selected,el("h3","Market prices on "+date),
    table("Published changes during each window",["Instrument","Statement","Press conference"],
      instruments.map(a=>[a.label,...stages.map(s=>{
        const n=event[s.id][a.id];
        return Number.isFinite(n)?anchor(value(n,a.unit),marketLink(bank.id,date,s.id,a.id)):"—";
      })])),
    el("p","Rate changes are in basis points. EUR/USD is US dollars per euro. Each equity entry is the percentage change in its local index.","es-note"));
  const bankSources=data.sources.filter(s=>bank.id==="fed"?/San Francisco Fed/i.test(s.label):/European Central Bank|^ECB/i.test(s.label));
  const period=bank.coverage.first+" to "+bank.coverage.last+" · "+bank.coverage.paired+" meetings.";
  page.append(details("Published data and observation windows",el("p",period),
    table("Publisher’s price windows",["Stage","Published window definition"],stages.map(s=>[s.label,bank.windowDefinitions[s.id]])),
    sources(bankSources)));
  return page;
}
function el(tag,text,style) {
  const node=document.createElement(tag);
  if(text!==undefined)node.textContent=text;
  if(style)node.className=style;
  return node;
}
function anchor(label,url) {
  const a=el("a",label);a.href=url;return a;
}
function signed(n,places) {
  return n.toLocaleString("en-GB",{minimumFractionDigits:places,maximumFractionDigits:places,signDisplay:"exceptZero"});
}
function svg(tag,attributes) {
  const node=document.createElementNS("http://www.w3.org/2000/svg",tag);
  for(const [key,val] of Object.entries(attributes))node.setAttribute(key,val);
  return node;
}
function priceFigure(label,unit,zone,changes,description) {
  const f=el("figure",undefined,"es-chart"),caption=el("figcaption",label);
  const width=innerWidth<560?420:740,height=innerWidth<560?315:342;
  const left=43,right=width-23,top=14,bottom=height-52;
  const values=[0,...changes.filter(Number.isFinite)];
  const low=Math.min(...values),high=Math.max(...values);
  const pad=(high-low)*.08||(unit==="bp"?1:.1);
  const min=low-pad,max=high+pad;
  const x=i=>left+(i+.65)*(right-left)/2.3;
  const y=v=>bottom-(v-min)*(bottom-top)/(max-min);
  const chart=svg("svg",{viewBox:"0 0 "+width+" "+height,class:"es-svg",role:"img","aria-labelledby":"price-title price-description"});
  const desc=svg("desc",{id:"price-description"});desc.textContent=description;chart.append(desc);caption.id="price-title";
  const rawStep=(max-min)/4,base=10**Math.floor(Math.log10(rawStep)),step=[1,2,2.5,5,10].map(m=>m*base).find(n=>n>=rawStep);
  for(let v=Math.ceil(min/step)*step;v<=max+step*.000001;v+=step){
    const zero=Math.abs(v)<step*.000001,tick=zero?0:v;
    chart.append(svg("line",{x1:left,x2:right,y1:y(tick),y2:y(tick),class:zero?"es-zero":"es-grid"}));
    const text=svg("text",{x:left-6,y:y(tick)+4,"text-anchor":"end"});
    text.textContent=tick.toLocaleString("en-GB",{maximumFractionDigits:3});chart.append(text);
  }
  for(const [i,stage] of stages.entries()){
    const text=svg("text",{x:x(i),y:bottom+22,"text-anchor":"middle"});text.textContent=stage.label;chart.append(text);
  }
  f.append(caption,el("div","Change in "+(unit==="bp"?"basis points":"percent"),"es-axis"),chart,el("div",zone,"es-axis es-x"));
  return {f,chart,x,y,left,right,bottom};
}
function pick(key,options,preferred) {
  const raw=new URLSearchParams(location.search).get(key);
  return [raw,preferred,options[0]?.id].find(v=>options.some(o=>o.id===v));
}
function select(key,label,options,value,clear=[]) {
  const holder=el("label",label,"es-control"),input=el("select");
  input.id="es-"+key;
  for(const o of options)input.add(new Option(o.label,o.id));
  input.value=value;
  input.addEventListener("change",()=>{
    const url=new URL(location.href);
    clear.forEach(k=>url.searchParams.delete(k));url.searchParams.set(key,input.value);
    url.hash="";history.replaceState(null,"",url.pathname+url.search);paint(key);
  });
  holder.append(input);return holder;
}
function addInputs(parent,...items) {
  const controls=el("div",undefined,"es-controls");controls.append(...items);parent.append(controls);
}
function resultPair(figure,aside) {
  const row=el("div",undefined,"es-result");row.append(figure,aside);return row;
}
function sources(rows) {
  const list=el("ul",undefined,"es-links");
  for(const s of rows){const entry=el("li");entry.append(anchor(s.label,s.url));list.append(entry);}
  return list;
}
function summaryFacts(heading,rows) {
  const aside=el("aside",undefined,"es-aside"),list=el("dl");
  for(const [key,val] of rows){const r=el("div");r.append(el("dt",key),el("dd",val));list.append(r);}
  aside.append(el("h3",heading),list);return aside;
}
function details(label,...items) {
  const box=el("details",undefined,"es-detail");box.append(el("summary",label),...items);return box;
}
function table(label,headers,rows) {
  const wrap=el("div",undefined,"es-tablewrap"),t=el("table",undefined,"es-table");
  wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-label",label);t.setAttribute("aria-label",label);
  const header=t.createTHead().insertRow();
  for(const title of headers){const cell=el("th",title);cell.scope="col";header.append(cell);}
  const body=t.createTBody();
  for(const values of rows){
    const row=body.insertRow();
    values.forEach((v,i)=>{
      const c=el(i?"td":"th");if(!i)c.scope="row";c.append(v);row.append(c);
    });
  }
  wrap.append(t);return wrap;
}
const ink={gold:"#edc398",blue:"#91cad1"};
const output=document.getElementById("prices");
let dataset;
function paint(changed) {
  output.replaceChildren(render(dataset));
  if(changed)document.getElementById("es-"+changed)?.focus({preventScroll:true});
}
async function load() {
  try{
    const response=await fetch("data/meeting-sequence.json");
    if(!response.ok)throw Error("Meeting prices are unavailable");
    dataset=await response.json();paint();
    if(location.hash==="#meeting")requestAnimationFrame(()=>document.getElementById("meeting")?.scrollIntoView());
    window.addEventListener("popstate",()=>paint());
  }catch{
    const notice=el("p",undefined,"es-note");notice.setAttribute("role","alert");
    notice.append("Meeting prices could not be loaded. ",anchor("Reload",location.href));output.replaceChildren(notice);
  }finally{output.setAttribute("aria-busy","false");}
}
load();
