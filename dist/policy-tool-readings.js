(() => {
  'use strict';
  let source;
  function element(tag, value) {
    const e = document.createElement(tag);
    if (value !== undefined) e.textContent = value;
    return e;
  }
  window.CBIPolicyTools = {async render(container, event) {
    if (!container || !event) return;
    const bank = event.bank || event._package?.bank;
    const key = [bank, event.id, event.date, event.stage].join('/');
    container.dataset.toolEvent = key;
    container.replaceChildren();
    try {
      source ??= fetch('data/policy-tool-readings.json').then(r => {
        if (!r.ok) throw Error('Tool evidence unavailable');
        return r.json();
      });
      const data = await source;
      if (container.dataset.toolEvent !== key) return;
      const readings = data.records.filter(row => row.bank === bank && row.date === event.date &&
        row.stage === event.stage && (!row.eventId || row.eventId === event.id));
      if (!readings.length) return;
      const section = element('section');
      section.append(element('h3', 'Policy tools beyond the rate decision'));
      for (const r of readings) {
        const p = element('p'); p.append(element('strong', r.channel + ' · ' + r.reading));
        section.append(p, element('p', r.evidence));
        const a = element('a', 'Official source'); a.href = r.url; section.append(a);
      }
      container.append(section);
    } catch {
      source = undefined;
    }
  }};
})();
