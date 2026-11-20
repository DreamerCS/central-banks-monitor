// Follow a shared episode link to its underlying operations and comparison dates.
function openLinkedEpisode() {
  const target = document.getElementById(window.location.hash.slice(1));
  if (target instanceof HTMLDetailsElement && target.id.startsWith('episode-')) {
    target.open = true;
  }
}
openLinkedEpisode();
window.addEventListener('hashchange', openLinkedEpisode);
