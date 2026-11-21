(() => {
  const print = document.querySelector('[data-journal-print]');
  if (!print) return;
  const button = print.querySelector('.journal-turn');
  const front = print.querySelector('.journal-print-front');
  const back = print.querySelector('.journal-print-back');
  button.hidden = false;
  button.addEventListener('click', () => {
    const showingNote = back.hidden;
    back.hidden = !showingNote;
    front.hidden = showingNote;
    print.dataset.side = showingNote ? 'back' : 'front';
    button.textContent = showingNote ? 'View photograph' : 'Turn print over';
    button.setAttribute('aria-expanded', String(showingNote));
  });
})();
