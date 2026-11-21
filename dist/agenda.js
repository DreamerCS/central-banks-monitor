(() => {
  'use strict';
  const root = document.querySelector('#speech-agenda');
  if (!root) return;

  const zone = 'Europe/London';
  const formatter = options => new Intl.DateTimeFormat('en-GB', { timeZone: zone, ...options });
  const dayParts = formatter({ year: 'numeric', month: '2-digit', day: '2-digit' });
  const shortDate = formatter({ day: 'numeric', month: 'short' });
  const weekday = formatter({ weekday: 'short', day: 'numeric', month: 'short' });
  const clock = formatter({ hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const agencies = {
    BLS: ['US', 'https://www.bls.gov/schedule/'],
    BEA: ['US', 'https://www.bea.gov/news/schedule'],
    ONS: ['UK', 'https://www.ons.gov.uk/releasecalendar'],
    Eurostat: ['Euro area', 'https://ec.europa.eu/eurostat/news/euro-indicators/release-calendar']
  };
  const speakingSources = new Map([
    ['European Central Bank', 'https://www.ecb.europa.eu/press/calendars/weekly/html/index.en.html'],
    ['Federal Reserve', 'https://www.federalreserve.gov/newsevents/calendar.htm'],
    ['Bank of England', 'https://www.bankofengland.co.uk/events/upcoming-events'],
    ['Bank of Canada', 'https://www.bankofcanada.ca/press/upcoming-events/']
  ]);
  const feeds = {
    speech: { state: 'loading', events: [] },
    data: { state: 'loading', events: [], sources: [] }
  };
  let filter = 'all';
  let expanded = false;
  let generation = 0;
  let previousView = '';

  function node(tag, className, value) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value != null) el.textContent = value;
    return el;
  }

  function safeUrl(raw) {
    try {
      const url = new URL(raw);
      if (url.protocol === 'https:' && !url.username && !url.password) return url.href;
    } catch { /* Unknown publisher links have no destination. */ }
    return '';
  }

  function link(title, url, className) {
    const el = node('a', className, title);
    el.href = url;
    return el;
  }

  function londonDate(value) {
    const parts = Object.fromEntries(dayParts.formatToParts(value).map(p => [p.type, p.value]));
    return parts.year + '-' + parts.month + '-' + parts.day;
  }

  function midday(day) { return Date.parse(day + 'T12:00:00Z'); }
  function validDay(day) {
    return /^\d{4}-\d{2}-\d{2}$/.test(day) && Number.isFinite(midday(day))
      && new Date(midday(day)).toISOString().slice(0, 10) === day;
  }
  function sumDays(day, offset) {
    const value = new Date(midday(day));
    value.setUTCDate(value.getUTCDate() + offset);
    return value.toISOString().slice(0, 10);
  }

  function events(rows, kind, sources = []) {
    const byId = new Map();
    for (const r of rows) {
      if (!r || !validDay(r.date) || !r.title || !safeUrl(r.source)) continue;
      const stamp = kind === 'speech' ? r.at : r.start;
      const timestamp = stamp && /(?:Z|[+-]\d{2}:\d{2})$/i.test(stamp) ? Date.parse(stamp) : NaN;
      const ms = Number.isFinite(timestamp) ? timestamp : null;
      const day = ms == null ? r.date : londonDate(ms);
      let type, owner, verified, retained = false;
      if (kind === 'speech') {
        if (!r.bank || !r.speaker) continue;
        type = r.eventType || (/speech text release/i.test(r.title) ? 'Speech text release' : '');
        owner = r.bank;
        retained = r.sourceStatus === 'retained';
        verified = !retained;
      } else {
        if (!r.agency || !r.id) continue;
        const s = sources.find(s => s.agency === r.agency);
        verified = s?.status === 'verified' && Boolean(s.verifiedFrom && s.verifiedThrough)
          && r.date >= s.verifiedFrom && r.date <= s.verifiedThrough;
        retained = s?.status === 'stale' || (s?.status === 'verified' && !verified);
        type = 'Economic data';
        owner = r.agency;
      }
      const key = kind === 'data' ? r.agency + '/' + r.id : [r.bank, r.speaker, r.title, r.date, stamp || ''].join('|');
      const textOnly = kind === 'speech' && type.toLowerCase() === 'speech text release';
      byId.set(key, { key, kind, date: day, ms, title: r.title, href: safeUrl(r.source), type,
        owner, country: r.country, speaker: r.speaker, verified, retained, textOnly,
        timeQualifier: r.timeQualifier, lastVerifiedAt: r.lastVerifiedAt });
    }
    return [...byId.values()];
  }

  function compare(a, b) {
    return a.date.localeCompare(b.date) || (a.ms ?? Infinity) - (b.ms ?? Infinity)
      || a.owner.localeCompare(b.owner) || a.title.localeCompare(b.title);
  }

  function remaining(ms) {
    const total = Math.max(1, Math.ceil(ms / 60000));
    const d = Math.floor(total / 1440);
    const h = Math.floor(total % 1440 / 60);
    const m = total % 60;
    return 'In ' + (d ? d + 'd ' : '') + (d || h ? h + 'h ' : '') + m + 'm';
  }

  const rail = node('div', 'wa-rail');
  const period = node('p', 'wa-period');
  const filters = node('div', 'wa-filters');
  filters.setAttribute('role', 'group');
  filters.setAttribute('aria-label', 'Filter calendar events');
  const filterButtons = [];
  for (const [value, label] of [['all', 'All'], ['speech', 'Speeches'], ['data', 'Economic data']]) {
    const button = node('button', '', label);
    button.type = 'button';
    button.dataset.agendaFilter = value;
    button.setAttribute('aria-pressed', String(value === filter));
    button.addEventListener('click', () => {
      if (filter === value) return;
      filter = value;
      expanded = false;
      for (const b of filterButtons) b.setAttribute('aria-pressed', String(b === button));
      render();
      if (list.animate && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        list.animate([{ opacity: .68, transform: 'translateY(-3px)' }, { opacity: 1, transform: 'translateY(0)' }],
          { duration: 160, easing: 'ease-out' });
      }
    });
    filters.append(button);
    filterButtons.push(button);
  }
  rail.append(period, filters);
  const clocks = node('div', 'wa-clocks');
  const list = node('div', 'wa-list');
  list.id = 'wa-events';
  const more = node('button', 'wa-toggle');
  more.type = 'button';
  more.hidden = true;
  more.setAttribute('aria-controls', list.id);
  more.addEventListener('click', () => { expanded = !expanded; render(); });
  const foot = node('div', 'wa-foot');
  const sources = node('details', 'wa-sources');
  const sourceBody = node('div', 'wa-source-body');
  sources.append(node('summary', '', 'Sources and coverage'), sourceBody);
  foot.append(sources, link('Trading Economics calendar', 'https://tradingeconomics.com/calendar', 'wa-external'));
  root.replaceChildren(rail, clocks, list, more, foot);

  function sourceNotes() {
    const sourceList = node('ul');
    for (const [agency, [country, fallback]] of Object.entries(agencies)) {
      const info = feeds.data.sources.find(s => s.agency === agency);
      const item = node('li');
      item.append(link(agency + ' · ' + country, safeUrl(info?.url) || fallback));
      let status = feeds.data.state === 'loading' ? 'Loading schedule' : 'Schedule unavailable';
      if (info?.status === 'verified') status = 'Verified ' + (info.lastVerifiedAt || '').slice(0, 10);
      if (info?.status === 'stale') status = 'Saved schedule · last verified ' + (info.lastVerifiedAt || '').slice(0, 10);
      if (info?.verifiedThrough) status += ' · coverage through ' + info.verifiedThrough;
      item.append(node('span', '', status));
      if (info?.scope) item.append(node('small', '', info.scope));
      sourceList.append(item);
    }
    const officials = node('p', 'wa-speaking-links');
    officials.append(document.createTextNode('Speaking calendars · '));
    for (const [name, url] of speakingSources) officials.append(link(name, url), document.createTextNode(' '));
    sourceBody.replaceChildren(sourceList, officials);
  }

  function noteFor(item) {
    const labels = item.kind === 'data' ? [item.owner, item.country] : [item.owner, item.type];
    if (item.timeQualifier) labels.push(item.timeQualifier);
    if (item.retained) labels.push('Saved schedule' + (item.lastVerifiedAt ? ' · last checked ' + item.lastVerifiedAt.slice(0, 10) : ''));
    return labels.filter(Boolean).join(' · ');
  }

  function titleFor(item) {
    return item.speaker ? item.speaker + ' · ' + item.title : item.title;
  }

  function emptyMessage(kind) {
    if (feeds[kind].state === 'loading') return 'Loading the official schedule…';
    if (feeds[kind].state === 'failed') return 'Official schedule unavailable.';
    if (kind === 'data' && feeds.data.sources.every(s => s.status !== 'verified')) return 'No current source verification.';
    return 'No upcoming time confirmed.';
  }

  function nextCard(kind, future, end, now) {
    const card = node('section', 'wa-clock');
    card.dataset.kind = kind;
    const eligible = future.filter(e => e.kind === kind && e.verified && !e.textOnly);
    const timed = eligible.filter(e => e.ms !== null).sort((a, b) => a.ms - b.ms);
    const first = timed[0] || eligible[0];
    const undatedClock = timed.length ? eligible.find(item => item.ms === null && item.date <= first.date) : null;
    let caption = kind === 'speech' ? 'Next speech' : 'Next data';
    if (undatedClock) caption = kind === 'speech' ? 'Next timed speech' : 'Next timed release';
    card.setAttribute('aria-label', caption);
    card.append(node('p', 'wa-clock-label', caption));
    if (!first) {
      card.append(node('p', 'wa-empty', emptyMessage(kind)));
      return card;
    }
    const simultaneous = first.ms === null ? [first] : timed.filter(e => e.ms === first.ms);
    const timer = node('p', 'wa-remaining', first.ms === null ? 'Time TBA' : remaining(first.ms - now));
    if (first.ms !== null) timer.dataset.at = String(first.ms);
    card.append(timer);
    const when = node('time', 'wa-clock-date',
      weekday.format(midday(first.date)) + (first.ms === null ? '' : ' · ' + clock.format(first.ms) + ' London') +
      (first.date > end ? ' · After this week' : ''));
    when.dateTime = first.ms === null ? first.date : new Date(first.ms).toISOString();
    card.append(when);
    for (const e of simultaneous) {
      const row = node('div', 'wa-clock-event');
      row.append(link(titleFor(e), e.href), node('span', 'wa-meta', noteFor(e)));
      card.append(row);
    }
    if (undatedClock) {
      const notice = node('div', 'wa-unscheduled-time');
      const day = weekday.format(midday(undatedClock.date));
      const context = undatedClock.date === first.date ? 'Also on ' : 'Earlier date · ';
      notice.append(node('span', '', context + day + ' · Time TBA'),
        link(titleFor(undatedClock), undatedClock.href));
      card.append(notice);
    }
    return card;
  }

  function dayRows(items) {
    const fragment = document.createDocumentFragment();
    let lastDay, entries;
    for (const item of items) {
      if (lastDay !== item.date) {
        const day = node('div', 'wa-day');
        const date = node('time', 'wa-day-label', weekday.format(midday(item.date)));
        date.dateTime = item.date;
        entries = node('ul', 'wa-day-entries');
        entries.setAttribute('aria-label', date.textContent);
        day.append(date, entries); fragment.append(day);
        lastDay = item.date;
      }
      const row = node('li', 'wa-row');
      row.dataset.id = item.key;
      const when = node('time', 'wa-row-time', item.ms === null ? 'Time TBA' : clock.format(item.ms));
      when.dateTime = item.ms === null ? item.date : new Date(item.ms).toISOString();
      const detail = node('div', 'wa-row-detail');
      detail.append(link(titleFor(item), item.href), node('span', 'wa-meta', noteFor(item)));
      row.append(when, detail); entries.append(row);
    }
    return fragment;
  }

  function compactRows(items) {
    if (items.length <= 8) return items;
    // Include the first speaking and data entry for every day, plus its simultaneous releases.
    const firstByKind = new Set();
    const slots = new Set();
    const selected = new Set();
    for (const item of items) {
      const category = item.date + '/' + item.kind;
      if (firstByKind.has(category)) continue;
      firstByKind.add(category);
      selected.add(item.key);
      if (item.ms !== null) slots.add(item.ms);
    }
    return items.filter(item => selected.has(item.key) || slots.has(item.ms));
  }

  function render() {
    const now = Date.now();
    const today = londonDate(now), end = sumDays(today, 6);
    const future = [...feeds.speech.events, ...feeds.data.events]
      .filter(e => e.ms !== null ? e.ms > now : e.date >= today).sort(compare);
    const signature = [today, generation, filter, expanded, future.map(e => e.key).join('\n')].join('|');
    if (previousView === signature) {
      for (const timer of clocks.querySelectorAll('[data-at]')) timer.textContent = remaining(Number(timer.dataset.at) - now);
      return;
    }
    previousView = signature;
    period.textContent = shortDate.format(midday(today)) + ' – ' + shortDate.format(midday(end)) + ' · London time';
    clocks.replaceChildren(nextCard('speech', future, end, now), nextCard('data', future, end, now));
    const matching = future.filter(e => e.date <= end && (filter === 'all' || (e.kind === filter && !e.textOnly)));
    const compact = compactRows(matching);
    const visible = expanded ? matching : compact;
    const partial = [];
    if (filter !== 'data') {
      if (feeds.speech.state === 'failed') partial.push('Speaking schedule unavailable.');
      const savedBanks = [...new Set(future.filter(e => e.kind === 'speech' && e.retained && e.date <= end).map(e => e.owner))];
      if (savedBanks.length) partial.push('Using a saved speaking schedule for ' + savedBanks.join(', ') + '.');
    }
    if (filter !== 'speech') {
      if (feeds.data.state === 'failed') partial.push('Economic release schedule unavailable.');
      else {
        const stale = feeds.data.sources.filter(s => s.status === 'stale').map(s => s.agency);
        const absent = feeds.data.sources.filter(s => s.status === 'unavailable').map(s => s.agency);
        const short = feeds.data.sources.filter(s => s.status === 'verified' &&
          (!s.verifiedFrom || !s.verifiedThrough || s.verifiedFrom > today || s.verifiedThrough < end)).map(s => s.agency);
        if (stale.length) partial.push('Using a saved schedule for ' + stale.join(', ') + '.');
        if (absent.length) partial.push('Schedule unavailable for ' + absent.join(', ') + '.');
        if (short.length) partial.push('Partial week coverage for ' + short.join(', ') + '.');
      }
    }
    list.replaceChildren(dayRows(visible));
    if (!matching.length) {
      const pending = (filter !== 'speech' && feeds.data.state === 'loading') || (filter !== 'data' && feeds.speech.state === 'loading');
      list.append(node('p', 'wa-empty', pending ? 'Loading scheduled events…' : 'No upcoming entries listed for this selection.'));
    }
    if (partial.length) list.append(node('p', 'wa-status', partial.join(' ')));
    more.hidden = compact.length === matching.length;
    more.setAttribute('aria-expanded', String(expanded));
    more.textContent = expanded ? 'Show fewer events' : 'Show all ' + matching.length + ' events';
  }

  async function load(kind, file) {
    try {
      const response = await fetch('data/' + file + '.json');
      if (!response.ok) throw Error('Calendar unavailable');
      const data = await response.json();
      if (kind === 'speech') {
        if (!Array.isArray(data)) throw Error('Missing speaking schedule');
        feeds.speech.events = events(data, kind);
      } else {
        if (!Array.isArray(data.events) || !Array.isArray(data.sources)) throw Error('Missing release schedule');
        feeds.data.sources = data.sources.filter(s => s && s.agency);
        feeds.data.events = events(data.events, kind, feeds.data.sources);
      }
      feeds[kind].state = 'ready';
    } catch {
      feeds[kind].state = 'failed';
    }
    generation++;
    sourceNotes();
    render();
  }
  sourceNotes();
  render();
  load('speech', 'speaking-calendar');
  load('data', 'economic-calendar');
  window.setInterval(render, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) render(); });
})();
