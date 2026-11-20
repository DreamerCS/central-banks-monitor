const transitions = {
  EU: "Employed to unemployed",
  UE: "Unemployed to employed",
  NU: "Outside the labour force to unemployed",
  UN: "Unemployed to outside the labour force"
};
const labels = {E: "employed", U: "unemployed", N: "outside the labour force"};
const figures = new Intl.NumberFormat("en-US");
const calendar = new Intl.DateTimeFormat("en-GB", {month: "short", year: "numeric", timeZone: "UTC"});
const monthName = month => calendar.format(new Date(month + "-01T00:00:00Z"));
const signed = n => n > 0 ? "+" + figures.format(n) : figures.format(n).replace("-", "−");
const offsetName = n => n === 0 ? "0" : signed(n);
const rate = (row, flow) => 100 * row[flow] / row["prior" + flow[0]];
const steps = Array.from({length: 15}, (_, i) => i - 2);

function transitionChart(data, flow, offset, svgNode) {
  const svg = svgNode("svg", {viewBox:"0 0 650 178", role:"img",
    "aria-label":transitions[flow] + " as a percentage of the previous month's origin group, from two months before each anchor to twelve months after."});
  const width = 650, left = 46, right = width - 15, bottom = 145, top = 14;
  const highest = Math.max(...data.episodes.flatMap(e => e.rows.map(r => rate(r, flow))));
  const step = Math.max(1, Math.ceil(highest / 4));
  const x = i => left + i * (right - left) / (steps.length - 1);
  const y = value => bottom - (bottom - top) * value / (4 * step);
  function textAt(text, x, y, anchor = "middle") {
    const t = svgNode("text", {x, y, "text-anchor":anchor});
    t.textContent = text;
    svg.append(t);
  }
  for (let i = 0; i <= 4; i++) {
    const value = i * step;
    svg.append(svgNode("line", {x1:left, x2:right, y1:y(value), y2:y(value), class:"lf-grid"}));
    textAt(value + "%", left - 7, y(value) + 4, "end");
  }
  for (const n of [-2,0,3,6,9,12]) textAt(offsetName(n), x(n + 2), bottom + 22);
  svg.append(svgNode("line", {x1:x(offset + 2), x2:x(offset + 2), y1:top, y2:bottom, class:"lf-guide"}));
  data.episodes.forEach((episode, i) => {
    const coordinates = episode.rows.map((r,j) => [x(j), y(rate(r, flow))]);
    svg.append(svgNode("polyline", {points:coordinates.map(p => p.join(",")).join(" "), class:"lf-line lf-line-" + i}));
    const [cx, cy] = coordinates[offset + 2];
    svg.append(svgNode("circle", {cx, cy, r:4, class:"lf-point lf-point-" + i}));
  });
  return svg;
}

export function labourFlows(data, {el, link, table, select, svgNode, sourceList}, params) {
  const page = el("article", undefined, "lf-article");
  let flow = Object.hasOwn(transitions, params.get("flow")) ? params.get("flow") : "EU";
  const requested = Number(params.get("offset"));
  let offset = steps.includes(requested) ? requested : 0;
  page.append(el("p", "United States · Current Population Survey", "hs-kicker"),
    el("h2", "Who entered unemployment, and who found work?"),
    el("p", "In October 2008, 1.56% of the people employed in September moved into unemployment. In April 2020 the corresponding share was 11.24%. The recovery paths also differed. Twelve months later, 15.44% of the previous month’s unemployed moved into work in the financial-crisis comparison, against 24.00% in the pandemic comparison.", "hs-deck"));
  const controls = el("div", undefined, "lf-controls");
  controls.append(select("Transition",Object.entries(transitions),flow,v=>{flow=v;update(true);}),
    select("Month relative to anchor",steps.map(n=>[String(n),offsetName(n)+" · "+data.episodes.map(e=>monthName(e.rows[n+2].month)).join(" / ")]),String(offset),v=>{offset=Number(v);update(true);}));
  const chart = el("figure", undefined, "lf-chart");
  const exact = el("div");
  exact.setAttribute("aria-live", "polite");
  page.append(controls, chart, exact);
  function update(save) {
    if (save) {
      const url = new URL(location.href);
      url.searchParams.set("flow",flow);
      url.searchParams.set("offset",String(offset));
      history.replaceState(null,"",url);
    }
    const legend = el("div",undefined,"lf-legend");
    data.episodes.forEach((e, i) => legend.append(el("span",e.title,"lf-key lf-key-" + i)));
    chart.replaceChildren(el("h3", transitions[flow] + " · share of prior " + labels[flow[0]] + " group"),legend,
      transitionChart(data,flow,offset,svgNode),
      el("figcaption","Months from October 2008 and April 2020. The selected month's values and denominators appear below."));
    const rows = data.episodes.map(e => e.rows[offset + 2]);
    const selection = table(["Month","People making the transition","People in the prior group","Transition rate"],
      rows.map(r=>[monthName(r.month),figures.format(r[flow]),figures.format(r["prior"+flow[0]]),rate(r,flow).toFixed(2)+"%"]),
      "Selected transition; people in thousands");
    const accounting = [
      ["Prior month unemployed",r=>r.priorU,false],
      ["Employed to unemployed",r=>r.EU,true],
      ["Unemployed to employed",r=>-r.UE,true],
      ["Outside labour force to unemployed",r=>r.NU,true],
      ["Unemployed to outside labour force",r=>-r.UN,true],
      ["Other inflows to unemployment",r=>r.OU,true],
      ["Other outflows from unemployment",r=>-r.UO,true],
      ["Rounding residual",r=>r.U-r.priorU-r.EU+r.UE-r.NU+r.UN-r.OU+r.UO,true],
      ["Change in unemployed",r=>r.U-r.priorU,true],
      ["Current month unemployed",r=>r.U,false]
    ];
    exact.replaceChildren(el("h3","Selected transition · thousands of people"),selection,
      el("h3","Account for the change in unemployment"),el("p","Inflows add to unemployment and outflows subtract from it. People who remained unemployed appear in both months and cancel. Counts below are in thousands."),
      table(["Unemployment stock and flows",...rows.map(r=>monthName(r.month))],
        accounting.map(([caption, value, sign])=>[caption,...rows.map(r=>(sign?signed:figures.format)(value(r)))]),
        "Monthly unemployment stock reconciliation in thousands"));
  }
  update(false);
  const method = el("details",undefined,"hs-details");
  method.append(el("summary","Sources, definitions and comparison dates"),
    el("p","October 2008 captures the first full survey month after the mid-September financial shock. April 2020 captures the spring shutdown. The two-month lead-ins are August 2008 and February 2020. The earlier US recession was already underway by August. These anchors organise the comparison and do not estimate the effect of either event."),
    el("p","The probability of entering unemployment uses the relevant employed or inactive population as its starting point. The probability of finding work begins with those unemployed. Divide each flow by the previous month’s population in its starting state, including movements into and out of the labour force."),
    el("p","BLS matches respondents across monthly interviews and adjusts the weighted flows to agree with official population stocks. The denominators are the previous month’s published seasonally adjusted stocks. The transition counts are population estimates in thousands. Other inflows include people turning 16 and population adjustments. Other outflows include estimated deaths and population adjustments. Rounding the published counts can leave a small residual."),
    el("p","The status pairs record where a person began and ended the month. They cannot distinguish a quit from a layoff or a recall from another hire. In April 2020 some people absent because of closures were recorded as employed when BLS guidance called for classification as unemployed on temporary layoff. The published series retains recorded responses. These revised historical estimates can differ from the figures available on release day."));
  const references = [
    {label:"BLS · research series on labour-force flows and historical series selector",url:"https://www.bls.gov/cps/cps_flows.htm"},
    {label:"BLS · stock-consistent estimation and seasonal adjustment",url:"https://www.bls.gov/opub/mlr/2005/09/art1full.pdf"},
    {label:"BLS · April 2020 survey classification, questions 13–14",url:"https://www.bls.gov/covid19/employment-situation-covid19-faq-april-2020.htm"}
  ];
  const seriesLabels = {...labels,...transitions, OU:"Other inflows to unemployed",UO:"Other outflows from unemployed"};
  const list=el("ul");
  for (const [key,id] of Object.entries(data.series)) {
    const li=el("li");
    li.append(link(seriesLabels[key]+" · "+id,"https://data.bls.gov/timeseries/"+id));
    list.append(li);
  }
  method.append(el("h3","Seasonally adjusted BLS series"),list);
  page.append(el("h3","What the net figure concealed"),
    el("p","In October 2008 the number entering unemployment from outside the labour force exceeded the number leaving it for nonparticipation by 424,000. That contribution was larger than the net 120,000 arriving from employment. By October 2009 job finding had slowed even as the number moving from unemployment into work rose, because so many more people had started the month unemployed."),
    el("p","In April 2020 the exchange with employment added 16.146 million to unemployment. Movements across the participation boundary offset 277,000 of that rise. Of those already unemployed in March, 36.00% were outside the labour force in April and 18.17% were employed. By June the job-finding rate had risen to 36.83%. Counts of people moving into work alone cannot identify how much of that rebound came from recalls."),
    method,sourceList(references));
  return page;
}
