const eraLabels = {"2000-07":"2000–2007", "2008-15":"2008–2015", "2016-19":"2016–2019", "2020-on":"2020 onwards"};
const dateFormat = new Intl.DateTimeFormat("en-GB",{year:"numeric",month:"short",day:"numeric",timeZone:"UTC"});
const numberFormat = new Intl.NumberFormat("en-GB",{maximumFractionDigits:3});
const dateText = day => dateFormat.format(new Date(day+"T12:00:00Z"));
const move = n => (n>0?"+":n<0?"−":"")+numberFormat.format(Math.abs(n))+" bp";
const pct = n => n.toFixed(1)+"%";

function chooseRows(rows,era,size,rule) {
  return rows.filter(row=>{
    const y=Number(row.date.slice(0,4));
    const bucket=y<2008?"2000-07":y<2016?"2008-15":y<2020?"2016-19":"2020-on";
    if(era!=="all" && era!==bucket) return false;
    const prior=Math.abs(row.priorBp);
    if ((size==="small" && prior>=10) || (size==="large" && prior<10)) return false;
    return rule!=="one-bp" || (prior>=1 && Math.abs(row.statementBp)>=1);
  });
}

function td(tag,value,scope) {
  const node=document.createElement(tag);
  node.textContent=value;
  if(scope) node.scope=scope;
  return node;
}

function renderMatrix(host,s) {
  host.replaceChildren(...s.matrix.map((entries,i)=>{
    const row=document.createElement("tr");
    row.append(td("th",["Yield rose","Yield fell","Unchanged"][i],"row"));
    for (const [j,value] of entries.entries()) {
      const cell=td("td",value);
      if(i<2 && j<2) cell.className=i===j?"fd-same":"fd-opposite";
      row.append(cell);
    }
    return row;
  }));
}

function makeLink(text,href) {
  const link=td("a",text);
  link.href=href;
  return link;
}

function showSpeech(host,cases) {
  if(!cases.length) {host.textContent="There is no separately documented two-year speech observation in the loaded source series.";return;}
  host.replaceChildren();
  for(const item of cases) {
    const text=item.speaker+" · "+dateText(item.date)+". The daily two-year yield moved "+move(item.priorBp)+
      " from "+dateText(item.start)+" to "+dateText(item.end)+". The speech-window change was "+move(item.speechBp)+
      " over "+item.window+" New York time. This shorter window is excluded from the statement counts. ";
    host.append(document.createTextNode(text),makeLink("Speech text",item.eventUrl), document.createTextNode(" · "),makeLink("Published observation · "+item.locator,item.study));
  }
}

async function initDirectionStudy() {
  if(!document.getElementById("fed-direction-study"))return;
  const el=name=>document.getElementById("fd-"+name);
  try {
    const response=await fetch("data/fed-direction-study.json");
    if(!response.ok) throw new Error("Unavailable");
    const data=await response.json();
    const rows=data.rows.map(values=>Object.fromEntries(data.fields.map((key,i)=>[key,values[i]])));
    const era=el("era"),size=el("size"),rule=el("rule"),picker=el("event");
    const params=new URLSearchParams(location.search);
    const deepLink=params.get("directionDate");
    let selectedDay=rows.some(r=>r.date===deepLink)?deepLink:null;
    let visible=[];
    const small=data.groups["all/small/raw"],large=data.groups["all/large/raw"];
    el("finding").textContent="From "+dateText(data.first)+" to "+dateText(data.last)+", "+large.opposite+" of "+
      (large.same+large.opposite)+" directional pairs reversed after a pre-meeting move of at least 10 bp. For smaller pre-meeting moves, "+
      small.opposite+" of "+(small.same+small.opposite)+" reversed. "+rows.length+" of "+data.calendarDates+" statement dates matched both yield series.";
    function inspect() {
      selectedDay=picker.value;
      const row=visible.find(item=>item.date===selectedDay);
      const links=el("pair-links");links.replaceChildren();
      if(!row){el("pair").textContent="No statement meets these settings.";return;}
      el("pair").textContent=(row.scheduled?"Scheduled":"Unscheduled")+" statement · "+row.releaseTimeET+" New York time. The two-year par yield moved from "+
        row.start2yPct.toFixed(2)+"% on "+dateText(row.start)+" to "+row.end2yPct.toFixed(2)+"% on "+dateText(row.end)+
        " ("+move(row.priorBp)+"). The on-the-run two-year yield moved "+move(row.statementBp)+" in the statement window.";
      const market=new URLSearchParams({bank:"fed",window:"statement",asset:"UST2Y",year:row.date.slice(0,4),date:row.date});
      links.append(makeLink("Open the statement window","?"+market+"#mr-detail-title"),
        makeLink("Inspect the earlier daily closes","?curveDate="+row.date+"#pre-event-curve"));
    }
    function render() {
      const key=[era.value,size.value,rule.value].join("/");
      const s=data.groups[key];
      const directional=s.same+s.opposite;
      visible=chooseRows(rows,era.value,size.value,rule.value);
      if(visible.length!==s.n)throw new Error("Event selection does not match source group");
      renderMatrix(el("matrix"),s);
      el("counts").textContent=s.n+" matched in this selection · "+directional+" with two non-zero moves · "+s.ties+" flat in at least one window.";
      el("share").textContent=directional ? s.same+" of "+directional+" continued ("+pct(s.samePct)+"). "+s.opposite+" reversed. The within-year sign benchmark is "+pct(s.yearMarginBenchmarkPct)+"." : "No pair has two directional moves.";
      el("effect").textContent=directional ? "The median statement change aligned to the earlier direction was "+move(s.medianAlignedBp)+"." : "";
      const scheduled=s.scheduledDirectional ? "Among scheduled statements, "+s.scheduledSame+" of "+s.scheduledDirectional+" directional pairs continued." : "";
      const range=s.omitYearRangePct;
      el("check").textContent=scheduled+(range?" Omitting one calendar year at a time gives "+pct(range[0])+" to "+pct(range[1])+" agreement.":"");
      el("periods").replaceChildren(...Object.entries(eraLabels).map(([id,label])=>{
        const g=data.groups[[id,size.value,rule.value].join("/")],tr=document.createElement("tr");
        tr.append(td("th",label,"row"),td("td",g.same),td("td",g.opposite),td("td",g.ties),
          td("td",g.samePct===null?"—":pct(g.samePct)),td("td",g.medianAlignedBp===null?"—":move(g.medianAlignedBp)));
        return tr;
      }));
      picker.replaceChildren(...visible.slice().reverse().map(r=>new Option(dateText(r.date),r.date)));
      picker.disabled=!visible.length;
      if(visible.some(r=>r.date===selectedDay))picker.value=selectedDay;
      inspect();
    }
    showSpeech(el("speech"),data.speechCases);
    for(const select of [era,size,rule])select.addEventListener("change",render);
    picker.addEventListener("change",inspect);
    render();
    el("content").hidden=false;el("status").hidden=true;
  } catch {
    el("content").hidden=true;el("status").hidden=false;el("status").textContent="The paired statement observations could not be loaded. Refresh to try again.";
  }
}

initDirectionStudy();
