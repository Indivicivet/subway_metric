import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { gunzipSync } from "node:zlib";
import { RoutingGraph } from "../src/routing.js";

const data = new URL("../public/data/", import.meta.url);
const meta = JSON.parse(await readFile(new URL("taipei.json", data), "utf8"));
const bytes = gunzipSync(await readFile(new URL("taipei.bin.gz", data)));
const graph = new RoutingGraph(meta, bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));

const points = {
  "Taipei Main": [121.517, 25.0468],
  "Taipei 101": [121.56453, 25.03307],
  "Chiang Kai-shek Memorial Hall": [121.51805, 25.03165],
  "Tamsui": [121.44469, 25.1674],
  "Dingpu": [121.41982, 24.96015],
  "Banqiao": [121.46376, 25.01479],
  "Sanchong": [121.48449, 25.05576],
  "Dapinglin": [121.54134, 24.98289],
  "Jiantan": [121.52521, 25.08514],
  "Nangang": [121.60646, 25.05219],
  "Xinzhuang": [121.45089, 25.0361],
  "Nanjing Fuxing": [121.5442, 25.05178],
};
const snaps = Object.fromEntries(Object.entries(points).map(([name, point]) => {
  const snap = graph.snap(point);
  assert.ok(snap, `No walking network at ${name}`);
  return [name, snap];
}));

for (const [from, to] of [
  ["Taipei Main", "Taipei 101"],
  ["Taipei Main", "Banqiao"],
  ["Taipei 101", "Dapinglin"],
  ["Dingpu", "Tamsui"],
  ["Taipei Main", "Chiang Kai-shek Memorial Hall"],
]) {
  graph.solve(snaps[from]);
  const trip = graph.route(snaps[to]);
  assert.ok(trip, `No route from ${from} to ${to}`);
  assert.ok(trip.legs.length);
  const summed = Object.values(trip.times).reduce((sum, time) => sum + time, 0);
  assert.ok(Math.abs(summed - trip.total) < 0.001, "Legs must add up to total time");
  assert.ok(trip.features.every(({ geometry }) => geometry.coordinates.length >= 2));
  console.log(`${from} → ${to}: ${(trip.total / 60).toFixed(1)} min, ${trip.legs.map((leg) => leg.line).join(" + ") || "walk"}`);
}

graph.solve(snaps["Taipei Main"]);
const nearby = [points["Taipei Main"][0] + 0.00008, points["Taipei Main"][1]];
const localTrip = graph.route(graph.snap(nearby));
assert.ok(localTrip?.times.walk < 60);
assert.equal(localTrip.legs.length, 0);

const samples = [];
for (let i = 0; i < 3; i++) {
  for (const snap of Object.values(snaps)) {
    const started = performance.now();
    graph.solve(snap, 36_000);
    const area = graph.heatmap();
    assert.equal(area.length, meta.grid[3] * meta.grid[4] * 4);
    samples.push(performance.now() - started);
  }
}
samples.sort((a, b) => a - b);
const percentile = (p) => samples[Math.ceil(samples.length * p) - 1].toFixed(0);
console.log(`Warm hover CPU, ${samples.length} samples: median ${percentile(.5)} ms, p95 ${percentile(.95)} ms, max ${percentile(1)} ms`);
