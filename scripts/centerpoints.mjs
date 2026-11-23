import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { gunzipSync } from "node:zlib";
import { cities } from "../src/cities.js";
import { RoutingGraph, TRANSFER, UNREACHED } from "../src/routing.js";

const data = new URL("../public/data/", import.meta.url);
const timeLimit = 36_000; // Deciseconds.

function rankCenterpoints(graph) {
  const { meta, cells, offsets, kinds, targets } = graph;
  const [west, north, step, width] = meta.grid;
  const [, south, east] = meta.bounds;
  const [eastX, southY] = graph.project([east, south]);
  const mapped = [];
  const area = new Float64Array(cells.length);
  for (let cell = 0; cell < cells.length; cell++) {
    if (cells[cell] === UNREACHED) continue;
    const x = west + (cell % width) * step;
    const y = north - Math.floor(cell / width) * step;
    // The last row and column can extend past the bundle bounds.
    area[cell] = Math.min(step, eastX - x) * Math.min(step, y - southY) / 1e6;
    mapped.push(cell);
  }

  const bestByComplex = new Map();
  for (const [index, station] of meta.stations.entries()) {
    // The builder stores platforms in metadata order just after the street
    // nodes and connects every pair of platforms in each station complex.
    const platform = meta.stats.streetNodes + index;
    let complex = platform;
    for (let edge = offsets[platform]; edge < offsets[platform + 1]; edge++) {
      if (kinds[edge] === TRANSFER) complex = Math.min(complex, targets[edge]);
    }
    if (!bestByComplex.has(complex)) bestByComplex.set(complex, null);
    const snap = graph.snap(station.coordinates);
    if (!snap) continue;
    graph.solve(snap, timeLimit);

    let score = 0;
    for (const cell of mapped) {
      const cost = graph.cellCost(cell);
      if (cost < timeLimit) score += (timeLimit - cost) * area[cell];
    }
    score /= 600;
    const best = bestByComplex.get(complex);
    if (!best || score > best.score) {
      bestByComplex.set(complex, { name: station.name, coordinates: station.coordinates, score });
    }
  }
  assert.equal(bestByComplex.size, meta.stats.stations, "Routing graph and station metadata disagree");
  return [...bestByComplex.values()].filter(Boolean).sort((a, b) => b.score - a.score).slice(0, 3);
}

export async function loadRankedCity(city) {
  assert.ok(Object.hasOwn(cities, city), "Choose a registered city");
  const [metadata, compressed] = await Promise.all([
    readFile(new URL(`${city}.json`, data), "utf8"),
    readFile(new URL(`${city}.bin.gz`, data)),
  ]);
  const meta = JSON.parse(metadata);
  const bytes = gunzipSync(compressed);
  const graph = new RoutingGraph(meta, bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
  return { ...meta, centerpoints: rankCenterpoints(graph) };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { centerpoints } = await loadRankedCity(process.argv[2]);
  console.log(JSON.stringify(centerpoints, null, 2));
}
