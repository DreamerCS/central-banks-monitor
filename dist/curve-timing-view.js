export function buildCurveView({el, pick, select, table, details, sources, summaryFacts, plot,
  limits, monthNumber, legend, monthReadout, ink, nfmt, signed, addInputs, resultPair, monthTicks, svg}) {
  const options = labels => Object.entries(labels).map(([id,label]) => ({id,label}));
  const percent = v => Number.isFinite(v) ? nfmt(v,1) + "%" : "—";
  const outcome = v => v === null ? "Follow-up incomplete" : v ? "Cut observed" : "No cut";
  function curveChart(data, curve) {
    const rows = data.monthly, field = curve.id + "Bp";
    const labelled = new Map(monthTicks(rows).map(r => [monthNumber(r.month), r.month]));
    const extent = [monthNumber(rows[0].month), monthNumber(rows.at(-1).month)];
    const g = plot(curve.label + " Treasury spread", "Long yield less short yield (bp)", "Observation month",
      extent, limits(rows.map(r => r[field]).concat(-curve.thresholdBp), true), [...labelled.keys()],
      x => labelled.get(x), "Last common daily observation in each calendar month. The dashed line is the primary inversion threshold. Signal dates use daily yields.");
    let path = "", previous = null;
    for (const row of rows) {
      const m = monthNumber(row.month), value = row[field];
      if (!Number.isFinite(value)) { previous = null; continue; }
      path += (previous !== null && m - previous === 1 ? "L" : "M") + g.x(m) + " " + g.y(value) + " ";
      previous = m;
    }
    const line = g.y(-curve.thresholdBp);
    g.layer.append(svg("line",{x1:g.left,x2:g.right,y1:line,y2:line,stroke:ink.coral,"stroke-dasharray":"5 3"}),
      svg("path",{d:path,fill:"none",stroke:ink.gold,"stroke-width":2.4}));
    const mark = svg("line",{y1:g.top,y2:g.bottom,stroke:ink.white,"stroke-dasharray":"2 4"});
    g.layer.append(mark);
    g.f.append(legend([["Monthly spread",ink.gold],["−"+curve.thresholdBp+" bp",ink.coral,true]]));
    monthReadout(g.f,rows,r => r.date+" · "+signed(r[field],0)+" bp"+(r.partial?" · partial month":""),
      r => {const x=g.x(monthNumber(r.month)); mark.setAttribute("x1",x);mark.setAttribute("x2",x);});
    return g.f;
  }

  return function curve(data) {
    const page = el("div"), curves = data.headline, thresholds = [
      {id:"12.5",label:"12.5 bp"},{id:"0",label:"Zero"},{id:"25",label:"25 bp"}
    ];
    const chosen = pick("slope",curves,"twoSix"), series = curves.find(c => c.id === chosen);
    const groups = options(data.groups), selections = options(data.selections);
    const group = pick("regime",groups,"all"), selection = pick("entry",selections,"episodes");
    const threshold = pick("depth",thresholds,"12.5");
    const cell = data.sensitivity.find(r => r.curve === chosen && r.group === group &&
      r.selection === selection && r.thresholdBp === Number(threshold));
    const primary = series.horizons;
    page.append(el("h2","How soon after inversion does the Fed cut?"),
      el("p","Follow US Treasury curve inversions through to the next announced policy cut. Compare the chance of a cut after a crossing with the frequency across all eligible days and in the particular years in which the curve inverted.","es-intro"));
    addInputs(page,select("slope","Treasury spread",curves,chosen));
    page.append(resultPair(curveChart(data,series),summaryFacts("At the 12.5 bp crossing",primary.map(h =>
      ["Within "+h.months+" months",h.hits+" of "+h.n+" · "+percent(h.pct)]).concat([
        ["Common yield dates",data.commonDays.toLocaleString("en-GB")],["Last yield observation",data.through]
      ]),"Fresh inversions are counted at least twelve calendar months apart. The sample size differs across horizons when the last signal still has time to run.")));
    page.append(el("h3","What happened after each inversion?"),
      table("Separate daily inversion episodes",["Entry date","Spread","Target or upper bound","Next cut","Calendar days","Next hike before a cut","Six months","Twelve months"],
        series.episodes.map(e => [e.date,signed(e.slopeBp,0)+" bp",nfmt(e.targetUpper,2)+"%",e.nextCut || "None through cutoff",
          e.daysToCut ?? "—",e.nextHike && (!e.nextCut || e.nextHike < e.nextCut) ? e.nextHike : "—",outcome(e.hit6),outcome(e.hit12)])),
      el("p","In October 2022 both curves crossed the threshold. The Fed raised its target the next week. Six increases totalling 225 bp followed the signal before the first cut in September 2024. A long wait exposes an investor to the cost of maintaining a rates position.","es-note"));
    page.append(el("h3","Does the signal add information beyond the year?"));
    addInputs(page,select("depth","Inversion depth",thresholds,threshold),select("regime","Sample",groups,group),
      select("entry","Counting rule",selections,selection));
    page.append(table("Cuts after a signal and on eligible comparison dates",["Horizon","Cuts / eligible signals","After signal","All eligible dates","Same-year benchmark","Gap to same year"],
      cell.horizons.map(h => [h.months+" months",h.hits+" / "+h.n,percent(h.pct),percent(h.basePct),
        percent(h.yearMatchedBasePct),Number.isFinite(h.yearMatchedLiftPp)?signed(h.yearMatchedLiftPp,1)+" pp":"—"])),
      el("p","The same-year benchmark averages the cut frequency on eligible dates in each signal’s calendar year, weighting the years as the signals do. It describes the sample retrospectively. Overlapping daily observations can share the very same cut.","es-note"));
    const sourceLabels = {DGS3MO:"3-month Treasury",DGS6MO:"6-month Treasury",DGS2:"2-year Treasury",DGS10:"10-year Treasury",DFEDTAR:"Funds target",DFEDTARL:"Lower target bound",DFEDTARU:"Upper target bound",calendar:"FOMC announcement dates"};
    page.append(details("Data, definitions and limits",...Object.values(data.methods).map(t => el("p",t)),
      sources([...data.sources.map(s => ({label:sourceLabels[s.id] || s.id,url:s.url})),...(data.decisionReferences || []).map(r=>({label:"FOMC decision · "+r.date,url:r.url}))])));
    return page;
  };
}
