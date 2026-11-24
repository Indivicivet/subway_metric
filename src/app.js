import { Map as MapView, NavigationControl, setWorkerUrl } from "../vendor/maplibre-gl.js";
import { cities, defaultCity } from "./cities.js";

const BASEMAP = "https://tiles.openfreemap.org/styles/positron";
const requested = new URLSearchParams(location.search).get("city");
const cityId = Object.hasOwn(cities, requested) ? requested : defaultCity;
const city = cities[cityId];
const EMPTY = { type: "FeatureCollection", features: [] };
const PREVIEW_METERS = 32;
const mapElement = document.querySelector("#map");
const trip = document.querySelector(".trip");
const mode = document.querySelector("#mode");
const prompt = document.querySelector("#prompt");
const clear = document.querySelector("#clear");
const summary = document.querySelector("#result");
const originLabel = document.querySelector("#origin-label");
const breakdown = document.querySelector("#breakdown");
const legs = document.querySelector("#lines-used");
const canvas = document.createElement("canvas");
const ctx = canvas.getContext("2d");
const touch = matchMedia("(hover: none)");
const workerUrl = new URL("./worker.js", import.meta.url);
workerUrl.searchParams.set("city", cityId);
const worker = new Worker(workerUrl, { type: "module" });
let map;
let meta;
let mapReady = false;
let generation = 0;
let sequence = 0;
let running = null;
let queued = null;
let lastArea = null;
let pointer = null;
let destination = null;
let pin = null;
let refine;
let routeFrame;
let latestRoute;
let snapToStation = false;
let cutoffMinutes = 60;
let resolution = 2;

function collection(features) {
  return { type: "FeatureCollection", features };
}

function feature(type, coordinates, properties = {}) {
  return { type: "Feature", geometry: { type, coordinates }, properties };
}

function splitStationName(name) {
  const match = name.match(/^(.*?)\s*\(([^()]*[\u4e00-\u9fff][^()]*)\)$/);
  return match ? { primary: match[2].trim(), secondary: match[1].trim() } : { primary: name, secondary: null };
}

function mapLabelText(name) {
  const { primary, secondary } = splitStationName(name);
  return secondary ? `${primary}\n${secondary}` : primary;
}

function stationNode(name) {
  const { primary, secondary } = splitStationName(name);
  if (!secondary) return document.createTextNode(primary);
  const stack = document.createElement("span");
  stack.className = "station-stack";
  const sub = document.createElement("span");
  sub.className = "station-sub";
  sub.textContent = secondary;
  stack.append(primary, sub);
  return stack;
}

function nearbyStations([lon, lat], maxMeters = 390, limit = 3) {
  const limitSq = maxMeters ** 2;
  const candidates = [];
  for (const station of meta.stations) {
    const [x, y] = station.coordinates;
    const distance = ((lon - x) * meta.scale[0]) ** 2 + ((lat - y) * meta.scale[1]) ** 2;
    if (distance < limitSq) candidates.push({ station, distance });
  }
  candidates.sort((a, b) => a.distance - b.distance);
  const seen = new Set();
  const result = [];
  for (const { station } of candidates) {
    if (seen.has(station.name)) continue;
    seen.add(station.name);
    result.push(station);
    if (result.length >= limit) break;
  }
  return result;
}

function nearestStation(point, maxMeters = 390) {
  return nearbyStations(point, maxMeters, 1)[0];
}

function nearby(point) {
  return nearestStation(point)?.name;
}

function setActiveMapLabels(stations) {
  const source = map?.getSource("active-station-labels");
  if (!source) return;
  const seen = new Set();
  const features = [];
  for (const station of stations) {
    if (!station || seen.has(station.name)) continue;
    seen.add(station.name);
    features.push(feature("Point", station.coordinates, { label: mapLabelText(station.name) }));
  }
  source.setData(collection(features));
}

function stationByLineAndName(line, name) {
  return meta.stations.find((s) => s.line === line && s.name === name)
    ?? meta.stations.find((s) => s.name === name);
}

function updateHoverStations(point) {
  if (pin || !meta) return;
  const near = point && isCovered(point) ? nearbyStations(point, 800, 2) : [];
  setActiveMapLabels(near);
  if (!near.length) {
    originLabel.hidden = true;
    originLabel.replaceChildren();
    return;
  }
  originLabel.hidden = false;
  const nodes = ["Near "];
  near.forEach((station, index) => {
    if (index > 0) nodes.push(", ");
    nodes.push(stationNode(station.name));
  });
  originLabel.replaceChildren(...nodes);
}

function isCovered([lon, lat]) {
  const [west, south, east, north] = meta.bounds;
  return lon >= west && lon <= east && lat >= south && lat <= north;
}

function showPrompt(message) {
  summary.hidden = true;
  prompt.textContent = message;
  prompt.hidden = false;
}

function showRoute(route, point) {
  map.getSource("route").setData(collection(route?.features ?? []));
  mark("destination", route ? point : null);
  if (route === null) {
    setActiveMapLabels([nearestStation(pin.point)]);
    showPrompt("No mapped walking connection to this point.");
    return;
  }
  const routeStations = [nearestStation(pin.point)];
  for (const { line, board, alight } of route.legs) {
    routeStations.push(stationByLineAndName(line, board), stationByLineAndName(line, alight));
  }
  routeStations.push(nearestStation(point));
  setActiveMapLabels(routeStations);
  document.querySelector("#total").textContent = route.total > 0 && route.total < 60
    ? "<1" : String(Math.round(route.total / 60));
  const station = nearby(point);
  const destinationEl = document.querySelector("#destination");
  if (station) destinationEl.replaceChildren("To near ", stationNode(station));
  else destinationEl.textContent = "To the point on the map";
  const labels = {
    walk: "Walk", to: `Walk to ${city.mode}`, wait: "Wait for trains", ride: `${city.mode} ride`,
    transfer: "Walk between trains", from: "Walk to destination",
  };
  breakdown.replaceChildren(...Object.entries(route.times)
    .filter(([name, time]) => time !== 0 || name === "walk")
    .map(([name, time]) => {
      const row = document.createElement("div");
      const term = document.createElement("dt");
      const value = document.createElement("dd");
      term.textContent = labels[name];
      value.textContent = time > 0 && time < 60 ? "<1 min" : `${Math.round(time / 60)} min`;
      row.append(term, value);
      return row;
    }));
  legs.replaceChildren(...route.legs.map(({ line, board, alight }) => {
    const item = document.createElement("li");
    const code = document.createElement("span");
    code.className = "line-code";
    code.style.setProperty("--line-color", meta.lines[line].color);
    code.textContent = city.shortLineLabels ? line : meta.lines[line].name;
    code.title = meta.lines[line].name;
    item.append(code, stationNode(board), " → ", stationNode(alight));
    return item;
  }));
  prompt.hidden = true;
  summary.hidden = false;
}

function mark(source, point) {
  map.getSource(source).setData(point ? feature("Point", point) : EMPTY);
}

function clearRoute() {
  destination = null;
  latestRoute = null;
  map.getSource("route").setData(EMPTY);
  mark("destination", null);
}

function drawArea(area, point, job) {
  const [, , , width, height] = meta.grid;
  const targetW = width * (job.resolution ?? 1);
  const targetH = height * (job.resolution ?? 1);
  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width = targetW;
    canvas.height = targetH;
  }
  if (area) {
    ctx.putImageData(new ImageData(area, targetW, targetH), 0, 0);
  } else {
    ctx.clearRect(0, 0, targetW, targetH);
  }
  const source = map.getSource("times");
  source.play();
  map.once("render", () => source.pause());
  map.triggerRepaint();
  mark("origin", area ? point : null);
  lastArea = job;
}

function sendArea() {
  if (running || !queued) return;
  running = queued;
  queued = null;
  worker.postMessage({ type: "origin", ...running });
}

function areaAt(point, preview = false) {
  if (preview) {
    point = point.map((value, i) => meta.origin[i]
      + Math.round((value - meta.origin[i]) * meta.scale[i] / PREVIEW_METERS)
      * PREVIEW_METERS / meta.scale[i]);
  }
  const job = queued ?? running ?? lastArea;
  if (
    job?.generation === generation
    && job.point[0] === point[0]
    && job.point[1] === point[1]
    && job.cutoff === cutoffMinutes
    && job.resolution === resolution
  ) return;
  queued = {
    id: ++sequence, generation, point, pin: Boolean(pin),
    cutoff: cutoffMinutes, resolution, requested: performance.now(),
  };
  sendArea();
}

function selectOrigin(point) {
  if (!isCovered(point)) return;
  clearTimeout(refine);
  generation++;
  pin = { point, readyId: null };
  clearRoute();
  trip.classList.add("pinned");
  mode.textContent = "Origin pinned";
  clear.hidden = false;
  originLabel.hidden = false;
  const station = nearestStation(point);
  setActiveMapLabels([station]);
  if (station) originLabel.replaceChildren("From near ", stationNode(station.name));
  else originLabel.textContent = "From the pinned point";
  mark("origin", point);
  map.setPaintProperty("origin-dot", "circle-color", "#18484c");
  showPrompt(touch.matches ? "Tap a destination." : "Hover a destination to see the route.");
  areaAt(point);
}

function resume() {
  if (!pin) return;
  generation++;
  pin = null;
  clearRoute();
  trip.classList.remove("pinned");
  mode.textContent = "Explore";
  clear.hidden = true;
  originLabel.hidden = true;
  map.setPaintProperty("origin-dot", "circle-color", "#078572");
  showPrompt("Hover to explore. Click to pin an origin.");
  updateHoverStations(pointer);
  areaAt(pointer && isCovered(pointer) ? pointer : city.start);
}

function routeAt(point) {
  destination = point;
  if (!isCovered(point)) {
    latestRoute = null;
    showPrompt("Destination is outside the coverage area.");
    map.getSource("route").setData(EMPTY);
    mark("destination", null);
    return;
  }
  if (!pin?.readyId || routeFrame) return;
  routeFrame = requestAnimationFrame(() => {
    routeFrame = null;
    if (!pin?.readyId || !destination || !isCovered(destination)) return;
    latestRoute = ++sequence;
    worker.postMessage({ type: "route", id: latestRoute, point: destination, pin: pin.readyId });
  });
}

function registerInteractions() {
  map.on("mousemove", ({ lngLat, originalEvent }) => {
    if (touch.matches || originalEvent.buttons || map.isMoving()) return;
    pointer = lngLat.toArray();
    if (pin) {
      routeAt(pointer);
      return;
    }
    clearTimeout(refine);
    if (!isCovered(pointer)) {
      updateHoverStations(null);
      return;
    }
    updateHoverStations(pointer);
    if (snapToStation) {
      const snapped = nearestStation(pointer, 600)?.coordinates ?? pointer;
      areaAt(snapped);
      return;
    }
    areaAt(pointer, true);
    refine = setTimeout(() => areaAt(pointer), 120);
  });
  map.on("click", ({ lngLat }) => {
    if (touch.matches && pin) {
      routeAt(lngLat.toArray());
    } else {
      selectOrigin(lngLat.toArray());
    }
  });
  clear.addEventListener("click", resume);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") resume();
    if (event.key === "Enter" && event.target === map.getCanvas()) {
      const center = map.getCenter().toArray();
      if (pin) routeAt(center);
      else selectOrigin(center);
    }
  });
}

function addLayers() {
  const [x, y, step, width, height] = meta.grid;
  canvas.width = width * resolution;
  canvas.height = height * resolution;
  const lonLat = (a, b) => [a / meta.scale[0] + meta.origin[0], b / meta.scale[1] + meta.origin[1]];
  const before = map.getStyle().layers.find((layer) => layer["source-layer"] === "transportation")?.id;
  map.addSource("times", {
    type: "canvas", canvas, animate: false,
    coordinates: [
      lonLat(x, y), lonLat(x + width * step, y),
      lonLat(x + width * step, y - height * step), lonLat(x, y - height * step),
    ],
  });
  map.addLayer({
    id: "travel-times", source: "times", type: "raster",
    paint: { "raster-fade-duration": 0, "raster-resampling": "linear" },
  }, before);
  const [west, south, east, north] = meta.bounds;
  map.addSource("coverage", {
    type: "geojson",
    data: feature("LineString", [[west, south], [east, south], [east, north], [west, north], [west, south]]),
  });
  map.addLayer({
    id: "coverage-outline", source: "coverage", type: "line",
    paint: { "line-color": "#4e7371", "line-opacity": .55, "line-width": 1.3, "line-dasharray": [3, 3] },
  });
  map.addSource("metro", {
    type: "geojson",
    data: collection(meta.shapes.map(({ line, coordinates }) => feature(
      "LineString", coordinates, { color: meta.lines[line].color },
    ))),
  });
  map.addLayer({
    id: "metro-lines", type: "line", source: "metro",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: {
      "line-color": ["get", "color"], "line-opacity": .79,
      "line-width": ["interpolate", ["linear"], ["zoom"], 10, 1.7, 14, 3.1],
    },
  });
  map.addSource("centerpoints", {
    type: "geojson",
    data: collection(meta.centerpoints.map(({ coordinates }, index) => feature(
      "Point", coordinates, { color: ["#bd8b0b", "#758396", "#ae6036"][index] },
    ))),
  });
  map.addLayer({
    id: "centerpoint-rings", type: "circle", source: "centerpoints",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2.85, 15, 5.35],
      "circle-opacity": 0, "circle-stroke-width": 3, "circle-stroke-color": ["get", "color"],
    },
  });
  map.addSource("stations", {
    type: "geojson",
    data: collection(meta.stations.map(({ line, name, coordinates }) => feature(
      "Point", coordinates, { name, label: mapLabelText(name), color: meta.lines[line].color },
    ))),
  });
  map.addLayer({
    id: "stations", type: "circle", source: "stations", minzoom: 10.5,
    paint: {
      "circle-color": "#fff", "circle-stroke-color": ["get", "color"], "circle-stroke-width": 1.35,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 1.5, 15, 4],
    },
  });
  if (map.getStyle().glyphs) {
    map.addLayer({
      id: "station-labels", type: "symbol", source: "stations", minzoom: 12.35,
      layout: {
        "text-field": ["get", "label"], "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 12.35, 15, 15, 22],
        "text-offset": [0, .65], "text-anchor": "top",
      },
      paint: { "text-color": "#2d3f3c", "text-halo-color": "#fff", "text-halo-width": 1.4 },
    });
  }
  map.addSource("active-station-labels", { type: "geojson", data: EMPTY });
  if (map.getStyle().glyphs) {
    map.addLayer({
      id: "active-station-labels", type: "symbol", source: "active-station-labels",
      layout: {
        "text-field": ["get", "label"], "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 10, 14, 15, 22],
        "text-offset": [0, .65], "text-anchor": "top",
        "text-allow-overlap": true,
      },
      paint: { "text-color": "#143e42", "text-halo-color": "#fff", "text-halo-width": 2 },
    });
  }
  map.addSource("route", { type: "geojson", data: EMPTY });
  const routeLayout = { "line-join": "round", "line-cap": "round" };
  map.addLayer({
    id: "route-outline", type: "line", source: "route", layout: routeLayout,
    paint: { "line-color": "#fff", "line-width": 8, "line-opacity": .93 },
  });
  map.addLayer({
    id: "route-ride", type: "line", source: "route", layout: routeLayout,
    filter: ["==", ["get", "kind"], "ride"],
    paint: { "line-color": ["get", "color"], "line-width": 5 },
  });
  map.addLayer({
    id: "route-walk", type: "line", source: "route", layout: routeLayout,
    filter: ["==", ["get", "kind"], "walk"],
    paint: { "line-color": "#18484c", "line-width": 3.5, "line-dasharray": [1, 1.25] },
  });
  for (const [name, radius, color] of [["origin", 7, "#078572"], ["destination", 5, "#e56f48"]]) {
    map.addSource(name, { type: "geojson", data: EMPTY });
    map.addLayer({
      id: `${name}-dot`, type: "circle", source: name,
      paint: {
        "circle-radius": radius, "circle-color": color,
        "circle-stroke-color": "#fff", "circle-stroke-width": 2,
      },
    });
  }
}

function setupWhenReady() {
  if (!mapReady || !meta) return;
  addLayers();
  registerInteractions();
  showPrompt(touch.matches ? "Tap the map to pin an origin." : "Hover to explore. Click to pin an origin.");
  areaAt(city.start);
}

function fail(message) {
  showPrompt(message);
  mapElement.dataset.routing = "error";
}

worker.addEventListener("message", ({ data }) => {
  if (data.type === "ready") {
    meta = data.meta;
    mapElement.dataset.graphLoadMs = String(Math.round(data.loadMs));
    setupWhenReady();
  } else if (data.type === "origin" && data.id === running?.id) {
    const job = running;
    running = null;
    if (job.generation === generation) {
      drawArea(data.area, job.point, job);
      mapElement.dataset.routing = "ready";
      mapElement.dataset.routingMs = String(Math.round(data.computeMs ?? 0));
      map.once("render", () => {
        mapElement.dataset.areaPaintMs = String(Math.round(performance.now() - job.requested));
      });
      if (pin) {
        pin.readyId = data.area ? job.id : null;
        if (!data.area) showPrompt("Choose an origin near a mapped walking path.");
        else if (destination) routeAt(destination);
      }
    }
    sendArea();
  } else if (data.type === "route" && data.id === latestRoute && pin) {
    showRoute(data.route, data.point);
  } else if (data.type === "error") {
    fail(data.message);
  }
});
worker.addEventListener("error", () => fail(`The ${city.name} routing worker could not start.`));

async function openMap() {
  let style;
  let credits = `<a href="./data-sources.html#${cityId}">${city.credit}</a>`;
  try {
    const response = await fetch(BASEMAP, { signal: AbortSignal.timeout(7500) });
    if (!response.ok) throw new Error(`Basemap returned ${response.status}`);
    style = await response.json();
  } catch {
    const status = document.querySelector("#map-status");
    status.textContent = "Street map unavailable";
    status.hidden = false;
    style = {
      version: 8, sources: {},
      layers: [{ id: "background", type: "background", paint: { "background-color": "#edf1eb" } }],
    };
    credits = '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a> · ' + credits;
  }
  setWorkerUrl(new URL("../vendor/maplibre-gl-worker.js", import.meta.url).href);
  map = new MapView({
    container: mapElement, style,
    bounds: city.view,
    fitBoundsOptions: { padding: { top: 65, right: 50, bottom: 45, left: 50 } },
    minZoom: city.minZoom ?? 9.5, maxZoom: 18, dragRotate: false, pitchWithRotate: false,
    attributionControl: { customAttribution: credits },
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
  map.once("load", () => {
    mapReady = true;
    setupWhenReady();
  });
}

document.title = `Subway Metric · ${city.name}`;
mapElement.setAttribute("aria-label", `Interactive ${city.name} travel time map`);
const citySwitch = document.querySelector("#city-switch");
citySwitch.replaceChildren(...Object.entries(cities).map(([id, config]) => {
  const option = document.createElement("option");
  option.value = id;
  option.textContent = config.name;
  return option;
}));
citySwitch.value = cityId;
citySwitch.addEventListener("change", () => {
  const url = new URL(location.href);
  url.searchParams.set("city", citySwitch.value);
  location.assign(url);
});
function refreshArea() {
  if (!meta || !mapReady) return;
  const target = pin ? pin.point : (lastArea?.point ?? city.start);
  areaAt(target);
}

function updateLegendTicks() {
  const ticks = [
    ...Array.from({ length: 7 }, (_, i) => String(Math.round((i * cutoffMinutes) / 6))),
    String(cutoffMinutes + 20),
    `${cutoffMinutes + 40}+`,
  ];
  document.querySelector("#legend-ticks").replaceChildren(...ticks.map((label) => {
    const span = document.createElement("span");
    span.textContent = label;
    return span;
  }));
}

function bindSliderPair(rangeId, numberId, min, max, step, onChange) {
  const range = document.querySelector(rangeId);
  const number = document.querySelector(numberId);
  range.addEventListener("wheel", (event) => event.preventDefault(), { passive: false });
  const apply = (raw) => {
    const parsed = Number(raw);
    const snapped = Number.isFinite(parsed) ? Math.round(parsed / step) * step : min;
    const value = Math.max(min, Math.min(max, Number(snapped.toFixed(2))));
    range.value = String(value);
    number.value = String(value);
    onChange(value);
  };
  range.addEventListener("input", () => apply(range.value));
  number.addEventListener("change", () => apply(number.value));
}

const settingsToggle = document.querySelector("#settings-toggle");
const settingsPanel = document.querySelector("#settings-panel");
settingsToggle.addEventListener("click", () => {
  const open = settingsPanel.hidden;
  settingsPanel.hidden = !open;
  settingsToggle.setAttribute("aria-expanded", String(open));
});
const snapCheckbox = document.querySelector("#snap-station");
snapCheckbox.addEventListener("change", () => {
  snapToStation = snapCheckbox.checked;
  if (!pin && meta && mapReady && pointer && isCovered(pointer)) {
    const target = snapToStation ? (nearestStation(pointer, 600)?.coordinates ?? pointer) : pointer;
    areaAt(target);
  }
});
bindSliderPair("#cutoff-range", "#cutoff-number", 30, 120, 5, (value) => {
  cutoffMinutes = value;
  updateLegendTicks();
  refreshArea();
});
bindSliderPair("#resolution-range", "#resolution-number", 0.5, 4, 0.5, (value) => {
  resolution = Math.max(1, Math.round(value * 2));
  refreshArea();
});
updateLegendTicks();

document.querySelector("#time-model").textContent = city.timeLabel ?? "Typical weekday";
document.querySelector("#credits-link").href = `./data-sources.html#${cityId}`;
showPrompt(`Loading ${city.name} routes…`);
openMap().catch(() => fail("The map could not start. Try a browser with WebGL enabled."));
