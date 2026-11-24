import { RoutingGraph } from "./routing.js";

let graph;
let pinned;
const city = new URL(import.meta.url).searchParams.get("city");

async function data(file) {
  const response = await fetch(new URL(`../data/${file}`, import.meta.url));
  if (!response.ok) throw new Error(`Couldn't load ${file} (${response.status}).`);
  return response;
}

async function load() {
  const started = performance.now();
  const [meta, buffer] = await Promise.all([
    data(`${city}.json`).then((response) => response.json()),
    data(`${city}.bin.gz`).then((response) => new Response(
      response.body.pipeThrough(new DecompressionStream("gzip")),
    ).arrayBuffer()),
  ]);
  graph = new RoutingGraph(meta, buffer);
  const { rideEdges, ...mapData } = meta;
  self.postMessage({ type: "ready", meta: mapData, loadMs: performance.now() - started });
}

function answer({ type, id, point, pin, cutoff = 60, resolution = 2 }) {
  const started = performance.now();
  const snap = graph.snap(point);
  if (type === "origin") {
    pinned = null;
    if (!snap) {
      self.postMessage({ type, id, area: null });
      return;
    }
    graph.solve(snap, pin ? undefined : (cutoff + 40) * 600);
    if (pin) pinned = id;
    const area = graph.heatmap(cutoff, resolution);
    self.postMessage({ type, id, area, cutoff, resolution, computeMs: performance.now() - started }, [area.buffer]);
  } else if (type === "route" && pinned === pin) {
    const route = snap ? graph.route(snap) : null;
    self.postMessage({ type, id, point, route });
  }
}

self.addEventListener("message", ({ data: query }) => {
  try {
    answer(query);
  } catch (error) {
    self.postMessage({ type: "error", message: error.message });
  }
});

load().catch((error) => self.postMessage({ type: "error", message: error.message }));
