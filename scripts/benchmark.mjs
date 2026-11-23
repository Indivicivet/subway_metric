import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { gunzipSync } from "node:zlib";
import { cities, defaultCity } from "../src/cities.js";
import { RoutingGraph } from "../src/routing.js";

const data = new URL("../public/data/", import.meta.url);
const city = process.argv[2] ?? defaultCity;
assert.ok(Object.hasOwn(cities, city), "Choose a registered city");
const meta = JSON.parse(await readFile(new URL(`${city}.json`, data), "utf8"));
const bytes = gunzipSync(await readFile(new URL(`${city}.bin.gz`, data)));
const graph = new RoutingGraph(meta, bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));

const points = city === "guangzhou" ? {
  "Guangzhou South": [113.2644761, 22.9917775],
  "Guangzhou Railway": [113.251255, 23.1510751],
  "Tiyu Xilu": [113.3161772, 23.1335002],
  "Airport North": [113.2996781, 23.3979662],
  "Canton Tower": [113.3183998, 23.1093065],
  "Linhexi": [113.317584, 23.1430258],
  "Zhujiang New Town": cities.guangzhou.start,
  "Wanshengwei": [113.3789337, 23.1000758],
  "Panyu Square": [113.3799046, 22.9382819],
} : city === "london" ? {
  "Bank": [-0.088, 51.5132],
  "Waterloo": [-0.1133, 51.5029],
  "Baker Street": [-0.1564, 51.5231],
  "Chesham": [-0.6111, 51.7052],
  "Epping": [0.1141, 51.6937],
  "Heathrow Terminal 5": [-0.49056, 51.470052],
  "Acton Town": [-0.2803, 51.503],
  "Battersea Power Station": [-0.1422, 51.4799],
  "Stratford": [-0.0058, 51.5415],
  "Upminster": [0.2511, 51.559],
  "King's Cross St Pancras": [-0.1237, 51.5308],
  "Charing Cross": [-0.1276, 51.508],
} : {
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

const trials = city === "guangzhou" ? [
  ["Guangzhou South", "Guangzhou Railway", "2"],
  ["Tiyu Xilu", "Airport North", "3"],
  ["Linhexi", "Canton Tower"],
  ["Wanshengwei", "Panyu Square"],
] : city === "london" ? [
  ["Bank", "Waterloo", "waterloo-city"],
  ["Baker Street", "Chesham", "metropolitan"],
  ["Epping", "Bank", "central"],
  ["Heathrow Terminal 5", "Acton Town", "piccadilly"],
  ["Battersea Power Station", "Waterloo", "northern"],
  ["Upminster", "Stratford", "district"],
] : [
  ["Taipei Main", "Taipei 101"],
  ["Taipei Main", "Banqiao"],
  ["Taipei 101", "Dapinglin"],
  ["Dingpu", "Tamsui"],
  ["Taipei Main", "Chiang Kai-shek Memorial Hall"],
];
if (city === "london") assert.equal(Object.keys(meta.lines).length, 11);
if (city === "guangzhou") assert.equal(Object.keys(meta.lines).length, 19);
for (const [from, to, line] of trials) {
  graph.solve(snaps[from]);
  const trip = graph.route(snaps[to]);
  assert.ok(trip, `No route from ${from} to ${to}`);
  assert.ok(trip.legs.length);
  if (line) assert.ok(trip.legs.some((leg) => leg.line === line), `Missing ${line} on ${from} → ${to}`);
  const summed = Object.values(trip.times).reduce((sum, time) => sum + time, 0);
  assert.ok(Math.abs(summed - trip.total) < 0.001, "Legs must add up to total time");
  assert.ok(trip.features.every(({ geometry }) => geometry.coordinates.length >= 2));
  console.log(`${from} → ${to}: ${(trip.total / 60).toFixed(1)} min, ${trip.legs.map((leg) => leg.line).join(" + ") || "walk"}`);
}

const home = { taipei: "Taipei Main", london: "Charing Cross", guangzhou: "Zhujiang New Town" }[city];
graph.solve(snaps[home]);
const nearby = [points[home][0] + 0.00008, points[home][1]];
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
