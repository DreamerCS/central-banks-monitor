"use strict";

(() => {
  const panel = document.querySelector("[data-stance-view]");
  if (!panel) return;
  const view = panel.dataset.stanceView;
  const full = view === "explorer";
  const mount = panel.querySelector("[data-stance-mount]") || panel;
  const params = new URLSearchParams(location.search);
  const isNum = Number.isFinite;
  const contrastSelections = new Map();
  const dayFormat = new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"});
  const day = value => dayFormat.format(new Date(value + "T12:00:00Z"));
  const seriesLabels = {leader:"Leadership tenure",cycle:"Business cycle",policyPhase:"Prior rate trend",sourceType:"Communication"};
  const queryKeys = {bank:"sxBank",leader:"sxLeader",cycle:"sxCycle",policyPhase:"sxPhase",sourceType:"sxWindow",date:"sxDate"};
  const selected = Object.fromEntries(Object.entries(queryKeys).map(([k,q]) => [k,params.get(q) || ""]));
  let grouping = params.get("sxGroup") || (view === "macro" ? "cycle" : "leader");
  let period = null;
  let pairData, pairBand=Number(params.get("sxBand") || 1);
  selected.pairDate=params.get("sxPairDate")||"";
  selected.priorDate=params.get("sxPriorDate")||"";
  let banks, bank, riskData, riskBank, riskByDate=new Map(), curveData, curves;
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  function link(text, href) {
    const a = el("a", text);
    a.href = href;
    return a;
  }
  function safeUrl(url) {
    if (typeof url !== "string") return "";
    try {return new URL(url).protocol === "https:" ? url : "";} catch {return "";}
  }
  function signed(x, precision = 0) {
    if (!isNum(x)) return "—";
    const text = Math.abs(x).toFixed(precision);
    return (Number(text) === 0 ? "" : x > 0 ? "+" : "−") + text;
  }
  const bp = x => isNum(x) ? signed(x,2) + " bp" : "Unavailable";
  function scoreText(n) {
    return isNum(n) ? signed(n) + " · " + (n === 0 ? "steady" : n > 0 ? "hawkish" : "dovish") : "Unscored";
  }
  function median(values) {
    if (!values.length) return null;
    const a = [...values].sort((x,y) => x-y);
    const i = Math.floor(a.length/2);
    return a.length % 2 ? a[i] : (a[i-1]+a[i])/2;
  }
  function summary(rows) {
    const numeric = rows.filter(r => isNum(r.score));
    const market = rows.filter(r => isNum(r.marketBp));
    const actions = rows.filter(r => isNum(r.actionBp));
    const large = market.filter(r => Math.abs(r.marketBp) > 1 + 1e-9);
    const paired = large.filter(r => isNum(r.score) && r.score !== 0);
    const directionalShifts = rows.filter(r => isNum(r.shift) && r.shift !== 0);
    return {n:rows.length,scored:numeric.length,hawk:numeric.filter(r => r.score>0).length,dove:numeric.filter(r => r.score<0).length,
      steady:numeric.filter(r => r.score===0).length,market:market.length,medianMarket:median(market.map(r => r.marketBp)),
      medianAbs:median(market.map(r => Math.abs(r.marketBp))),large:large.length,paired:paired.length,
      opposing:paired.filter(r => r.score*r.marketBp<0).length,actions:actions.length,hike:actions.filter(r => r.actionBp>0).length,
      held:actions.filter(r => r.actionBp===0).length,cut:actions.filter(r => r.actionBp<0).length,shifts:directionalShifts.length};
  }
  const windowLabel = t => ({release:"Decision release",conference:"Press conference",statement:"Statement",decision:"Decision",minutes:"Minutes"}[t] || t);
  function values(key,rows=bank.records) {return [...new Set(rows.map(r=>r[key]).filter(Boolean))];}
  function belongs(row, omit="") {
    if (period && (row.date.slice(0,7)<period.from || row.date.slice(0,7)>period.to)) return false;
    return Object.keys(seriesLabels).every(k => k === omit || !selected[k] || row[k] === selected[k]);
  }
  function urlFor(file, includeDate=true) {
    const q = new URLSearchParams();
    for (const [k,v] of Object.entries(selected)) if(v && (k!=="date" || includeDate)) q.set(queryKeys[k],v);
    if(grouping!=="leader") q.set("sxGroup",grouping);
    if(pairBand!==1)q.set("sxBand",String(pairBand));
    if(selected.pairDate)q.set("sxPairDate",selected.pairDate);
    if(selected.priorDate)q.set("sxPriorDate",selected.priorDate);
    if(period) {q.set("sxFrom",period.from);q.set("sxTo",period.to);}
    return file+"?"+q+(file==="stance-history.html" ? "" : "#stance-periods");
  }
  function storeSelection() {
    if (!full) return;
    const own = new URL(urlFor("stance-history.html"),location.href);
    history.replaceState(null,"",own.pathname+own.search+location.hash);
  }
  function labelled(container,text,choices,value,onChange) {
    const label=el("label",text), select=el("select");
    for(const [k,v] of choices) select.append(new Option(v,k));
    select.value=value;
    select.addEventListener("change",()=>onChange(select.value));
    label.append(select); container.append(label);
    return select;
  }
  function moveBank(id) {
    bank=banks.find(b=>b.id===id)||banks[0];selected.bank=bank.id;
    for(const key of Object.keys(seriesLabels)) selected[key]="";
    selected.date="";selected.pairDate="";selected.priorDate="";
  }
  function facts(entries) {
    const dl=el("dl",undefined,"sx-facts");
    for(const [title,value,detail] of entries) {
      const div=el("div"), dd=el("dd",value);
      if(detail) dd.append(el("small",detail));
      div.append(el("dt",title),dd);dl.append(div);
    }
    return dl;
  }
  function fraction(a,b) {return b ? a+" / "+b : "—";}
  function addFacts(target,s) {
    let items;
    if(view==="market") {
      items=[["Median window change",bp(s.medianMarket),s.market+" matched market observations"],
        ["Median absolute change",isNum(s.medianAbs)?s.medianAbs.toFixed(2)+" bp":"Unavailable","Size irrespective of direction"],
        ["Opposite directions",fraction(s.opposing,s.paired),"Directional wording and a move beyond ±1 bp"]];
    } else if(view==="policy") {
      items=[["Hikes / holds / cuts",s.hike+" / "+s.held+" / "+s.cut,s.actions+" observed decisions"],
        ["Hawkish / dovish wording",s.hawk+" / "+s.dove,s.scored+" scored records, including steady guidance"],
        ["Changes in wording score",String(s.shifts),targetShifts()]];
    } else {
      items=[["Meetings",String(s.n),bank.label],["Scorable guidance",fraction(s.scored,s.n),s.hawk+" hawkish · "+s.dove+" dovish · "+s.steady+" steady"],
        ["Matched market observations",String(s.market),bank.marketLabel || "See the instrument below"]];
    }
    target.append(facts(items));
    function targetShifts() {return "Among "+bank.records.filter(r=>belongs(r)&&isNum(r.shift)).length+" scored comparisons";}
  }
  function distribution(target,s) {
    const list=el("ul",undefined,"sx-dist");
    list.setAttribute("aria-label","Number of records by guidance direction");
    for(const [name,n,c] of [["Hawkish",s.hawk,"#935635"],["Steady",s.steady,"#868975"],["Dovish",s.dove,"#367061"],["Unscored",s.n-s.scored,"#9c9a8b"]]) {
      const li=el("li"), track=el("span",undefined,"sx-track"),fill=el("i");
      track.setAttribute("aria-hidden","true");fill.style.setProperty("--p",(s.n?100*n/s.n:0)+"%");fill.style.setProperty("--c",c);
      track.append(fill);li.append(el("span",name),el("strong",String(n)),track);list.append(li);
    }
    target.append(list);
  }
  function cohortTable(container) {
    const base=bank.records.filter(r=>belongs(r,grouping));
    const cohortValues=values(grouping,base);
    const table=el("table",undefined,"sx-table");
    table.append(el("caption","Each row applies the other selected filters. Counts include unscored records. Select a row to read its meetings."));
    const thead=el("thead"), header=el("tr");
    const headings=view==="policy" ? [seriesLabels[grouping],"Meetings","Hawkish / dovish","Hikes / holds / cuts","Scored"]
      : [seriesLabels[grouping],"Meetings","Hawkish / dovish","Median change","Market n","Opposite / paired"];
    for(const text of headings) {const th=el("th",text);th.scope="col";header.append(th);}
    thead.append(header);table.append(thead);
    const tbody=el("tbody");
    for(const value of cohortValues) {
      const rows=base.filter(r=>r[grouping]===value);const s=summary(rows);
      const tr=el("tr"), rowHead=el("th"),btn=el("button",value);
      rowHead.scope="row";btn.type="button";btn.setAttribute("aria-pressed",String(selected[grouping]===value));
      if(selected[grouping]===value) btn.className="sx-current";
      btn.addEventListener("click",()=>{selected[grouping]=selected[grouping]===value?"":value;selected.date="";render(grouping);});
      rowHead.append(btn);tr.append(rowHead);
      const numbers=view==="policy" ? [s.n,s.hawk+" / "+s.dove,s.hike+" / "+s.held+" / "+s.cut,s.scored]
        : [s.n,s.hawk+" / "+s.dove,bp(s.medianMarket),s.market,fraction(s.opposing,s.paired)];
      for(const n of numbers)tr.append(el("td",String(n)));
      tbody.append(tr);
    }
    table.append(tbody);
    const wrap=el("div",undefined,"sx-tablewrap");wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-label","Cohort comparison table");
    wrap.append(table);container.append(wrap);
    const notes=view==="policy"?"Hikes, holds and cuts use recorded rate decisions. The wording score uses the communication text.":
      "Opposite / paired counts disagreeing signs among directional texts with absolute repricing above 1 bp. A small group can have a median driven by a single meeting.";
    container.append(el("p",notes,"sx-foot"));
  }
  function compareTwo(container) {
    const rows=bank.records.filter(r=>belongs(r,grouping));
    const labels=values(grouping,rows);
    if(labels.length<2)return;
    const key=bank.id+"|"+grouping;
    const saved=contrastSelections.get(key)||[];
    let first=labels.includes(saved[0])?saved[0]:labels[0];
    let second=labels.includes(saved[1])&&saved[1]!==first?saved[1]:labels.filter(x=>x!==first).at(-1);
    const box=el("section",undefined,"sx-divider");
    box.append(el("h3","Compare two groups"),el("p","Both groups use the selected bank, dates and other filters.","sx-foot"));
    const controls=el("div",undefined,"sx-controls"), result=el("div");
    const options=labels.map(v=>[v,v]);
    const a=labelled(controls,"First group",options,first,v=>{if(v===second)second=first;first=v;draw();});
    const b=labelled(controls,"Second group",options,second,v=>{if(v===first)first=second;second=v;draw();});
    function draw() {
      a.value=first;b.value=second;contrastSelections.set(key,[first,second]);
      const one=summary(rows.filter(r=>r[grouping]===first)),two=summary(rows.filter(r=>r[grouping]===second));
      const p=x=>x.scored?100*x.hawk/x.scored:null;
      const rate=x=>x.scored?(100*x.hawk/x.scored).toFixed(1)+"% ("+x.hawk+"/"+x.scored+")":"Unavailable";
      const pp=isNum(p(one))&&isNum(p(two))?signed(p(two)-p(one),1)+" pp":"Unavailable";
      const medianText=x=>isNum(x.medianAbs)?x.medianAbs.toFixed(2)+" bp (n="+x.market+")":"Unavailable";
      const head=el("p","Second minus first · hawkish share among scored texts "+pp+".");
      const l1=el("p",first+" · "+rate(one)+" hawkish. Median absolute market move "+medianText(one)+".","sx-foot");
      const l2=el("p",second+" · "+rate(two)+" hawkish. Median absolute market move "+medianText(two)+".","sx-foot");
      result.replaceChildren(head,l1,l2);
      if(Math.min(one.scored,two.scored)<10||Math.min(one.market,two.market)<10)result.append(el("p","At least one group has fewer than ten scored texts or market observations. Read the individual dates before interpreting this difference.","sx-foot"));
    }
    box.append(controls,result);container.append(box);draw();
  }
  function cycleCheck(container) {
    const windows=bank.cycleComparison?.windows||[];
    if(!windows.length) return;
    const box=el("details",undefined,"sx-source");
    if(view==="macro")box.open=true;
    box.append(el("summary","Does the contraction comparison change on rate holds?"),
      el("p","Bank-wide samples use the full dated history. Compare median absolute market moves during and outside contractions, then retain only meetings where the policy rate was held. The two samples can differ in composition.","sx-foot"));
    for(const w of windows) {
      box.append(el("h4",(w.marketInstrument||bank.marketLabel)+" · "+windowLabel(w.sourceType||"")));
      for(const [label,stat] of [["All dated meetings",w.all],["Unchanged policy rate",w.hold]]) {
        if(!stat)continue;
        const abs=x=>isNum(x)?x.toFixed(2)+" bp":"unavailable";
        box.append(el("p",label+" · contraction "+abs(stat.contractionMedianAbsBp)+" (n="+stat.contractionN+"), outside "+abs(stat.outsideMedianAbsBp)+" (n="+stat.outsideN+"). Difference "+bp(stat.gapBp)+".","sx-foot"));
      }
    }
    container.append(box);
  }
  function twoWindowComparison(container) {
    const bankPairs=pairData?.banks?.find(item=>item.id===bank.id);
    const section=el("section",undefined,"sx-divider sx-window-study");
    section.id="stance-window-pairs";
    section.append(el("h3","Did the press conference reinforce or reverse the decision?"));
    if(!bankPairs) {
      section.append(el("p","Paired one-year OIS observations are unavailable for this selection.","sx-foot"));
      container.append(section);return;
    }
    const mainByDate=new Map(bank.records.map(r=>[r.date,r]));
    const subset=bankPairs.records.filter(r=> {
      const original=mainByDate.get(r.date);
      if(selected.leader&&selected.leader!==r.leader || selected.cycle&&selected.cycle!==r.cycle)return false;
      if(selected.policyPhase&&original?.policyPhase!==selected.policyPhase)return false;
      if(period&&(r.date.slice(0,7)<period.from||r.date.slice(0,7)>period.to))return false;
      return isNum(r.releaseBp)&&isNum(r.conferenceBp);
    }).sort((a,b)=>a.date.localeCompare(b.date));
    const tenor=(bankPairs.currency||({fed:"USD",ecb:"EUR"}[bank.id]))+" one-year OIS";
    section.append(el("p",tenor+" measures the same maturity in both windows. Each meeting contributes a rate-release observation and a later press-conference observation. Bank, leadership, cycle and prior-trend filters apply to the paired sample.","sx-foot"));
    const controls=el("div",undefined,"sx-controls"), result=el("div"), recordBox=el("div");
    const bands=bankPairs.thresholds||pairData.thresholds||[0.5,1,2];
    if(!bands.includes(pairBand))pairBand=1;
    labelled(controls,"Minimum absolute move in both windows",bands.map(v=>[String(v),"Above "+v+" bp"]),String(pairBand),v=>{
      pairBand=Number(v);showCounts();showRecord();storeSelection();updateLinks();
    });
    section.append(controls,result,recordBox);
    const more=el("details",undefined,"sx-source");more.append(el("summary","Observation windows and sources"));
    for(const item of [bankPairs.releaseWindow,bankPairs.conferenceWindow,bankPairs.windowNote]) {
      if(typeof item==="string"&&item)more.append(el("p",item,"sx-foot"));
    }
    more.append(el("p","The two windows can omit intervening trading. Their sum counts the net change across the measured legs. A separately measured combined-window change can differ. Window lengths differ, and other information may move rates during either interval.","sx-foot"));
    const sources=el("div",undefined,"sx-links");
    sources.append(link("Paired meetings and source definitions (JSON)","data/stance-window-pairs.json"));
    const feed=pairData.sources?.find(s=>String(s.label).includes(bank.id==="fed"?"USMPD":"EA-MPD"));
    const marketSource=bankPairs.sourceUrl || feed?.url || bank.marketUrl;
    if(safeUrl(marketSource))sources.append(link(bank.id==="fed"?"USMPD source and windows":"EA-MPD data and windows",marketSource));
    more.append(sources);section.append(more);
    const isLarge=(x)=>Math.abs(x)>pairBand+1e-9;
    const isPaired=r=>isLarge(r.releaseBp)&&isLarge(r.conferenceBp);
    const opposed=r=>r.releaseBp*r.conferenceBp<0;
    const overturned=r=>opposed(r)&&Math.abs(r.conferenceBp)>Math.abs(r.releaseBp)+1e-9;
    function showCounts(){
      const eligible=subset.filter(isPaired), opposite=eligible.filter(opposed), reversed=opposite.filter(overturned);
      result.replaceChildren(facts([["Both legs beyond ±"+pairBand+" bp",fraction(eligible.length,subset.length),"Of matched meetings"],
        ["Opposite / same sign",opposite.length+" / "+(eligible.length-opposite.length),eligible.length+" qualifying pairs"],
        ["Fully reversed",fraction(reversed.length,opposite.length),"Of opposing pairs where the conference crosses the initial level"]]));
    }
    function showRecord(){
      recordBox.replaceChildren();
      if(!subset.length){recordBox.append(el("p","No paired quotes match this period.","sx-foot"));return;}
      const preferred=bank.id==="fed"?"2022-11-02":"2024-12-12";
      const r=subset.find(r=>r.date===selected.pairDate)||subset.find(r=>r.date===(params.get("sxDate")||params.get("date")))||
        subset.find(r=>r.date===preferred)||[...subset].reverse().find(r=>isPaired(r)&&overturned(r))||subset.at(-1);
      selected.pairDate=r.date;
      const controller=el("div",undefined,"sx-controls"), card=el("div",undefined,"sx-reading");
      labelled(controller,"Read a paired meeting",[...subset].reverse().map(x=>[x.date,day(x.date)+" · "+x.leader]),r.date,v=>{
        selected.pairDate=v;showRecord();storeSelection();updateLinks();
      });
      const left=el("div"), right=el("div"),dl=el("dl");
      const label=!isPaired(r)?"At least one leg falls within the selected band.":overturned(r)?"The press conference fully reversed the release move.":opposed(r)?"The press conference offset the release without crossing the initial level.":"Both windows moved in the same direction.";
      left.append(el("h4",day(r.date)+" · "+r.leader),el("p",label),el("p",r.cycle+" · "+scoreText(r.score),"sx-foot"));
      const links=el("div",undefined,"sx-links");
      if(safeUrl(r.sourceUrl))links.append(link("Official communication",r.sourceUrl));
      if(r.compareUrl && (safeUrl(r.compareUrl)||/^[a-z][a-z0-9-]*\.html(?:[?#]|$)/.test(r.compareUrl)))links.append(link("Meeting detail",r.compareUrl));
      left.append(links);
      for(const [label,reading] of [["Rate release",r.releaseBp],["Press conference",r.conferenceBp],["Sum of measured legs",r.totalBp],["Combined window",r.combinedWindowBp]])
        dl.append(el("dt",label),el("dd",bp(reading)));
      right.append(dl);
      const o=mainByDate.get(r.date);
      const times=bank.id==="fed"?"Fed release −10 to +20 minutes. Conference −10 to +60 minutes around its own start.":[o?.releaseReading?.marketWindow&&"Release "+o.releaseReading.marketWindow,o?.marketWindow&&"Conference "+o.marketWindow].filter(Boolean).join(". ");
      if(times)right.append(el("p",times,"sx-foot"));
      card.append(left,right);recordBox.append(controller,card);
    }
    showCounts();showRecord();container.append(section);
  }
  function pairedWindows(container) {
    const w=bank.pairedWindows?.all;
    if(!w?.n)return;
    const box=el("details",undefined,"sx-source");
    box.open=view==="market";
    box.append(el("summary","Which ECB window moved one-year OIS more?"),
      el("p","Across the same "+w.n+" meetings, the median absolute move was "+w.releaseMedianAbsBp.toFixed(2)+" bp at the rate release and "+w.conferenceMedianAbsBp.toFixed(2)+" bp during the press conference. The conference move was larger at "+w.conferenceLarger+" meetings. The release move was larger at "+w.releaseLarger+". The conference window is longer.","sx-foot"));
    const part=bank.pairedWindows.byLeader?.find(i=>i.label===selected.leader)||bank.pairedWindows.byCycle?.find(i=>i.label===selected.cycle);
    if(part?.n)box.append(el("p",part.label+" · "+part.n+" paired meetings. Median absolute release move "+part.releaseMedianAbsBp.toFixed(2)+" bp, conference move "+part.conferenceMedianAbsBp.toFixed(2)+" bp.","sx-foot"));
    box.append(link("EA-MPD observations",bank.marketUrl));container.append(box);
  }
  function riskComparison(container,rows) {
    if(!riskBank)return;
    const groupBySignal=new Map();
    let unscored=0, identified=0, directional=0;
    const oneSided=new Set(["Inflation upside","Inflation downside","Growth downside","Employment downside","Unduly low inflation"]);
    for(const r of rows) {
      if(!isNum(r.score))unscored++;
      const risk=riskByDate.get(r.date);
      if(!risk?.signal)continue;
      const counts=groupBySignal.get(risk.signal)||{all:0,noScore:0};
      counts.all++;
      if(!isNum(r.score)) {
        counts.noScore++;identified++;
        if(oneSided.has(risk.signal))directional++;
      }
      groupBySignal.set(risk.signal,counts);
    }
    const box=el("details",undefined,"sx-source");
    if(view==="policy")box.open=true;
    box.append(el("summary",riskBank.label+" where rate guidance was absent"));
    box.append(el("p","Of "+unscored+" meetings without a forward-rate score in this selection, "+identified+
      " had an explicit risk assessment. "+directional+" identified a one-sided inflation, employment or growth risk. The risk tally is separate from the rate-guidance score.","sx-foot"));
    if(groupBySignal.size) {
      const wrap=el("div",undefined,"sx-tablewrap"),t=el("table",undefined,"sx-table");
      wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-label","Explicit risk readings by type");
      t.append(el("caption","Each label preserves the economic risk described by the committee."));
      const thead=el("thead"),h=el("tr");
      for(const label of ["Published risk assessment","Meetings","Without a forward-rate score"]){const th=el("th",label);th.scope="col";h.append(th);}
      thead.append(h);t.append(thead);const body=el("tbody");
      for(const [label,counts] of [...groupBySignal].sort((a,b)=>b[1].all-a[1].all||a[0].localeCompare(b[0]))) {
        const tr=el("tr"),th=el("th",label);th.scope="row";tr.append(th,el("td",String(counts.all)),el("td",String(counts.noScore)));body.append(tr);
      }
      t.append(body);wrap.append(t);box.append(wrap);
    }
    if(typeof riskBank.scope==="string")box.append(el("p",riskBank.scope,"sx-foot"));
    box.append(link("Download dates, labels and underlying passages","data/stance-risk-signals.json"));
    container.append(box);
  }
  function isProxy(r) {
    return r.priorIsProxy===true || r.priorSourceKind==="digitised-figure" || r.priorQuoteQualifier==="proxy";
  }
  function matchedGap(r) {
    return !isProxy(r) && r.priorGapEligible!==false && isNum(r.pricingGapBp) ? r.pricingGapBp : null;
  }
  function pricingCoverage(container,rows) {
    const priors=rows.filter(r=>isNum(r.priorMoveBp));
    const gaps=priors.filter(r=>isNum(matchedGap(r)));
    const evidence=rows.filter(r=>isNum(r.priorMoveBp)||r.priorQuoteQualifier||r.priorPricingNote);
    const section=el("section",undefined,"sx-divider sx-prior-comparison");
    section.append(el("h3","What was priced for the decision?"),
      el("p",priors.length+" of "+rows.length+" selected meetings have a numeric pre-decision expectation. "+gaps.length+
        " have a comparable announced policy move and a measured or reconstructed gap.","sx-foot"));
    if(bank.id==="ecb" && priors.length) {
      const proxies=priors.filter(isProxy).length;
      section.append(el("p",(priors.length-proxies)+" published numeric expectations · "+proxies+" estimates digitised from market charts. Each row states which rate was priced. Approximate MRO readings are excluded from the deposit-rate gap.","sx-foot"));
    }
    if(gaps.length) {
      const tighter=gaps.filter(r=>r.pricingGapBp>1+1e-9).length,easier=gaps.filter(r=>r.pricingGapBp< -1-1e-9).length;
      section.append(el("p","Among the "+gaps.length+" comparable decisions, "+tighter+" delivered more tightening than priced, "+easier+" delivered more easing, and "+(gaps.length-tighter-easier)+" were within ±1 bp. Median absolute gap "+median(gaps.map(r=>Math.abs(r.pricingGapBp))).toFixed(2)+" bp.","sx-foot"));
    }
    if(evidence.length>priors.length)section.append(el("p",(evidence.length-priors.length)+" additional meetings have a reported pricing condition or outcome without a usable point estimate.","sx-foot"));
    if(!evidence.length) {container.append(section);return;}
    section.append(el("p",bank.id==="fed"?"The Fed prior is reconstructed from the announced target move and the published current-meeting futures surprise. Its timestamp describes the event window. The prior has no separately observed quote.":
      "Each ECB observation names the meeting, rate, source and timing. Quoted bounds and outcome probabilities retain the source qualifier. Estimates read from research figures carry their own method and precision. A gap requires comparable policy rates. One-year OIS repricing appears separately.","sx-foot"));
    const controls=el("div",undefined,"sx-controls"), output=el("div");
    const preferred=bank.id==="fed"?"2022-11-02":"2023-06-15";
    const record=evidence.find(r=>r.date===selected.priorDate)||evidence.find(r=>r.date===(params.get("sxDate")||params.get("date")))||
      evidence.find(r=>r.date===preferred)||priors.at(-1)||evidence.at(-1);
    labelled(controls,"Meeting with pre-decision pricing evidence",[...evidence].reverse().map(r=>[r.date,day(r.date)+" · "+r.leader+(isProxy(r)?" · chart estimate":"")]),record.date,v=>{
      draw(evidence.find(r=>r.date===v));storeSelection();updateLinks();
    });
    function draw(r) {
      if(!r)return;
      selected.priorDate=r.date;output.replaceChildren();
      const wrap=el("div",undefined,"sx-tablewrap"),table=el("table",undefined,"sx-table");
      wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-label","Prior expectation and realised policy action");
      table.append(el("caption",day(r.date)+" · "+(r.priorInstrument || (bank.id==="fed"?"Current FOMC policy-rate change":"Current ECB policy-rate change"))));
      const head=el("thead"),labels=el("tr");
      for(const t of ["Before the decision","Announced on the same instrument","Actual minus before"]){const th=el("th",t);th.scope="col";labels.append(th);}
      head.append(labels);const body=el("tbody"),line=el("tr");
      line.append(el("td",priorLabel(r)),el("td",bp(isNum(matchedGap(r))?r.actionBp:null)),el("td",bp(matchedGap(r))));
      body.append(line);table.append(head,body);wrap.append(table);output.append(wrap);
      priorProvenance(output,r,true);
    }
    section.append(controls,output);draw(record);container.append(section);
  }
  function priorLabel(r) {
    if(isNum(r.priorMoveBp))return (isProxy(r)?"≈ ":"")+bp(r.priorMoveBp);
    return ({minimum:"Bound only",probability:"Outcome probability only","near-full":"Near-fully priced"})[r.priorQuoteQualifier] || "Unavailable";
  }
  function priorProvenance(box,r,links) {
    if(!isNum(r.priorMoveBp)&&!r.priorPricingNote&&!r.priorInstrument&&!r.priorPricingDate)return;
    const method=r.priorMethod || (bank.id==="fed"?"Reconstructed from the current-meeting futures surprise (MP1).":"Source-reported meeting expectation.");
    box.append(el("p",method,"sx-foot"));
    if(isProxy(r) && isNum(r.priorToleranceBp))box.append(el("p","Approximate chart reading with ±"+r.priorToleranceBp+" bp digitisation tolerance. This tolerance covers the reading of the figure alone. The relation between the swap rate and the policy move introduces further uncertainty.","sx-foot"));
    if(r.priorPricingDate)box.append(el("p","Observation timing · "+r.priorPricingDate,"sx-foot"));
    if(r.priorPricingNote)box.append(el("p",r.priorPricingNote,"sx-foot"));
    if(isNum(r.earlierPriorMoveBp)&&isNum(r.priorMoveBp)) {
      const timeline=el("p",undefined,"sx-foot");
      timeline.append(el("strong","Change before the decision · "),document.createTextNode(bp(r.earlierPriorMoveBp)+" on "+r.earlierPriorDate+" → "+bp(r.priorMoveBp)+
        " in the later pre-meeting observation. The same meeting was repriced by "+bp(r.priorMoveBp-r.earlierPriorMoveBp)+" before the announcement."));
      if(safeUrl(r.earlierPriorSource))timeline.append(document.createTextNode(" "),link("Earlier pricing source",r.earlierPriorSource));
      box.append(timeline);
      if(r.earlierPriorPricingNote)box.append(el("p",r.earlierPriorPricingNote,"sx-foot"));
    }
    if(isNum(matchedGap(r))&&r.pricingGapMethod)box.append(el("p",r.pricingGapMethod,"sx-foot"));
    if(links) {
      const nav=el("div",undefined,"sx-links");
      if(safeUrl(r.priorPricingSource))nav.append(link("Pricing source",r.priorPricingSource));
      const actualUrl=r.releaseUrl||r.url;
      if(safeUrl(actualUrl))nav.append(link("Announced decision",actualUrl));
      if(safeUrl(r.pricingGapSource)&&r.pricingGapSource!==r.priorPricingSource&&r.pricingGapSource!==actualUrl)nav.append(link("Comparable rate or surprise series",r.pricingGapSource));
      box.append(nav);
    }
  }
  function priorCurve(box,r) {
    if(bank.id!=="ecb"||!curves)return;
    const quote=curves.get(r.date);
    if(!quote||quote.status!=="observed"||!isNum(quote.prior2yPct)||!isNum(quote.prior10yPct)) {
      const reason={"before-series":"The ECB AAA yield series begins on 6 September 2004, after this meeting.","insufficient-history":"The five-interval window lacks sufficient paired fixings.","stale":"The latest available ECB AAA fixing is too old for this pre-meeting comparison."};
      box.append(el("p",reason[quote?.status]||"An ECB AAA curve comparison is unavailable before this meeting.","sx-foot"));return;
    }
    const details=el("details",undefined,"sx-source");
    details.open=full||view==="market";
    details.append(el("summary","Euro-area AAA zero-coupon curve before the decision"));
    const wrap=el("div",undefined,"sx-tablewrap"),table=el("table",undefined,"sx-table");
    table.style.minWidth="275px";wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-label","Pre-meeting euro-area AAA yield curve");
    table.append(el("caption","Last available fixing "+day(quote.priorEnd)+". "+(quote.priorStart?"Five fixing intervals from "+day(quote.priorStart)+" to "+day(quote.priorEnd)+".":"The comparison window is unavailable.")));
    const head=el("thead"),header=el("tr");for(const t of ["Series","Prior level","Change"]){const th=el("th",t);th.scope="col";header.append(th);}head.append(header);
    const body=el("tbody");
    for(const [t,level,change] of [["2Y",quote.prior2yPct.toFixed(2)+"%",quote.change2yBp],["10Y",quote.prior10yPct.toFixed(2)+"%",quote.change10yBp],
      ["2s10s (10Y minus 2Y)",bp(quote.priorSlopeBp),quote.changeSlopeBp]]) {
      const row=el("tr"),th=el("th",t);th.scope="row";row.append(th,el("td",level),el("td",bp(change)));body.append(row);
    }
    table.append(head,body);wrap.append(table);details.append(wrap,el("p","Daily sovereign zero-coupon yields measure the broader curve. Meeting-specific policy expectations require separate pricing evidence.","sx-foot"));
    const nav=el("div",undefined,"sx-links");nav.append(link("Download pre-meeting curve observations","data/ecb-prior-curve.json"));
    const curveSource=curveData.sources?.curve;const url=typeof curveSource==="string"?curveSource:curveSource?.url;
    if(safeUrl(url))nav.append(link("ECB yield curve source",url));
    details.append(nav);box.append(details);
  }
  function bandCheck(container) {
    const windows=bank.cycleComparison?.windows?.filter(w=>w.sensitivity?.length)||[];
    if(!windows.length)return;
    const box=el("details",undefined,"sx-source");box.append(el("summary","How much does the market-move threshold matter?"),
      el("p","For each window and instrument, count only directional texts whose market move exceeds the selected band. Each fraction gives matching signs divided by the number of comparable meetings in the full bank sample.","sx-foot"));
    for(const w of windows) {
      const entries=w.sensitivity.map(r=>r.bandBp+" bp · "+fraction(r.same,r.comparable));
      box.append(el("h4",(w.marketInstrument||bank.marketLabel)+" · "+windowLabel(w.sourceType||"")),el("p",entries.join(" ··· "),"sx-foot"));
    }
    container.append(box);
  }
  function bankCoverage(container) {
    if(banks.length<2)return;
    const box=el("details",undefined,"sx-source");box.append(el("summary","Compare coverage and instruments across banks"));
    const table=el("table",undefined,"sx-table");
    table.append(el("caption","Whole-bank samples. Different tenors and communication windows measure different parts of the expected policy path."));
    const thead=el("thead"),header=el("tr");
    for(const t of ["Institution","Records","Scored","Market observations","Primary market measure"]){const th=el("th",t);th.scope="col";header.append(th);}
    thead.append(header);table.append(thead);
    const tbody=el("tbody");
    for(const item of banks) {
      const stat=summary(item.records),row=el("tr"),h=el("th",item.label);h.scope="row";row.append(h);
      for(const v of [item.records.length,stat.scored,stat.market,item.marketLabel])row.append(el("td",String(v)));tbody.append(row);
    }
    table.append(tbody);const wrap=el("div",undefined,"sx-tablewrap");wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-label","Central bank coverage");wrap.append(table);box.append(wrap);container.append(box);
  }
  function methods(container) {
    const box=el("details",undefined,"sx-source");box.append(el("summary","Definitions, coverage and sources"));
    const pieces=["The leader identifies who chaired the institution on the meeting date. The score describes the committee’s public guidance. Different tools, mandates and shocks also vary across tenures.",
      bank.cycleMethod,bank.policyPhaseMethod,bank.macroMethod,bank.marketMethod || bank.marketWindow,
      bank.id==="fed"?"For the Fed, the estimated pre-decision move equals the announced move less the current-meeting futures surprise. It assumes a stable spread between the effective rate and the target. MP2 tracks changes in the expected rate at the following meeting.":"ECB actions use the deposit facility rate. Before the floor-system era, other key rates also mattered. Each prior names its meeting, instrument, observation timing and source. Approximate rates reconstructed from charts, bounds and probability-qualified outcomes are identified on the record. The deposit-rate gap uses only comparable point readings. A one-year OIS spans several meetings.",
      "Missing wording or market observations are excluded from the corresponding statistic. The magnitude and horizon of each market series are specific to its central bank."];
    for(const item of pieces.filter(v=>typeof v==="string"&&v)) box.append(el("p",item));
    const anchors=el("div",undefined,"sx-links");
    const sourceList=[...(bank.leaderSources||[]),...(bank.cycleSources||[]),...(bank.macroSources||[]),{url:bank.policySource,label:"Policy rate series"},{url:bank.marketUrl||bank.marketSource,label:"Market series"}];
    const used=new Set();
    for(const source of sourceList) {
      const url=safeUrl(typeof source==="string" ? source : source.url);
      if(url&&!used.has(url)) {used.add(url);anchors.append(link(source.label||"Source",url));}
    }
    anchors.append(link("Download data and group statistics (JSON)","data/stance-cohorts.json"));box.append(anchors);container.append(box);
  }
  function defaultRecord(rows) {
    return rows.find(r => r.date===selected.date) || [...rows].reverse().find(r => isNum(r.score)&&r.score!==0&&isNum(r.marketBp)) ||
      [...rows].reverse().find(r=>isNum(r.score)) || rows.at(-1);
  }
  function recordCard(box,r) {
    const card=el("div",undefined,"sx-reading"), words=el("div"), measurements=el("div");
    words.append(el("h4",day(r.date)+" · "+r.leader),el("p",scoreText(r.score)));
    if(r.evidence) {
      words.append(el("h4",r.evidenceKind || (bank.id==="ecb"?"Reading of the official communication":"Statement evidence")),el("p",r.evidence));
    }
    else if(r.rationale) words.append(el("p",r.rationale));
    const risk=riskByDate.get(r.date);
    if(riskBank) {
      const detail=el("div");
      detail.append(el("h4",riskBank.label));
      if(risk?.signal) {
        detail.append(el("p",risk.signal,"sx-foot"));
        if(risk.evidence)detail.append(el("blockquote",risk.evidence));
        if(safeUrl(risk.sourceUrl))detail.append(link("Official risk passage",risk.sourceUrl));
      } else detail.append(el("p","No explicit balance identified for this meeting.","sx-foot"));
      words.append(detail);
    } else if(r.riskSignal)words.append(el("p","Risk assessment · "+r.riskSignal,"sx-foot"));
    if(r.sourceType==="conference" && r.releaseReading) {
      const rel=r.releaseReading, detail=el("details",undefined,"sx-source");
      detail.append(el("summary","Earlier release that day · "+scoreText(rel.score)));
      if(rel.evidence)detail.append(el("p",rel.evidence,"sx-foot"));
      if(rel.marketWindow)detail.append(el("p","1-year OIS "+bp(rel.marketBp)+" · "+rel.marketWindow,"sx-foot"));
      if(safeUrl(rel.sourceUrl))detail.append(link("Official decision release",rel.sourceUrl));
      words.append(detail);
    }
    if(isNum(r.shift)) words.append(el("p","Change in score "+signed(r.shift)+(r.previousDate?" since "+day(r.previousDate):"")+".","sx-foot"));
    const urls=el("div",undefined,"sx-links");
    if(safeUrl(r.url))urls.append(link("Official communication",r.url));
    if(safeUrl(r.releaseUrl)&&r.releaseUrl!==r.url)urls.append(link("Decision release",r.releaseUrl));
    if(bank.id==="fed")urls.append(link("FOMC evidence and prior pricing","policy-stance.html?date="+r.date));
    if(safeUrl(r.marketUrl||r.marketSource||bank.marketUrl))urls.append(link("Market data",r.marketUrl||r.marketSource||bank.marketUrl));
    words.append(urls);
    const dl=el("dl");
    function value(k,v){dl.append(el("dt",k),el("dd",v));}
    value(r.priorInstrument?"Before decision · "+r.priorInstrument:"Before the decision",priorLabel(r));
    value(bank.id==="ecb"?"Announced deposit facility rate change":"Announced policy-rate change",bp(r.actionBp));
    value("Actual minus before, same target",bp(matchedGap(r)));
    if(isNum(r.currentSurpriseBp)&&!isNum(r.pricingGapBp))value("Current decision futures surprise (MP1)",bp(r.currentSurpriseBp));
    value(r.marketInstrument||bank.marketLabel||"Window change",bp(r.marketBp));
    if(r.sourceType==="conference" && isNum(r.releaseMeasures?.ois1yBp))value("1-year euro OIS at earlier decision release",bp(r.releaseMeasures.ois1yBp));
    if(isNum(r.prior2yBp))value("2Y before the statement",bp(r.prior2yBp));
    if(isNum(r.prior2s10sBp))value("2s10s before the statement",bp(r.prior2s10sBp));
    if(isNum(r.marketMeasures?.de2s10sBp))value("German 2s10s in this window",bp(r.marketMeasures.de2s10sBp));
    if(isNum(r.policyChangeBp))value("Policy move over preceding 180 days",bp(r.policyChangeBp));
    measurements.append(dl,el("p",r.marketWindow||bank.marketWindow||"","sx-foot"));
    if(r.priorStart&&r.priorEnd)measurements.append(el("p","Treasury comparison · "+day(r.priorStart)+" to "+day(r.priorEnd)+", before the statement.","sx-foot"));
    priorProvenance(measurements,r,true);
    priorCurve(measurements,r);
    if(r.contextMonth && (isNum(r.inflationYoY)||isNum(r.unemploymentPct))) {
      const measures=[];
      if(isNum(r.inflationYoY))measures.push((bank.inflationLabel || (bank.id==="ecb"?"HICP":"CPI"))+" "+r.inflationYoY.toFixed(1)+"% year on year");
      if(isNum(r.unemploymentPct))measures.push("unemployment "+r.unemploymentPct.toFixed(1)+"%");
      measurements.append(el("p","Macro context for "+r.contextMonth+" · "+measures.join(" · ")+". Latest-vintage observations, measured two calendar months before the meeting.","sx-foot"));
    }
    measurements.append(el("p",r.cycle+" · "+r.policyPhase+" prior rate trend","sx-foot"));
    card.append(words,measurements);box.append(card);
  }
  function reader(container,rows) {
    if(!rows.length)return;
    const chosen=defaultRecord(rows);
    selected.date=chosen.date;
    const section=el(full?"section":"details",undefined,"sx-evidence");
    section.append(el(full?"h3":"summary",full?"Read the decision and market observation":"Read a meeting from this selection"));
    const selection=el("div",undefined,"sx-controls"), holder=el("div");
    labelled(selection,"Meeting date",[...rows].reverse().map(r=>[r.date,day(r.date)+" · "+r.leader]),chosen.date,value=>{
      const record=rows.find(r=>r.date===value);if(!record)return;selected.date=value;holder.replaceChildren();recordCard(holder,record);storeSelection();updateLinks();
    });
    section.append(selection,holder);recordCard(holder,chosen);container.append(section);
  }
  function updateLinks() {
    const block=mount.querySelector("[data-sx-crosslinks]");if(!block)return;
    block.replaceChildren();
    if(!full) {
      block.append(link("Open this selection in the full study",urlFor("stance-history.html")));
      block.append(bank.id==="ecb"?link("ECB speakers and one-year OIS","ecb-speech-stance.html"+(selected.leader?"?"+new URLSearchParams({leader:selected.leader.split(" ").at(-1)}):"")):link("Fed chairs’ speeches","fed-leader-speeches.html"+(selected.leader?"?"+new URLSearchParams({leader:selected.leader.split(" ").at(-1)}):"")));
    }
    else for(const [text,file] of [["Market reactions","market-reactions.html"],["Policy history","historical-data.html"],["Macro history","macro-history.html"]])
      block.append(link(text,urlFor(file)));
  }
  function render(focus="") {
    riskBank=riskData?.banks?.[bank.id]||null;
    riskByDate=new Map((riskBank?.records||[]).map(r=>[r.date,r]));
    mount.replaceChildren();
    const controls=el("div",undefined,"sx-controls"),selects={};
    selects.bank=labelled(controls,"Central bank",banks.map(b=>[b.id,b.label]),bank.id,v=>{
      moveBank(v);render("bank");
    });
    for(const [k,label] of Object.entries(seriesLabels)) {
      const possible=values(k);
      if(k==="sourceType" && possible.length<2)continue;
      selects[k]=labelled(controls,label,[["","All"],...possible.map(v=>[v,k==="sourceType"?windowLabel(v):v])],selected[k],v=>{
        selected[k]=v;selected.date="";render(k);
      });
    }
    if(full && banks.length>1)mount.append(el("p",banks.map(b=>b.label+" · "+b.records.length+" meetings").join("   /   "),"sx-coverage"));
    mount.append(controls);
    const rows=bank.records.filter(r=>belongs(r)).sort((a,b)=>a.date.localeCompare(b.date));
    const s=summary(rows);
    if(period) {
      const p=el("p","Historical window "+period.from+" to "+period.to+" · ","sx-coverage");
      const b=el("button","Clear date window");b.type="button";b.onclick=()=>{period=null;render("bank");};p.append(b);mount.append(p);
    }
    const coverage=el("p",rows.length?rows.length+" of "+bank.records.length+" records · "+day(rows[0].date)+" – "+day(rows.at(-1).date):"No meetings match these filters.","sx-coverage");
    coverage.setAttribute("role","status");mount.append(coverage);
    if(!rows.length) {
      const clear=el("button","Show all meetings for "+bank.label);clear.type="button";clear.onclick=()=>{moveBank(bank.id);period=null;render("bank");};mount.append(clear);
    } else {
      addFacts(mount,s);
      if(full || view==="market")pricingCoverage(mount,rows);
      const content=el("div",undefined,full?"sx-split":"");
      const primary=el("div"),secondary=el("div");
      const comparison=el(full?"section":"details",undefined,"sx-compare");
      if(!full) comparison.open=true;
      comparison.append(el(full?"h3":"summary",view==="macro"?"Compare economic phases":"Compare groups"));
      const groupPicker=el("div",undefined,"sx-controls");
      selects.group=labelled(groupPicker,"Group meetings by",["leader","cycle","policyPhase"].map(k=>[k,seriesLabels[k]]),grouping,v=>{grouping=v;render("group");});
      comparison.append(groupPicker);cohortTable(comparison);primary.append(comparison);
      if(full) {
        compareTwo(primary);
        secondary.className="sx-divider";
        secondary.append(el("h3","Guidance in this sample"));distribution(secondary,s);
        const marketName=bank.marketLabel||"Market rate";
        secondary.append(el("p",marketName+" · "+s.market+" window observations.","sx-foot"),
          el("p","Median signed change "+bp(s.medianMarket)+". "+s.large+" observations moved by more than 1 bp. Of "+s.paired+" qualifying directional texts, "+s.opposing+" moved the other way.","sx-foot"));
        if(new Set(rows.filter(r=>isNum(r.marketBp)).map(r=>r.sourceType).filter(Boolean)).size>1)
          secondary.append(el("p","This selection combines communication types. Choose a communication window to compare a single event type.","sx-foot"));
      } else {
        primary.append(el("p",bank.marketLabel+" · "+(bank.marketWindow||"See each meeting for the observation window."),"sx-foot"));
        if(view==="market"&&new Set(rows.filter(r=>isNum(r.marketBp)).map(r=>r.sourceType).filter(Boolean)).size>1)
          primary.append(el("p","The selected dates include decision releases and conferences. Use the communication filter to compare a single primary window.","sx-foot"));
      }
      content.append(primary);if(full)content.append(secondary);
      mount.append(content);reader(mount,rows);
    }
    if(full || view==="policy")riskComparison(mount,rows);
    if(full || view==="macro")cycleCheck(mount);
    if(full || view==="market") {
      twoWindowComparison(mount);pairedWindows(mount);bandCheck(mount);
    }
    if(full)bankCoverage(mount);
    methods(mount);
    const links=el("nav",undefined,"sx-links");links.dataset.sxCrosslinks="";links.setAttribute("aria-label","Related stance studies");mount.append(links);updateLinks();
    if(full) {
      const other=el("section",undefined,"sx-divider");
      other.append(el("h3","Speeches by individual policymakers"),el("p","Trace an individual speaker’s words and the pricing around the speech separately from a committee decision.","sx-foot"));
      const nav=el("div",undefined,"sx-links");
      nav.append(link("Fed chairs’ speeches","fed-leader-speeches.html"),link("ECB speeches and one-year OIS","ecb-speech-stance.html"),link("Powell at Jackson Hole","jackson-hole-stance.html"),link("Fed speeches, 16–20 November 2026","fed-speech-week.html"));other.append(nav);mount.append(other);
    }
    if(focus) {selects[focus]?.focus({preventScroll:true});storeSelection();}
  }
  async function start() {
    const [response,pairResponse,riskResponse,curveResponse]=await Promise.all([fetch("data/stance-cohorts.json"),
      (full||view==="market")?fetch("data/stance-window-pairs.json").catch(()=>null):null,
      (full||view==="policy")?fetch("data/stance-risk-signals.json").catch(()=>null):null,
      fetch("data/ecb-prior-curve.json").catch(()=>null)]);
    if(curveResponse?.ok)try{curveData=await curveResponse.json();if(Array.isArray(curveData.records))curves=new Map(curveData.records.map(r=>[r.date,r]));}catch{}
    if(riskResponse?.ok)try{riskData=await riskResponse.json();}catch{}
    if(pairResponse?.ok)try{pairData=await pairResponse.json();}catch{}
    if(!response.ok) throw Error("Cohort data unavailable");
    const data=await response.json();
    banks=data.banks.filter(b=>["fed","ecb"].includes(b.id)&&b.records?.length);
    bank=banks.find(b=>b.id===(selected.bank||params.get("bank")))||banks[0];
    selected.bank=bank.id;
    if(!selected.leader && view==="macro" && params.get("view")==="leaders") {
      const wanted=params.get("leader");
      if(wanted)selected.leader=values("leader").find(v=>v.toLowerCase().split(/\s+/).at(-1)===wanted.toLowerCase())||"";
      else selected.leader=bank.records.at(-1).leader;
    }
    const from=params.get("sxFrom"),to=params.get("sxTo");
    if(/^\d{4}-(0[1-9]|1[0-2])$/.test(from)&&/^\d{4}-(0[1-9]|1[0-2])$/.test(to)&&from<=to)period={from,to};
    else if(view==="macro" && params.get("episode")) {
      const response=await fetch("data/history-episodes.json");if(response.ok) {
        const episodes=await response.json();
        const ep=episodes.find(e=>e.id===params.get("episode"));
        if(ep && (!ep.geography || ep.geography==="United States"))period={from:ep.start,to:ep.end};
      }
    }
    for(const k of Object.keys(seriesLabels)) if(!values(k).includes(selected[k]))selected[k]="";
    if(!selected.date && (full || view==="market")) selected.date=params.get("date")||"";
    if(!["leader","cycle","policyPhase"].includes(grouping))grouping="leader";
    render();
  }
  start().catch(()=>{mount.replaceChildren(el("p","The meeting comparisons could not be loaded. "),link("Open the data file","data/stance-cohorts.json"));});
})();
