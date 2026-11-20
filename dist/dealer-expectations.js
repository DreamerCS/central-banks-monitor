const get = id => document.getElementById(id);
const node = (tag, text = "") => {
  const n = document.createElement(tag);
  n.textContent = text;
  return n;
};
const formatDay = iso => new Intl.DateTimeFormat("en-GB", {day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}).format(new Date(iso + "T12:00:00Z"));
const sign = value => value === 0 ? "0" : value < 0 ? "−" + Math.abs(value) : "+" + value;
const link = (label, url) => { const a=node("a", label); a.href=url; return a; };

function table(headers, rows, caption) {
  const box = node("div");
  box.className = "mr-table-scroll";
  box.tabIndex = 0;
  box.setAttribute("role","region");
  box.setAttribute("aria-label",caption);
  const t = node("table");
  t.className = "mr-method-table";
  t.createCaption().textContent = caption;
  const head = t.createTHead().insertRow();
  for (const label of headers) { const th=node("th",label); th.scope="col"; head.append(th); }
  const body = t.createTBody();
  for (const values of rows) {
    const tr=body.insertRow();
    values.forEach((value,i) => {
      const td = node(i===0?"th":"td");
      if (i===0) td.scope="row";
      td.append(value);
      tr.append(td);
    });
  }
  box.append(t);
  return box;
}

function gridStep(bin, start) {
  // The first survey bin below zero excludes zero. All observed starting midpoints
  // end in .125 or .375 etc., so no zero-grid conversion lands on that boundary.
  if (bin.low == null) return "≤ " + sign(Math.floor((bin.high-start)*4)*25);
  if (bin.high == null) return "≥ " + sign(Math.ceil((bin.low-start)*4)*25);
  const lo = Math.ceil((bin.low-start)*4)*25;
  const hi = Math.floor((bin.high-start)*4)*25;
  return lo === hi ? sign(lo) : sign(lo) + " to " + sign(hi);
}

async function load() {
  const response=await fetch("data/dealer-expectations.json");
  if (!response.ok) throw new Error("Survey data unavailable");
  const {meetings}=await response.json();
  const selector=get("dealer-meeting");
  const byDate=new Map(meetings.map(m=>[m.meeting,m]));
  const urlFor = day => { const url=new URL(location.href); url.searchParams.set("dealerMeeting",day); url.hash="dealer-expectations"; return url; };
  const pick = day => {
    history.replaceState(history.state,"",urlFor(day));
    render(day);
  };
  const matched=meetings.filter(m=>m.errorBp===0).length;
  const absMean=key=>(meetings.reduce((n,m)=>n+Math.abs(m[key]),0)/meetings.length).toFixed(1);
  const nDist=meetings.filter(m=>m.bins.length).length;
  get("dealer-status").textContent = matched + " of " + meetings.length + " median forecasts matched the realised midpoint at published precision. Mean absolute error was " + absMean("errorBp") + " bp, compared with " + absMean("stepBp") + " bp for an unchanged-rate forecast. " + nDist + " meetings have a matching probability distribution.";
  const links = new Map();
  const rows=meetings.map(m=>{
    const option=node("option",formatDay(m.meeting)); option.value=m.meeting; selector.append(option);
    const a=link(formatDay(m.meeting),urlFor(m.meeting).href);
    a.addEventListener("click",event=>{
      if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
      event.preventDefault(); pick(m.meeting); selector.focus();
    });
    links.set(m.meeting,a);
    return [a,formatDay(m.due),m.mode+"%",m.midpoint+"%",sign(m.errorBp), m.bins.length ? m.bins[m.realisedBin].p+"%" : "—"];
  });
  get("dealer-table").append(table(["Decision","Replies due","Median modal midpoint","Actual midpoint","Error · bp","Probability of realised bin"],rows,"Premeeting dealer forecasts and realised policy"));
  function render(day) {
    const m=byDate.get(day) || byDate.get("2022-06-15");
    selector.value=m.meeting;
    for (const [date,a] of links) {
      if (m.meeting===date) a.setAttribute("aria-current","true"); else a.removeAttribute("aria-current");
    }
    const stats=node("dl"); stats.className="dealer-stats";
    for (const [name,value] of [["Median modal midpoint",m.mode+"%"],["Realised target range",m.target.join("–")+"%"],["Actual decision",sign(m.stepBp)+" bp"],["Signed forecast error",sign(m.errorBp)+" bp"]]) {
      const pair=node("div"); pair.append(node("dt",name),node("dd",value)); stats.append(pair);
    }
    const timing=node("p","Fieldwork from "+formatDay(m.sent)+" through "+formatDay(m.due)+". "+m.modeN+" dealers gave a modal forecast. The premeeting midpoint was "+m.priorMid+"% and the midpoint after the decision was "+m.midpoint+"%.");
    get("dealer-result").replaceChildren(stats,timing);
    const dist=get("dealer-distribution");
    if (m.bins.length) {
      const cells=m.bins.map((b,i)=>{
        const p=node("span"), bar=node("span"), fill=node("span"); bar.className="dealer-bar"; bar.setAttribute("aria-hidden","true");fill.style.width=b.p+"%";bar.append(fill);p.append(bar,b.p+"%");
        return [b.label+(i===m.realisedBin?" · realised":""),gridStep(b,m.priorMid),p];
      });
      const panel=table(["Target midpoint bin","Move on 25 bp grid","Average probability"],cells,"Next-meeting outcome probabilities from "+m.probN+" dealers");
      panel.querySelectorAll("tbody tr")[m.realisedBin].className="dealer-realised";
      dist.replaceChildren(panel);
    } else dist.replaceChildren(node("p","No immediate-meeting probability distribution. "+m.reason));
    const market=get("dealer-market");
    market.replaceChildren();
    if (m.market) {
      const b=m.market, dealer=m.bins[m.realisedBin].p;
      market.append(node("h3","What did futures imply on the survey deadline?"),
        node("p","For the same "+Math.abs(b.step)+" bp "+(b.step>0?"hike":"cut")+", dealers assigned "+dealer+"% on average. "+b.note+" Individual survey responses could have arrived earlier in the fieldwork window."),
        link(b.source+" · "+formatDay(b.date),b.url));
    }
    const sources=[link("New York Fed results · Q"+m.modeQ+" and Q"+m.probQ,m.pdf),link("FOMC decision · "+formatDay(m.meeting),m.statement)];
    if(m.workbook) sources.push(link("New York Fed data workbook",m.workbook));
    if(m.meeting==="2022-06-15") {
      const review=node("p","The survey closed on 6 June. The FOMC minutes report that market pricing had favoured a 50 bp increase before the 10 June CPI release, then assigned greater weight to 75 bp. A forecast collected nine days before the meeting could therefore look quite different from prices immediately before the decision.");
      market.append(review);
      sources.push(link("10 June CPI release","https://www.bls.gov/news.release/archives/cpi_06102022.htm"),link("FOMC minutes on the intervening news","https://www.federalreserve.gov/monetarypolicy/fomcminutes20220615.htm"));
    }
    get("dealer-links").replaceChildren(...sources);
  }
  const fromURL=()=>new URLSearchParams(location.search).get("dealerMeeting");
  render(fromURL());
  selector.addEventListener("change",()=>pick(selector.value));
  window.addEventListener("popstate",()=>render(fromURL()));
  get("dealer-content").hidden=false;
}

if (get("dealer-expectations")) load().catch(()=>{
  const status=get("dealer-status");
  status.textContent="The dealer survey data could not load. ";
  status.append(link("Open the New York Fed archive","https://www.newyorkfed.org/markets/primarydealer_survey_questions"));
});
