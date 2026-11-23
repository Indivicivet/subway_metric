"""Shared pedestrian and transit graph builder for static city bundles."""

import gzip
import json
import math
import struct
import time
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations, pairwise
from pathlib import Path

import numpy as np
import osmium
import shapely
from shapely.ops import substring

SNAP_METERS = 120
WALK_COST = 7.5  # Deciseconds per meter at 4.8 km/h.
WALK, ACCESS, WAIT, RIDE, TRANSFER, ALIGHT = range(6)
NO_ROAD = 0xFFFFFFFF
WALKABLE = {
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "pedestrian",
    "footway",
    "path",
    "steps",
    "track",
    "cycleway",
    "road",
    "corridor",
    "bridleway",
}


class MapArea:
    def __init__(
        self,
        id: str,
        origin,
        bounds,
        buffer: float,
        cell_meters: int,
        min_component: int = 1,
    ):
        self.id = id
        self.origin = origin
        self.bounds = bounds
        self.buffer = buffer
        self.cell_meters = cell_meters
        self.min_component = min_component
        self.scale = (111_195 * math.cos(math.radians(origin[1])), 111_195)

    def project(self, lon, lat):
        return (
            (lon - self.origin[0]) * self.scale[0],
            (lat - self.origin[1]) * self.scale[1],
        )

    def geographic(self, x, y):
        return (
            round(x / self.scale[0] + self.origin[0], 7),
            round(y / self.scale[1] + self.origin[1], 7),
        )


@dataclass(frozen=True)
class TrainPattern:
    line: str
    stops: tuple[str, ...]
    runs: tuple[float, ...]
    dwell: dict[str, float]
    headway: float


def read_streets(area: MapArea, cache: Path, pbf: Path):
    packed = cache / f"{pbf.stem}-{area.id}-walk-v1.npz"
    if packed.exists() and packed.stat().st_mtime >= pbf.stat().st_mtime:
        with np.load(packed) as data:
            return data["xy"], data["roads"]

    west, south, east, north = area.bounds
    project = area.project
    blocked = set()
    positions = {}
    points = []
    roads = {}
    print(f"Extracting {area.id} streets and footpaths", flush=True)
    entities = osmium.osm.NODE | osmium.osm.WAY
    for obj in osmium.FileProcessor(pbf, entities).with_locations("flex_mem"):
        tags = obj.tags
        if obj.is_node():
            if tags.get("foot") == "no" or tags.get("barrier") in {
                "wall",
                "fence",
                "hedge",
                "retaining_wall",
                "block",
            }:
                blocked.add(obj.id)
            continue
        highway = tags.get("highway")
        foot = tags.get("foot")
        if highway is None or foot in {"no", "private", "use_sidepath"}:
            continue
        if tags.get("indoor") == "yes" or tags.get("construction") is not None:
            continue
        if foot not in {"yes", "designated", "permissive"} and (
            highway not in WALKABLE or tags.get("access") in {"no", "private"}
        ):
            continue
        flags = {"yes": 1, "-1": 2}.get(tags.get("oneway:foot"), 3)
        pace = 11.0 if highway == "steps" else WALK_COST
        for a, b in pairwise(obj.nodes):
            if (
                a.ref in blocked
                or b.ref in blocked
                or not (a.location.valid() and b.location.valid())
            ):
                continue
            if not (
                west - area.buffer <= a.lon <= east + area.buffer
                and south - area.buffer <= a.lat <= north + area.buffer
                and west - area.buffer <= b.lon <= east + area.buffer
                and south - area.buffer <= b.lat <= north + area.buffer
            ):
                continue
            for node in (a, b):
                if node.ref not in positions:
                    positions[node.ref] = len(points)
                    points.append(project(node.lon, node.lat))
            start, end = positions[a.ref], positions[b.ref]
            if start == end:
                continue
            seconds = max(1, round(pace * math.dist(points[start], points[end])))
            if start > end:
                start, end = end, start
                flags_for_edge = ((flags & 1) << 1) | ((flags & 2) >> 1)
            else:
                flags_for_edge = flags
            existing_flags, existing_cost = roads.get((start, end), (0, seconds))
            roads[start, end] = (
                existing_flags | flags_for_edge,
                min(existing_cost, seconds),
            )

    xy = np.asarray(points, dtype="<f4")
    segments = np.asarray(
        [(a, b, *values) for (a, b), values in roads.items()], dtype="<u4"
    )
    if len(xy) < 10_000:
        raise ValueError(f"Only {len(xy)} walking nodes found for {area.id}")
    np.savez(packed, xy=xy, roads=segments)
    return xy, segments


def matched_track(area: MapArea, paths, a, b):
    start_point = shapely.Point(a)
    end_point = shapely.Point(b)
    length = math.dist(a, b)
    scored = []
    starts = []
    ends = []
    for path in paths:
        start = path.project(start_point)
        end = path.project(end_point)
        start_offset = path.interpolate(start).distance(start_point)
        end_offset = path.interpolate(end).distance(end_point)
        if start_offset < 110:
            starts.append((path, start, start_offset))
        if end_offset < 110:
            ends.append((path, end, end_offset))
        if (
            start_offset + end_offset < 200
            and length * 0.48 < abs(start - end) < length * 2.4 + 150
        ):
            scored.append((start_offset + end_offset, path, start, end))
    if scored:
        _, path, start, end = min(scored, key=lambda item: item[0])
        shape = substring(path, start, end)
        return [area.geographic(*point) for point in shape.coords], False
    # Historical track features can end on another feature partway along it,
    # as at the junction between a main line and its branch.
    joins = []
    for first, start, start_offset in starts:
        for second, end, end_offset in ends:
            if first is second:
                continue
            junctions = [
                (at, second.project(first.interpolate(at))) for at in (0, first.length)
            ] + [
                (first.project(second.interpolate(at)), at) for at in (0, second.length)
            ]
            for exit_pos, entry_pos in junctions:
                gap = first.interpolate(exit_pos).distance(
                    second.interpolate(entry_pos)
                )
                span = abs(start - exit_pos) + gap + abs(end - entry_pos)
                if gap <= 70 and length * 0.6 < span < length * 2.4 + 150:
                    joins.append(
                        (
                            start_offset + end_offset + gap,
                            first,
                            start,
                            exit_pos,
                            second,
                            entry_pos,
                            end,
                        )
                    )
    if joins:
        _, first, start, exit_pos, second, entry_pos, end = min(
            joins, key=lambda join: join[0]
        )
        points = (
            *substring(first, start, exit_pos).coords,
            *substring(second, entry_pos, end).coords,
        )
        return [area.geographic(*point) for point in points], False
    return [area.geographic(*a), area.geographic(*b)], True


def grid_for(area: MapArea, tree):
    west, south = area.project(*area.bounds[:2])
    east, north = area.project(*area.bounds[2:])
    width = math.ceil((east - west) / area.cell_meters)
    height = math.ceil((north - south) / area.cell_meters)
    cx, cy = np.meshgrid(
        west + (np.arange(width) + 0.5) * area.cell_meters,
        north - (np.arange(height) + 0.5) * area.cell_meters,
    )
    matches = tree.query_nearest(
        shapely.points(cx.flatten(), cy.flatten()),
        max_distance=SNAP_METERS,
        all_matches=False,
    )
    cells = np.full(width * height, NO_ROAD, dtype="<u4")
    cells[matches[0]] = matches[1]
    return cells, [west, north, area.cell_meters, width, height]


def prepare_streets(area: MapArea, xy, roads):
    kept = np.arange(len(xy), dtype="<u4")
    if area.min_component > 1:
        a, b = roads[:, :2].T
        roots = kept
        while True:
            left, right = roots[a], roots[b]
            if np.array_equal(left, right):
                break
            parents = roots.copy()
            np.minimum.at(parents, np.maximum(left, right), np.minimum(left, right))
            roots = parents[parents]
            while not np.array_equal(roots, roots[roots]):
                roots = roots[roots]
        # Dropping tiny islands avoids snapping to an isolated staircase or
        # footpath fragment when the connected pavement is a few meters away.
        keep = np.bincount(roots)[roots] >= area.min_component
        kept = kept[keep]
        roads = roads[keep[a]]
    else:
        roads = roads.copy()

    # Spatially nearby nodes tend to be settled together by the route search.
    # Keep them together in the exported arrays to reduce random memory reads.
    tiles = np.floor(xy[kept] / 200).astype("<i4")
    ordered = kept[np.argsort(tiles[:, 0] * 4096 + tiles[:, 1], kind="stable")]
    node_ids = np.empty(len(xy), dtype="<u4")
    node_ids[ordered] = np.arange(len(ordered), dtype="<u4")
    roads[:, :2] = node_ids[roads[:, :2]]
    roads = roads[np.argsort(np.minimum(roads[:, 0], roads[:, 1]), kind="stable")]
    return xy[ordered], roads


def build_bundle(
    area: MapArea,
    *,
    cache: Path,
    output: Path,
    extract: Path,
    lines,
    stations,
    entrances,
    tracks,
    services: list[TrainPattern],
    transfer_overrides,
    transfer_seconds: int,
):
    started = time.perf_counter()
    street_xy, roads = read_streets(area, cache, extract)
    street_xy, roads = prepare_streets(area, street_xy, roads)
    tree = shapely.STRtree(shapely.linestrings(street_xy[roads[:, :2]]))
    cells, grid = grid_for(area, tree)
    extra_xy = []
    extra_edges = []
    shape_ids = {}
    shapes = []
    fallback_tracks = 0
    for service in services:
        line = service.line
        for start, end in pairwise(service.stops):
            if (line, start, end) in shape_ids:
                continue
            coordinates, estimated = matched_track(
                area,
                tracks[line],
                stations[line, start][0],
                stations[line, end][0],
            )
            fallback_tracks += estimated
            shape_ids[line, start, end] = (len(shapes), False)
            shape_ids[line, end, start] = (len(shapes), True)
            shapes.append({"line": line, "coordinates": coordinates})

    def node(point):
        extra_xy.append(point)
        return len(street_xy) + len(extra_xy) - 1

    def edge(a, b, cost, kind, detail=None):
        extra_edges.append((a, b, cost, kind, detail))

    platforms = {key: node(value[0]) for key, value in stations.items()}
    entrances_used = set()
    fallback_entrances = []
    for (line, stop), platform in platforms.items():
        point, label = stations[line, stop]
        candidates = entrances.get((line, stop), [])
        connected = False
        for xy, number in [*candidates, (point, "")]:
            if not number and connected:
                break
            target = shapely.Point(xy)
            road_id = int(tree.nearest(target))
            segment = tree.geometries[road_id]
            offset = segment.distance(target)
            if offset > SNAP_METERS:
                continue
            a, b, flags, cost = map(int, roads[road_id])
            fraction = segment.project(target, normalized=True)
            door = node(xy)
            access_time = round(350 + math.dist(xy, point) * WALK_COST)
            edge(door, platform, access_time, ACCESS)
            edge(platform, door, access_time, ACCESS)
            a_time = round(offset * WALK_COST + cost * fraction)
            b_time = round(offset * WALK_COST + cost * (1 - fraction))
            if flags & 1:
                edge(a, door, a_time, WALK)
                edge(door, b, b_time, WALK)
            if flags & 2:
                edge(b, door, b_time, WALK)
                edge(door, a, a_time, WALK)
            if number:
                entrances_used.add((stop, xy))
            else:
                fallback_entrances.append(label)
            connected = True
        if not connected:
            raise ValueError(f"No walking connection for {area.id} {line} {label}")
    del tree

    groups = defaultdict(list)
    for platform in platforms:
        groups[transfer_overrides.get(platform, platform[1])].append(platform)
    for group in groups.values():
        for a, b in combinations(group, 2):
            cost = round(
                transfer_seconds * 10
                + math.dist(stations[a][0], stations[b][0]) * WALK_COST
            )
            edge(platforms[a], platforms[b], cost, TRANSFER)
            edge(platforms[b], platforms[a], cost, TRANSFER)

    for service in services:
        line = service.line
        arrivals = [node(stations[line, stop][0]) for stop in service.stops]
        departures = [node(stations[line, stop][0]) for stop in service.stops]
        for index, stop in enumerate(service.stops):
            platform = platforms[line, stop]
            if index:
                edge(arrivals[index], platform, 0, ALIGHT)
            if index < len(service.runs):
                edge(platform, departures[index], round(service.headway * 5), WAIT)
                if index:
                    edge(
                        arrivals[index],
                        departures[index],
                        round(service.dwell.get(stop, 0) * 10),
                        RIDE,
                    )
                following = service.stops[index + 1]
                shape, reversed_shape = shape_ids[line, stop, following]
                edge(
                    departures[index],
                    arrivals[index + 1],
                    round(service.runs[index] * 10),
                    RIDE,
                    [
                        shape,
                        reversed_shape,
                        line,
                        stations[line, stop][1],
                        stations[line, following][1],
                    ],
                )

    # Keep the large walk graph in arrays throughout assembly. Only transit and
    # entrance edges need Python records and optional route drawing metadata.
    forward = roads[(roads[:, 2] & 1) != 0]
    reverse = roads[(roads[:, 2] & 2) != 0]
    walking_edges = len(forward) + len(reverse)
    extra = np.asarray([edge[:4] for edge in extra_edges], dtype="<u4")
    sources = np.concatenate((forward[:, 0], reverse[:, 1], extra[:, 0]))
    targets = np.concatenate((forward[:, 1], reverse[:, 0], extra[:, 1]))
    costs = np.concatenate((forward[:, 3], reverse[:, 3], extra[:, 2]))
    kinds = np.concatenate(
        (np.zeros(walking_edges, dtype="u1"), extra[:, 3].astype("u1"))
    )
    node_count = len(street_xy) + len(extra_xy)
    order = np.argsort(sources, kind="stable")
    offsets = np.empty(node_count + 1, dtype="<u4")
    offsets[0] = 0
    np.cumsum(np.bincount(sources, minlength=node_count), dtype="<u4", out=offsets[1:])
    ride_edges = {}
    for position in np.flatnonzero(order >= walking_edges):
        detail = extra_edges[order[position] - walking_edges][4]
        if detail is not None:
            ride_edges[int(position)] = detail

    output.mkdir(parents=True, exist_ok=True)
    with (output / f"{area.id}.bin.gz").open("wb") as raw, gzip.GzipFile(
        fileobj=raw, mode="wb", mtime=0, compresslevel=5
    ) as out:
        out.write(struct.pack("<4I", node_count, len(order), len(roads), len(cells)))
        for values in (
            street_xy,
            np.asarray(extra_xy, dtype="<f4"),
            offsets,
            targets[order],
            roads,
            cells,
            costs[order],
            kinds[order],
        ):
            out.write(values.tobytes())
    stats = {
        "streetNodes": len(street_xy),
        "roadSegments": len(roads),
        "directedEdges": len(order),
        "stations": len(groups),
        "entrancesUsed": len(entrances_used),
        "estimatedTrackLinks": fallback_tracks,
        "estimatedEntrances": sorted(set(fallback_entrances)),
    }
    metadata = {
        "origin": area.origin,
        "scale": area.scale,
        "bounds": area.bounds,
        "grid": grid,
        "walkCost": WALK_COST,
        "snapMeters": SNAP_METERS,
        "lines": {
            code: {"name": name, "color": color}
            for code, (name, color) in lines.items()
        },
        "stations": [
            {"line": line, "name": label, "coordinates": area.geographic(*point)}
            for (line, stop), (point, label) in stations.items()
        ],
        "shapes": shapes,
        "rideEdges": ride_edges,
        "stats": stats,
    }
    (output / f"{area.id}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False), flush=True)
    print(
        f"Generated {area.id} bundle in {time.perf_counter() - started:.1f}s",
        flush=True,
    )
