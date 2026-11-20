"use strict";

(() => {
  const find = (id) => document.getElementById(id);
  const stage = find("map-stage");
  const canvas = find("map-canvas");
  const pins = find("map-pins");
  const ctx = canvas.getContext("2d");
  const regionList = find("map-regions");
  const locations = find("map-locations");
  const details = find("map-selection");
  const status = find("map-status");
  const datePicker = find("map-day");

  const regions = {
    World: {bounds: [-180, -57, 180, 83], colour: "#406477"},
    "North America": {bounds: [-172, 10, -45, 77], colour: "#65c7b9"},
    "South America": {bounds: [-87, -58, -31, 15], colour: "#da9e71"},
    Europe: {bounds: [-26, 32, 43, 73], colour: "#81bbff"},
    Africa: {bounds: [-24, -37, 55, 38], colour: "#ecba6d"},
    Asia: {bounds: [23, -14, 160, 57], colour: "#b2a2f2"},
    Oceania: {bounds: [108, -51, 181, 4], colour: "#68cddd"},
  };
  const dayIndex = new Map();
  const todayUtc = () => new Date().toISOString().slice(0, 10);
  const state = {region: "World", bank: null, day: "", latest: "", map: null, revision: null, archivePeriods: []};
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

  function renderEvents(items, bank, limit) {
    const list = element("ol", "", "map-events");
    for (const item of items.slice(0, limit)) {
      const link = sourceLink(item);
      if (!link) continue;
      const row = element("li");
      row.append(element("small", item.type), link);
      const period = item.archive && state.archivePeriods.find(({start, end}) => start <= item.day && item.day <= end);
      if (period) row.append(archiveLink(bank, period.id, "Open in archive", item.title));
      list.append(row);
    }
    if (items.length > limit) {
      list.append(element("li", `Showing ${limit} of ${items.length} publications on this day.`, "map-more"));
    }
    details.append(list);
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
    const oldLocation = document.activeElement?.dataset.bank;
    const active = state.map.targets.filter((bank) => eventsFor(bank.name).length > 0);
    const eventCount = active.reduce((total, bank) => total + eventsFor(bank.name).length, 0);
    status.textContent = `${state.day} · ${eventCount} ${eventCount === 1 ? "publication" : "publications"} · ${active.length} active ${active.length === 1 ? "location" : "locations"}`;

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
    const locationButtons = [];
    locations.replaceChildren();
    const locationOrder = [...visible].sort((a, b) =>
      Number(Boolean(eventsFor(b.name).length)) - Number(Boolean(eventsFor(a.name).length)) ||
      a.name.localeCompare(b.name)
    );
    for (const bank of locationOrder) {
      const button = element("button", bank.name, "map-location");
      button.type = "button";
      updateButton(button, state.bank === bank.name, bank.region, eventsFor(bank.name).length);
      button.dataset.bank = bank.name;
      button.addEventListener("click", () => choose(bank.region, bank.name));
      locations.append(button);
      locationButtons.push(button);
    }
    const activeControl = locationButtons.find((button) => button.dataset.bank === (focusLocation ? state.bank : oldLocation));
    activeControl?.focus({preventScroll: true});

    details.replaceChildren();
    if (state.bank) {
      const bank = state.map.targets.find((item) => item.name === state.bank);
      const items = eventsFor(bank.name);
      details.append(element("h4", bank.name));
      if (items.length) renderEvents(items, bank, 8);
      else details.append(element("p", "No publications recorded for this date."));
      const links = element("div", "", "map-archive-links");
      for (const period of state.archivePeriods) {
        links.append(archiveLink(bank, period.id, period.label));
      }
      details.append(links);
    } else {
      const leaders = active.filter((bank) => visible.includes(bank));
      details.append(element("p", leaders.length
        ? `New on this day: ${leaders.map((bank) => bank.name).join(", ")}.`
        : "No publications recorded in this view. Select a jurisdiction to open its archive."));
    }
    paint();

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
    ctx.strokeStyle = "#6bb8d51d";
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
      button.addEventListener("click", () => choose(bank.region, clustered ? null : bank.name, !clustered));
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
      ctx.fillStyle = isSelected ? "#e8a85b" : match ? activeRegion.colour + (covered ? "7b" : "52") : state.region === "World" && covered ? "#30576d" : "#152f43";
      ctx.strokeStyle = isSelected ? "#ffe5ad" : "#507485";
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
    ctx.strokeStyle = "#c6dcea88";
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
    const keepOlderDay = state.day && state.day !== state.latest;
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
    state.day = keepOlderDay && days.includes(state.day) ? state.day : state.latest;
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
    beginPulse();
    render();
  });

  async function start() {
    try {
      const results = await Promise.allSettled([
        getJSON("data/world-map.json"), getJSON("data/world-map-activity.json"), getJSON("data/archive-periods.json"),
      ]);
      if (results[0].status === "rejected") throw results[0].reason;
      state.map = results[0].value;
      state.archivePeriods = results[2].value ?? [];
      if (results[1].status === "fulfilled") useSnapshot(results[1].value);
      else state.day = todayUtc();
      render();
      new ResizeObserver(paint).observe(stage);
      setInterval(refreshActivity, 15 * 60 * 1000);
    } catch {
      status.textContent = "The map could not be loaded. The source atlas remains available below.";
    }
  }
  start();
})();
