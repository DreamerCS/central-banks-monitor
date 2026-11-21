(() => {
  const chapters = document.querySelectorAll('.hub-section');
  if (!chapters.length) return;
  const query = new URLSearchParams(location.search);
  const has = (...keys) => keys.some(key => query.has(key));
  const reveal = id => {
    const target = document.getElementById(id);
    for (let node = target; node; node = node.parentElement) {
      if (node.matches('details')) node.open = true;
    }
    return target;
  };
  const hashId = () => {
    try { return decodeURIComponent(location.hash.slice(1)); }
    catch { return ''; }
  };
  function fromHash() {
    const wanted = hashId();
    if (!wanted) return;
    const target = reveal(wanted);
    if (!target || !target.hidden) return;
    const waiter = new MutationObserver(() => {
      if (target.hidden) return;
      waiter.disconnect();
      if (hashId() === wanted && target.closest('.hub-section')?.open) target.scrollIntoView();
    });
    waiter.observe(target, {attributes: true, attributeFilter: ['hidden']});
  }
  window.addEventListener('hashchange', fromHash);
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href^="#"]');
    if (link) reveal(link.hash.slice(1));
  });
  if (location.hash) {
    // The macro router places this shared mount in the selected chapter.
    if (!(document.body.classList.contains('hist-body') && hashId() === 'study')) fromHash();
    return;
  }

  // A query-only link can select a section without naming its HTML anchor.
  let id;
  if (document.body.classList.contains('history-page')) {
    if (has('metric')) id = 'history-explorer';
    else if (has('policyRegion')) id = 'policy-world-year';
    else if (has('historyYear')) id = 'annual-policy-ledger';
  } else if (document.body.classList.contains('reaction-page')) {
    if (has('historyYear','historyWindow','historyAsset','historyBefore')) id = 'annual-market-history';
    else if (has('directionDate')) id = 'fed-direction-study';
    else if (has('curveDate','curveEvent')) id = 'pre-event-curve';
    else if (has('bank','window','date','asset','year')) id = 'mr-explorer';
  }
  if ([...query.keys()].some(key => key.startsWith('sx'))) id = 'stance-periods';
  const target = id && reveal(id);
  if (target) target.closest('.hub-section')?.scrollIntoView({block:'start'});
})();
