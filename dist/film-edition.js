(() => {
  const catalogue = window.CBI_SITE_INDEX;
  const launcher = document.querySelector('[data-index-open]');
  if (!launcher || !Array.isArray(catalogue)) return;
  const make = (tag, className, text) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text) el.textContent = text;
    return el;
  };
  const fold = value => value.normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu,' ').trim();
  const locationKey = url => url.pathname.replace(/\/index\.html$/, '/');
  const dialog = make('dialog', 'film-index-dialog');
  if (typeof dialog.showModal !== 'function') return; // The launch link opens the full directory.
  dialog.id = 'film-site-index';
  dialog.setAttribute('aria-labelledby', 'film-index-title');
  launcher.setAttribute('aria-haspopup', 'dialog');
  launcher.setAttribute('aria-controls', dialog.id);
  launcher.setAttribute('aria-expanded', 'false');
  const head = make('div', 'film-index-head');
  const row = make('div', 'film-index-title-row');
  const title = make('h2', '', 'Site index');
  title.id = 'film-index-title';
  const close = make('button', '', '×');
  close.type = 'button';
  close.setAttribute('aria-label', 'Close site index');
  row.append(title, close);
  const label = make('label', '', 'Find a page or topic');
  const search = make('input');
  search.type = 'search';
  search.placeholder = 'Search the index';
  search.autocomplete = 'off';
  label.append(search);
  head.append(row, label);
  const scroll = make('div', 'film-index-scroll');
  const status = make('p', 'film-index-status');
  status.setAttribute('role', 'status');
  scroll.append(status);
  const groups = catalogue.map(group => {
    const panel = make('details', 'film-index-group');
    const summary = make('summary', '', group.label);
    const list = make('ul');
    const items = group.items.map(({label, href, keywords = ''}) => {
      const li = make('li');
      const link = make('a', '', label);
      link.setAttribute('href', href);
      li.append(link);
      list.append(li);
      return {li, link, url: new URL(href, document.baseURI), words: fold([group.label,label,keywords].join(' '))};
    });
    panel.append(summary, list);
    scroll.append(panel);
    return {panel, items};
  });
  dialog.append(head, scroll);
  document.body.append(dialog);

  function currentLocation() {
    const here = new URL(location.href);
    const score = url => {
      if (url.origin !== here.origin || locationKey(url) !== locationKey(here)) return -1;
      if (url.hash && url.hash !== here.hash) return -1;
      const params = [...url.searchParams];
      if (!params.every(([k,v]) => here.searchParams.get(k) === v)) return -1;
      return (url.hash ? 100 : 0) + params.length;
    };
    let best = null;
    let high = -1;
    for (const {items} of groups) {
      for (const item of items) {
        item.link.removeAttribute('aria-current');
        const s = score(item.url);
        if (s > high) { high = s; best = item; }
      }
    }
    best?.link.setAttribute('aria-current', high > 0 ? 'location' : 'page');
    for (const a of document.querySelectorAll('.film-primary a')) {
      if (locationKey(new URL(a.href)) === locationKey(here)) a.setAttribute('aria-current','page');
      else a.removeAttribute('aria-current');
    }
  }

  function filter() {
    const terms = fold(search.value).split(' ').filter(Boolean);
    let count = 0;
    for (const {panel,items} of groups) {
      let matches = 0;
      for (const {li,words} of items) {
        li.hidden = !terms.every(term => words.includes(term));
        if (!li.hidden) matches++;
      }
      panel.hidden = matches === 0;
      panel.open = Boolean(terms.length && matches);
      count += matches;
    }
    status.textContent = terms.length
      ? (count ? count + (count === 1 ? ' matching entry' : ' matching entries') : 'No matching entries. Try another search.')
      : '';
    scroll.scrollTop = 0;
  }
  search.addEventListener('input',filter);
  launcher.addEventListener('click',event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    event.preventDefault();
    search.value = '';
    filter();
    currentLocation();
    dialog.showModal();
    launcher.setAttribute('aria-expanded','true');
    // Avoid covering the index with a virtual keyboard when opening it on a phone.
    (matchMedia('(pointer: fine)').matches ? search : close).focus({preventScroll:true});
  });
  close.addEventListener('click',() => dialog.close());
  dialog.addEventListener('close',() => {
    launcher.setAttribute('aria-expanded','false');
    if (document.activeElement === document.body) launcher.focus({preventScroll:true});
  });
  dialog.addEventListener('click',event => {
    if (event.target.closest('a[href]') && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) dialog.close();
    else if (event.target === dialog) {
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
    }
  });
  currentLocation();

  // Charts, filters and long tables may populate above a deep link after native fragment scrolling.
  // Keep the requested record in view until the reader starts interacting.
  let stopTracking = () => {};
  function followFragment() {
    stopTracking();
    const hash = location.hash;
    if (!hash) return;
    let id;
    try { id = decodeURIComponent(hash.slice(1)); } catch { return; }
    let queued = 0;
    let previousTarget = null;
    const controller = new AbortController();
    const options = {passive:true, capture:true, signal:controller.signal};
    const update = () => {
      queued = 0;
      if (location.hash !== hash) return stopTracking();
      const target = document.getElementById(id);
      if (!target) return;
      for (let parent = target; parent; parent = parent.parentElement) {
        if (parent instanceof HTMLDetailsElement && !parent.open) parent.open = true;
      }
      if (!target.getClientRects().length) return;
      const margin = parseFloat(getComputedStyle(target).scrollMarginTop) || 0;
      if (previousTarget !== target || Math.abs(target.getBoundingClientRect().top - margin) > 3) {
        target.scrollIntoView({block:'start',behavior:'instant'});
      }
      previousTarget = target;
    };
    const schedule = () => { if (!queued) queued = requestAnimationFrame(update); };
    const observer = new MutationObserver(schedule);
    observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['hidden','open']});
    const sizes = typeof ResizeObserver === 'function' ? new ResizeObserver(schedule) : null;
    sizes?.observe(document.body);
    const timeout = setTimeout(() => stopTracking(),12000);
    const cancel = () => {
      controller.abort();
      observer.disconnect();
      sizes?.disconnect();
      clearTimeout(timeout);
      cancelAnimationFrame(queued);
      stopTracking = () => {};
    };
    stopTracking = cancel;
    for (const type of ['pointerdown','wheel','touchstart','keydown']) window.addEventListener(type,cancel,options);
    document.fonts?.ready.then(() => { if (!controller.signal.aborted) schedule(); });
    schedule();
  }
  window.addEventListener('hashchange',followFragment);
  document.addEventListener('click',event => {
    const a = event.target.closest?.('a[href]');
    if (!a || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    if (a.hash && a.href === location.href) followFragment();
  });
  followFragment();
})();
