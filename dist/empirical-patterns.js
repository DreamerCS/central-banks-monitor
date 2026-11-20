export function buildPatternViews(ui) {
  const {
    el, anchor, pick, select, table, details, sources, summaryFacts, plot, legend,
    nfmt, signed, interval, limits, ticks, svg, monthNumber, monthTicks, monthReadout,
    resultPair, addInputs, sentences, ink
  } = ui;
  const componentKeys=["demand","supply","ambiguous"];
  const componentLabels={demand:"Demand",supply:"Supply",ambiguous:"Ambiguous"};
  const componentColors={demand:ink.gold,supply:ink.blue,ambiguous:"#829985"};

  function componentPlot(panel,rows) {
    const monthIds=rows.map(r=>monthNumber(r.month)),begin=monthIds[0],end=monthIds.at(-1);
    const lookup=new Map(monthTicks(rows).map(r=>[monthNumber(r.month),r.month]));
    const values=rows.flatMap(r=>{
      const parts=componentKeys.map(k=>r[k]).filter(Number.isFinite);
      return [parts.reduce((a,b)=>a+Math.min(0,b),0),parts.reduce((a,b)=>a+Math.max(0,b),0),r.pce];
    });
    const graph=plot(panel.label+" inflation and its contributions",
      "12-month inflation (%) and contributions (percentage points)","Reference month",
      [begin-.5,end+.5],limits(values,true),[...lookup.keys()],n=>lookup.get(n),
      "Monthly supply, demand and ambiguous contributions stack above or below zero. A line shows the official annual inflation rate.");
    const barWidth=Math.max(.35,graph.x(begin+.46)-graph.x(begin-.46));
    let path="",previous=null;
    rows.forEach((r,i)=>{
      const m=monthIds[i],x=graph.x(m);let positive=0,negative=0;
      if(componentKeys.every(k=>Number.isFinite(r[k]))){
        for(const k of componentKeys){
          const v=r[k],prev=v<0?negative:positive;
          const next=prev+v;
          if(v<0)negative=next;else positive=next;
          graph.layer.append(svg("rect",{x:x-barWidth/2,y:Math.min(graph.y(prev),graph.y(next)),
            width:barWidth,height:Math.abs(graph.y(prev)-graph.y(next)),fill:componentColors[k]}));
        }
      }
      if(Number.isFinite(r.pce)){
        path+=(previous===m-1?"L":"M")+x.toFixed(2)+" "+graph.y(r.pce).toFixed(2)+" ";previous=m;
      }else previous=null;
    });
    graph.layer.append(svg("path",{d:path,fill:"none",stroke:"#20342b","stroke-width":4}),
      svg("path",{d:path,fill:"none",stroke:ink.white,"stroke-width":2.3}));
    const cursor=svg("line",{y1:graph.top,y2:graph.bottom,stroke:ink.white,opacity:.8,"stroke-dasharray":"3 4"});
    graph.layer.append(cursor);
    graph.f.append(legend([...componentKeys.map(k=>[componentLabels[k],componentColors[k]]),["Reported PCE inflation",ink.white]]));
    monthReadout(graph.f,rows,r=>[
      r.month,"PCE "+nfmt(r.pce)+"%",...componentKeys.map(k=>componentLabels[k]+" "+signed(r[k])+" pp")
    ].join(" · "),r=>{
      const x=graph.x(monthNumber(r.month));cursor.setAttribute("x1",x);cursor.setAttribute("x2",x);
    });
    return graph.f;
  }

  function composition(d){
    const root=el("div");
    const measure=pick("measure",d.panels,"headline"),panel=d.panels.find(p=>p.id===measure);
    const preferred=panel.periods.find(p=>p.id==="reopening")||panel.periods.find(p=>p.start.startsWith("2021")||p.start.startsWith("2020"))||panel.periods[0];
    const episode=pick("episode",panel.periods,preferred.id),p=panel.periods.find(p=>p.id===episode);
    const rows=panel.rows.filter(r=>r.month>=p.start&&r.month<=p.end);
    root.append(el("h2","Which prices drove US inflation?"),
      el("p","Track the supply, demand and ambiguous components of twelve-month US personal consumption expenditures inflation. Compare what moved most during an episode and which components subsequently reversed.","es-intro"));
    addInputs(root,select("measure","Price measure",d.panels,measure),select("episode","Episode",panel.periods,episode));
    if(!rows.length)return root;
    const last=rows.at(-1),first=rows[0];
    const max=componentKeys.reduce((a,b)=>Math.abs(p.change[b])>Math.abs(p.change[a])?b:a);
    root.append(resultPair(componentPlot(panel,rows),summaryFacts("Change across the episode",[
      ["Period",first.month+" to "+last.month],["PCE inflation",signed(p.change.pce)+" pp"],
      ["Largest component change",componentLabels[max]+" · "+signed(p.change[max])+" pp"],
      ["Monthly observations",String(p.n)]
    ],"A contribution is measured in percentage points of annual inflation. Its change shows how much it added to the rise or fall between the two endpoints.")));
    root.append(el("h3","Decomposing the change"),table("US PCE inflation and classified contributions",["Measure",first.month,last.month,"Change (pp)","Period average"],
      [["PCE inflation (%)","pce"],["Supply contribution (pp)","supply"],["Demand contribution (pp)","demand"],["Ambiguous contribution (pp)","ambiguous"],["Sum of contributions (pp)","total"],["PCE less component sum (pp)","residual"]].map(([label,key])=>
        [label,nfmt(p.first[key]),nfmt(p.last[key]),signed(p.change[key]),nfmt(p.mean[key])])));
    root.append(el("p","In this period, demand’s contribution moved "+signed(p.change.demand)+" percentage points and supply’s moved "+signed(p.change.supply)+". The ambiguous component moved "+signed(p.change.ambiguous)+" points. The residual captures the difference between the component sum and the separately calculated official rate.","es-note"));
    const referenceRows=(panel.anchors||[]).map(anchor=>{
      const observation=panel.rows.find(r=>r.month===anchor.month);
      return observation?[anchor.label,anchor.month,nfmt(observation.pce),signed(observation.demand),signed(observation.supply),signed(observation.ambiguous)]:null;
    }).filter(Boolean);
    if(panel.accounting){
      const a=panel.accounting;
      root.append(el("p","Across "+panel.rows.length+" months, the mean absolute accounting gap is "+nfmt(a.meanAbsoluteGap,3)+" percentage points. The largest absolute gap occurs in "+a.maxGapMonth+" ("+signed(a.signedGapAtMax,3)+" points). The ambiguous category is already included in the component sum.","es-note"));
    }
    if(referenceRows.length)root.append(details("Selected observations across cycles",table("Inflation composition on selected dates",["Episode","Month","PCE (%)","Demand (pp)","Supply (pp)","Ambiguous (pp)"],referenceRows)));
    if(panel.findings?.length)root.append(el("h3","What changed across cycles?"),...sentences(panel.findings));
    root.append(details("How the categories are estimated",...sentences(d.methods),sources(d.sources)));
    return root;
  }

  function panelId(p){return p.bank+"-"+p.window;}
  function eligible(e,period){
    switch(period){
      case "pre2009":return e.date<"2009-01-01";
      case "post2008":return e.date>="2009-01-01";
      case "exPandemic":return e.date<"2020-03-01"||e.date>="2022-01-01";
      case "matchedDates":return e.matchedDate;
      default:return true;
    }
  }
  function classify(row,cut){
    if(!Number.isFinite(row.rate)||!Number.isFinite(row.equity))return "missing";
    if(Math.abs(row.rate)<cut.rateBp||Math.abs(row.equity)<cut.equityPct)return "near";
    return Math.sign(row.rate)===Math.sign(row.equity)?"same":"opposite";
  }
  function scatter(panel,rows,cut){
    const priced=rows.filter(e=>classify(e,cut)!=="missing");
    if(!priced.length)return el("p","No event in this selection has both market observations.");
    const xs=limits([...priced.map(e=>e.rate),cut.rateBp,-cut.rateBp],true);
    const ys=limits([...priced.map(e=>e.equity),cut.equityPct,-cut.equityPct],true);
    const g=plot("Short yields and equities in the same window",panel.equityLabel+" change (%)",
      panel.rateLabel+" change (bp)",xs,ys,ticks(...xs,5),v=>nfmt(v,Number.isInteger(v)?0:1),
      "Each observation pairs a short yield and an equity return around the same central bank release. Colours distinguish same-sign, opposite-sign and below-threshold cases.");
    const shade="#d7decc";
    const xL=g.x(-cut.rateBp),xR=g.x(cut.rateBp),yT=g.y(cut.equityPct),yB=g.y(-cut.equityPct);
    g.layer.append(svg("rect",{x:xL,y:g.top,width:xR-xL,height:g.bottom-g.top,fill:shade,opacity:.12}),
      svg("rect",{x:g.left,y:yT,width:g.right-g.left,height:yB-yT,fill:shade,opacity:.12}));
    for(const x of [xL,xR])g.layer.append(svg("line",{x1:x,x2:x,y1:g.top,y2:g.bottom,stroke:shade,opacity:.6,"stroke-dasharray":"2 4"}));
    for(const y of [yT,yB])g.layer.append(svg("line",{y1:y,y2:y,x1:g.left,x2:g.right,stroke:shade,opacity:.6,"stroke-dasharray":"2 4"}));
    g.layer.append(svg("line",{x1:g.x(0),x2:g.x(0),y1:g.top,y2:g.bottom,class:"es-zero"}));
    const colors={same:ink.gold,opposite:ink.blue,near:"#bfc6b7"};
    for(const group of ["near","same","opposite"]){
      for(const r of priced.filter(e=>classify(e,cut)===group)){
        const point=svg("circle",{cx:g.x(r.rate),cy:g.y(r.equity),r:group==="near"?2.8:3.6,fill:colors[group],opacity:group==="near"?.54:.77});
        const title=svg("title",{});title.textContent=r.date+" · "+signed(r.rate)+" bp · "+signed(r.equity)+"%";point.append(title);g.layer.append(point);
      }
    }
    g.f.append(legend([["Opposite signs",colors.opposite],["Same sign",colors.same],["Below cutoff",colors.near]]));
    return g.f;
  }
  function signals(d){
    const root=el("div");
    const panels=d.panels.map(p=>({id:panelId(p),label:p.label}));
    const sid=pick("release",panels,"fed-statement"),pid=pick("period",d.periods,"all"),
      tid=pick("cutoff",d.thresholds,"base"),aid=pick("outcome",d.outcomes,"fx");
    const panel=d.panels.find(p=>panelId(p)===sid),cut=d.thresholds.find(t=>t.id===tid),
      asset=d.outcomes.find(o=>o.id===aid),p=d.periods.find(x=>x.id===pid);
    const cell=panel.cells.find(c=>c.period===pid&&c.threshold===tid),rows=panel.events.filter(e=>eligible(e,pid));
    const localFX=panel.bank==="fed"?"US dollar against the euro":"Euro against the US dollar";
    const instruments=d.outcomes.map(o=>({id:o.id,label:o.id==="fx"?localFX:o.label}));
    root.append(el("h2","Does a rate move tell the same story as equities?"),
      el("p","A rise in short yields can accompany falling shares as discount rates rise, or rising shares as growth expectations improve. Compare how currencies and long bonds behaved in those two sets of policy announcements.","es-intro"));
    addInputs(root,select("release","Institution and window",panels,sid),select("cutoff","Minimum moves",d.thresholds,tid),
      select("period","Sample",d.periods,pid),select("outcome","Secondary instrument",instruments,aid));
    root.append(el("p",panel.windowDefinition,"es-sub"));
    if(!cell){root.append(el("p","No events match this selection."));return root;}
    const counts=cell.counts,measure=cell.outcomes[aid],total=counts.opposite+counts.same;
    root.append(resultPair(scatter(panel,rows,cut),summaryFacts("Observed combinations",[
      ["Opposite bond-yield and equity signs",counts.opposite+" events"],
      ["Same sign",counts.same+" events"],["Below either cutoff",String(counts.near)],["Missing a defining price",String(counts.missing)]
    ],total+" of "+cell.n+" eligible events meet both move thresholds. A common sign can be consistent with outlook news. Prices alone cannot identify the underlying shock.")));
    const digits=aid==="fx"?3:2,unit=asset.unit,gapUnit=aid==="fx"?"percentage points":"bp";
    const oriented=aid==="fx"?"A positive value means the local currency strengthened when short yields rose or weakened when yields fell.":"A positive value means ten-year yields moved in the same direction as short yields.";
    root.append(el("h3",(aid==="fx"?localFX:asset.label)+" across signal groups"),el("p",oriented+" The difference compares opposite-sign events with same-sign events in "+p.label.toLowerCase()+"."),
      table("Direction-adjusted market responses",["Group","Events with outcome","Median ("+unit+")"],[
        ["Opposite signs",measure.opposite.n,nfmt(measure.opposite.median,digits)],["Same sign",measure.same.n,nfmt(measure.same.median,digits)]]),
      el("p","Median difference "+(Number.isFinite(measure.difference)?signed(measure.difference,digits)+" "+gapUnit:"unavailable")+
        (measure.ci95?.every(Number.isFinite)?". The 95% interval is "+nfmt(measure.ci95[0],digits)+" to "+nfmt(measure.ci95[1],digits)+" "+gapUnit+".":". The sample is too sparse for the uncertainty rule."),"es-note"));
    const thresholdRows=d.thresholds.map(t=>{
      const comparison=panel.cells.find(c=>c.period===pid&&c.threshold===t.id);
      const result=comparison.outcomes[aid];
      return [t.label,result.opposite.n,result.same.n,nfmt(result.difference,digits),
        result.ci95?.every(Number.isFinite)?nfmt(result.ci95[0],digits)+" to "+nfmt(result.ci95[1],digits):"—"];
    });
    const comparison=details("How much do the cutoffs matter?",table("Sensitivity of the median difference to cutoff choice",
      ["Minimum yield and equity moves","Opposite signs","Same sign","Gap ("+gapUnit+")","95% interval"],thresholdRows));
    root.append(comparison);
    if(pid==="all"&&tid==="base"&&panel.matchedMagnitude){
      const matched=panel.matchedMagnitude;
      const result=matched.outcomes[aid];
      if(result.nPairs)root.append(el("p","Pairing an opposite-sign event with a same-sign event from the same rate direction and historical period, with yield moves at most 1 bp apart, leaves "+result.nPairs+" pairs for this instrument. Their median paired difference is "+signed(result.medianPairedGap,digits)+" "+gapUnit+". This comparison gives each matched pair equal weight.","es-note"));
    }
    const q=cell.quadrants;
    root.append(details("The four yield and equity combinations",
      table("Counts of events meeting both cutoffs",["Short yield","Equity return","Events"],[
        ["Up","Down",q.upDown],["Down","Up",q.downUp],["Up","Up",q.upUp],["Down","Down",q.downDown]])));
    if(rows.length){
      const all=details("Individual event-window observations");
      all.addEventListener("toggle",()=>{
        if(!all.open||all.childElementCount>1)return;
        const labels={same:"Same sign",opposite:"Opposite signs",near:"Below cutoff",missing:"Missing"};
        const rowsForTable=rows.slice().reverse().map(e=>[
          anchor(e.date,"market-reactions.html?"+new URLSearchParams({bank:panel.bank,window:panel.window,date:e.date,year:e.date.slice(0,4),asset:panel.bank==="fed"?"UST2Y":"DE2Y"})),
          nfmt(e.rate),nfmt(e.equity),labels[classify(e,cut)],nfmt(e.fx,3),nfmt(e.tenYear)
        ]);
        all.append(el("p","Individual prices appear in their original market direction. A positive EUR/USD move is a stronger euro.","es-note"),
          table("Observed release-window price moves",["Date","Short yield (bp)","Equity (%)","Pattern","EUR/USD (%)","Ten-year yield (bp)"],rowsForTable));
      });root.append(all);
    }
    if(d.findings?.length)root.append(details("Full-sample findings at the 1 bp and 0.10% cutoffs",...sentences(d.findings)));
    root.append(details("Classification, uncertainty and data",...sentences(d.methods),sources(d.sources)));
    return root;
  }

  return {composition,signals};
}
