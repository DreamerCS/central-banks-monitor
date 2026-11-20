import { renderVintageCheck } from './vintage-check.js';

const content = document.querySelector("#es-content");
const query = new URLSearchParams(location.search);
const studies = {inflation:"inflation-study", markets:"event-study", guidance:"guidance-study"};
const requested = query.get("study");
const current = Object.hasOwn(studies, requested) ? requested : "inflation";
const ink = {gold:"#edc398", blue:"#91cad1", green:"#a6c493", white:"#f2efda", coral:"#e6a493"};
const word = {tightening:"Tightening", easing:"Easing", balanced:"Hold or two-sided", unclear:"No explicit direction"};
const futureCodes = ["tightening","easing","balanced","unclear"];
const monthNumber = m => Number(m.slice(0,4)) * 12 + Number(m.slice(5,7)) - 1;
const nfmt = (n, decimals=2) => Number.isFinite(n) ? n.toLocaleString("en-GB",{minimumFractionDigits:decimals,maximumFractionDigits:decimals}) : "—";
const signed = (n, digits=2) => (n > 0 ? "+" : "") + nfmt(n,digits);
const interval = (a,b) => Number.isFinite(a) && Number.isFinite(b) ? nfmt(a)+" to "+nfmt(b) : "—";
function el(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}
function anchor(text,url) {
  const a = el("a",text);
  a.href=url;
  return a;
}
function pick(key,values,preferred) {
  return [query.get(key),preferred,values[0]?.id].find(id=>values.some(option=>option.id===id));
}
function select(key,label,options,value,clear=[]) {
  const wrapper=el("label",label,"es-control");
  const input=el("select"); input.id="es-"+key;
  for(const option of options) input.add(new Option(option.label,option.id));
  input.value=value;
  input.addEventListener("change",()=>{
    clear.forEach(name=>query.delete(name));
    query.set("study", current);query.set(key,input.value);
    history.replaceState(null,"","?"+query.toString());
    paint(key);
  });
  wrapper.append(input);
  return wrapper;
}
function table(caption, headers, rows) {
  const wrap=el("div",undefined,"es-tablewrap");
  wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-label",caption);
  const t=el("table",undefined,"es-table");t.setAttribute("aria-label",caption);
  const h=t.createTHead().insertRow();
  for(const label of headers){const cell=el("th",label);cell.scope="col";h.append(cell);}
  const body=t.createTBody();
  for(const row of rows) {
    const tr=body.insertRow();
    row.forEach((item,i)=>{
      const cell=el(i===0?"th":"td");
      if(i===0)cell.scope="row";
      if(item instanceof Node)cell.append(item);else cell.textContent=item;
      tr.append(cell);
    });
  }
  wrap.append(t);
  return wrap;
}
function details(label, ...nodes) {
  const box=el("details",undefined,"es-detail");
  box.append(el("summary",label),...nodes);
  return box;
}
function sources(list) {
  const ul=el("ul",undefined,"es-links");
  for (const s of list) {
    if(!s.url)continue;
    const item=el("li");item.append(anchor(s.label,s.url));ul.append(item);
  }
  return ul;
}
function summaryFacts(heading, facts, note) {
  const aside=el("aside",undefined,"es-aside");aside.append(el("h3",heading));
  const list=el("dl");
  for(const [label,value] of facts){const box=el("div");box.append(el("dt",label),el("dd",value));list.append(box);}
  aside.append(list);if(note)aside.append(el("p",note));return aside;
}
function svg(tag,attrs) {
  const n=document.createElementNS("http://www.w3.org/2000/svg",tag);
  for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));
  return n;
}
function limits(values,incZero) {
  const valid=values.filter(Number.isFinite);
  if(!valid.length)return [-1,1];
  let min=Math.min(...valid), max=Math.max(...valid);
  if(incZero){min=Math.min(min,0);max=Math.max(max,0);}
  const pad=max===min?Math.max(1,Math.abs(max)*.12):(max-min)*.08;
  return [min-pad,max+pad];
}
function ticks(min,max,count=4) {
  const rough=(max-min)/count,base=10**Math.floor(Math.log10(rough));
  const step=[1,2,2.5,5,10].map(x=>x*base).find(x=>x>=rough);
  const out=[];
  for(let v=Math.ceil(min/step)*step;v<=max+step*.0001;v+=step)out.push(Math.abs(v)<step*.00001?0:v);
  return out;
}
let graphCount=0;
function plot(title, yLabel, xLabel, xBounds, yBounds, xticks, xtickText, chartDescription) {
  const f=el("figure",undefined,"es-chart");const id="es-plot-"+(++graphCount);
  const cap=el("figcaption",title);cap.id=id;
  const compact=window.innerWidth<560;
  const width=compact?420:740,height=compact?300:326;
  const left=40,right=width-26,top=14,bottom=height-34;
  const x=v=>left+(v-xBounds[0])*(right-left)/(xBounds[1]-xBounds[0]);
  const y=v=>bottom-(v-yBounds[0])*(bottom-top)/(yBounds[1]-yBounds[0]);
  const chart=svg("svg",{viewBox:"0 0 "+width+" "+height,class:"es-svg",role:"img","aria-labelledby":id+" "+id+"-desc"});
  const desc=svg("desc",{id:id+"-desc"});desc.textContent=chartDescription;chart.append(desc);
  const defs=svg("defs",{}),clip=svg("clipPath",{id:id+"-clip"});
  clip.append(svg("rect",{x:left,y:top,width:right-left,height:bottom-top}));defs.append(clip);chart.append(defs);
  for(const v of ticks(...yBounds)) {
    const at=y(v);chart.append(svg("line",{x1:left,x2:right,y1:at,y2:at,class:v===0?"es-zero":"es-grid"}));
    const text=svg("text",{x:left-6,y:at+4,"text-anchor":"end"});
    text.textContent=nfmt(v,Number.isInteger(v)?0:Math.abs(v)>=.1?1:2);chart.append(text);
  }
  const layer=svg("g",{"clip-path":"url(#"+id+"-clip)"});chart.append(layer);
  for(const [i,tick] of xticks.entries()){
    const text=svg("text",{x:x(tick),y:bottom+22,"text-anchor":xticks.length>1&&Math.abs(x(tick)-left)<10?"start":xticks.length>1&&Math.abs(x(tick)-right)<10?"end":"middle"});
    text.textContent=xtickText(tick,i);chart.append(text);
  }
  f.append(cap,el("div",yLabel,"es-axis"),chart,el("div",xLabel,"es-axis es-x"));
  return {f,chart,layer,x,y,width,height,left,right,top,bottom};
}
function legend(items){
  const list=el("ul",undefined,"es-legend");
  for(const [label,color,dashed] of items){
    const li=el("li"),mark=el("span",undefined,dashed?"es-dotted":undefined);
    mark.setAttribute("aria-hidden","true");mark.style.setProperty("--swatch",color);li.append(mark,label);list.append(li);
  }return list;
}
function dateRange(rows, key) {
  return rows.length?rows[0][key]+" to "+rows.at(-1)[key]:"No matched observations";
}
function addInputs(root, ...items) {
  const controls=el("div",undefined,"es-controls");controls.append(...items);root.append(controls);
}
function resultPair(figure,aside){
  const row=el("div",undefined,"es-result");row.append(figure,aside);return row;
}
function sentences(values){return (values||[]).map(text=>el("p",text));}
function monthTicks(list){
  const count=window.innerWidth<560?3:5;
  return [...new Set(Array.from({length:count},(_,i)=>Math.round((list.length-1)*i/(count-1))))].map(i=>list[i]);
}
function monthReadout(figure, rows, show, move) {
  const holder=el("div",undefined,"es-readout");
  const label=el("label","Target month"),range=el("input"),out=el("output");
  range.id="es-month-slider";label.htmlFor=range.id;out.setAttribute("for",range.id);
  range.type="range";range.min=0;range.max=rows.length-1;range.value=rows.length-1;
  const update=()=>{
    const idx=Number(range.value);out.textContent=show(rows[idx]);
    range.setAttribute("aria-valuetext",out.textContent);move(rows[idx]);
  };
  range.addEventListener("input",update);
  holder.append(label,range,out);figure.append(holder);update();
}
function forecastingChart(study,rows,windowId,windowLabel) {
  const rolling=windowId==="rolling120";
  const series=[
    {label:"Realised inflation",field:"actual",color:ink.white},
    {label:"Persistence",field:"naive",color:ink.gold,dash:"3 4"},
    {label:"AR",field:rolling?"rolling120Ar":"expandingAr",color:ink.blue},
    {label:"AR with slack",field:rolling?"rolling120Arx":"expandingArx",color:ink.coral,dash:"8 3"}
  ];
  const months=rows.map(r=>monthNumber(r.targetMonth)),first=months[0],last=months.at(-1);
  const tickMap=new Map(monthTicks(rows).map(r=>[monthNumber(r.targetMonth),r.targetMonth]));
  const unit=study.id==="fresh6"?"Annualised inflation (%)":"Year-on-year inflation (%)";
  const g=plot("Forecast against realised inflation",unit,"Target month",first===last?[first-1,last+1]:[first,last],
    limits(rows.flatMap(r=>series.map(s=>r[s.field])),true),[...tickMap.keys()],v=>tickMap.get(v),
    "Observed inflation and three forecasts on identical target dates, using "+windowLabel.toLowerCase()+" estimation.");
  for(const s of series){
    let path="",previous=null;
    for(const r of rows){
      const v=r[s.field],m=monthNumber(r.targetMonth);
      if(!Number.isFinite(v)){previous=null;continue;}
      path+=(m-previous===1?"L":"M")+g.x(m).toFixed(2)+" "+g.y(v).toFixed(2)+" ";previous=m;
    }
    g.layer.append(svg("path",{d:path,fill:"none",stroke:s.color,"stroke-width":s.field==="actual"?2.8:1.8,...(s.dash?{"stroke-dasharray":s.dash}:{})}));
  }
  const cursor=svg("line",{y1:g.top,y2:g.bottom,stroke:ink.white,opacity:.6,"stroke-dasharray":"2 5"});
  g.layer.append(cursor);g.f.append(legend(series.map(s=>[s.label,s.color,!!s.dash])));
  monthReadout(g.f,rows,r=>r.targetMonth+" · Origin "+r.originMonth+" · "+series.map(s=>s.label+" "+nfmt(r[s.field])+"%").join(" · "),
    r=>{const pos=g.x(monthNumber(r.targetMonth));cursor.setAttribute("x1",pos);cursor.setAttribute("x2",pos);});
  return g.f;
}
let vintageSection;
function inflation(d) {
  const box=el("div");
  const sid=pick("target",d.studies,"yoy6"),model=pick("estimation",d.windows,"rolling120"),pid=pick("period",d.periods,"recent");
  const s=d.studies.find(r=>r.id===sid), windowSpec=d.windows.find(r=>r.id===model), period=d.periods.find(r=>r.id===pid);
  const result=s.results.find(r=>r.period===pid&&r.window===model);
  box.append(el("h2","Does economic slack help forecast inflation?"),el("p","A monthly US forecast exercise compares the latest inflation reading with models that learn from inflation persistence and labour-market slack. Switch periods to see when the extra information helped.","es-intro"));
  addInputs(box,select("target","Forecast target",d.studies,sid),select("estimation","Estimation window",d.windows,model),select("period","Evaluation targets",d.periods,pid));
  const vintageLink=el("p",undefined,"es-sub");
  vintageLink.append("This monthly experiment uses historically revised observations. ",anchor("Compare forecasts made with data available at the time","#vintage-check"));
  box.append(vintageLink);
  if(result&&result.n>0){
    const rows=s.path.map(r=>Object.fromEntries(d.pathColumns.map((k,i)=>[k,r[i]]))).filter(r=>r.targetMonth>=result.firstTarget&&r.targetMonth<=result.lastTarget);
    const preferred=result.scores.reduce((a,b)=>a.mae<=b.mae?a:b);
    const label=id=>d.models.find(m=>m.id===id).label;
    const arx=result.scores.find(m=>m.model==="arx");
    box.append(resultPair(forecastingChart(s,rows,model,windowSpec.label),summaryFacts("Forecast performance",[
      ["Lowest mean absolute error",label(preferred.model)],["Absolute error",nfmt(preferred.mae)+" pp"],
      ["Matched targets",result.n+" months"],["First and last targets",result.firstTarget+" to "+result.lastTarget]
    ],"The model with the lowest average error can still miss important individual months.")));
    box.append(el("h3","Errors on the same target months"),table("Forecast errors in percentage points",["Model","Mean absolute error","Root mean squared error","Mean forecast error","MAE gain vs persistence","95% interval for gain"],
      result.scores.map(r=>[label(r.model),nfmt(r.mae),nfmt(r.rmse),nfmt(r.bias),r.model==="naive"?"Reference":signed(r.maeGain),interval(r.ciLow,r.ciHigh)])));
    if(arx){
      const direction=arx.maeGain>=0?"reduced":"increased";
      let inference="";
      if(Number.isFinite(arx.ciLow)&&Number.isFinite(arx.ciHigh))inference=(arx.ciLow<=0&&arx.ciHigh>=0?" Its uncertainty interval spans zero.":" Its uncertainty interval excludes zero.");
      box.append(el("p","Relative to persistence, the model with slack "+direction+" mean absolute error by "+nfmt(Math.abs(arx.maeGain))+" percentage points in this sample."+inference+" Positive gains favour the fitted model. Intervals allow absolute errors in adjacent months to move together.","es-note"));
    }
    const gain=result.slackIncrement;
    if(gain){
      box.append(el("p","Adding the change in unemployment to the inflation-only model "+(gain.maeGain>=0?"reduced":"increased")+" mean absolute error by "+nfmt(Math.abs(gain.maeGain),3)+" percentage points. The 95% interval for the incremental gain is "+interval(gain.ciLow,gain.ciHigh)+" points.","es-note"));
    }
    if(result.smallSample)box.append(el("p","Few target months contribute to this estimate. Its uncertainty interval is sensitive to individual shocks and the dependence assumption.","es-note"));
    const grid=(s.sparseChecks||[]).filter(c=>c.period===pid&&c.window===model);
    if(grid.length)box.append(details("Sensitivity to overlapping forecast horizons",
      el("p","Each grid starts in a different month and scores targets spaced one horizon apart. Gains change when the choice of starting month changes."),
      table("Forecast accuracy across spaced target grids",["Model","Positive-gain grids","Targets per grid","Smallest gain (pp)","Largest gain (pp)"],
        grid.map(c=>[label(c.model),c.favourable+" / "+c.grids,c.nMin+"–"+c.nMax,signed(c.minGain),signed(c.maxGain)]))));
  }else box.append(el("p","This target and period have no common observations."));
  box.append(el("h3","What the forecasts measure"),el("p",s.definition),el("p",windowSpec.description),
    details("Model definitions and forecast design",...d.models.map(m=>el("p",m.label+". "+m.description)),...sentences(d.methods)));
  if(!vintageSection){
    vintageSection=el("section");vintageSection.id="vintage-check";
    renderVintageCheck(vintageSection);
  }
  box.append(vintageSection);
  box.append(details("Research findings and data",...sentences(d.interpretation),sources(d.sources)));
  return box;
}
function sliceEvent(date,period){
  return period==="all" || (period==="pre2009"?date<"2009-01-01":date>="2009-01-01");
}
function xyFor(e,asset,proj){
  const outcome=e.values[asset];
  if(!Number.isFinite(outcome)||!Number.isFinite(e.x))return null;
  if(!proj)return {date:e.date,x:e.x,y:outcome};
  if(!Number.isFinite(e.control))return null;
  return {date:e.date,x:e.x-proj.xIntercept-proj.xSlope*e.control,y:outcome-proj.yIntercept-proj.ySlope*e.control};
}
function eventPlot(rows,fit,asset,spec) {
  const xs=limits(rows.map(r=>r.x),true),ys=limits(rows.map(r=>r.y),true),partial=!!fit.projection;
  const xLabel=spec.xLabel;
  const yLabel=(partial?"Residualised ":"")+asset.label+" change ("+asset.unit+")";
  const g=plot("Repricing across policy events",yLabel,xLabel,xs,ys,ticks(...xs,5),v=>nfmt(v,Number.isInteger(v)?0:1),"Event-level scatter with the estimated linear association across the selected sample.");
  g.layer.append(svg("line",{x1:g.x(0),x2:g.x(0),y1:g.top,y2:g.bottom,class:"es-zero"}));
  for(const r of rows){
    const dot=svg("circle",{cx:g.x(r.x),cy:g.y(r.y),r:3.5,fill:ink.blue,"fill-opacity":.64});
    const tip=svg("title",{});tip.textContent=r.date+" · "+nfmt(r.x)+" bp · "+nfmt(r.y)+" "+asset.unit;dot.append(tip);g.layer.append(dot);
  }
  if(Number.isFinite(fit.beta10)){
    const offset=partial?0:fit.intercept;
    g.layer.append(svg("line",{x1:g.x(xs[0]),x2:g.x(xs[1]),y1:g.y(offset+xs[0]*fit.beta10/10),y2:g.y(offset+xs[1]*fit.beta10/10),stroke:ink.gold,"stroke-width":2.3}));
  }
  g.f.append(legend([["Policy event",ink.blue],["Estimated slope",ink.gold]]));return g.f;
}
function markets(d) {
  const box=el("div");
  const specs=d.specs.map(s=>({id:s.id,label:(s.bank==="fed"?"Fed":"ECB")+" · "+(s.window==="conference"?"Conference":"Decision")+" · "+s.label}));
  const sid=pick("signal",specs,"fed-statement-current"),s=d.specs.find(c=>c.id===sid);
  const pid=pick("period",d.periods,"all"),aid=pick("asset",s.assets,s.bank==="fed"?"UST2Y":"DE2Y"),asset=s.assets.find(a=>a.id===aid);
  const f=s.fits.find(item=>item.period===pid&&item.asset===aid);
  box.append(el("h2","How do markets reprice a policy surprise?"),el("p","Compare changes in market-implied policy rates with movements in bond yields, exchange rates and equities over the same announcement window. Each dot is one central bank event.","es-intro"));
  addInputs(box,select("signal","Institution, window and signal",specs,sid,["asset"]),select("asset","Market instrument",s.assets,aid),select("period","Sample",d.periods,pid));
  box.append(el("p",s.description+" "+s.windowDefinition,"es-sub"));
  if(f){
    const rows=s.events.filter(e=>sliceEvent(e.date,pid)).map(e=>xyFor(e,aid,f.projection)).filter(Boolean);
    box.append(resultPair(eventPlot(rows,f,asset,s),summaryFacts("For a 10 bp rise in the signal",[
      ["Estimated "+asset.label+" move",signed(f.beta10)+" "+asset.unit],["95% slope interval",interval(...f.ci95)+" "+asset.unit],
      ["Matched events",f.n+" of "+f.eligible],["Sample dates",f.from+" to "+f.through]
    ],"The rate surprise and the asset move share a release window. The estimate includes the market’s response to economic information conveyed by the central bank.")));
    const unit=asset.unit+" per 10 bp";
    box.append(el("p","Observed signals ranged from "+nfmt(f.xRange[0])+" to "+nfmt(f.xRange[1])+" bp. The 10 bp scale expresses the fitted sensitivity."+((f.xRange[1]<10)?" An upward signal of that size lies beyond this sample’s observed range.":""),"es-note"));
    box.append(el("h3","Sensitivity of the estimated response"),table("Regression sensitivities",["Sample","Events","Response ("+unit+")","95% interval","Excluded event"],
      [[ "Selected sample",f.n,signed(f.beta10),interval(...f.ci95),"—"],...f.sensitivity.map(r=>[r.label,r.n,signed(r.beta10),interval(...r.ci95),r.excludedDate||"—"])]));
    const difference=s.periodDifferences.find(row=>row.asset===aid);
    const alternate=el("div");
    alternate.append(el("p","The full regression explains "+nfmt(100*f.r2,1)+"% of the variation in the market move. "+f.missing+" eligible events lack one or more required observations. The main 95% interval uses HC3 standard errors. Allowing adjacent events’ residuals to co-move gives an interval of "+interval(...f.hac95)+" "+unit+".","es-note"));
    if(difference)alternate.append(el("p","In the period comparison, the post-2008 slope minus the 2000–08 slope is "+signed(difference.beta10Difference)+" "+unit+". The 95% interval is "+interval(...difference.ci95)+". The size and uncertainty of this difference matter when interpreting an apparent change in transmission.","es-note"));
    box.append(alternate);
    const pair=d.pairedWindows.find(p=>p.bank===s.bank&&p.factor===s.factor&&p.asset===aid&&p.period===pid);
    if(pair){
      box.append(el("h3","Decision versus conference on the same dates"),
        el("p","Across "+pair.nDates+" dates with both windows ("+pair.from+" to "+pair.through+"), the difference in slopes is "+signed(pair.conferenceMinusStatement)+" "+unit+". Its 95% paired interval is "+interval(...pair.pairedCI95)+". Both slopes are fitted on the common dates. The announcements and conferences still differ in duration and news content."),
        table("Date-matched slopes and difference",["Window","Response ("+unit+")","95% interval"],
          [["Decision statement",signed(pair.statementBeta10),interval(...pair.statementCI95)],["Press conference",signed(pair.conferenceBeta10),interval(...pair.conferenceCI95)],["Conference minus decision",signed(pair.conferenceMinusStatement),interval(...pair.pairedCI95)]]));
    }
    const examples=rows.slice().sort((a,b)=>Math.abs(b.x)-Math.abs(a.x)).slice(0,7);
    const eventLink=r=>anchor(r.date,"market-reactions.html?"+new URLSearchParams({bank:s.bank,date:r.date,year:r.date.slice(0,4),window:s.window,asset:aid}));
    box.append(details("Largest absolute signals in this sample",el("p",f.projection?"Signal and outcome columns show changes after removing their fitted association with the short-rate control. The linked event shows the raw market moves.":"Market changes are measured in the selected release window."),
      table("Largest market surprises in absolute size",["Date","Signal (bp)",asset.label+" ("+asset.unit+")"],examples.map(r=>[eventLink(r),signed(r.x),signed(r.y)]))));
    const allRows=details("All "+rows.length+" matched market observations");
    allRows.addEventListener("toggle",()=>{
      if(allRows.open&&allRows.childElementCount===1){
        const dataRows=rows.slice().reverse().map(r=>[eventLink(r),signed(r.x),signed(r.y)]);
        allRows.append(table("Matched observations shown in the chart",["Date",s.xLabel,(f.projection?"Residual ":"")+asset.label+" change ("+asset.unit+")"],dataRows));
      }
    });
    box.append(allRows);
  }else box.append(el("p","This sample has too few eligible events for an estimate."));
  box.append(details("Estimation and source data",...sentences(d.methodology),sources(d.sources)));
  return box;
}
function guidancePlot(events, groups, asset) {
  const points=events.filter(e=>Number.isFinite(e.values[asset.id]));
  if(!points.length){const note=el("p","No matched market changes in this selection.");return note;}
  const short=["Tightening","Easing","Hold / two-sided","Unclear"];
  const g=plot("Market moves by forward guidance",asset.label+" change ("+asset.unit+")","Rate direction communicated at release",
    [-.45,3.45],limits(points.map(e=>e.values[asset.id]),true),[0,1,2,3],(_,i)=>short[i],"Each dot is a meeting. Gold horizontal marks show the median within a guidance category.");
  for(const [i,state] of futureCodes.entries()){
    const members=points.filter(e=>e.state===state);
    members.forEach((e,j)=>{
      const offset=((j*.61803398875+.5)%1-.5)*.47;
      const point=svg("circle",{cx:g.x(i+offset),cy:g.y(e.values[asset.id]),r:4,"fill-opacity":.72,fill:ink.blue});
      const title=svg("title",{});title.textContent=e.date+" · "+word[state]+" · "+signed(e.values[asset.id])+" "+asset.unit;point.append(title);g.layer.append(point);
    });
    const median=groups.find(t=>t.state===state)?.median;
    if(Number.isFinite(median))g.layer.append(svg("line",{x1:g.x(i-.27),x2:g.x(i+.27),y1:g.y(median),y2:g.y(median),stroke:ink.gold,"stroke-width":3.3}));
  }
  g.f.append(legend([["Matched release",ink.blue],["Group median",ink.gold]]));
  return g.f;
}
function guidance(d){
  const box=el("div");
  const banks=d.banks.map(b=>({id:b.id,label:b.name})),bid=pick("bank",banks,"fed"),bank=d.banks.find(b=>b.id===bid);
  const wid=pick("window",bank.windows,"statement"),aid=pick("asset",bank.assets,bid==="fed"?"UST2Y":"DE2Y"),asset=bank.assets.find(a=>a.id===aid),w=bank.windows.find(r=>r.id===wid);
  const actions=[{id:"all",label:"All rate decisions"},{id:"hold",label:"Holds only"},{id:"raise",label:"Increases only"},{id:"cut",label:"Cuts only"}];
  const action=pick("action",actions,"hold");
  const inSample=e=>e.window===wid&&(action==="all"||e.action===action);
  const events=bank.events.filter(inSample).sort((a,b)=>a.date.localeCompare(b.date));
  const groups=bank.groups.filter(c=>c.window===wid&&c.action===action&&c.asset===aid);
  const contrast=bank.contrasts.find(c=>c.window===wid&&c.action===action&&c.asset===aid);
  box.append(el("h2","When rates stay on hold, does guidance move markets?"),el("p","Compare release-window moves across recorded policy signals. Holding the rate decision fixed lets you examine what the committee said about its future path alongside how investors repriced it.","es-intro"));
  addInputs(box,select("bank","Institution",banks,bid,["window","asset"]),select("window","Event window",bank.windows,wid),select("action","Rate action",actions,action),select("asset","Market instrument",bank.assets,aid));
  box.append(el("p",w.definition,"es-sub"));
  const matched=events.filter(e=>Number.isFinite(e.values[aid]));
  const scatter=guidancePlot(events,groups,asset);
  const gap=contrast?.medianGap;
  box.append(resultPair(scatter,summaryFacts("Tightening versus easing",[
    ["Median gap",Number.isFinite(gap)?signed(gap)+" "+asset.unit:"Unavailable"],
    ["Directional observations",(contrast?.tighteningN||0)+" tightening · "+(contrast?.easingN||0)+" easing"],
    ["Priced observations",matched.length+" of "+events.length],
    ["Observed dates",dateRange(matched,"date")]
  ],"The gap is the tightening median minus the easing median. Policy guidance, economic news and prior expectations can all affect prices.")));
  box.append(el("h3","Distribution within each signal"),table("Price moves by communicated rate direction",["Forward guidance","Priced / eligible","Median ("+asset.unit+")","Mean","Minimum","Maximum","Positive / negative / flat"],
    futureCodes.map(state=>{
      const g=groups.find(c=>c.state===state);
      return [word[state],(g?.n||0)+" / "+(g?.eligible||0),nfmt(g?.median),nfmt(g?.mean),nfmt(g?.min),nfmt(g?.max),[g?.positive||0,g?.negative||0,g?.zero||0].join(" / ")];
    })));
  box.append(el("p","These are selected, hand-verified policy communications. A sparse category can be dominated by one policy cycle. A missing price or a missing category is reported separately from an observed zero move.","es-note"));
  if(bank.nearPricedHolds&&action==="hold"){
    const holds=bank.nearPricedHolds;
    const groups=holds.groups.filter(row=>row.asset===aid);
    box.append(details("Holds already priced by the market",el("p",holds.definition+" "+holds.matched+" of "+holds.actualHolds+" holds pass this restriction. A small current-meeting surprise still permits news about later policy."),
      table("Market-priced holds",["Guidance","Priced observations","Median ("+asset.unit+")","Mean ("+asset.unit+")"],groups.map(r=>[word[r.state],r.n,nfmt(r.median),nfmt(r.mean)]))));
  }
  if(bank.examples?.length){
    const examples=el("ul");
    for(const example of bank.examples){
      const li=el("li");li.append(anchor(example.date,"macro-history.html?"+new URLSearchParams({view:"guidance",bank:bid,date:example.date}))," · "+example.note);examples.append(li);
    }
    box.append(details("Documented policy episodes",...sentences(bank.findings),examples));
  }
  if(events.length){
    const recordRows=events.slice().reverse().map(e=>{
      const source=el("span");source.append(anchor("Official release",e.url));
      if(e.noteFile)source.append(" · ",anchor("Archive analysis","research-archive.html?analysis="+encodeURIComponent(e.noteFile.replace(/\.json$/,""))));
      const change=e.values[aid];
      const price=Number.isFinite(change)?anchor(signed(change)+" "+asset.unit,"market-reactions.html?"+new URLSearchParams({bank:bid,date:e.date,year:e.date.slice(0,4),window:wid,asset:aid})):"—";
      const description=anchor(e.date,"macro-history.html?"+new URLSearchParams({view:"guidance",bank:bid,date:e.date}));
      return [description,word[e.state],Number.isFinite(e.rateChangeBps)?signed(e.rateChangeBps,0)+" bp":e.action,price,source];
    });
    box.append(details("Individual releases and observed moves",table("Policy releases and exact market windows",["Date","Signal","Rate decision","Market change","Source"],recordRows)));
  }
  box.append(details("Sample construction and data",...sentences(d.method),sources([{label:bank.sourceLabel,url:bank.source}])));
  return box;
}
const views={inflation,markets,guidance};
let dataset;
function paint(focus) {
  content.replaceChildren(views[current](dataset));
  if(focus)document.getElementById("es-"+focus)?.focus({preventScroll:true});
}
async function main() {
  document.querySelector('[data-study="'+current+'"]').setAttribute("aria-current","page");
  try{
    const r=await fetch("data/"+studies[current]+".json");
    if(!r.ok)throw Error("Research data unavailable");
    dataset=await r.json();paint();
    if(location.hash==="#vintage-check"&&vintageSection)requestAnimationFrame(()=>vintageSection.scrollIntoView());
  }catch(e){
    const msg=el("p","This study could not be loaded. ");msg.setAttribute("role","alert");msg.append(anchor("Reload the page",location.href));
    content.replaceChildren(msg);console.error(e);
  }finally{content.setAttribute("aria-busy","false");}
}
main();
