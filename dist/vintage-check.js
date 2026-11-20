function element(tag, value, css) {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = value;
  if (css) node.className = css;
  return node;
}
function control(label) {
  const field = element("label", label, "vc-field");
  const select = element("select");
  field.append(select);
  return {field, select};
}
function grid(headings, rows) {
  const wrapper = element("div",undefined,"es-tablewrap");
  const table = element("table",undefined,"es-table");
  const row = table.createTHead().insertRow();
  for(const label of headings) {
    const h = element("th",label);
    h.scope = "col";row.append(h);
  }
  const body = table.createTBody();
  for(const cells of rows) {
    const tr = body.insertRow();
    for(const value of cells) tr.insertCell().textContent = value;
  }
  wrapper.append(table);
  return wrapper;
}
const two = value => value.toFixed(2);
const officials = [
  ["Quarterly CPI vintages","https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/cpi"],
  ["Quarterly unemployment vintages","https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/ruc"],
  ["Monthly CPI vintages","https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/pcpi"]
];
export async function renderVintageCheck(section) {
  section.setAttribute("aria-label","Real-time inflation forecast check");
  section.append(element("h2","Would the result have held in real time?"));
  try {
    const response = await fetch("data/vintage-check.json");
    if (!response.ok) throw new Error("Vintage results unavailable");
    const data = await response.json();
    const period = control("Evaluation targets");
    for(const p of data.periods) period.select.add(new Option(p.label,p.id));
    period.select.value="recent";
    const panel=element("div");
    const findings = element("p",undefined,"es-intro");
    const recent = data.periods.find(p=>p.id==="recent"), pandemic = data.periods.find(p=>p.id==="pandemic");
    const score = (p,id) => two(p.scores.find(x=>x.model===id).realTime);
    findings.textContent = "Using only the data available at the time, the model fitted to 2000–08 had a mean absolute error of "+score(recent,"through08")+" percentage points over "+recent.n+" recent targets. Keeping inflation unchanged produced an error of "+score(recent,"unchanged")+". That ranking reversed across the "+pandemic.n+" pandemic targets: "+score(pandemic,"through08")+" against "+score(pandemic,"unchanged")+".";
    function draw() {
      const p=data.periods.find(x=>x.id===period.select.value);
      const caption=element("p",p.first+" to "+p.last+" · "+p.n+" matched targets · mean absolute error in percentage points. Smaller is closer.","es-note");
      panel.replaceChildren(caption,grid(["Training history","As known then","Revised inputs¹","Revised outcome²"],p.scores.map(s=>[data.models[s.model],two(s.realTime),two(s.revisedInput),two(s.revisedOutcome)])));
    }
    period.select.addEventListener("change",draw); draw();
    const detail=element("details",undefined,"es-detail");
    detail.append(element("summary","Forecast design and data revisions"),
      element("p","At each quarterly information date, the latest month with both CPI and unemployment anchors the forecast. The target is year-on-year CPI inflation six months after that observation month. The cutoff varies with publication lags. Coefficients use only training pairs whose outcomes are already present in that vintage."),
      element("p","The regression uses current year-on-year CPI inflation and the twelve-month change in unemployment. The expanding estimation starts in 1960. The fixed historical samples require both the training origin and the target to fall within their stated years. The unchanged benchmark carries current inflation forward."),
      element("p","The outcome is measured in the earliest subsequent monthly Philadelphia Fed vintage containing both CPI levels needed for the year-on-year rate. It is an archived monthly reading. The quarterly information sets limit the number of observations, and six-month outcomes from adjacent quarters overlap. The sample ranking is descriptive."),
      element("p","¹ Refit using revised inputs through the same observation cutoff while retaining the early-vintage outcome. ² Keep the original as-known forecast and evaluate it against the later November 2026 data snapshot. A missing price level or base month leaves the corresponding comparison unscored."));
    const unscored=element("p", "Unscored target months · "+data.unscored.map(r=>r.target+" ("+r.reason.toLowerCase()+")").join(", ")+".");
    detail.append(unscored);
    const byDate=element("details",undefined,"es-detail");
    const date=control("Quarterly information set"),point=element("div");
    for(const r of [...data.observations].reverse()) date.select.add(new Option(r.vintage,r.vintage));
    function showPoint(){
      const row=data.observations.find(r=>r.vintage===date.select.value);
      const note=element("p","Latest common economic month "+row.origin+" · Target "+row.target+" · First available monthly outcome vintage "+row.outcomeVintage+".","es-note");
      const forecasts=Object.entries(row.asKnown).map(([name,v])=>[data.models[name],two(v)+"%"]);
      forecasts.push(["Subsequently observed inflation",two(row.initial)+"%"]);
      point.replaceChildren(note,grid(["At this origin","Six-month forecast or outcome"],forecasts));
    }
    date.select.addEventListener("change",showPoint);showPoint();
    byDate.append(element("summary","Inspect an individual forecast"), date.field, point);
    const sources=element("p",undefined,"es-links");
    for(const [name,url] of officials) {
      if(sources.childNodes.length) sources.append(" · ");
      const a=element("a",name);a.href=url;sources.append(a);
    }
    const clock=element("p","The horizon is six months from the last common CPI and unemployment observation. Publication lags put the first available target reading four to six calendar months after the quarterly forecast snapshot.","es-note");
    section.append(findings,clock,period.field,panel,detail,byDate,sources);
  }catch {
    const p=element("p","Historic-vintage results could not be loaded. ");
    const retry=element("button","Retry");retry.addEventListener("click",()=>{section.replaceChildren();renderVintageCheck(section);});
    p.append(retry);section.append(p);
  }
}
