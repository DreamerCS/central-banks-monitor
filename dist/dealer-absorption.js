const byId = id => document.getElementById(id);
const issue = byId('da-type');
const regime = byId('da-regime');
const reference = byId('da-baseline');
const auction = byId('da-auction');
const statusText = byId('da-status');
const dateFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'
});
const formatDate = date => dateFormat.format(new Date(date + 'T00:00:00Z'));
const groups = ['High', 'Middle', 'Low'];
const reportNames = {
  preTrend: 'One week before auction baseline', baseline: 'Last report before auction',
  preSettlement: 'Last report before settlement', settlement: 'First report on/after settlement',
  week1: 'One week later', week2: 'Two weeks later', week3: 'Three weeks later'
};
let events, sameSecurities, visible = [], aggregates = [], periodLabels = new Map();

function textElement(tag, content) {
  const node = document.createElement(tag);
  node.textContent = content;
  return node;
}

function signed(value, places = 2) {
  if (value === null || !Number.isFinite(value)) return '—';
  const magnitude = Math.abs(value).toFixed(places);
  if (Number(magnitude) === 0) return magnitude;
  return (value > 0 ? '+' : '−') + magnitude;
}

function change(event, stage) {
  const base = event.reports[reference.value]?.positionBn;
  const value = event.reports[stage]?.positionBn;
  return Number.isFinite(base) && Number.isFinite(value) ? value - base : null;
}

function median(observations) {
  if (!observations.length) return null;
  const sorted = [...observations].sort((a,b) => a-b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function row(cells) {
  const tr = document.createElement('tr');
  const head = textElement('th', cells[0]);
  head.scope = 'row';
  tr.append(head, ...cells.slice(1).map(value => textElement('td', value)));
  return tr;
}

function updateAddress() {
  const url = new URL(location.href);
  const params = {type:issue.value, period:regime.value, from:reference.value, auction:auction.value};
  Object.entries(params).forEach(([key, value]) => {
    if (!value || value === 'all' || value === 'baseline') url.searchParams.delete(key);
    else url.searchParams.set(key, value);
  });
  history.replaceState(null, '', url);
}

function selectValue(select, value) {
  if (value && [...select.options].some(option => option.value === value)) select.value = value;
}

function drawFigure() {
  const plot = byId('da-plot');
  const width = Math.min(940, Math.max(288, plot.clientWidth || 680));
  const compact = width < 530;
  const height = compact ? 215 : 255;
  const left = compact ? 35 : 50, right = compact ? 13 : 29;
  const top = 18, bottom = height - 34;
  const points = aggregates.flatMap(item => [item.High.value, item.Low.value]).filter(Number.isFinite);
  if (!points.length) {
    plot.textContent = 'No matched observations for these settings.';
    return;
  }
  const min = Math.min(0, ...points), max = Math.max(0, ...points);
  const rough = Math.max((max-min)/4, .1);
  const order = 10 ** Math.floor(Math.log10(rough));
  const step = ([1,2,5,10].find(value => value * order >= rough) || 10) * order;
  const bottomTick = Math.floor(min / step) * step, topTick = Math.max(bottomTick + step, Math.ceil(max / step) * step);
  const y = value => top - (value - topTick) / (topTick - bottomTick) * (bottom - top);
  const x = index => left + (width - left - right) * index / (aggregates.length - 1);
  const ns = 'http://www.w3.org/2000/svg';
  function shape(tag, attrs, text) {
    const element = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([key,value]) => element.setAttribute(key, value));
    if (text != null) element.textContent = text;
    return element;
  }
  const svg = shape('svg', {viewBox:'0 0 '+width+' '+height,role:'img','aria-labelledby':'da-chart-title da-chart-desc'});
  svg.append(shape('title',{id:'da-chart-title'},'Weekly changes in net Treasury positions by auction award share'),
    shape('desc',{id:'da-chart-desc'},'Ordinary lines compare high and low award shares. Exact values and sample counts are in the table that follows.'));
  for (let tick = bottomTick; tick <= topTick + step/10; tick += step) {
    const zero = Math.abs(tick) < step/10;
    svg.append(shape('line',{x1:left,y1:y(tick),x2:width-right,y2:y(tick),stroke:zero?'#6c786c':'#c7cfc2','stroke-width':zero?1.4:1}),
      shape('text',{x:left-5,y:y(tick)+4,'text-anchor':'end'},signed(tick,step < 1 ? 1 : 0)));
  }
  aggregates.forEach((item,index) => {
    svg.append(shape('text',{x:x(index),y:height-9,'text-anchor':index === 0 ? 'start' : index === aggregates.length-1 ? 'end' : 'middle'},compact?item.short:item.axis));
  });
  for (const group of ['High','Low']) {
    const colour = group === 'High' ? '#24573e' : '#93502f';
    let path = '', open = false;
    const markers = [];
    aggregates.forEach((item,index) => {
      const value = item[group].value;
      if (!Number.isFinite(value)) {open = false;return;}
      path += (open ? 'L' : 'M') + x(index) + ' ' + y(value) + ' ';
      open = true;
      const marker = shape('circle',{cx:x(index),cy:y(value),r:group==='High'?3.7:2.8,fill:group==='High'?colour:'#f7f8ee',stroke:colour,'stroke-width':1.7});
      marker.append(shape('title',{},group+' award share · '+item.label+' · '+signed(value)+' US$ billion, '+item[group].count+' auctions'));
      markers.push(marker);
    });
    svg.append(shape('path',{d:path,fill:'none',stroke:colour,'stroke-width':2.5,'stroke-dasharray':group==='High'?'none':'7 4'}),...markers);
  }
  plot.replaceChildren(svg);
}

function settledSample() {
  const matched = events.filter(event => sameSecurities[event.auctionDate] &&
    (regime.value === 'all' || regime.value === event.regime));
  const summaryRows = [];
  for (const key of ['settlement','week1','week2','week3']) {
    const cells = [reportNames[key]];
    for (const group of ['All',...groups]) {
      const changes = matched.filter(event => group === 'All' || group === event.awardGroup)
        .map(event => sameSecurities[event.auctionDate].reports[key]?.changeBn).filter(Number.isFinite);
      const typical = median(changes);
      cells.push(signed(typical)+' ('+changes.length+')');
      if (key === 'settlement' && group === 'All') {
        const numberUp = changes.filter(value => value > 0).length;
        const stillShort = matched.filter(event => {
          const observation = sameSecurities[event.auctionDate].reports.settlement;
          return observation && observation.changeBn > 0 && observation.positionBn < 0;
        }).length;
        byId('da-settled-summary').textContent = changes.length
          ? 'At the first report on or after settlement, '+numberUp+' of '+changes.length+' reopenings had a larger net settled position than at the preceding report. The median change was '+signed(typical)+' US$ billion. In '+stillShort+' of the '+numberUp+' increases, dealers were still net short after settlement.'
          : 'No reopening observations available for this reporting period.';
      }
    }
    summaryRows.push(row(cells));
  }
  byId('da-settled-table').replaceChildren(...summaryRows);
}

function showEvent() {
  const selected = visible.find(event => event.auctionDate === auction.value);
  byId('da-settled-event').hidden = true;
  if (!selected) {
    byId('da-instance').textContent = 'No auction matches these filters.';
    byId('da-event-table').replaceChildren();
    return;
  }
  const amount = value => Number.isFinite(value) ? '$'+value.toFixed(2)+'bn' : 'an unavailable amount';
  const label = periodLabels.get(selected.regime) || selected.regime;
  byId('da-instance').textContent = selected.issueType+' · '+selected.cusip+' · '+label+'. On '+formatDate(selected.auctionDate)+', primary dealers won '+amount(selected.dealerAwardBn)+' of '+amount(selected.competitiveAwardBn)+' in accepted competitive bids ('+selected.dealerSharePct.toFixed(1)+'%, '+selected.awardGroup.toLowerCase()+' group). The issue settled on '+formatDate(selected.issueDate)+'.';
  if (selected.resultsUrl) {
    const link = textElement('a','Treasury auction result (PDF)');
    link.href = selected.resultsUrl;
    byId('da-instance').append(document.createTextNode(' '),link);
  }
  const beforeAuction = selected.reports.baseline, beforeIssue = selected.reports.preSettlement;
  const afterIssue = selected.reports.settlement;
  if (beforeAuction && beforeIssue && afterIssue && beforeAuction.date !== beforeIssue.date) {
    const auctionChange = afterIssue.positionBn - beforeAuction.positionBn;
    const issueChange = afterIssue.positionBn - beforeIssue.positionBn;
    byId('da-instance').append(textElement('p','At the '+formatDate(afterIssue.date)+' report, net holdings had changed by '+signed(auctionChange)+' US$ billion since the last pre-auction report and '+signed(issueChange)+' US$ billion since the last pre-settlement report.'));
  }
  const rows = Object.entries(reportNames).map(([key,label]) => {
    const report = selected.reports[key];
    return row([label,report ? formatDate(report.date) : (selected.unavailable?.[key] || '—'),report ? signed(report.positionBn) : '—',signed(change(selected,key))]);
  });
  byId('da-event-table').replaceChildren(...rows);
  const matched = sameSecurities[selected.auctionDate];
  if (matched && matched.cusip === selected.cusip) {
    const settledRows = Object.entries(matched.reports).map(([key,report]) =>
      row([reportNames[key],formatDate(report.date),signed(report.positionBn),signed(report.changeBn)]));
    byId('da-settled-event-table').replaceChildren(...settledRows);
    byId('da-settled-event').hidden = false;
  }
}

function showSample(preferredDate) {
  visible = events.filter(event => (issue.value === 'all' || issue.value === event.issueType) &&
    (regime.value === 'all' || regime.value === event.regime));
  const options = [...visible].reverse().map(event => new Option(formatDate(event.auctionDate)+' · '+event.issueType,event.auctionDate));
  auction.replaceChildren(...options);
  const recentComplete = [...visible].reverse().find(event => event.reports.week2 && event.reports.settlement);
  selectValue(auction, recentComplete?.auctionDate);
  selectValue(auction, preferredDate);
  const earlier = reference.value === 'baseline'
    ? {key:'preTrend',label:'One week before reference (earlier level less reference)',axis:'Prior week',short:'Prior'}
    : {key:'baseline',label:'Last report before auction',axis:'Pre-auction',short:'Prior'};
  const stageList = [
    earlier,
    {key:reference.value,label:reportNames[reference.value],axis:'Reference',short:'Ref.'},
    {key:'settlement',label:reportNames.settlement,axis:'Settlement report',short:'Settle.'},
    {key:'week1',label:reportNames.week1,axis:'+1 week',short:'+1w'},
    {key:'week2',label:reportNames.week2,axis:'+2 weeks',short:'+2w'},
    {key:'week3',label:reportNames.week3,axis:'+3 weeks',short:'+3w'}
  ];
  const grouped = Object.fromEntries(groups.map(group => [group,visible.filter(event => event.awardGroup === group)]));
  aggregates = stageList.map(stage => {
    const summary = {...stage};
    groups.forEach(group => {
      const values = grouped[group].map(event => change(event,stage.key)).filter(Number.isFinite);
      summary[group] = {value:median(values),count:values.length};
    });
    return summary;
  });
  byId('da-count').textContent = visible.length
    ? visible.length+' auctions from '+formatDate(visible[0].auctionDate)+' to '+formatDate(visible.at(-1).auctionDate)+'.'
    : 'No auctions in this selection.';
  byId('da-group-table').replaceChildren(...aggregates.map(stage => row([stage.label,...groups.map(group =>
    signed(stage[group].value)+' ('+stage[group].count+')')])));
  const early = aggregates.find(stage => stage.key === 'settlement');
  const late = aggregates.find(stage => stage.key === 'week1');
  const gap = item => Number.isFinite(item.High.value) && Number.isFinite(item.Low.value) ? item.High.value - item.Low.value : null;
  const firstGap = gap(early), laterGap = gap(late);
  byId('da-finding').textContent = Number.isFinite(firstGap) && Number.isFinite(laterGap)
    ? 'Measured from the '+reportNames[reference.value].toLowerCase()+', the high-minus-low gap between median position changes was '+signed(firstGap)+' US$ billion at the settlement report and '+signed(laterGap)+' US$ billion one week later.'
    : 'At least one award group has no matched report at these horizons. The table shows the available observations.';
  drawFigure();
  settledSample();
  showEvent();
}

async function initialise() {
  try {
    const response = await fetch('data/dealer-absorption.json');
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    events = [...data.events].sort((a,b) => a.auctionDate.localeCompare(b.auctionDate));
    sameSecurities = data.sameSecurity.events;
    if (!events.length) throw new Error('No auctions');
    for (const info of data.regimes || []) {
      if (typeof info === 'string') periodLabels.set(info,info);
      else periodLabels.set(info.id || info.regime, info.label || info.name || info.id || info.regime);
    }
    byId('da-cutoffs').replaceChildren(...data.groupCutoffs.map(group =>
      row([periodLabels.get(group.regime) || group.regime,group.issueType,String(group.n),
        group.lowMaxPct.toFixed(2)+'%',group.highMinPct.toFixed(2)+'%'])));
    byId('da-threshold-table').hidden=false;
    const keys = [...new Set(events.map(event => event.regime))];
    keys.forEach(key => regime.add(new Option(periodLabels.get(key) || key,key)));
    const query = new URLSearchParams(location.search);
    selectValue(issue,query.get('type'));
    selectValue(regime,query.get('period'));
    selectValue(reference,query.get('from'));
    statusText.hidden=true;
    byId('da-interactive').hidden=false;
    showSample(query.get('auction') || '2020-03-11');
    for (const select of [issue,regime,reference]) select.addEventListener('change',() => {
      showSample(auction.value);
      updateAddress();
    });
    auction.addEventListener('change', () => {showEvent();updateAddress();});
    if (window.ResizeObserver) new ResizeObserver(drawFigure).observe(byId('da-plot'));
  } catch {
    statusText.textContent = 'The auction comparison could not load. Reload the page or use the data download and sources below.';
  }
}

initialise();
