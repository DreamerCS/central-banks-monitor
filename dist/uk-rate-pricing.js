// Monetary Policy Reports, Table 1.B. Each vintage quotes a Q4 average to one decimal place.
const reports = [
  {name: "November 2023", date: "2 Nov 2023", cutoff: "24 Oct 2023", slug: "2023/november-2023", implied: {2024: 5.1, 2025: 4.5}},
  {name: "February 2024", date: "1 Feb 2024", cutoff: "23 Jan 2024", slug: "2024/february-2024", implied: {2024: 4.2, 2025: 3.4}},
  {name: "May 2024", date: "9 May 2024", cutoff: "29 Apr 2024", slug: "2024/may-2024", implied: {2024: 4.8, 2025: 4.3}}
];
const outcomes = {
  2024: {opening: 5, effectiveDate: "2024-11-07", newRate: 4.75, decision: "7 November 2024"},
  2025: {opening: 4, effectiveDate: "2025-12-18", newRate: 3.75, decision: "18 December 2025"}
};
const reportUrl = report => "https://www.bankofengland.co.uk/monetary-policy-report/" + report.slug;
const bankRateUrl = "https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp";

function node(tag, text) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  return element;
}
function link(text, href) {
  const a = node("a", text);
  a.href = href;
  return a;
}
function basisPoints(value) {
  const rounded = Math.round(100 * value);
  return (rounded > 0 ? "+" : rounded < 0 ? "−" : "") + Math.abs(rounded) + " bp";
}
function realisedQuarter(year) {
  const {opening, effectiveDate, newRate} = outcomes[year];
  const start = Date.UTC(year, 9, 1);
  const end = Date.UTC(year + 1, 0, 1);
  const change = Date.parse(effectiveDate + "T00:00:00Z");
  return (opening * (change - start) + newRate * (end - change)) / (end - start);
}

export function mountPricing(root) {
  root.classList.add("uk-pricing");
  const heading = node("h2", "What future Bank Rate did markets price?");
  const intro = node("p", "The MPC held Bank Rate at 5.25% on all three report dates. Choose a future quarter and track the rate investors priced for those same three months as new information arrived.");
  root.append(heading, intro);
  const controls = node("div");
  controls.className = "uk-controls";
  const label = node("label", "Target quarter ");
  const target = node("select");
  for (const year of [2024, 2025]) target.add(new Option(year + " Q4", year));
  label.append(target);
  const toggle = node("label");
  const reveal = node("input");
  reveal.type = "checkbox";
  toggle.append(reveal, " Show the realised quarter");
  controls.append(label, toggle);
  root.append(controls);
  const result = node("div");
  result.setAttribute("aria-live", "polite");
  root.append(result);
  function render() {
    const year = Number(target.value), actual = realisedQuarter(year);
    const table = node("table");
    const caption = table.createCaption();
    caption.textContent = year + " Q4 · average Bank Rate";
    const row = table.createTHead().insertRow();
    const headings = ["Report date", "Pricing window ended", "Market-implied rate", "Change since prior report"];
    if (reveal.checked) headings.push("Realised minus implied");
    for (const title of headings) {
      const cell = node("th", title);
      cell.scope = "col";
      row.append(cell);
    }
    const body = table.createTBody();
    reports.forEach((report, i) => {
      const line = body.insertRow(), value = report.implied[year];
      const header = node("th");
      header.scope = "row";
      header.append(link(report.date, reportUrl(report)));
      line.append(header);
      line.insertCell().textContent = report.cutoff;
      line.insertCell().textContent = value.toFixed(1) + "%";
      line.insertCell().textContent = i ? basisPoints(value - reports[i - 1].implied[year]) : "—";
      if (reveal.checked) line.insertCell().textContent = basisPoints(actual - value);
    });
    const wrap = node("div");
    wrap.className = "uk-scroll";
    wrap.append(table);
    result.replaceChildren(wrap);
    if (reveal.checked) {
      const {opening, newRate, decision} = outcomes[year];
      const outcome = node("p");
      outcome.className = "uk-outcome";
      outcome.append(node("strong", "Realised average " + actual.toFixed(2) + "%. "),
        "The quarter opened at " + opening.toFixed(2) + "%. On " + decision + " the rate fell to " + newRate.toFixed(2) + "%. The average weights each rate by calendar days in effect. ",
        link("Official rate changes", bankRateUrl));
      result.append(outcome);
    }
  }
  target.addEventListener("change", render);
  reveal.addEventListener("change", render);
  render();
  const method = node("p", "The Bank used a 15-working-day average of forward interest rates derived from overnight index swaps before each report. Table 1.B rounds each quarter to 0.1 percentage point; basis-point differences inherit that rounding. A forecast conditioning assumption describes market pricing. A meeting surprise requires prices immediately before and after the announcement.");
  method.className = "uk-method";
  root.append(method);
  const interpretation = node("p", "A multi-year overnight swap reflects both expected future overnight rates and the price of bearing interest-rate risk. The MPC used the market path to construct its forecasts and retained discretion over its next decision.");
  const details = node("details");
  details.append(node("summary", "Interpreting the forward curve"), interpretation);
  root.append(details, giltComparison(), link("See daily SONIA forward pricing before individual UK speeches", "market-reactions.html#pre-speech-sonia"), document.createTextNode(" · "), link("Trace the same repricing into UK mortgages and deposits", "macro-history.html?view=uk-credit"));
}

// Last trading day of each UK financial year. Yields are DMO fitted nominal par yields.
const giltHistory = [
  {date: "31 Mar 2022", rate: 0.75, five: 1.45, ten: 1.62, report: "wipjxglr/gar2022_final.pdf"},
  {date: "31 Mar 2023", rate: 4.25, five: 3.45, ten: 3.50, report: "tfidb5fy/gar2023.pdf"},
  {date: "28 Mar 2024", rate: 5.25, five: 3.81, ten: 3.91, report: "5rqb2scf/gar2024_final.pdf"},
  {date: "31 Mar 2025", rate: 4.50, five: 4.19, ten: 4.64, report: "dmgaetip/gar2025a.pdf"}
];

function giltComparison() {
  const details = node("details");
  details.id = "uk-gilt-slope";
  details.append(node("summary", "Did a steeper UK gilt curve signal cuts?"));
  const table = node("table");
  table.createCaption().textContent = "UK financial year-end · fitted nominal par yields";
  const headerRow = table.createTHead().insertRow();
  for (const label of ["Observation", "Bank Rate", "5-year gilt", "10-year gilt", "10Y minus 5Y"]) {
    const th = node("th", label);
    th.scope = "col";
    headerRow.append(th);
  }
  const body = table.createTBody();
  for (const point of giltHistory) {
    const row = body.insertRow(), th = node("th");
    th.scope = "row";
    const source = link(point.date, "https://www.dmo.gov.uk/media/" + point.report);
    source.title = "Debt Management Office annual review, nominal par gilt curve, Chart " + (point.date.endsWith("2025") ? "2" : "1");
    th.append(source);
    row.append(th);
    for (const value of [point.rate, point.five, point.ten]) row.insertCell().textContent = value.toFixed(2) + "%";
    row.insertCell().textContent = basisPoints(point.ten - point.five);
  }
  const wrap = node("div");
  wrap.className = "uk-scroll";
  wrap.append(table);
  const sources = node("p");
  sources.append("Each dated link opens the Debt Management Office annual review. Its fitted par curve reports the yields of hypothetical bonds priced at face value. ",
    link("Bank Rate change dates", bankRateUrl));
  details.append(wrap,
    node("p", "The spread narrowed by 12 basis points through March 2023 as the five-year yield rose faster than the ten-year. It then widened by 5 basis points while Bank Rate rose another percentage point. Through March 2025 the spread widened a further 35 basis points even as Bank Rate fell 75. Both gilt yields rose in that final year, with the ten-year rising more."),
    node("p", "Annual endpoints cannot isolate a policy announcement. In early 2025 the DMO observed UK yields tracking international markets, especially the US. Comparing sterling overnight swaps with gilt yields at the same maturities would help distinguish a new policy path from changes in the compensation for holding longer bonds."), sources);
  return details;
}

const products = {
  mortgage: {
    title: "Fixed-rate mortgages",
    periods: [
      "The quotes available to new borrowers fell as wholesale reference rates eased. Borrowers already on fixed contracts faced a different timetable. In the Bank’s household survey, just over 30% of mortgagors still waiting for their deal to expire said they had already cut spending.",
      "Around 85% of outstanding UK mortgages had a fixed rate. New fixed-rate quotes fell again with the two-year overnight index swap rate. The Bank saw signs of unusually fast initial pass-through, but lender competition could also explain the move.",
      "Quoted rates rose again as two-year funding benchmarks moved up. Someone refinancing a cheap older loan could still face a higher bill even when the new quote was below the previous summer’s peak."
    ],
    test: "Compare like-for-like new quotes with the two-year swap, then compare effective rates on outstanding loans with the schedule of fixed deals expiring. New quotes measure the price of the next contract. The expiry schedule determines when payments on the stock can reset."
  },
  savings: {
    title: "Fixed and instant-access savings",
    periods: [
      "Instant-access rates had risen about 90 basis points between June and October as earlier Bank Rate rises fed through. The Bank also pointed to the regulator’s cash-savings action plan as a possible influence on competition for deposits.",
      "The quoted rate on two-year fixed savings bonds had fallen around 100 basis points since the November report. Instant-access deposit rates edged higher even as the fixed quotes fell.",
      "New fixed savings rates changed little from February. Instant-access accounts made up around two thirds of household deposits. Their aggregate rate had levelled off about 2½ percentage points below Bank Rate."
    ],
    test: "Match fixed savings bonds to two-year swaps and instant-access accounts to current Bank Rate. Compare advertised offers with effective rates on existing balances and check whether households shifted between accounts. An advertised rate alone does not measure aggregate interest income."
  }
};

export function ukCredit() {
  const article = node("article");
  article.id = "uk-rate-pass-through";
  article.className = "uk-pricing uk-credit";
  article.append(node("h2", "How future rate cuts reached UK households"),
    node("p", "Bank Rate stayed at 5.25% between the November 2023 and May 2024 reports. Market pricing for 2024 Q4 moved down 90 basis points and then back up 60. Fixed mortgages, fixed savings products and instant-access deposits adjusted at different speeds."));
  const label = node("label", "Household product ");
  const select = node("select");
  for (const [key, product] of Object.entries(products)) select.add(new Option(product.title, key));
  label.append(select);
  const controls = node("div");
  controls.className = "uk-controls";
  controls.append(label);
  const result = node("div");
  result.setAttribute("aria-live", "polite");
  article.append(controls, result);
  function render() {
    const product = products[select.value], story = node("ol");
    story.className = "uk-stages";
    const charts = ["2.6", "2.7", "2.8"];
    product.periods.forEach((text, i) => {
      const item = node("li");
      const sourceTitle = i === 0 && select.value === "mortgage" ? "Chart 2.6 and §3.3" : "Chart " + charts[i];
      item.append(node("h3", reports[i].name), node("p", text), link(sourceTitle, reportUrl(reports[i])));
      story.append(item);
    });
    result.replaceChildren(story, node("h3", "What would test that explanation?"), node("p", product.test));
  }
  select.addEventListener("change", render);
  render();
  const transmission = node("p", "A change in the expected path of Bank Rate can move the two-year reference rate immediately. The effect on household cash flows depends on lenders’ spreads, the date each loan reprices and the balance still outstanding.");
  transmission.className = "uk-method";
  article.append(transmission, link("Compare the dated market paths with realised Bank Rate", "historical-data.html#uk-bank-rate-pricing"));
  return article;
}
