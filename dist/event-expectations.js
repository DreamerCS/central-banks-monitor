// Dated market expectations for the US pre-event curve explorer.
const dataUrl = new URL("./data/event-expectations.json", import.meta.url);
let dataRequest;
const fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });
const prettyDate = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const dateLabel = iso => prettyDate.format(new Date(iso + "T12:00:00Z"));
const moneyRate = n => fmt.format(n) + "%";
const sign = n => (n > 0 ? "+" : n < 0 ? "−" : "") + fmt.format(Math.abs(n));
const daysBetween = (a,b) => Math.round((Date.parse(b)-Date.parse(a))/86400000);

function make(tag, text, klass) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (klass) node.className = klass;
  return node;
}

function appendLinks(parent, pairs) {
  const list = make("p", undefined, "pc-sources");
  for (const [label,url] of pairs) {
    const a = make("a",label);
    a.href = url;
    list.append(a, " ");
  }
  parent.append(list);
}

function method(title, text) {
  const box = make("details",undefined,"mr-help");
  box.append(make("summary",title),make("p",text));
  return box;
}

function quote(value, date) {
  const cell = make("td");
  cell.append(make("strong", value),make("br"),make("small",dateLabel(date)));
  return cell;
}

function addRow(body, label, earlier, later, delta) {
  const row = make("tr");
  const name = make("th", label);
  name.scope = "row";
  row.append(name, quote(...earlier), quote(...later), make("td",delta));
  body.append(row);
}

function rateTable() {
  const scroll = make("div",undefined,"mr-table-scroll");
  scroll.tabIndex = 0;
  scroll.setAttribute("role","region");
  scroll.setAttribute("aria-label","Market pricing observations before the selected date");
  const table = make("table",undefined,"mr-method-table");
  table.append(make("caption","Matched market measures and the net change before the selected US event"));
  const header = table.createTHead().insertRow();
  for (const label of ["Market measure","Earlier pricing","Later pricing","Net change"]) {
    const th = make("th",label);
    th.scope = "col";
    header.append(th);
  }
  const body = table.createTBody();
  scroll.append(table);
  return { scroll, body };
}

export function eligibleReport(data, day) {
  // A report published on the event date has no verified earlier release time.
  if (!day || day > data.asOf) return null;
  return data.reports.filter(r => r.published < day && r.dates[1] < day).at(-1) || null;
}

export function futureQuarters(report, day) {
  if (!report) return [];
  const quarter = day.slice(0,4)+" Q"+(Math.floor((Number(day.slice(5,7))-1)/3)+1);
  return Object.keys(report.quarters).filter(label => label > quarter).sort();
}

export function grossMove(path) {
  return path.reduce((total, [, rate], i) => total + (i ? Math.abs(rate-path[i-1][1]) : 0), 0);
}

function render(mount, data, day, selectedQuarter) {
  mount.replaceChildren();
  if (!day || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return;
  mount.append(make("h3","What was already priced before this date?"));
  const report = eligibleReport(data,day);
  const quarters = futureQuarters(report, day);
  const quarter = quarters.includes(selectedQuarter) ? selectedQuarter : quarters[0];
  const daily = day <= data.asOf ? data.daily[day] : null;
  const odds = day <= data.asOf ? data.meetingOdds[day] : null;
  if (!odds && !daily && !quarter) {
    mount.append(make("p","This date has no verified pair of earlier policy-pricing observations in the archive."));
    appendLinks(mount,[["Federal Reserve report archive",data.sources.reportIndex],["Atlanta Fed tracker",data.sources.tracker]]);
    return;
  }

  const {scroll,body} = rateTable();
  if (odds) {
    const [first,a] = odds.earlier, [last,b] = odds.later;
    addRow(body,"Chance of a "+odds.outcome+" on "+dateLabel(odds.meeting),
      [moneyRate(a),first],[(odds.approximate ? "≈" : "")+moneyRate(b),last],
      (odds.approximate ? "≈" : "")+sign(b-a)+" pp");
  }
  if (daily) {
    const [a,b] = daily.meanBp;
    addRow(body,"Three-month SOFR from "+dateLabel(daily.referenceStart),
      [moneyRate(a/100),daily.earlier],[moneyRate(b/100),daily.later],sign(b-a)+" bp");
  }
  if (quarter) {
    const [a,b] = report.quarters[quarter];
    addRow(body,quarter+" effective federal funds rate, fitted OIS path",
      [moneyRate(a),report.dates[0]],[moneyRate(b),report.dates[1]],sign((b-a)*100)+" bp");
  }
  mount.append(scroll);
  if (odds) {
    const box = method("Meeting probability and sources",odds.note);
    if (odds.impliedMove) box.append(make("p",odds.impliedMove));
    box.append(make("p","The reported probabilities come from futures pricing and model assumptions. Each row compares the same meeting and outcome. A percentage-point change in its probability has different units from a basis-point change in a rate."));
    appendLinks(box,[...odds.sources,["CME FedWatch methodology",data.sources.fedwatch]]);
    mount.append(box);
    if (odds.eventDay) {
      const after = method(odds.eventDay.label,odds.eventDay.text);
      appendLinks(after,odds.eventDay.sources);
      mount.append(after);
    }
  }
  if (daily) {
    const gross = grossMove(daily.path);
    const net = daily.meanBp[1]-daily.meanBp[0];
    mount.append(make("p","Across five quoted intervals, the mean for this SOFR contract moved "+fmt.format(gross)+" bp in total when each move is counted without its sign. Its net change was "+sign(net)+" bp."));
    const box = method("SOFR contract observations and source",
      "The Atlanta Fed fits a distribution to CME options on the same three-month compounded secured overnight financing rate. The displayed rate is its mean. Repo funding conditions and risk premia also affect it. The reference quarter spans multiple dates and gives no probability for a single FOMC decision.");
    box.append(make("p",daily.path.map(([d, bp]) => dateLabel(d)+" · "+moneyRate(bp/100)).join(" | ")));
    box.append(make("p","The tracker generally publishes the following day. These dates identify the market inputs. The archive supplies no intraday release timestamp for the model estimates."));
    box.append(make("p","Educational excerpts from the Atlanta Fed Market Probability Tracker, © Federal Reserve Bank of Atlanta."));
    appendLinks(box,[["Atlanta Fed Market Probability Tracker",data.sources.tracker],["Original workbook and data dictionary",data.sources.workbook]]);
    mount.append(box);
  }
  if (quarter) {
    const lag = daysBetween(report.dates[1], day);
    const box = method("Federal funds path, vintage and other quarters",
      "The Board reports an effective federal funds rate path fitted to overnight index swaps, assuming a zero term premium. Both columns refer to the same calendar quarter. The report was published "+dateLabel(report.published)+". The later pricing snapshot was "+lag+" calendar "+(lag===1?"day":"days")+" before the selected event.");
    box.dataset.policyQuarters = "";
    const label = make("label","Compare a future quarter ");
    const select = make("select");
    for (const option of quarters) {
      const opt = make("option",option);
      opt.value = option;
      opt.selected = option === quarter;
      select.append(opt);
    }
    select.addEventListener("change",() => {
      const value = select.value;
      render(mount,data,day,value);
      const details = mount.querySelector("details[data-policy-quarters]");
      if (details) {
        details.open = true;
        details.querySelector("select")?.focus();
      }
    });
    label.append(select);
    box.append(label);
    appendLinks(box,[["Board report chart data, "+report.figure,report.source],["Published report",report.report]]);
    mount.append(make("p","The latest published Board path uses swap quotes from "+dateLabel(report.dates[1])+", "+lag+" calendar "+(lag===1?"day":"days")+" before the event."),box);
  }
  if (!daily && !odds) {
    mount.append(make("p","A matched daily contract or meeting-probability pair is unavailable for this date. The Board row shows the published report’s two dated snapshots."));
  }
}

function fetchData() {
  if (!dataRequest) dataRequest = fetch(dataUrl).then(response => {
    if (!response.ok) throw Error("Unable to load pricing data");
    return response.json();
  }).catch(error => { dataRequest = undefined; throw error; });
  return dataRequest;
}

export async function mountEventExpectations(mount, {date} = {}) {
  if (!mount) return;
  mount.dataset.pricingDate = date || "";
  if (!date) { mount.replaceChildren(); return; }
  try {
    const data = await fetchData();
    if (mount.dataset.pricingDate === date) render(mount,data,date);
  } catch {
    if (mount.dataset.pricingDate === date) mount.replaceChildren(make("p","Policy pricing observations could not be loaded."));
  }
}

function init() {
  const mount = document.querySelector("#pc-expectations");
  if (!mount) return;
  const scope = mount.closest("#pre-event-curve");
  document.addEventListener("pre-event-date",event => {
    if (event.target === scope) mountEventExpectations(mount,{date:event.detail?.date});
  });
  mountEventExpectations(mount,{date:scope?.dataset.date});
}
if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",init,{once:true});
  else init();
}
