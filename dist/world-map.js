"use strict";

(() => {
  const find = (id) => document.getElementById(id);
  const stage = find("map-stage");
  const canvas = find("map-canvas");
  const pins = find("map-pins");
  const ctx = canvas.getContext("2d");
  const regionList = find("map-regions");
  const locationPicker = find("map-location-select");
  const mapSection = find("world-map");
  const details = find("map-selection");
  const status = find("map-status");
  const datePicker = find("map-day");

  const regions = {
    World: {bounds: [-180, -57, 180, 83], colour: "#ac835d"},
    "North America": {bounds: [-172, 10, -45, 77], colour: "#d6b477"},
    "South America": {bounds: [-87, -58, -31, 15], colour: "#d39270"},
    Europe: {bounds: [-26, 32, 43, 73], colour: "#a7bac5"},
    Africa: {bounds: [-24, -37, 55, 38], colour: "#beaa7b"},
    Asia: {bounds: [23, -14, 160, 57], colour: "#ad93a6"},
    Oceania: {bounds: [108, -51, 181, 4], colour: "#a9b3a5"},
  };
  const dayIndex = new Map();
  const todayUtc = () => new Date().toISOString().slice(0, 10);
  const state = {region: "World", bank: null, day: "", latest: "", followLatest: true, map: null, activityReady: false, revision: null, archivePeriods: []};
  let paths = [];
  let layoutSignature = "";
  let pulseDay = "";
  let pulseUntil = 0;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  async function getJSON(path) {
    const response = await fetch(path, {cache: "no-cache"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function eventsFor(bank) {
    return dayIndex.get(state.day)?.get(bank) ?? [];
  }

  function beginPulse() {
    if (pulseDay !== state.day) {
      pulseDay = state.day;
      pulseUntil = Date.now() + 4500;
      layoutSignature = "";
    }
  }

  function archiveLink(bank, month, label, query) {
    const params = new URLSearchParams({month, bank: bank.name, view: "region"});
    if (query) params.set("q", query);
    const link = element("a", label);
    link.href = `research-archive.html?${params}#${month}-bank-${bank.index}`;
    return link;
  }

  function sourceLink(item) {
    try {
      const url = new URL(item.url);
      if (url.protocol !== "https:" || url.username || url.password) return null;
      const link = element("a", item.title);
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      return link;
    } catch {
      return null;
    }
  }

  function renderEvents(items, limit, bank = null) {
    const list = element("ol", "", "map-events");
    for (const item of items.slice(0, limit)) {
      const link = sourceLink(item);
      if (!link) continue;
      const row = element("li");
      row.append(element("small", bank ? item.type : [item.institution || item.bank, item.type].filter(Boolean).join(" · ")), link);
      const period = bank && item.archive && state.archivePeriods.find(({start, end}) => start <= item.day && item.day <= end);
      if (period) row.append(archiveLink(bank, period.id, "Open in archive", item.title));
      list.append(row);
    }
    details.append(list);
    if (items.length > limit) {
      details.append(element("p", `Showing ${limit} of ${items.length} publications.`, "map-more"));
    }
  }

  // Show one record per active jurisdiction before filling remaining slots from the same day.
  function dayPreview(groups) {
    return [...groups.map(items => items[0]), ...groups.flatMap(items => items.slice(1))];
  }

  function choose(region, bank = null, focus = false) {
    state.region = region;
    state.bank = bank;
    if (focus) render(true);
    else render();
  }

  function updateButton(button, pressed, current, count, unit = "publications") {
    button.setAttribute("aria-pressed", String(pressed));
    button.style.setProperty("--region-accent", regions[current].colour);
    if (count) {
      const badge = element("span", String(count), "map-count");
      badge.setAttribute("aria-label", `${count} ${unit}`);
      button.append(badge);
    }
  }

  function render(focusLocation = false) {
    const oldRegion = document.activeElement?.dataset.region;
    if (!state.map) {
      const groups = [...(dayIndex.get(state.day)?.values() ?? [])];
      const items = dayPreview(groups);
      status.textContent = state.activityReady
        ? `${state.day} · Geographic map unavailable. ${items.length} recorded publications.`
        : "The map and publication records are currently unavailable. You can browse the publication archive below.";
      details.replaceChildren();
      if (items.length) renderEvents(items, 3);
      return;
    }
    const active = state.map.targets.filter((bank) => eventsFor(bank.name).length > 0);
    const eventCount = active.reduce((total, bank) => total + eventsFor(bank.name).length, 0);
    status.textContent = state.activityReady
      ? `${state.day} · ${eventCount} ${eventCount === 1 ? "publication" : "publications"} across ${active.length} ${active.length === 1 ? "jurisdiction" : "jurisdictions"} worldwide`
      : "Publication records are currently unavailable. You can still browse jurisdictions and their archives.";

    regionList.replaceChildren();
    for (const region of Object.keys(regions)) {
      const count = active.filter((bank) => region === "World" || bank.region === region).length;
      const button = element("button", region, "map-region");
      button.type = "button";
      updateButton(button, region === state.region, region, count, "active locations");
      button.dataset.region = region;
      button.addEventListener("click", () => choose(region));
      regionList.append(button);
      if (oldRegion === region) button.focus({preventScroll: true});
    }

    const visible = state.map.targets.filter((bank) => state.region === "World" || bank.region === state.region);
    const locationOrder = [...visible].sort((a, b) =>
      Number(Boolean(eventsFor(b.name).length)) - Number(Boolean(eventsFor(a.name).length)) ||
      a.name.localeCompare(b.name)
    );
    const all = element("option", state.region === "World" ? "All jurisdictions" : `All in ${state.region}`);
    all.value = "";
    locationPicker.replaceChildren(all);
    for (const bank of locationOrder) {
      const count = eventsFor(bank.name).length;
      const option = element("option", count ? `${bank.name} · ${count} ${count === 1 ? "publication" : "publications"}` : bank.name);
      option.value = bank.name;
      locationPicker.append(option);
    }
    locationPicker.value = state.bank ?? "";
    locationPicker.disabled = false;

    details.replaceChildren();
    if (state.bank) {
      const bank = state.map.targets.find((item) => item.name === state.bank);
      const items = eventsFor(bank.name);
      details.append(element("h4", bank.name));
      if (items.length) renderEvents(items, 8, bank);
      else if (state.activityReady) details.append(element("p", "No publications recorded for this date."));
      const links = element("div", "", "map-archive-links");
      for (const period of state.archivePeriods) {
        links.append(archiveLink(bank, period.id, period.label));
      }
      details.append(links);
    } else {
      const items = dayPreview(locationOrder.map(bank => eventsFor(bank.name)).filter(group => group.length));
      if (items.length) renderEvents(items, 3);
      else if (state.activityReady) details.append(element("p", "No publications recorded in this view. Select a jurisdiction to open its archive."));
    }
    paint();
    if (focusLocation) locationPicker.focus({preventScroll: true});

  }

  function fit(bounds, width, height) {
    const [west, south, east, north] = bounds;
    const scale = Math.min((width - 28) / (east - west), (height - 53) / (north - south));
    const left = (width - (east - west) * scale) / 2;
    const top = (height - 25 - (north - south) * scale) / 2;
    return (lon, lat) => [left + (lon - west) * scale, top + (north - lat) * scale];
  }

  function drawGrid(project, bounds, width, height) {
    const [west, south, east, north] = bounds;
    const spacing = state.region === "World" ? 30 : 15;
    ctx.strokeStyle = "#c2b8a422";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let lon = Math.ceil(west / spacing) * spacing; lon < east; lon += spacing) {
      const [x] = project(lon, 0);
      ctx.moveTo(x, 12);
      ctx.lineTo(x, height - 27);
    }
    for (let lat = Math.ceil(south / spacing) * spacing; lat < north; lat += spacing) {
      const [, y] = project(west, lat);
      ctx.moveTo(12, y);
      ctx.lineTo(width - 12, y);
    }
    ctx.stroke();
  }

  function makePath(rings, project) {
    const path = new Path2D();
    for (const ring of rings) {
      for (let i = 0; i < ring.length; i += 2) {
        const [x, y] = project(ring[i] / 100, ring[i + 1] / 100);
        if (i) path.lineTo(x, y);
        else path.moveTo(x, y);
      }
      path.closePath();
    }
    return path;
  }

  function layOutPins(project) {
    const bankPositions = state.map.targets
      .filter((bank) => state.region === "World" || bank.region === state.region)
      .map((bank) => ({bank, xy: project(bank.lon, bank.lat)}));
    const groups = [];
    if (state.region === "World") {
      for (const {bank, xy} of bankPositions) {
        const near = groups.find((group) => group.region === bank.region &&
          Math.hypot(group.xy[0] - xy[0], group.xy[1] - xy[1]) < 28);
        if (near) near.banks.push(bank);
        else groups.push({region: bank.region, xy, banks: [bank]});
      }
    } else {
      const placed = [];
      const offsets = [[0, 0], [0, -25], [25, 0], [-25, 0], [0, 25], [25, -25], [-25, 25]];
      for (const {bank, xy} of bankPositions) {
        const candidates = offsets.map(([dx, dy]) => [xy[0] + dx, xy[1] + dy]);
        const spot = candidates.find(([x, y]) => placed.every(([a, b]) => Math.hypot(x - a, y - b) >= 23)) ?? xy;
        placed.push(spot);
        groups.push({region: bank.region, xy: spot, anchor: xy, banks: [bank]});
      }
    }
    return groups;
  }

  function drawPins(groups) {
    const signature = JSON.stringify([state.region, state.bank, state.day,
      groups.map((g) => [g.xy, g.banks.map((b) => [b.name, eventsFor(b.name).length])])]);
    if (signature === layoutSignature) return;
    layoutSignature = signature;
    const focusKey = document.activeElement?.dataset.pin;
    pins.replaceChildren();
    for (const group of groups) {
      const bank = group.banks[0];
      const clustered = group.banks.length > 1;
      const newCount = group.banks.reduce((n, b) => n + eventsFor(b.name).length, 0);
      const label = clustered ? `${group.region}, ${group.banks.length} jurisdictions` : bank.name;
      const button = element("button", clustered ? String(group.banks.length) : "", "map-pin");
      button.type = "button";
      button.dataset.pin = label;
      button.setAttribute("aria-label", `${label}${newCount ? `, ${newCount} publications` : ""}`);
      button.setAttribute("aria-pressed", String(!clustered && state.bank === bank.name));
      button.title = `${label}${newCount ? ` · ${newCount} publications` : ""}`;
      button.style.setProperty("--px", `${group.xy[0]}px`);
      button.style.setProperty("--py", `${group.xy[1]}px`);
      button.style.setProperty("--region-accent", regions[bank.region].colour);
      if (clustered) button.classList.add("cluster");
      if (newCount) {
        button.classList.add("map-pin-new");
        if (Date.now() < pulseUntil) button.classList.add("map-pin-pulse");
      }
      button.addEventListener("click", () => choose(bank.region, clustered ? null : bank.name, true));
      pins.append(button);
      if (focusKey === label) button.focus({preventScroll: true});
    }
  }

  function paint() {
    if (!ctx || !state.map) return;
    const {width, height} = stage.getBoundingClientRect();
    if (width < 30 || height < 60) return;
    const ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const activeRegion = regions[state.region];
    const project = fit(activeRegion.bounds, width, height);
    const selected = state.map.targets.find((bank) => bank.name === state.bank);
    drawGrid(project, activeRegion.bounds, width, height);
    paths = [];
    for (const [code, region, rings] of state.map.countries) {
      const path = makePath(rings, project);
      const isSelected = selected?.codes.includes(code) && (code !== "FRA" || state.region === "Europe");
      const match = region === state.region;
      const covered = state.map.targets.some((bank) => bank.codes.includes(code));
      ctx.fillStyle = isSelected ? "#e8a85b" : match ? activeRegion.colour + (covered ? "7b" : "52") : state.region === "World" && covered ? "#66564c" : "#353332";
      ctx.strokeStyle = isSelected ? "#ffe5ad" : "#867769";
      ctx.lineWidth = isSelected ? 1.15 : .55;
      ctx.fill(path, "evenodd");
      ctx.stroke(path);
      paths.push({code, region, path});
    }
    if (selected && !paths.some(({code}) => selected.codes.includes(code))) {
      const [x, y] = project(selected.lon, selected.lat);
      ctx.beginPath();
      ctx.arc(x, y, 10, 0, 2 * Math.PI);
      ctx.fillStyle = "#e8a85b";
      ctx.fill();
    }
    const pinLayout = layOutPins(project);
    ctx.strokeStyle = "#d9cbb188";
    for (const {xy, anchor} of pinLayout) {
      if (!anchor || xy === anchor) continue;
      ctx.beginPath();
      ctx.moveTo(...anchor);
      ctx.lineTo(...xy);
      ctx.stroke();
    }
    drawPins(pinLayout);
  }

  canvas.addEventListener("click", (event) => {
    const box = canvas.getBoundingClientRect();
    const x = (event.clientX - box.left) * canvas.width / box.width;
    const y = (event.clientY - box.top) * canvas.height / box.height;
    const result = paths.find(({path}) => ctx.isPointInPath(path, x, y, "evenodd"));
    if (!result) return;
    const target = state.map.targets.find(({codes}) => codes.includes(result.code));
    if (target) choose(target.region, target.name);
    else if (regions[result.region]) choose(result.region);
  });

  function useSnapshot(snapshot) {
    if (!snapshot) return;
    state.activityReady = true;
    dayIndex.clear();
    for (const item of snapshot.items) {
      if (!dayIndex.has(item.day)) dayIndex.set(item.day, new Map());
      const byBank = dayIndex.get(item.day);
      if (!byBank.has(item.bank)) byBank.set(item.bank, []);
      byBank.get(item.bank).push(item);
    }
    const today = todayUtc();
    const days = [...new Set([today, ...dayIndex.keys()])].filter((day) => day <= today).sort().reverse();
    state.latest = days.find((day) => dayIndex.has(day)) ?? today;
    state.day = !state.followLatest && days.includes(state.day) ? state.day : state.latest;
    state.revision = snapshot.revision;
    datePicker.replaceChildren();
    for (const day of days) {
      const note = day === today ? " · Today (UTC)" : day === state.latest ? " · Latest recorded" : "";
      const option = element("option", day + note);
      option.value = day;
      datePicker.append(option);
    }
    datePicker.value = state.day;
    datePicker.disabled = false;
    beginPulse();
  }

  async function refreshActivity() {
    try {
      const snapshot = await getJSON("data/world-map-activity.json");
      if (snapshot.revision !== state.revision || todayUtc() !== datePicker.options[0]?.value) {
        useSnapshot(snapshot);
        render();
      }
    } catch (error) {
      console.warn("Publication refresh unavailable", error);
    }
  }

  datePicker.addEventListener("change", () => {
    state.day = datePicker.value;
    state.followLatest = state.day === state.latest;
    beginPulse();
    render();
  });

  locationPicker.addEventListener("change", () => {
    const bank = state.map?.targets.find(item => item.name === locationPicker.value);
    choose(bank?.region ?? state.region, bank?.name ?? null);
  });

  async function start() {
    try {
      const results = await Promise.allSettled([
        getJSON("data/world-map.json"), getJSON("data/world-map-activity.json"), getJSON("data/archive-periods.json"),
      ]);
      state.map = results[0].status === "fulfilled" ? results[0].value : null;
      if (!state.map) mapSection.classList.add("map-unavailable");
      state.archivePeriods = results[2].value ?? [];
      if (results[1].status === "fulfilled") useSnapshot(results[1].value);
      else {
        state.day = todayUtc();
        datePicker.options[0].textContent = "Dates unavailable";
      }
      render();
      if (state.map && typeof ResizeObserver === "function") new ResizeObserver(paint).observe(stage);
      else window.addEventListener("resize", paint);
      setInterval(refreshActivity, 15 * 60 * 1000);
    } catch {
      mapSection.classList.add("map-unavailable");
      status.textContent = "Publication data could not be loaded. You can browse the publication archive below.";
    }
  }
  start();
})();
