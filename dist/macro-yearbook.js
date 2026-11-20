const names = {US:"United States", EA:"Euro area", UK:"United Kingdom"};
const measures = {prices:"Consumer price inflation", jobless:"Unemployment rate", industry:"Industrial production growth"};
const pairs = {US_EA:["US","EA"], US_UK:["US","UK"], EA_UK:["EA","UK"]};
const number = value => Number.isFinite(value) ? value.toFixed(1) + "%" : "—";
const delta = value => Number.isFinite(value) ? (value < -.00001 ? "−" : value > .00001 ? "+" : "") + Math.abs(value).toFixed(1) : "—";
const period = month => new Intl.DateTimeFormat("en-GB",{month:"short",year:"numeric",timeZone:"UTC"}).format(new Date(month+"-01T00:00Z"));
const valid = Number.isFinite;
const availability = {
  US:{prices:"CPI-U, all items, unadjusted. Twelve-month change calculated from BLS index CUUR0000SA0 and rounded to the published precision. The October 2025 index is missing because of the US government shutdown, which also leaves October 2026 annual inflation unavailable.",jobless:"BLS U-3 civilian unemployment rate, age 16 and over, seasonally adjusted. The October 2025 household-survey reading is unavailable.",industry:"Federal Reserve G.17 real output in manufacturing, mining and utilities. Twelve-month change from the seasonally adjusted production index."},
  EA:{prices:"Eurostat’s published all-items HICP annual change, unadjusted. The fixed 21-country series starts in December 2000, so earlier months have no comparable published rate here.",jobless:"Eurostat’s harmonised unemployment rate for both sexes, total ages, seasonally adjusted. The source covers ages 15–74.",industry:"Eurostat volume of industry excluding construction (NACE B–D). Seasonally and calendar-adjusted. Twelve-month growth uses that index. Flags on the index or its year-earlier value carry through."},
  UK:{prices:"ONS published annual change in all-items CPI, D7G7. UK CPI and euro-area HICP follow harmonised concepts. The US CPI-U basket and housing treatment differ.",jobless:"ONS X01, age 16+, seasonally adjusted single-month unemployment estimate. Its sample is about a third of the headline three-month survey. ONS cautions that individual months may be unrepresentative and advises using longer movements.",industry:"ONS K222, the seasonally adjusted chained-volume index for production (SIC B–E). UK coverage includes water and waste activities. Growth is calculated from the published index."}
};
const sourceLinks = {
  US:{prices:["BLS all-items CPI-U","https://data.bls.gov/timeseries/CUUR0000SA0"],jobless:["BLS unemployment rate","https://data.bls.gov/timeseries/LNS14000000"],industry:["Federal Reserve G.17","https://www.federalreserve.gov/releases/g17/"]},
  EA:{prices:["Eurostat HICP","https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_minr/default/table?lang=en"],jobless:["Eurostat unemployment","https://ec.europa.eu/eurostat/databrowser/view/une_rt_m/default/table?lang=en"],industry:["Eurostat industrial production","https://ec.europa.eu/eurostat/databrowser/view/sts_inpr_m/default/table?lang=en"]},
  UK:{prices:["ONS CPI annual rate","https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7g7/mm23"],jobless:["ONS X01 single-month estimates","https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/datasets/labourforcesurveysinglemonthestimatesx01"],industry:["ONS index of production","https://www.ons.gov.uk/economy/economicoutputandproductivity/output/timeseries/k222/diop"]}
};

const policyRecords = {
  2001: ["20 March 2001 · The Fed cut its target to 5% as inventories built up and manufacturing production adjusted. Compare industrial output and unemployment around the period of weakness.", "FOMC decision", "https://www.federalreserve.gov/boarddocs/press/general/2001/20010320/"],
  2003: ["25 June 2003 · The Fed cut its target to 1%. It described firmer spending alongside the risk that inflation could fall further. The price series and output series give two independent checks on that diagnosis.", "FOMC decision", "https://www.federalreserve.gov/boarddocs/press/monetary/2003/20030625/default.htm"],
  2010: ["10 May 2010 · The ECB introduced securities purchases to address disruption in debt markets. Region-wide output tracks the subsequent recovery, while a test of the programme’s transmission would also need country-level financial conditions.", "ECB measures", "https://www.ecb.europa.eu/press/pr/date/2010/html/pr100510.en.html"],
  2011: ["21 September 2011 · The Fed announced purchases of longer-dated Treasuries and matching sales at shorter maturities. The distinction matters when reading a weak recovery alongside a policy rate with little room to fall.", "FOMC maturity extension", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20110921a.htm"],
  2012: ["6 September 2012 · The ECB specified the conditions for outright purchases of sovereign bonds. The commitment addressed financial fragmentation within the monetary union, which an area-wide unemployment rate can conceal.", "ECB OMT terms", "https://www.ecb.europa.eu/press/pr/date/2012/html/pr120906_1.en.html"],
  2013: ["4 July 2013 · The ECB described an extended period of low rates in light of subdued inflation and weak activity. Compare the two regions’ inflation paths with the slower adjustment in unemployment.", "ECB press conference", "https://www.ecb.europa.eu/press/press_conference/monetary-policy-statement/2013/html/is130704.en.html"],
  2014: ["5 June 2014 · The ECB announced a negative deposit facility rate. Check whether the inflation rate was already falling before June and how long the decline continued.", "ECB rate decision", "https://www.ecb.europa.eu/press/pr/date/2014/html/pr140605.en.html"],
  2015: ["22 January 2015 · The ECB announced that sovereign bonds would join its expanded asset purchases. Comparing the price and output series helps distinguish disinflation from a contraction in production.", "ECB purchase announcement", "https://www.ecb.europa.eu/press/pr/date/2015/html/pr150122_1.en.html"],
  2016: ["4 August 2016 · The Bank of England cut Bank Rate to 0.25% and introduced a Term Funding Scheme. Compare UK output and prices with another region across the referendum and the August decision.", "Bank of England decision", "https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2016/mpc-august-2016"]
};
function yearMonths(year) {
  return Array.from({length:12},(_,i)=>year+"-"+String(i+1).padStart(2,"0"));
}
function lineChart(months,codes,read,svgNode) {
  const svg=svgNode("svg",{viewBox:"0 0 690 220",role:"img","aria-label":"Monthly observed rates for "+codes.map(c=>names[c]).join(" and ")+", "+period(months[0])+" through "+period(months.at(-1))+". The monthly readings table provides each value."});
  const values=codes.flatMap(c=>months.map(m=>read(c,m))).filter(valid);
  if(!values.length)return svg;
  const min=Math.min(...values),max=Math.max(...values);
  const steps=[.1,.25,.5,1,2,5,10,20];
  const step=steps.find(s=>s>=(max-min)/4)||25;
  const low=Math.floor(min/step)*step,high=Math.max(low+step,Math.ceil(max/step)*step);
  const left=52,right=668,top=14,bottom=178;
  const x=i=>left+i*(right-left)/(months.length-1), y=v=>bottom-(v-low)*(bottom-top)/(high-low);
  function label(t,xx,yy,anchor){const text=svgNode("text",{x:xx,y:yy,"text-anchor":anchor});text.textContent=t;svg.append(text);}
  for(let v=low;v<high+step/3;v+=step){
    svg.append(svgNode("line",{x1:left,x2:right,y1:y(v),y2:y(v),class:"yb-rule"}));
    label(Number(v.toFixed(2))+"%",left-7,y(v)+4,"end");
  }
  for(const i of new Set([0,Math.round((months.length-1)/4),Math.round((months.length-1)/2),Math.round(3*(months.length-1)/4),months.length-1])){
    label(period(months[i]), x(i),bottom+23,i===0?"start":i===months.length-1?"end":"middle");
  }
  codes.forEach((c,j)=>{
    let path="",penUp=true;
    for(const [i,m] of months.entries()){
      const value=read(c,m);
      if(!valid(value)){penUp=true;continue;}
      path+=(penUp?" M":" L")+x(i)+" "+y(value);penUp=false;
      const dot=svgNode("circle",{cx:x(i),cy:y(value),r:months.length<=13?2.8:1.5,class:"yb-point yb-colour-"+j});
      const tip=svgNode("title",{});tip.textContent=names[c]+" · "+period(m)+" · "+number(value);dot.append(tip);svg.append(dot);
    }
    svg.append(svgNode("path",{d:path.trim(),class:"yb-line yb-colour-"+j}));
  });
  return svg;
}

export function yearbook(data, episodes, {el,select,table,link,svgNode}, params) {
  const lastYear=Number(data.asOf.slice(0,4));
  const years=Array.from({length:lastYear-1999},(_,i)=>2000+i);
  let year=Number(params.get("historyYear"));if(!years.includes(year))year=lastYear;
  let metric=Object.hasOwn(measures,params.get("indicator"))?params.get("indicator"):"prices";
  let pair=Object.hasOwn(pairs,params.get("regions"))?params.get("regions"):"US_EA";
  let span=params.get("span")==="3"?3:1;
  const page=el("article",undefined,"yb-panel");
  const heading=el("h2"), desc=el("p",undefined,"hs-deck");
  const filters=el("div",undefined,"yb-filters");
  const content=el("div");
  filters.append(
    select("Year",[...years].reverse().map(y=>[String(y),String(y)]),String(year),v=>{year=Number(v);render(true);}),
    select("Regions",Object.entries(pairs).map(([k,c])=>[k,c.map(v=>names[v]).join(" and ")]),pair,v=>{pair=v;render(true);}),
    select("Indicator",Object.entries(measures),metric,v=>{metric=v;render(true);}),
    select("Chart window",[["1","Selected year"],["3","Three years to selection"]],String(span),v=>{span=Number(v);render(true);}));
  page.append(heading,desc,filters,content);
  function render(save){
    const codes=pairs[pair];
    const months=yearMonths(year);
    const prior=(year-1)+"-12";
    const start=Math.max(2000,year-span+1);
    const through=(data.asOf.slice(0,7));
    const plotMonths=[(start-1)+"-12",...Array.from({length:year-start+1},(_,i)=>yearMonths(start+i)).flat()].filter(m=>m<through);
    const get=(c,m,key=metric)=>data.panels[c]?.[m]?.[key]??null;
    const paired=key=>months.filter(m=>codes.every(c=>valid(get(c,m,key))));
    const common=paired(metric),end=common.at(-1);
    heading.textContent="Macro indicators in "+year+(year===lastYear?" to date":"");
    desc.textContent="Compare prices, unemployment and industrial output month by month. Each comparison uses the latest month both regions reported for that indicator.";
    const figure=el("figure",undefined,"yb-chart");
    const legend=el("div",undefined,"yb-legend");
    codes.forEach((c,i)=>legend.append(el("span",names[c],"yb-key yb-key-"+i)));
    const unit=metric==="jobless"?"% of the labour force":"% change from a year earlier";
    figure.append(el("h3",measures[metric]+" · "+unit),legend,lineChart(plotMonths,codes,get,svgNode),
      el("figcaption","From "+period(plotMonths[0])+" to "+period(plotMonths.at(-1))+". Breaks indicate missing monthly observations."));
    const highlight=el("p",undefined,"yb-readout");
    if(end) {
      const gap=get(codes[0],end)-get(codes[1],end);
      highlight.textContent=period(end)+" · "+names[codes[0]]+" "+number(get(codes[0],end))+" and "+names[codes[1]]+" "+number(get(codes[1],end))+". The difference ("+codes[0]+" minus "+codes[1]+") was "+delta(gap)+" percentage points.";
    } else highlight.textContent="The two series have no shared observation for this indicator in "+year+".";
    const method=el("p",undefined,"yb-note");
    method.textContent="Prior-December changes compare that December with each indicator’s latest common month. Prices and unemployment show percentage-point changes in their rates. Industrial output shows the percentage change in the production level.";
    const summary=table(["Indicator","Latest common month",names[codes[0]],names[codes[1]],"Change since Dec "+(year-1)+" · "+codes[0],"Change since Dec "+(year-1)+" · "+codes[1],"Common months"],
      Object.entries(measures).map(([key,label])=>{
        const list=paired(key),e=list.at(-1), change=c=>{
          if(!e)return "—";
          const k=key==="industry"?"output":key, before=get(c,prior,k), after=get(c,e,k);
          if(!valid(before)||!valid(after))return "—";
          return key==="industry"?delta(100*(after/before-1))+"%":delta(after-before)+" pp";
        };
        return [label,e?period(e):"—",number(get(codes[0],e,key)),number(get(codes[1],e,key)),...codes.map(change),String(list.length)];
      }),"Three indicators at their common reference months");
    const lastOutput=paired("industry").at(-1);
    if(codes.includes("EA")&&data.euroProductionFlags[lastOutput]){
      summary.append(el("p","Eurostat flags an input to the "+period(lastOutput)+" euro-area output growth rate as imputed.","yb-note"));
    }
    const reported=el("p",undefined,"yb-note");
    reported.textContent=codes.map(c=>{
      const last=months.filter(m=>valid(get(c,m))).at(-1);
      return names[c]+" · "+(last?period(last)+" ("+number(get(c,last))+")":"no observation");
    }).join(" · ") + ". Latest individual observations in the selected year.";
    const monthly=el("details",undefined,"hs-details");monthly.append(el("summary","Monthly readings and source flags"),
      table(["Month",...codes.map(c=>names[c]),"Difference · pp"],
      plotMonths.map(m=>{
        const values=codes.map(c=>get(c,m));
        return [period(m),...values.map((v,i)=>number(v)+(valid(v)&&codes[i]==="EA"&&metric==="industry"&&data.euroProductionFlags[m]?" *":"")),values.every(valid)?delta(values[0]-values[1]):"—"];
      }),"Monthly rates in the chart window"));
    if(codes.includes("EA")&&metric==="industry"&&plotMonths.some(m=>data.euroProductionFlags[m]))monthly.append(el("p","* Eurostat flags an input to this growth rate as imputed."));
    const reading=el("div",undefined,"yb-reading");
    reading.append(el("h3","Read the year in context"));
    if(policyRecords[year]){
      const [text,label,url]=policyRecords[year];
      const context=el("p",undefined,"yb-context");
      context.append(text+" ",link(label,url));
      reading.append(context);
    }
    const related=episodes.filter(e=>e.start.slice(0,4)<=String(year)&&e.end.slice(0,4)>=String(year));
    for(const e of related)reading.append(link(e.name,"macro-history.html?view=cycles&episode="+encodeURIComponent(e.id)));
    if(year>=2011&&year<=2015)reading.append(link("Swiss franc floor, 2011–15","historical-data.html#swiss-franc-floor"));
    if(year===2012)reading.append(link("ECB bond backstop, 2012","historical-data.html#ecb-omt"));
    reading.append(link("Compare annual GDP growth and inflation across economies in "+year,"yearbook.html?historyYear="+year));
    const notes=el("details",undefined,"hs-details");
    notes.append(el("summary","Definitions and data sources"),el("p","Observation vintage "+data.asOf+". The series include historical revisions available by this date. Euro-area membership is fixed at 21 countries throughout. Monthly observations refer to economic activity during a period and were published later."));
    for(const c of codes){const p=el("p");p.append(names[c]+". "+availability[c][metric]+" ",link(...sourceLinks[c][metric]));notes.append(p);}
    content.replaceChildren(figure,highlight,reported,el("h3","What changed within "+year+"?"),method,summary,monthly,reading,notes);
    if(save){const u=new URL(location.href);u.searchParams.set("historyYear",year);u.searchParams.set("regions",pair);u.searchParams.set("indicator",metric);u.searchParams.set("span",span);history.replaceState(null,"",u);}
  }
  render(false);
  return page;
}
