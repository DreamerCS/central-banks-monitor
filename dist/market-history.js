"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const plot = $("tape-plot");
  const instruments = {
    "2": {column: 1, id: "DGS2", unit: "%"},
    "10": {column: 2, id: "DGS10", unit: "%"},
    spread: {id: "DGS10", unit: " bp"},
    eur: {column: 3, id: "DEXUSEU", unit: " USD"},
    jpy: {column: 4, id: "DEXJPUS", unit: " JPY"}
  };
  let raw = [], range = "All", points = [], selectPoint;
  const dayMs = 86400000;
  function bucket(stamp, frequency) {
    const day = new Date(stamp);
    if (frequency === "Year") return day.getUTCFullYear();
    if (frequency === "Month") return day.toISOString().slice(0, 7);
    if (frequency === "Week") return stamp - (day.getUTCDay() + 6) % 7 * dayMs;
    return stamp;
  }
  function plotMarket() {
    if (!raw.length) return;
    const key = $("tape-asset").value, series = instruments[key];
    const frequency = $("tape-freq").value, changes = $("tape-view").value === "Change";
    const unit = changes ? (series.column >= 3 ? "%" : " bp") : series.unit;
    const decimals = changes ? 2 : key === "eur" ? 4 : key === "spread" ? 0 : 2;
    const groups = new Map();
    for (const row of raw) {
      const level = key === "spread" ? (row[1] !== null && row[2] !== null ? (row[2] - row[1]) * 100 : null) : row[series.column];
      if (level !== null) groups.set(bucket(row[0], frequency), {time: row[0], level});
    }
    const all = [...groups.values()];
    const end = all.at(-1).time;
    const from = new Date(end);
    if (range !== "All") from.setUTCFullYear(from.getUTCFullYear() - parseInt(range, 10));
    const start = range === "All" ? Date.UTC(2000,0,1) : +from;
    points = [];
    all.forEach(({time, level}, index) => {
      if (time < start || (changes && !index)) return;
      let value = level;
      if (changes) {
        const prior = all[index - 1].level;
        value = series.column >= 3 ? (level / prior - 1) * 100 : (level - prior) * (key === "spread" ? 1 : 100);
      }
      points.push({time, value});
    });
    const width = Math.max(260,plot.clientWidth), height = plot.clientHeight;
    const pad = {left: 50, right: 10, top: 12, bottom: 30};
    const first = points[0].time, last = points.at(-1).time;
    let low = Math.min(...points.map(p => p.value)), high = Math.max(...points.map(p => p.value));
    if (changes) {low = Math.min(0, low); high = Math.max(0, high);}
    const margin = Math.max((high - low) * .07, .005);
    low -= margin; high += margin;
    const x = t => pad.left + (t-first) / Math.max(1,last-first) * (width-pad.left-pad.right);
    const y = v => pad.top + (high-v) / (high-low) * (height-pad.top-pad.bottom);
    plot.replaceChildren();
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns,"svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("aria-hidden","true");
    plot.append(svg);
    function shape(tag,attrs,value) {
      const node = document.createElementNS(ns,tag);
      for (const [name,attr] of Object.entries(attrs)) node.setAttribute(name,attr);
      if (value !== undefined) node.textContent = value;
      svg.append(node);
      return node;
    }
    for (let i = 0; i <= 3; i++) {
      const value = low + (high-low) * i/3;
      shape("line",{x1:pad.left,x2:width-pad.right,y1:y(value),y2:y(value),stroke:"#cdd0c1","stroke-dasharray":"2 4"});
      shape("text",{x:pad.left-7,y:y(value)+4,"text-anchor":"end"},value.toFixed(key==="eur" && !changes?2:1));
    }
    const ticks = width < 600 ? 3 : 6;
    for (let i=0;i<ticks;i++){
      const time = first+(last-first)*i/(ticks-1);
      const date = new Date(time).toISOString();
      shape("text",{x:x(time),y:height-7,"text-anchor":i===0?"start":i===ticks-1?"end":"middle"},last-first>3*365*dayMs?date.slice(0,4):date.slice(0,7));
    }
    if(changes) shape("line",{x1:pad.left,x2:width-pad.right,y1:y(0),y2:y(0),stroke:"#a87b58"});
    shape("path",{d:points.map((p,i)=>(i?"L":"M")+x(p.time).toFixed(1)+","+y(p.value).toFixed(1)).join(" "),fill:"none",stroke:"#385744","stroke-width":1.7,"stroke-linejoin":"round"});
    const marker=shape("line",{y1:pad.top,y2:height-pad.bottom,stroke:"#936f51","stroke-dasharray":"3 3"});
    const dot=shape("circle",{r:4,fill:"#a55535",stroke:"#fff","stroke-width":1.5});
    const format = new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"});
    let selected=points.length-1;
    selectPoint = index => {
      selected=Math.max(0,Math.min(points.length-1,index));
      const p=points[selected], cx=x(p.time);
      marker.setAttribute("x1",cx); marker.setAttribute("x2",cx);
      dot.setAttribute("cx",cx); dot.setAttribute("cy",y(p.value));
      $("tape-value").textContent=(changes && p.value>0?"+":"")+p.value.toFixed(decimals)+unit;
      $("tape-date").textContent=format.format(p.time);
      plot.setAttribute("aria-label",[$("tape-asset").selectedOptions[0].textContent, frequency, $("tape-view").value,$("tape-value").textContent,$("tape-date").textContent,"Use left and right arrow keys to inspect."].join(". "));
    };
    selectPoint(selected);
    plot.onpointermove=e=>{
      const target=first+(e.clientX-plot.getBoundingClientRect().left-pad.left)/(width-pad.left-pad.right)*(last-first);
      let lo=0,hi=points.length-1;
      while(lo<hi){const mid=Math.floor((lo+hi)/2);if(points[mid].time<target)lo=mid+1;else hi=mid;}
      selectPoint(lo>0 && target-points[lo-1].time<points[lo].time-target ? lo-1:lo);
    };
    plot.onpointerleave=()=>selectPoint(points.length-1);
    plot.onkeydown=e=>{if(["ArrowLeft","ArrowRight","Home","End"].includes(e.key)){e.preventDefault();selectPoint(e.key==="Home"?0:e.key==="End"?points.length-1:selected+(e.key==="ArrowLeft"?-1:1));}};
    $("tape-source").href="https://fred.stlouisfed.org/series/"+series.id;
  }
  document.querySelector(".tape-controls").addEventListener("change",plotMarket);
  $("tape-ranges").addEventListener("click",e=>{
    const button=e.target.closest("button");if(!button)return;
    range=button.textContent;
    for(const item of $("tape-ranges").children)item.setAttribute("aria-pressed",String(item===button));
    plotMarket();
  });
  new ResizeObserver(plotMarket).observe(plot);
  fetch("data/market-history.csv").then(response=>{
    if(!response.ok)throw Error(response.status);
    return response.text();
  }).then(csv=>{
    raw=csv.trim().split(/\r?\n/).slice(1).map(line=>{
      const [date,...levels]=line.split(",");
      return [Date.parse(date+"T00:00:00Z"),...levels.map(v=>v===""?null:Number(v))];
    });
    plotMarket();
  }).catch(()=>{plot.textContent="Market history unavailable.";});
})();
