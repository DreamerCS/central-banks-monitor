(() => {
  'use strict';
  let request;
  const element = (tag, content) => {
    const node = document.createElement(tag);
    if (content !== undefined) node.textContent = content;
    return node;
  };
  function position(rows, date, after) {
    let start = 0, end = rows.length;
    while (start < end) {
      const mid = Math.floor((start + end) / 2);
      if (rows[mid][0] < date || (after && rows[mid][0] === date)) start = mid + 1;
      else end = mid;
    }
    return start;
  }
  function delta(a, b) {
    const n = Math.round((b - a) * 100);
    return (n > 0 ? '+' : n < 0 ? '−' : '') + '$' + (Math.abs(n) / 100).toFixed(2);
  }
  function draw(host, day, data) {
    const box = element('details');
    box.className = 'oil-event-context';
    box.append(element('summary', 'Oil prices before and after this date'));
    box.append(element('p', 'Brent and WTI spot assessments in US dollars per barrel. The last quote before the event date and first quote afterwards span the entire event day, including other news. Every event on the same date shares this comparison.'));
    const scroller = element('div');
    scroller.style.overflowX = 'auto';
    const table = element('table');
    const header = element('tr');
    for (const label of ['Benchmark', 'Before', 'After', 'Change across dates', 'Change into event¹']) {
      const th = element('th', label); th.scope = 'col'; header.append(th);
    }
    const head = element('thead'); head.append(header); table.append(head);
    const body = element('tbody');
    for (const asset of data.assets) {
      const rows = asset.rows, i = position(rows, day, false) - 1, j = position(rows, day, true);
      const prev = rows[i], next = rows[j], earlier = rows[i-5];
      const tr = element('tr'), th = element('th'), link = element('a', asset.label);
      th.scope = 'row'; link.href = asset.url; th.append(link); tr.append(th);
      for (const value of [prev, next]) tr.append(element('td', value ? '$' + value[1].toFixed(2) + ' · ' + value[0] : 'Unavailable'));
      tr.append(element('td', prev && next ? delta(prev[1], next[1]) : 'Unavailable'));
      tr.append(element('td', prev && earlier ? delta(earlier[1], prev[1]) + ' since ' + earlier[0] : 'Unavailable'));
      body.append(tr);
    }
    table.append(body); scroller.append(table); box.append(scroller, element('p', '¹ From five published quote intervals before the last pre-event assessment. The US Energy Information Administration publishes both series.'));
    host.replaceChildren(box);
  }
  window.CBICommodityContext = {async render(host, day) {
    if (!host || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return;
    host.dataset.oilDate = day;
    try {
      request ??= fetch('data/commodity-event-days.json').then(r => {
        if (!r.ok) throw Error('Oil data unavailable');
        return r.json();
      });
      const data = await request;
      if (host.dataset.oilDate === day) draw(host, day, data);
    } catch {
      request = undefined;
      if (host.dataset.oilDate === day) host.textContent = 'Daily spot oil observations are unavailable.';
    }
  }};
})();
