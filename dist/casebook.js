"use strict";

(() => {
  const book = document.querySelector("main.casebook");
  if (!book) return;
  const articles = Array.from(book.querySelectorAll("article.case-entry[id]"));
  const cases = new Map(articles.map(article => [article.id, article]));
  const links = Array.from(book.querySelectorAll(".case-index a[href^='#']"));
  const picker = book.querySelector("#case-picker");
  const select = book.querySelector("#case-select");
  if (!articles.length || !links.length || !picker || !select) return;

  function fragmentId(hash) {
    try {
      return decodeURIComponent(hash.slice(1));
    } catch {
      return "";
    }
  }

  function showCase(article) {
    for (const item of articles) item.hidden = item !== article;
    for (const link of links) {
      if (fragmentId(link.hash) === article.id) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
    for (const option of select.options) {
      if (option.value.replace(/^#/, "") === article.id) {
        select.value = option.value;
        break;
      }
    }
  }

  function followLocation() {
    const id = fragmentId(window.location.hash);
    const target = document.getElementById(id);
    const article = cases.get(id) || target?.closest("article.case-entry[id]");
    if (article && cases.has(article.id)) showCase(article);
    else if (!window.location.hash) showCase(articles[0]);
  }

  function choose(article) {
    if (fragmentId(window.location.hash) !== article.id) {
      window.history.pushState(null, "", "#" + encodeURIComponent(article.id));
    }
    showCase(article);
    const heading = article.querySelector("h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
    article.scrollIntoView({ block: "start", behavior: "instant" });
  }

  book.addEventListener("click", event => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest("a[href]");
    if (!link || link.hasAttribute("download") || (link.target && link.target !== "_self")) return;
    const destination = new URL(link.href);
    if (destination.origin !== location.origin || destination.pathname !== location.pathname || destination.search !== location.search) return;
    const article = cases.get(fragmentId(destination.hash));
    if (!article) return;
    event.preventDefault();
    choose(article);
  });

  select.addEventListener("change", () => {
    const article = cases.get(select.value.replace(/^#/, ""));
    if (article) choose(article);
  });

  showCase(articles[0]);
  followLocation();
  window.addEventListener("hashchange", followLocation);
  window.addEventListener("popstate", followLocation);
  book.classList.add("case-enhanced");
  picker.hidden = false;
})();

(() => {
  const form = document.getElementById("btp-repo-calculator");
  if (!form) return;
  const haircut = form.elements.namedItem("haircut");
  const priceFall = form.elements.namedItem("priceFall");
  const gap = form.querySelector("#repo-funding-gap");
  const loss = form.querySelector("#repo-bond-loss");
  const message = form.querySelector("#repo-input-message");
  const amount = new Intl.NumberFormat("en-GB", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const originalCollateral = 100;
  const principalDue = 98;

  function percentage(input) {
    const value = input.valueAsNumber;
    const valid = Number.isFinite(value) && value >= 0 && value <= 100;
    input.setAttribute("aria-invalid", String(!valid));
    if (valid) input.removeAttribute("aria-describedby");
    else input.setAttribute("aria-describedby", message.id);
    return valid ? value : null;
  }

  function update() {
    const haircutPercent = percentage(haircut);
    const fallPercent = percentage(priceFall);
    const valid = haircutPercent !== null && fallPercent !== null;
    message.textContent = valid ? "" : "Enter a percentage from 0 to 100 in each highlighted field.";
    message.hidden = valid;
    const priceLoss = fallPercent === null ? null : originalCollateral * fallPercent / 100;
    loss.textContent = priceLoss === null ? "—" : "€" + amount.format(priceLoss) + " million";
    if (!valid) {
      gap.textContent = "—";
      return;
    }
    const renewedAdvance = (originalCollateral - priceLoss) * (1 - haircutPercent / 100);
    const fundingGap = Math.max(0, principalDue - renewedAdvance);
    gap.textContent = "€" + amount.format(fundingGap) + " million";
  }

  form.addEventListener("input", update);
  form.addEventListener("submit", event => event.preventDefault());
  form.addEventListener("reset", () => queueMicrotask(update));
  update();
  form.hidden = false;
})();
