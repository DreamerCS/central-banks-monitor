export function buildRepricingView(ui) {
  const {el,anchor,pick,select,table,details,sources,summaryFacts,plot,legend,nfmt,signed,
    interval,limits,svg,resultPair,addInputs,sentences,ink,word} = ui;
  const actionLabel={raise:"Rate increase",hold:"Rate hold",cut:"Rate cut"};
  const bankLabels={fed:"Federal Reserve",ecb:"European Central Bank"};
  const windowLabels={statement:"Decision statement",conference:"Press conference"};
  const fixedCases={fed:"2022-11-02",ecb:"2023-09-14"};
  function actionText(r) {
    const action=actionLabel[r.action]||r.action;
    return Number.isFinite(r.changeBp)?action+" · "+(r.changeBp===0?"0":signed(r.changeBp,0))+" bp":action+" · published target range";
  }
  function href(panel,e,extra={}) {
    return "empirical-studies.html?"+new URLSearchParams({study:"repricing",bank:panel.bank,window:panel.window,date:e.date,...extra});
  }
  function marketEvent(p,e,asset) {
    return "market-reactions.html?"+new URLSearchParams({bank:p.bank,window:p.window,year:e.date.slice(0,4),date:e.date,asset});
  }
  function applicableWindow(p,date) {
    if(p.bank!=="ecb"||!p.windowDefinition.includes(" From July 2022,"))return p.windowDefinition;
    const parts=p.windowDefinition.split(" From July 2022,");
    return date>="2022-07-21"?"Median quotes at "+parts[1].trim().replace(/\.$/,"")+" Frankfurt time.":parts[0];
  }
  function factList(entries) {
    const list=el("dl");
    for(const [key,value] of entries){
      const row=el("div");row.append(el("dt",key),el("dd",value));list.append(row);
    }
    return list;
  }
  function releaseRecord(p,e) {
    const section=el("section",undefined,"es-release"),body=el("div");
    const text=e.voice||(p.bank==="fed"?"Federal Open Market Committee":"ECB Governing Council");
    body.append(el("h3",e.date+" · "+windowLabels[p.window]),el("p",text,"es-sub"),el("p",e.evidence,"es-intro"));
    if(e.analysis)body.append(el("p",e.analysis));
    const links=el("p",undefined,"es-links");
    links.append(anchor("Link to this release",href(p,e)),anchor("Official publication",e.url),anchor("Guidance record","macro-history.html?"+new URLSearchParams({view:"guidance",bank:p.bank,window:p.window,date:e.date})));
    if(e.noteFile)links.append(anchor("Read analysis","research-archive.html?analysis="+encodeURIComponent(e.noteFile.replace(/\.json$/,""))));
    body.append(links);
    section.append(body,factList([["Day’s decision",actionText(e)],["Forward rate guidance",word[e.state]],["Release window",applicableWindow(p,e.date)]]));
    return section;
  }
  function prices(p,e){
    const isFed=p.bank==="fed";
    const rows=[
      ["One-year "+(isFed?"USD":"euro")+" OIS",e.ois1y,"bp",isFed?"OIS1Y":"OIS_1Y"],
      [isFed?"Two-year US Treasury yield":"Two-year German government yield",e.twoYear,"bp",isFed?"UST2Y":"DE2Y"],
      [isFed?"Next-meeting repricing":"One-month euro OIS",e.nearRate,"bp",isFed?"MP2":"OIS_1M"],
      ["EUR/USD",e.fx,"%", "EURUSD"]
    ];
    if(isFed)rows.splice(2,0,["Current-meeting policy surprise",e.mp1,"bp","MP1"]);
    const priceRows=rows.map(([name,value,unit,id])=>[name,
      Number.isFinite(value)?signed(value,unit==="%"?3:2)+" "+unit:"—",
      Number.isFinite(value)?anchor("Open market window",marketEvent(p,e,id)):"No matched price"]);
    return table("Observed changes for the selected communication",["Market instrument","Window change","Observation"],priceRows);
  }
  function laterPressConference(e) {
    const c=e.companion,section=el("section");
    section.append(el("h3",c.heading),el("p",c.interpretation),
      el("p",c.windowDefinition,"es-sub"),
      table("Paired but separately measured changes on "+e.date,
        ["Instrument","Statement window","Press conference window"],
        c.instruments.map(i=>{
          const change=v=>Number.isFinite(v)?signed(v,i.unit==="%"?3:2)+" "+i.unit:"—";
          return [i.label,change(i.statement),change(i.conference)];
        })));
    const source=el("p",undefined,"es-note");
    source.append(anchor("Chair’s press conference transcript",c.url)," · "+c.pages+". The conference window is shown separately from the statement observations scored below.");
    section.append(source);
    return section;
  }
  function rangeOf(values){
    if(!values.length)return {};
    const sorted=values.slice().sort((a,b)=>a-b);
    function quantile(q){
      const at=(sorted.length-1)*q,i=Math.floor(at);
      return sorted[i]+(sorted[Math.ceil(at)]-sorted[i])*(at-i);
    }
    return {min:sorted[0],q25:quantile(.25),median:quantile(.5),q75:quantile(.75),max:sorted.at(-1)};
  }
  function peerChart(panel,e,peers,group) {
    const rows=peers.filter(r=>Number.isFinite(r.ois1y)).sort((a,b)=>a.date.localeCompare(b.date));
    if(!rows.length)return el("p","No one-year OIS observation is available for this comparison group.");
    const points=rows.map((r,i)=>i);
    const shown=[...new Set([0,Math.floor((rows.length-1)/2),rows.length-1])];
    const g=plot("One-year OIS in comparable releases","Signed one-year OIS change (bp)","Comparable releases in chronological order",
      [-.5,Math.max(.5,rows.length-.5)],limits(rows.map(r=>r.ois1y),true),shown,v=>rows[v].date.slice(0,7),
      "Each mark is a reviewable announcement with the selected action and guidance. Dates are spaced by meeting. Gold marks the selected release.");
    if(Number.isFinite(group?.median)){
      g.layer.append(svg("line",{x1:g.left,x2:g.right,y1:g.y(group.median),y2:g.y(group.median),stroke:ink.green,"stroke-width":2,"stroke-dasharray":"5 5"}));
    }
    points.forEach(i=>{
      const r=rows[i],chosen=r.date===e.date;
      const dot=svg("circle",{cx:g.x(i),cy:g.y(r.ois1y),r:chosen?6:4.3,fill:chosen?ink.gold:ink.blue,opacity:chosen?1:.83});
      const title=svg("title",{});title.textContent=r.date+" · "+signed(r.ois1y)+" bp";dot.append(title);g.layer.append(dot);
    });
    const items=[["Comparable release",ink.blue],["Median",ink.green,true]];
    if(Number.isFinite(e.ois1y))items.splice(1,0,["Selected release",ink.gold]);
    g.f.append(legend(items));
    return g.f;
  }
  function comparison(p,e) {
    const options=[{id:"action",label:"Same rate action"}];
    if(Number.isFinite(e.changeBp))options.push({id:"size",label:"Same basis-point change"});
    const match=pick("match",options,"action");
    const peers=p.events.filter(r=>r.action===e.action&&r.state===e.state&&(match==="action"||r.changeBp===e.changeBp));
    const group=rangeOf(peers.map(r=>r.ois1y).filter(Number.isFinite));
    const n=peers.filter(row=>Number.isFinite(row.ois1y)).length;
    const section=el("section");section.append(el("h3","Same action, same forward guidance"),
      el("p","Compare "+bankLabels[p.bank]+" "+windowLabels[p.window].toLowerCase()+" releases showing a "+(actionLabel[e.action]||e.action).toLowerCase()+" with "+word[e.state].toLowerCase()+". Monetary outcomes are for the exact release window. The comparison can include dates later than the selected meeting.","es-note"));
    addInputs(section,select("match","Peer comparison",options,match));
    section.append(resultPair(peerChart(p,e,peers,group),summaryFacts("Comparable one-year moves",[
      ["Priced / documented releases",n+" / "+peers.length],
      ["Median",Number.isFinite(group?.median)?signed(group.median)+" bp":"—"],
      ["Middle half",Number.isFinite(group?.q25)&&Number.isFinite(group?.q75)?interval(group.q25,group.q75)+" bp":"—"],
      ["Minimum to maximum",Number.isFinite(group?.min)&&Number.isFinite(group?.max)?interval(group.min,group.max)+" bp":"—"]
    ],"Small groups can be concentrated in a single rate cycle.")));
    const ordered=peers.slice().sort((a,b)=>b.date.localeCompare(a.date));
    section.append(details("Inspect comparable releases",table("Individual meetings with the same coded rate action and guidance",
      ["Date","One-year OIS","Two-year yield","EUR/USD"],ordered.map(r=>[
        anchor(r.date,href(p,r,{match})),Number.isFinite(r.ois1y)?signed(r.ois1y)+" bp":"—",
        Number.isFinite(r.twoYear)?signed(r.twoYear)+" bp":"—",Number.isFinite(r.fx)?signed(r.fx,3)+"%":"—"
      ]))));
    const example=p.examples?.find(g=>g.action===e.action&&g.state===e.state&&g.changeBp===e.changeBp);
    if(example){
      const compared=example.dates.map(dt=>p.events.find(r=>r.date===dt));
      if(compared.every(r=>r&&Number.isFinite(r.ois1y))){
        const item=el("p",undefined,"es-note");item.append("Even at the same decision size, the one-year swap fell ",
          anchor(nfmt(Math.abs(compared[0].ois1y))+" bp on "+compared[0].date,href(p,compared[0],{match:"size"})),
          " and rose ",anchor(nfmt(compared[1].ois1y)+" bp on "+compared[1].date,href(p,compared[1],{match:"size"})),".");
        section.append(item);
      }
    }
    return section;
  }
  function errorText(g) {
    if(!g||!Number.isFinite(g.gain))return "Unavailable";
    let text=signed(g.gain,2)+" bp";
    if(g.ci95?.length===2&&g.ci95.every(Number.isFinite))text+=" (95% interval "+interval(...g.ci95)+")";
    return text;
  }
  function predictionPanel(d,p,e,protocol,cohort) {
    const section=el("section"),models=d.models;
    const protocols=d.protocols.find(r=>r.id===protocol);
    section.append(el("h3","Does the text improve held-out estimates?"),
      el("p","The target is the signed one-year OIS move in the same event window. A model may use the released text and the rate decision. Its historical response estimates use only earlier outcomes. This is a test of how informative the release is, using data that become observable during the event."),
      el("p",protocols.description,"es-sub"));
    const test=p.tests.find(t=>t.protocol===protocol&&t.cohort===cohort);
    const cohortMeta=d.cohorts.find(c=>c.id===cohort);
    if(cohortMeta.description)section.append(el("p",cohortMeta.description,"es-sub"));
    if(test&&test.n>0) {
      const byModel=new Map(test.scores.map(s=>[s.model,s]));
      section.append(table("Held-out one-year OIS forecast errors in basis points",["Estimate","Mean absolute error","Root mean squared error","Mean error"],
        models.filter(m=>byModel.has(m.id)).map(m=>{const r=byModel.get(m.id);return [m.label,nfmt(r.mae),nfmt(r.rmse),signed(r.bias)];})),
        el("p",test.n+" scored releases · "+test.first+" to "+test.last+" · all errors in basis points. Mean error is the estimate minus the observed move. Intervals resample calendar quarters and require at least 24 releases across 12 quarters.","es-sub"));
      const early=el("div",undefined,"es-aside");early.append(el("h3","Gain from including guidance"),
        factList([["Against the action-only estimate",errorText(test.guidanceVsAction)],["Against recent releases",errorText(test.guidanceVsRecent)],["Against zero repricing",errorText(test.guidanceVsZero)]]),
        el("p","A positive gain means a lower average absolute error. "+test.supportedN+" held-out releases had at least three earlier cases with the same action and guidance. Adding wording changed the estimate on "+test.predictionChangedN+" releases."));
      section.append(early);
      const size=test.exactSize;
      if(size&&Number.isFinite(size.actionMae)&&Number.isFinite(size.guidanceMae)){
        section.append(details("Condition on the number of basis points moved",
          el("p","On the numerical-action sensitivity, the action-only error is "+nfmt(size.actionMae)+" bp and the action-and-wording error is "+nfmt(size.guidanceMae)+" bp. Gain from wording: "+errorText(size.guidanceVsAction)+". There are "+size.supportedN+" held-out cases with at least three previous observations of the exact rate move and guidance.")));
      }
    }else {
      const message=protocol==="frozen2022"&&p.coverage.pre2022<8
        ?"The fixed pre-2022 calibration has "+p.coverage.pre2022+" matched earlier observations in this window. The exercise requires eight to estimate the historical benchmarks."
        :"This selection has no scored releases under the chosen training protocol.";
      section.append(el("p",message));
    }
    const sensitivity=p.codingSensitivity;
    if(sensitivity){
      const variants=sensitivity.variants.map(v=>{
        const score=v.scores.find(s=>s.model==="guidance");
        return [v.id==="original"?"Original evidence coding":"Alternative reading",v.n,
          nfmt(score?.mae),errorText(v.guidanceVsAction)];
      });
      const records=el("ul");
      for(const r of sensitivity.recoded){
        const item=el("li");item.append(anchor(r.date,href(p,r)), " · "+word[r.from]+" to "+word[r.to]+". "+r.reason);
        records.append(item);
      }
      section.append(details("Sensitivity to an alternative reading of the press conference",
        el("p",sensitivity.description),
        table("Year-by-year held-out estimates for 2022 onward",["Reading","Scored events","Wording MAE (bp)","Gain vs action only"],variants),
        el("p",sensitivity.changedPredictionN+" held-out estimates changed across the two readings. The alternatives use the same outcomes and scoring dates.","es-note"),records));
    }
    section.append(el("h3","Estimates for "+e.date));
    const forecast=e.forecasts?.[protocol];
    if(forecast&&forecast.predictions){
      const cell=forecast.cellN>=3?"Historical action-and-guidance cell":"Fallback used for the text-conditioned estimate";
      const fact=el("p",forecast.trainN+" previously observed windows through "+forecast.trainThrough+"  · "+forecast.actionN+" with the same action · "+forecast.cellN+" with the same action and forward guidance. "+cell+".","es-sub");
      const tracked=models.filter(m=>Number.isFinite(forecast.predictions[m.id]));
      section.append(fact,table("One-year OIS estimates for the selected release",["Estimate","Fitted move","Absolute error vs observed"],
        tracked.map(m=>[m.label,signed(forecast.predictions[m.id])+" bp",Number.isFinite(e.ois1y)?nfmt(Math.abs(forecast.predictions[m.id]-e.ois1y))+" bp":"—"])));
      if(Number.isFinite(e.ois1y))section.append(el("p","Observed one-year OIS move "+signed(e.ois1y)+" bp.","es-sub"));
    }else section.append(el("p","No estimate is recorded for this meeting under the selected protocol.","es-note"));
    return section;
  }
  return function repricing(d){
    const root=el("div"),range=new URLSearchParams(location.search);
    const candidates=d.panels.filter(p=>p.events.some(e=>e.date===range.get("date")));
    const availableBanks=[...new Set(d.panels.map(p=>p.bank))].map(id=>({id,label:bankLabels[id]||id}));
    const bank=pick("bank",availableBanks,candidates[0]?.bank||"fed");
    const panels=d.panels.filter(p=>p.bank===bank),windowOptions=panels.map(p=>({id:p.window,label:windowLabels[p.window]||p.window}));
    const windowId=pick("window",windowOptions,candidates.find(p=>p.bank===bank)?.window||"statement");
    const panel=panels.find(p=>p.window===windowId);
    const ordered=panel.events.slice().sort((a,b)=>b.date.localeCompare(a.date));
    const dates=ordered.map(e=>({id:e.date,label:e.date+" · "+(actionLabel[e.action]||e.action)}));
    const picked=pick("date",dates,fixedCases[bank]),e=ordered.find(e=>e.date===picked);
    root.append(el("h2","How much does a meeting move the expected rate path?"),
      el("p","Read the committee’s contemporaneous guidance beside the rate it actually set. Compare the one-year market response with other meetings that took the same action and signalled the same direction.","es-intro"));
    addInputs(root,select("bank","Institution",availableBanks,bank,["window","date","cohort"]),
      select("window","Publication window",windowOptions,windowId,["date","cohort"]),
      select("date","Selected release",dates,picked));
    if(!e){root.append(el("p","No reviewed release is available in this window."));return root;}
    const alternate=panels.find(p=>p.window!==panel.window&&p.events.some(row=>row.date===e.date));
    root.append(releaseRecord(panel,e));
    if(alternate){
      const other=el("p",undefined,"es-sub");
      other.append("Same meeting · ",anchor("Open the "+windowLabels[alternate.window].toLowerCase(),href(alternate,e)));
      root.append(other);
    }
    root.append(prices(panel,e),el("p","Positive EUR/USD means the euro strengthened. A one-year OIS change combines repricing across expected short rates and any change in the contract’s risk premium.","es-note"));
    if(e.companion)root.append(laterPressConference(e));
    root.append(comparison(panel,e));
    const candidatesForCohort=d.cohorts.filter(c=>c.id!=="nearPricedHolds"||panel.bank==="fed"&&panel.window==="statement");
    const availableTest=panel.tests.find(t=>t.cohort==="all"&&t.n>0);
    const protocol=pick("protocol",d.protocols,availableTest?.protocol||"frozen2022");
    const cohort=pick("cohort",candidatesForCohort,"all");
    addInputs(root,select("protocol","Training and test split",d.protocols,protocol),select("cohort","Scoring sample",candidatesForCohort,cohort));
    root.append(predictionPanel(d,panel,e,protocol,cohort));
    const covered=panel.coverage;
    const method=details("Estimation and source data",el("p",covered.matched+" of "+covered.coded+" coded communications have one-year OIS moves in the specified window. Matched outcomes run from "+covered.first+" to "+covered.last+". Each market instrument retains its own availability."),...sentences(d.methods),sources(d.sources));
    root.append(method);
    return root;
  };
}
