export const WALK = 0;
export const ACCESS = 1;
export const WAIT = 2;
export const RIDE = 3;
export const TRANSFER = 4;
export const ALIGHT = 5;
export const UNREACHED = 0xffffffff;
const BUCKET_METERS = 150;
const HEAT_COLORS = [
  [20, 170, 131, 136],
  [85, 186, 123, 130],
  [172, 200, 92, 129],
  [239, 205, 82, 130],
  [240, 165, 80, 127],
  [221, 112, 100, 122],
  [156, 135, 166, 92],
];

class CostQueue {
  constructor(capacity, maxStep) {
    this.nodes = new Uint32Array(capacity);
    this.next = new Int32Array(capacity);
    this.heads = new Int32Array(maxStep + 1);
    this.reset();
  }

  reset() {
    this.heads.fill(-1);
    this.size = 0;
    this.count = 0;
    this.cost = 0;
    this.bucket = 0;
  }

  push(node, cost) {
    const bucket = cost % this.heads.length;
    const index = this.count++;
    this.nodes[index] = node;
    this.next[index] = this.heads[bucket];
    this.heads[bucket] = index;
    this.size++;
  }

  pop() {
    while (this.heads[this.bucket] === -1) {
      this.cost++;
      if (++this.bucket === this.heads.length) this.bucket = 0;
    }
    const index = this.heads[this.bucket];
    this.heads[this.bucket] = this.next[index];
    this.size--;
    return this.nodes[index];
  }
}

function bucketKey(x, y) {
  return x * 4096 + y;
}

export class RoutingGraph {
  constructor(meta, buffer) {
    this.meta = meta;
    const [nodes, edges, roads, cells] = new Uint32Array(buffer, 0, 4);
    let offset = 16;
    const read = (Type, count) => {
      const view = new Type(buffer, offset, count);
      offset += view.byteLength;
      return view;
    };
    this.xy = read(Float32Array, 2 * nodes);
    this.offsets = read(Uint32Array, nodes + 1);
    this.targets = read(Uint32Array, edges);
    this.roads = read(Uint32Array, roads * 4);
    this.cells = read(Uint32Array, cells);
    this.costs = read(Uint32Array, edges);
    this.kinds = read(Uint8Array, edges);
    this.distances = new Uint32Array(nodes);
    this.previousNode = new Int32Array(nodes);
    this.previousEdge = new Int32Array(nodes);
    let maxCost = 0;
    for (const cost of this.costs) maxCost = Math.max(maxCost, cost);
    // Integer costs let the queue recycle buckets after one maximum edge cost.
    // The first two entries can also include the offset from the map to a road.
    this.queue = new CostQueue(edges + 2, maxCost + Math.ceil(
      (meta.stationSnapMeters ?? meta.snapMeters) * meta.walkCost,
    ));
    this.roadBuckets = new Map();
    this.cellCosts = new Uint32Array(cells * 2);
    this.bands = new Uint8Array(cells);
    this.indexRoads();
    this.prepareCells();
  }

  project([lon, lat]) {
    const { origin, scale } = this.meta;
    return [(lon - origin[0]) * scale[0], (lat - origin[1]) * scale[1]];
  }

  geographic(x, y) {
    const { origin, scale } = this.meta;
    return [x / scale[0] + origin[0], y / scale[1] + origin[1]];
  }

  nodeCoordinate(node) {
    return this.geographic(this.xy[2 * node], this.xy[2 * node + 1]);
  }

  indexRoads() {
    const { xy, roads, roadBuckets } = this;
    for (let road = 0; road < roads.length; road += 4) {
      const a = roads[road] * 2;
      const b = roads[road + 1] * 2;
      const xMin = Math.floor(Math.min(xy[a], xy[b]) / BUCKET_METERS);
      const xMax = Math.floor(Math.max(xy[a], xy[b]) / BUCKET_METERS);
      const yMin = Math.floor(Math.min(xy[a + 1], xy[b + 1]) / BUCKET_METERS);
      const yMax = Math.floor(Math.max(xy[a + 1], xy[b + 1]) / BUCKET_METERS);
      for (let x = xMin; x <= xMax; x++) {
        for (let y = yMin; y <= yMax; y++) {
          const key = bucketKey(x, y);
          if (!roadBuckets.has(key)) roadBuckets.set(key, []);
          roadBuckets.get(key).push(road);
        }
      }
    }
  }

  projectToRoad(x, y, road) {
    const { xy, roads } = this;
    const a = roads[road] * 2;
    const b = roads[road + 1] * 2;
    const dx = xy[b] - xy[a];
    const dy = xy[b + 1] - xy[a + 1];
    const lengthSquared = dx * dx + dy * dy;
    const fraction = lengthSquared === 0 ? 0 : Math.max(
      0, Math.min(1, ((x - xy[a]) * dx + (y - xy[a + 1]) * dy) / lengthSquared),
    );
    const px = xy[a] + fraction * dx;
    const py = xy[a + 1] + fraction * dy;
    const distanceSquared = (x - px) ** 2 + (y - py) ** 2;
    return { road, fraction, px, py, distanceSquared };
  }

  snap(point, limit = this.meta.snapMeters) {
    const [x, y] = this.project(point);
    let closest = null;
    let bestDistance = limit * limit;
    for (let i = Math.floor((x - limit) / BUCKET_METERS); i <= Math.floor((x + limit) / BUCKET_METERS); i++) {
      for (let j = Math.floor((y - limit) / BUCKET_METERS); j <= Math.floor((y + limit) / BUCKET_METERS); j++) {
        for (const road of this.roadBuckets.get(bucketKey(i, j)) ?? []) {
          const candidate = this.projectToRoad(x, y, road);
          if (candidate.distanceSquared < bestDistance) {
            closest = candidate;
            bestDistance = candidate.distanceSquared;
          }
        }
      }
    }
    if (closest === null) {
      const { stationSnapMeters, stations } = this.meta;
      if (stationSnapMeters > limit && stations.some(({ coordinates }) => {
        const [sx, sy] = this.project(coordinates);
        return (x - sx) ** 2 + (y - sy) ** 2 <= 60 ** 2;
      })) {
        return this.snap(point, stationSnapMeters);
      }
      return null;
    }
    const offset = Math.round(Math.sqrt(bestDistance) * this.meta.walkCost);
    const cost = this.roads[closest.road + 3];
    return {
      ...closest,
      point,
      coordinate: this.geographic(closest.px, closest.py),
      offset,
      aCost: offset + Math.round(cost * closest.fraction),
      bCost: offset + Math.round(cost * (1 - closest.fraction)),
    };
  }

  prepareCells() {
    const [west, north, step, width] = this.meta.grid;
    for (let cell = 0; cell < this.cells.length; cell++) {
      if (this.cells[cell] === UNREACHED) continue;
      const road = this.cells[cell] * 4;
      const { fraction, distanceSquared } = this.projectToRoad(
        west + ((cell % width) + 0.5) * step,
        north - (Math.floor(cell / width) + 0.5) * step,
        road,
      );
      const flags = this.roads[road + 2];
      const cost = this.roads[road + 3];
      const offset = Math.round(Math.sqrt(distanceSquared) * this.meta.walkCost);
      this.cellCosts[2 * cell] = flags & 1 || fraction === 0
        ? offset + Math.round(cost * fraction) : UNREACHED;
      this.cellCosts[2 * cell + 1] = flags & 2 || fraction === 1
        ? offset + Math.round(cost * (1 - fraction)) : UNREACHED;
    }
  }

  solve(origin, limit = UNREACHED) {
    const { distances, previousNode, previousEdge, offsets, targets, costs, roads, queue } = this;
    const trace = limit === UNREACHED;
    this.start = origin;
    distances.fill(UNREACHED);
    if (trace) {
      previousNode.fill(-1);
      previousEdge.fill(-1);
    }
    queue.reset();
    const flags = roads[origin.road + 2];
    if (flags & 2 || origin.fraction === 0) {
      const a = roads[origin.road];
      distances[a] = origin.aCost;
      queue.push(a, origin.aCost);
    }
    if (flags & 1 || origin.fraction === 1) {
      const b = roads[origin.road + 1];
      distances[b] = origin.bCost;
      queue.push(b, origin.bCost);
    }

    while (queue.size) {
      const from = queue.pop();
      const cost = queue.cost;
      if (cost > limit) break;
      if (cost !== distances[from]) continue;
      for (let edge = offsets[from]; edge < offsets[from + 1]; edge++) {
        const to = targets[edge];
        const next = cost + costs[edge];
        if (next >= distances[to] || next > limit) continue;
        distances[to] = next;
        if (trace) {
          previousNode[to] = from;
          previousEdge[to] = edge;
        }
        queue.push(to, next);
      }
    }
  }

  cellCost(cell) {
    const road = this.cells[cell] * 4;
    return Math.min(
      this.distances[this.roads[road]] + this.cellCosts[2 * cell],
      this.distances[this.roads[road + 1]] + this.cellCosts[2 * cell + 1],
    );
  }

  heatmap() {
    const rgba = new Uint8ClampedArray(this.cells.length * 4);
    const { cells, bands } = this;
    const [, , , width, height] = this.meta.grid;
    for (let c = 0; c < cells.length; c++) {
      if (cells[c] === UNREACHED) {
        bands[c] = 255;
        continue;
      }
      const cost = this.cellCost(c);
      bands[c] = cost >= UNREACHED ? 6 : Math.min(254, Math.floor(cost / 6000));
    }
    for (let y = 0, c = 0; y < height; y++) {
      for (let x = 0; x < width; x++, c++) {
        const band = bands[c];
        if (band === 255) continue;
        const edge =
          (x > 0 && bands[c - 1] < band) ||
          (x + 1 < width && bands[c + 1] < band) ||
          (y > 0 && bands[c - width] < band) ||
          (y + 1 < height && bands[c + width] < band);
        const color = HEAT_COLORS[Math.min(6, band)];
        const index = c * 4;
        if (edge) {
          rgba[index] = Math.round(color[0] * 0.74);
          rgba[index + 1] = Math.round(color[1] * 0.74);
          rgba[index + 2] = Math.round(color[2] * 0.74);
          rgba[index + 3] = Math.min(255, color[3] + 26);
        } else {
          rgba[index] = color[0];
          rgba[index + 1] = color[1];
          rgba[index + 2] = color[2];
          rgba[index + 3] = color[3];
        }
      }
    }
    return rgba;
  }

  route(goal) {
    const { start, roads, distances, previousNode, previousEdge } = this;
    const { road, fraction } = goal;
    const flags = roads[road + 2];
    const a = roads[road];
    const b = roads[road + 1];
    const aTotal = flags & 1 || fraction === 0 ? distances[a] + goal.aCost : UNREACHED;
    const bTotal = flags & 2 || fraction === 1 ? distances[b] + goal.bCost : UNREACHED;
    const total = Math.min(aTotal, bTotal);
    const difference = fraction - start.fraction;
    if (start.point[0] === goal.point[0] && start.point[1] === goal.point[1]) {
      return { total: 0, times: { walk: 0 }, legs: [], features: [] };
    }
    if (start.road === road && ((difference >= 0 && flags & 1) || (difference <= 0 && flags & 2))) {
      const direct = start.offset + goal.offset + Math.round(Math.abs(difference) * roads[road + 3]);
      if (direct <= total) {
        return {
          total: direct / 10,
          times: { walk: direct / 10 },
          legs: [],
          features: [routeFeature("walk", "", [start.point, start.coordinate, goal.coordinate, goal.point])],
        };
      }
    }
    if (total >= UNREACHED) return null;

    const destination = aTotal <= bTotal ? a : b;
    const path = [];
    let node = destination;
    while (previousEdge[node] !== -1) {
      path.push([previousNode[node], node, previousEdge[node]]);
      node = previousNode[node];
    }
    path.reverse();
    return this.trace(path, node, destination, goal, total);
  }

  trace(path, initialNode, destination, goal, total) {
    const { start, kinds, costs, meta } = this;
    const firstTrain = path.findIndex(([, , edge]) => kinds[edge] === RIDE);
    const lastTrain = path.findLastIndex(([, , edge]) => kinds[edge] === RIDE);
    const usesMrt = firstTrain !== -1;
    const times = usesMrt
      ? { to: this.distances[initialNode], wait: 0, ride: 0, transfer: 0, from: total - this.distances[destination] }
      : { walk: total };
    const features = [];
    const legs = [];
    let walk = [start.point, start.coordinate, this.nodeCoordinate(initialNode)];
    let train = null;

    for (const [index, [from, to, edge]] of path.entries()) {
      const kind = kinds[edge];
      if (kind === WAIT) {
        times.wait += costs[edge];
      } else if (kind === RIDE) {
        times.ride += costs[edge];
        const details = meta.rideEdges[edge];
        if (!details) continue;
        const [shapeId, reverse, line, board, alight] = details;
        if (walk.length > 1) features.push(routeFeature("walk", "", walk));
        walk = [];
        if (!train) {
          train = { line, board, alight, stops: 0 };
          legs.push(train);
        }
        train.alight = alight;
        train.stops++;
        const shape = meta.shapes[shapeId].coordinates;
        features.push(routeFeature("ride", meta.lines[line].color, [
          this.nodeCoordinate(from),
          ...(reverse ? shape.toReversed() : shape),
          this.nodeCoordinate(to),
        ]));
      } else if (kind === ALIGHT) {
        train = null;
      } else {
        if (usesMrt) times[index < firstTrain ? "to" : index > lastTrain ? "from" : "transfer"] += costs[edge];
        if (walk.length === 0) walk.push(this.nodeCoordinate(from));
        walk.push(this.nodeCoordinate(to));
      }
    }
    if (walk.length === 0) walk.push(this.nodeCoordinate(destination));
    walk.push(goal.coordinate, goal.point);
    features.push(routeFeature("walk", "", walk));
    for (const key of Object.keys(times)) times[key] /= 10;
    return { total: total / 10, times, legs, features };
  }
}

function routeFeature(kind, color, coordinates) {
  return {
    type: "Feature",
    properties: { kind, color },
    geometry: { type: "LineString", coordinates },
  };
}
