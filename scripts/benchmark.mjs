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

const mainland = {
  zhengzhou: {
    points: { "Railway": [113.6500665, 34.7473938], "East": [113.7707911, 34.7601056], "University": [113.5360877, 34.8283818], "Medical": [113.636912, 34.7486919] },
    trials: [["Railway", "East", "1"], ["Medical", "University", "1"]], home: "Railway",
  },
  shanghai: {
    points: { "People's Square": [121.4709758, 31.234099], "Lujiazui": [121.4981186, 31.2401354], "Disney": [121.6645067, 31.143498], "Jiading North": [121.2323044, 31.3931194], "Huaqiao": [121.1003662, 31.3005465], "Hongqiao": [121.3143112, 31.1959576] },
    trials: [["People's Square", "Lujiazui", "2"], ["Jiading North", "Disney", "11"], ["Huaqiao", "Disney", "11"], ["Hongqiao", "People's Square", "2"]], home: "People's Square",
  },
  chongqing: {
    points: { "Lianglukou": [106.5445934, 29.55578], "Xiaoshizi": [106.5792561, 29.5617785], "Shapingba": [106.4554378, 29.5582503], "North Station": [106.5461941, 29.6096912], "Yudong": [106.5020191, 29.378642] },
    trials: [["Lianglukou", "Xiaoshizi", "1"], ["Shapingba", "North Station", "环"], ["Lianglukou", "Yudong", "3"]], home: "Lianglukou",
  },
  chengdu: {
    points: { "Tianfu Square": [104.0637962, 30.6598362], "East Station": [104.1375485, 30.6316093], "Weijianian": [104.0844471, 30.720173], "Science City": [104.0703492, 30.3939194], "Wugensong": [104.0791522, 30.5043235], "Jinshi": [104.086116, 30.5929701], "Zhujiang": [104.0053084, 30.5690335], "Longquanyi South": [104.1941553, 30.5957903], "Shuangliu T2 East": [103.9560228, 30.5716274] },
    trials: [["Tianfu Square", "East Station", "2"], ["Weijianian", "Science City", "1"], ["Tianfu Square", "Wugensong", "1"], ["Jinshi", "Zhujiang", "30"], ["Longquanyi South", "Shuangliu T2 East", "30"]], home: "Weijianian",
  },
  beijing: {
    points: { "Tiananmen East": [116.3949205, 39.9062701], "Guomao": [116.4532958, 39.9069856], "Xizhimen": [116.3492602, 39.9391324], "South Station": [116.3728993, 39.8635282], "Universal": [116.6735171, 39.8479277] },
    trials: [["Tiananmen East", "Guomao", "1"], ["Xizhimen", "South Station", "4"], ["Guomao", "Universal", "1"]], home: "Tiananmen East",
  },
  qingdao: {
    points: { "May Fourth": [120.3753084, 36.0646098], "Wangjiagang": [120.1573134, 35.9422808], "Airport": [120.0892746, 36.3592275], "Miaoling": [120.4602413, 36.1004171] },
    trials: [["May Fourth", "Airport", "8"], ["May Fourth", "Miaoling", "2"], ["May Fourth", "Wangjiagang"]], home: "May Fourth",
  },
  shenzhen: {
    points: { "Science Museum": [114.0897624, 22.5431472], "Window": [113.9692595, 22.5397676], "Futian": [114.0641051, 22.5184704], "North Station": [114.0252952, 22.6131652], "Chiwan": [113.8926904, 22.4823959] },
    trials: [["Science Museum", "Window", "1"], ["Futian", "North Station", "4"], ["Window", "Chiwan", "2;8"]], home: "Science Museum",
  },
};
if (mainland[city]) {
  assert.ok(meta.stations.length > 0);
  assert.ok(meta.stations.every(({ name }) => /\p{Script=Han}/u.test(name)), "Stations need Chinese names");
  assert.equal(Object.keys(meta.lines).length, { zhengzhou: 13, shanghai: 20, chongqing: 13, chengdu: 17, beijing: 26, qingdao: 8, shenzhen: 16 }[city]);
}
if (city === "beijing") assert.equal(meta.stations.filter(({ line }) => line === "18").length, 11);
if (city === "chengdu") {
  const line30 = meta.stations.filter(({ line }) => line === "30");
  assert.equal(line30.length, 22);
  assert.ok(line30.every(({ name }) => !/玉虹路|分水/.test(name)));
}
const points = mainland[city]?.points ?? (city === "guangzhou" ? {
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
});
const snaps = Object.fromEntries(Object.entries(points).map(([name, point]) => {
  const snap = graph.snap(point);
  assert.ok(snap, `No walking network at ${name}`);
  return [name, snap];
}));

const trials = mainland[city]?.trials ?? (city === "guangzhou" ? [
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
]);
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

const home = mainland[city]?.home ?? { taipei: "Taipei Main", london: "Charing Cross", guangzhou: "Zhujiang New Town" }[city];
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
