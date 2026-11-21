const id = key => document.getElementById("oil-" + key);
const measures = {output:"Industrial output", energy:"Energy inflation", core:"Core inflation"};
const regions = {US:"United States", EA:"Euro area"};
const months = Array.from({length:19},(_,i)=>i-6);
const query = new URLSearchParams(location.search);
const valid = Number.isFinite;
const fmt = (n, digits = 1) => valid(n) ? n.toFixed(digits) : "—";
const signed = n => valid(n) ? (n < 0 ? "−" : n > 0 ? "+" : "") + Math.abs(n).toFixed(1) : "—";
const signedPercent = n => valid(n) ? signed(n) + "%" : "—";
function step(m,n) {
  const total=Number(m.slice(0,4))*12+Number(m.slice(5))-1+n;
  return Math.floor(total/12)+"-"+String(total%12+1).padStart(2,"0");
}
const month = m => new Intl.DateTimeFormat("en-GB",{month:"short",year:"numeric",timeZone:"UTC"}).format(new Date(m+"-01T00:00Z"));
const pct = (a,b) => valid(a)&&valid(b)&&b!==0 ? 100*(a/b-1) : null;
function node(name,text) {const e=document.createElement(name);if(text!==undefined)e.textContent=text;return e;}
function table(caption,headers,rows) {
  const wrap=node("div"), t=node("table");wrap.className="oil-scroll";t.createCaption().textContent=caption;
  const head=t.createTHead().insertRow();for(const label of headers){const c=node("th",label);c.scope="col";head.append(c);}
  const body=t.createTBody();
  for(const entries of rows){
    const tr=body.insertRow();entries.forEach((entry,i)=>{const c=node(i===0?"th":"td",entry);if(i===0)c.scope="row";tr.append(c);});
  }
  wrap.append(t);return wrap;
}
function svgElement(name,attrs) {const el=document.createElementNS("http://www.w3.org/2000/svg",name);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);return el;}
function drawChart(series) {
  const svg=id("plot");svg.replaceChildren();
  const values=Object.values(series).flat().filter(valid);if(!values.length)return;
  const min=Math.min(0,...values),max=Math.max(0,...values);
  const interval=[.25,.5,1,2,5,10,20,40].find(n=>n>=(max-min)/4)||50;
  const lo=Math.floor(min/interval)*interval,hi=Math.max(lo+interval,Math.ceil(max/interval)*interval);
  const width=Math.round(svg.getBoundingClientRect().width)||670;
  svg.setAttribute("viewBox","0 0 "+width+" 210");
  const left=47,right=width-18,top=12,bottom=173;
  const x=n=>left+(n+6)*(right-left)/18, y=v=>bottom-(v-lo)*(bottom-top)/(hi-lo);
  function label(text,xx,yy,anchor){const l=svgElement("text",{x:xx,y:yy,"text-anchor":anchor});l.textContent=text;svg.append(l);}
  for(let v=lo;v<=hi+interval/10;v+=interval){svg.append(svgElement("line",{x1:left,x2:right,y1:y(v),y2:y(v),class:v===0?"oil-zero":"oil-grid"}));label(String(v),left-6,y(v)+4,"end");}
  for(const n of (width<390?[-6,0,6,12]:[-6,-3,0,3,6,9,12]))label(n>0?"+"+n:String(n),x(n),bottom+30,"middle");
  svg.append(svgElement("line",{x1:x(0),x2:x(0),y1:top,y2:bottom,class:"oil-zero"}));
  for(const [area,line] of Object.entries(series)){let d="",gap=true;line.forEach((v,i)=>{if(!valid(v)){gap=true;return;}d+=(gap?" M":" L")+x(months[i])+" "+y(v);gap=false;});svg.append(svgElement("path",{d:d.trim(),class:"oil-trace "+area.toLowerCase()}));}
}
function median(list) {
  const sorted=list.filter(valid).sort((a,b)=>a-b),n=sorted.length;
  if(!n)return null;
  return n%2 ? sorted[(n-1)/2] : (sorted[n/2-1]+sorted[n/2])/2;
}
async function start() {
  const response=await fetch("data/oil-price-study.json");if(!response.ok)throw Error(response.status);
  const data=await response.json();
  const threshold=id("threshold"), measure=id("measure"), horizon=id("horizon"), event=id("event");
  for(const [control,key,allowed] of [[threshold,"threshold",Object.keys(data.events)],[measure,"measure",Object.keys(measures)],[horizon,"horizon",["3","6","12"]]]){
    if(allowed.includes(query.get(key)))control.value=query.get(key);
  }
  let displayedSeries;
  function populate(anchor) {
    const anchors=data.events[threshold.value];
    event.replaceChildren(...anchors.map(m=>new Option(month(m),m)));
    event.value=anchors.includes(anchor)?anchor:(anchors.find(m=>m.startsWith("2014"))||anchors[0]);
  }
  populate(query.get("event"));
  const obs=m=>data.observations[m]||{};
  function change(anchor,n,area,key) {
    const a=obs(step(anchor,n))[area]?.[key],b=obs(anchor)[area]?.[key];
    return key==="output"?pct(a,b):(valid(a)&&valid(b)?a-b:null);
  }
  function render(save) {
    const key=measure.value,h=Number(horizon.value),anchors=data.events[threshold.value],a=event.value;
    const unit=key==="output"?"%":"pp",criterion=key==="output"?"output rose":"inflation accelerated";
    const paired=anchors.filter(m=>Object.keys(regions).every(area=>valid(change(m,h,area,key))));
    id("sample-summary").textContent=anchors.length+" crossings through "+month(data.through)+" · "+paired.length+" with both regions observed at +"+h+" months. Outcomes are changes from the crossing month, "+(key==="output"?"as a percentage of the output index.":"in percentage points of 12-month inflation.");
    id("events").replaceChildren(table(measures[key]+" after "+h+" months",["Crossing","Six-month Brent move","Brent at +"+h+" vs six months before","US change · "+unit,"Euro-area change · "+unit,"Policy rates · US / euro area"],
      anchors.map(m=>[month(m),signedPercent(pct(obs(m).brent,obs(step(m,-6)).brent)),signedPercent(pct(obs(step(m,h)).brent,obs(step(m,-6)).brent)),signed(change(m,h,"US",key)),signed(change(m,h,"EA",key)),data.policies[m].US+"% / "+data.policies[m].EA+"%"])));
    const groups=[["Both rates at or below 0.25%",m=>Object.values(data.policies[m]).every(v=>v<=.25)],["At least one rate above 0.25%",m=>Object.values(data.policies[m]).some(v=>v>.25)]];
    id("rate-groups").replaceChildren(table("Outcomes grouped by the benchmark rates in effect at month-end",["Month-end policy rates","Events","US median · "+unit,"Events where US "+criterion,"Euro-area median · "+unit,"Events where euro-area "+criterion],
      groups.map(([label,test])=>{
        const g=anchors.filter(test);
        return [label,g.length,...Object.keys(regions).flatMap(area=>{const outcomes=g.map(m=>change(m,h,area,key)).filter(valid);return [signed(median(outcomes)),outcomes.filter(v=>v>1e-8).length+" / "+outcomes.length];})];
      })));
    const paths=Object.fromEntries(Object.keys(regions).map(area=>[area,months.map(n=>change(a,n,area,key))]));
    displayedSeries=paths;drawChart(paths);id("plot").setAttribute("aria-label",measures[key]+", change in "+unit+" from "+month(a)+" in the US and euro area, from six months before through twelve months after.");
    id("caption").textContent=measures[key]+" · "+unit+" relative to "+month(a)+". Horizontal axis shows months from crossing. At +"+h+" months the changes were "+signed(change(a,h,"US",key))+" "+unit+" in the US and "+signed(change(a,h,"EA",key))+" "+unit+" in the euro area.";
    const rows=months.map(n=>{
      const m=step(a,n),r=obs(m);
      return [month(m),fmt(r.brent,2),...Object.keys(regions).flatMap(area=>["energy","core","output"].map(k=>{
        const f=area==="EA"?data.flags[k]?.[m]:"";return fmt(r[area]?.[k],k==="output"?2:1)+(f?" ["+f+"]":"");
      }))];
    });
    id("raw").replaceChildren(table("Published measures around "+month(a),["Month","Brent · $/bbl","US energy · % y/y","US core · % y/y","US output · index","Euro energy · % y/y","Euro core · % y/y","Euro output · index"],rows),
      node("p","US output uses 2017 = 100 and euro-area output uses 2021 = 100. Eurostat flags include d (definition differs), b (break in series) and i (imputed). Dashes indicate unavailable observations."));
    if(save){const u=new URL(location.href);for(const [k,val] of Object.entries({threshold:threshold.value,measure:key,horizon:h,event:a}))u.searchParams.set(k,val);history.replaceState(null,"",u);}
  }
  threshold.addEventListener("change",()=>{populate(event.value);render(true);});
  for(const input of [measure,horizon,event])input.addEventListener("change",()=>render(true));
  id("study").hidden=false;render(false);id("status").hidden=true;
  if(window.ResizeObserver){
    new ResizeObserver(()=>{
      const svg=id("plot");
      if(displayedSeries && Math.round(svg.getBoundingClientRect().width)!==svg.viewBox.baseVal.width)drawChart(displayedSeries);
    }).observe(id("plot"));
  }
}
start().catch(()=>{id("status").textContent="The oil-price data could not be loaded. Reload the page to try again.";});
