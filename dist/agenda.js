(() => {
  'use strict';
  const root = document.querySelector('#speech-agenda');
  if (!root) return;
  const calendar = 'https://www.ecb.europa.eu/press/calendars/weekly/html/index.en.html';
  const london = 'Europe/London';
  const date = new Intl.DateTimeFormat('en-GB', { timeZone: london, day: 'numeric', month: 'short' });
  const time = new Intl.DateTimeFormat('en-GB', { timeZone: london, hour: '2-digit', minute: '2-digit' });
  const londonDay = new Intl.DateTimeFormat('en-CA', { timeZone: london, year: 'numeric', month: '2-digit', day: '2-digit' });
  let events = [];
  let current;
  let timer;

  function element(tag, className, value) {
    const el = document.createElement(tag);
    el.className = className;
    el.textContent = value;
    return el;
  }

  function countdown(milliseconds) {
    const minutes = Math.ceil(milliseconds / 60000);
    if (minutes <= 0) return 'Now';
    const hours = Math.floor(minutes / 60);
    if (hours >= 24) return 'In ' + Math.floor(hours / 24) + 'd ' + hours % 24 + 'h';
    return 'In ' + (hours ? hours + 'h ' : '') + minutes % 60 + 'm';
  }

  function render() {
    const now = Date.now();
    const day = londonDay.format(now);
    const next = events.find(event => event.at ? new Date(event.at).getTime() > now : event.date >= day);
    if (!next) {
      if (!root.querySelector('.agenda-calendar')) {
        const link = element('a', 'agenda-calendar', 'Speaking calendar');
        link.href = calendar;
        root.replaceChildren(link);
      }
      return;
    }
    if (current !== next) {
      current = next;
      const when = new Date(next.at || next.date + 'T12:00:00Z');
      const link = element('a', 'agenda-speaker', next.speaker);
      link.href = next.source;
      link.title = next.title;
      const label = element('span', 'agenda-label', 'Up next');
      const bank = element('span', 'agenda-bank', next.bank);
      const schedule = element('time', 'agenda-time', date.format(when) + (next.at ? ' · ' + time.format(when) + ' London' : ''));
      schedule.dateTime = next.at || next.date;
      timer = element('span', 'agenda-countdown', '');
      root.replaceChildren(label, bank, link, schedule, timer);
    }
    timer.textContent = next.at ? countdown(new Date(next.at).getTime() - now) : 'Time to be confirmed';
  }

  fetch('data/speaking-calendar.json').then(response => {
    if (!response.ok) throw new Error('Calendar unavailable');
    return response.json();
  }).then(data => {
    events = data.filter(item => item.speaker && /^https:\/\//.test(item.source) && /^\d{4}-\d{2}-\d{2}$/.test(item.date))
      .sort((a, b) => a.date.localeCompare(b.date) || (a.at || '~').localeCompare(b.at || '~'));
    render();
    window.setInterval(render, 15000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) render(); });
  }).catch(render);
})();
