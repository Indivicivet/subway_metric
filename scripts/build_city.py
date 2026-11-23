"""Build the Taipei assets consumed by the static browser app."""

import argparse
import csv
import gzip
import itertools
import json
import math
import struct
import time
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np
import osmium
import pyproj
import shapely
from shapely.ops import substring

ROOT = Path(__file__).resolve().parents[1]
PORTAL = "https://data.taipei/api/frontstage/tpeod/dataset/resource.download?rid="
SOURCES = {
    "runtimes.csv": PORTAL + "c32998fa-c9b2-4324-9016-e19fbe0815f1",
    "entrances.csv": PORTAL + "307a7f61-e302-4108-a817-877ccbfca7c1",
    "stations.geojson": PORTAL + "a63e3278-9d10-4916-9f24-e5a4d78afb31",
    "lines.geojson": PORTAL + "1139b06e-8128-4a07-8148-f27f038bd8b4",
    "station-labels.json": "https://metroly.zzxxccvv.com/data/taipei-v1.json",
    "taiwan.osm.pbf": "https://download.geofabrik.de/asia/taiwan/taiwan-latest.osm.pbf",
}
ORIGIN = (121.52, 25.05)
SCALE = (111_195 * math.cos(math.radians(ORIGIN[1])), 111_195)
BOUNDS = (121.354, 24.908, 121.666, 25.187)
BUFFER = 0.034
CELL_METERS = 90
SNAP_METERS = 120
WALK_COST = 7.5  # Deciseconds per meter at 4.8 km/h.
WALK, ACCESS, WAIT, RIDE, TRANSFER, ALIGHT = range(6)
NO_ROAD = 0xFFFFFFFF

LINES = {
    "R": ("Tamsui–Xinyi", "#d12d49", ("淡水線", "信義線", "信義線東延段")),
    "G": ("Songshan–Xindian", "#008b65", ("新店線", "松山線", "小南門線", "碧潭支線")),
    "O": ("Zhonghe–Xinlu", "#c26c0b", ("中和線", "新莊線", "蘆洲線")),
    "BL": ("Bannan", "#1764bd", ("板橋線", "南港線")),
    "BR": ("Wenhu", "#8e603b", ("木柵線", "內湖線")),
    "Y": ("Circular", "#a17a05", ("環狀線",)),
}
# Representative off-peak headways in seconds. Patterns that share a corridor
# also get a pooled service, so a rider can take the first train that serves it.
SERVICES = {
    "淡水-廣慈/奉天宮": ("R", 600),
    "北投-大安": ("R", 600),
    "北投-新北投": ("R", 660),
    "松山-新店": ("G", 600),
    "松山-台電大樓": ("G", 600),
    "七張-小碧潭": ("G", 960),
    "南勢角-蘆洲": ("O", 600),
    "南勢角-迴龍": ("O", 600),
    "南港展覽館-頂埔": ("BL", 600),
    "南港展覽館-亞東醫院": ("BL", 600),
    "動物園-南港展覽館": ("BR", 420),
    "新北產業園區-大坪林": ("Y", 450),
}
SHARED_SERVICES = (
    ("淡水-廣慈/奉天宮", "北投-大安"),
    ("松山-新店", "松山-台電大樓"),
    ("南勢角-蘆洲", "南勢角-迴龍"),
    ("南港展覽館-頂埔", "南港展覽館-亞東醫院"),
)
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


def project(lon, lat):
    return (lon - ORIGIN[0]) * SCALE[0], (lat - ORIGIN[1]) * SCALE[1]


def geographic(x, y):
    return round(x / SCALE[0] + ORIGIN[0], 7), round(y / SCALE[1] + ORIGIN[1], 7)


def normalized(name):
    return (
        unicodedata.normalize("NFKC", name)
        .replace("臺", "台")
        .strip()
        .removeprefix("捷運")
        .removesuffix("站")
    )


def download_sources(cache: Path, custom_extract: Path | None):
    cache.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        if name == "taiwan.osm.pbf" and custom_extract is not None:
            continue
        target = cache / name
        if target.exists() and target.stat().st_size:
            continue
        print(f"Downloading {name}", flush=True)
        partial = target.with_suffix(".partial")
        request = urllib.request.Request(
            url, headers={"User-Agent": "SubwayMetric/0.1"}
        )
        with urllib.request.urlopen(request, timeout=120) as source, partial.open(
            "wb"
        ) as out:
            while chunk := source.read(1024 * 1024):
                out.write(chunk)
        partial.replace(target)


def csv_rows(path: Path):
    with path.open(encoding="cp950", newline="") as source:
        yield from itertools.islice(csv.reader(source), 1, None)


def load_patterns(cache: Path):
    patterns = defaultdict(list)
    for _, service, start, end, run, _, dwell, *_ in csv_rows(cache / "runtimes.csv"):
        patterns[service.replace("臺", "台")].append(
            (normalized(start), normalized(end), int(run), int(dwell))
        )
    if patterns.keys() != SERVICES.keys():
        raise ValueError(f"Service patterns have changed: {list(patterns)}")
    return patterns


def read_streets(cache: Path, pbf: Path):
    packed = cache / f"{pbf.stem}-taipei-walk-v1.npz"
    if packed.exists() and packed.stat().st_mtime >= pbf.stat().st_mtime:
        with np.load(packed) as data:
            return data["xy"], data["roads"]

    west, south, east, north = BOUNDS
    blocked = set()
    positions = {}
    points = []
    roads = {}
    print("Extracting Greater Taipei streets and footpaths", flush=True)
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
        for a, b in itertools.pairwise(obj.nodes):
            if (
                a.ref in blocked
                or b.ref in blocked
                or not (a.location.valid() and b.location.valid())
            ):
                continue
            if not (
                west - BUFFER <= a.lon <= east + BUFFER
                and south - BUFFER <= a.lat <= north + BUFFER
                and west - BUFFER <= b.lon <= east + BUFFER
                and south - BUFFER <= b.lat <= north + BUFFER
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
        raise ValueError(f"Only {len(xy)} walking nodes found for Greater Taipei")
    np.savez(packed, xy=xy, roads=segments)
    return xy, segments


def track_paths(cache: Path, convert):
    source = json.loads((cache / "lines.geojson").read_text(encoding="utf-8-sig"))
    by_name = defaultdict(list)
    for feature in source["features"]:
        for line in shapely.get_parts(
            shapely.from_geojson(json.dumps(feature["geometry"]))
        ):
            by_name[feature["properties"]["RouteName"]].append(
                shapely.LineString(
                    [project(*convert(*p)) for p in line.coords]
                ).simplify(2.5)
            )
    return {
        code: list(
            shapely.get_parts(
                shapely.line_merge(
                    shapely.MultiLineString(
                        [path for name in names for path in by_name[name]]
                    )
                )
            )
        )
        for code, (_, _, names) in LINES.items()
    }


def station_data(cache: Path, patterns, convert, paths):
    source = json.loads((cache / "station-labels.json").read_text(encoding="utf-8"))
    labels = {normalized(station["name"]): station for station in source["stations"]}
    official = json.loads((cache / "stations.geojson").read_text(encoding="utf-8-sig"))
    official_points = defaultdict(list)
    for feature in official["features"]:
        official_points[normalized(feature["properties"]["NAME"])].append(
            project(*convert(*feature["geometry"]["coordinates"]))
        )
    stations = {}
    for service, rows in patterns.items():
        line = SERVICES[service][0]
        for start, end, *_ in rows:
            for name in (start, end):
                station = labels[name]
                xy = project(station["lon"], station["lat"])
                if len(official_points[name]) > 1:
                    xy = min(
                        official_points[name],
                        key=lambda point: min(
                            path.distance(shapely.Point(point)) for path in paths[line]
                        ),
                    )
                english = (
                    "Taipei Main Station"
                    if name == "台北車"
                    else station.get("name:en")
                )
                stations[line, name] = (xy, english or name)
    return stations


def matched_track(paths, a, b):
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
        return [geographic(*point) for point in shape.coords], False
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
        return [geographic(*point) for point in points], False
    return [geographic(*a), geographic(*b)], True


def access_points(cache: Path, stations):
    exits = defaultdict(list)
    names = sorted({name for _, name in stations}, key=len, reverse=True)
    for _, label, number, lon, lat, *_ in csv_rows(cache / "entrances.csv"):
        normalized_label = normalized(label)
        name = next(
            (name for name in names if normalized_label.startswith(name + "站")), None
        )
        if name is None:
            continue
        exits[name].append((project(float(lon), float(lat)), number))
    return exits


def grid_for(tree):
    west, south = project(*BOUNDS[:2])
    east, north = project(*BOUNDS[2:])
    width = math.ceil((east - west) / CELL_METERS)
    height = math.ceil((north - south) / CELL_METERS)
    cx, cy = np.meshgrid(
        west + (np.arange(width) + 0.5) * CELL_METERS,
        north - (np.arange(height) + 0.5) * CELL_METERS,
    )
    matches = tree.query_nearest(
        shapely.points(cx.flatten(), cy.flatten()),
        max_distance=SNAP_METERS,
        all_matches=False,
    )
    cells = np.full(width * height, NO_ROAD, dtype="<u4")
    cells[matches[0]] = matches[1]
    return cells, [west, north, CELL_METERS, width, height]


def build(cache: Path, output: Path, extract: Path):
    started = time.perf_counter()
    patterns = load_patterns(cache)
    convert = pyproj.Transformer.from_crs(3826, 4326, always_xy=True).transform
    paths = track_paths(cache, convert)
    stations = station_data(cache, patterns, convert, paths)
    entrances = access_points(cache, stations)
    street_xy, roads = read_streets(cache, extract)
    tree = shapely.STRtree(shapely.linestrings(street_xy[roads[:, :2]]))
    cells, grid = grid_for(tree)
    xyz = [tuple(map(float, point)) for point in street_xy]
    links = defaultdict(list)
    shape_ids = {}
    shapes = []
    fallback_tracks = 0
    for service, rows in patterns.items():
        line = SERVICES[service][0]
        for start, end, *_ in rows:
            if (line, start, end) in shape_ids:
                continue
            coordinates, estimated = matched_track(
                paths[line],
                stations[line, start][0],
                stations[line, end][0],
            )
            fallback_tracks += estimated
            shape_ids[line, start, end] = (len(shapes), False)
            shape_ids[line, end, start] = (len(shapes), True)
            shapes.append({"line": line, "coordinates": coordinates})

    def node(point):
        xyz.append(point)
        return len(xyz) - 1

    def edge(a, b, cost, kind, detail=None):
        links[a].append((b, cost, kind, detail))

    for a, b, flags, cost in roads.tolist():
        if flags & 1:
            edge(a, b, cost, WALK)
        if flags & 2:
            edge(b, a, cost, WALK)

    platforms = {key: node(value[0]) for key, value in stations.items()}
    entrances_used = set()
    fallback_entrances = []
    for (line, name), platform in platforms.items():
        point, label = stations[line, name]
        candidates = entrances[name]
        if name == "板橋":
            candidates = [
                (xy, number)
                for xy, number in candidates
                if math.dist(xy, point)
                <= math.dist(xy, stations["Y" if line == "BL" else "BL", name][0])
            ]
        connected = False
        for xy, number in candidates or [(point, "")]:
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
                entrances_used.add((name, xy))
            connected = True
        if not connected:
            raise ValueError(f"No walkable access point for {line} {label}")
        if not candidates:
            fallback_entrances.append(f"{line} {label}")

    for a, b in itertools.combinations(platforms, 2):
        if a[1] == b[1] and a[1] != "板橋":
            cost = round(650 + math.dist(stations[a][0], stations[b][0]) * WALK_COST)
            edge(platforms[a], platforms[b], cost, TRANSFER)
            edge(platforms[b], platforms[a], cost, TRANSFER)

    def add_service(line, rows, headway):
        stops = [rows[0][0], *(end for _, end, *_ in rows)]
        dwell = {start: wait for start, _, _, wait in rows}
        for direction in (stops, stops[::-1]):
            arrivals = [node(stations[line, name][0]) for name in direction]
            departures = [node(stations[line, name][0]) for name in direction]
            runs = [row[2] for row in rows]
            if direction is not stops:
                runs.reverse()
            for index, name in enumerate(direction):
                platform = platforms[line, name]
                if index:
                    edge(arrivals[index], platform, 0, ALIGHT)
                if index < len(runs):
                    edge(platform, departures[index], round(headway * 5), WAIT)
                    if index:
                        edge(
                            arrivals[index],
                            departures[index],
                            dwell.get(name, 0) * 10,
                            RIDE,
                        )
                    following = direction[index + 1]
                    shape, reversed_shape = shape_ids[line, name, following]
                    edge(
                        departures[index],
                        arrivals[index + 1],
                        runs[index] * 10,
                        RIDE,
                        [
                            shape,
                            reversed_shape,
                            line,
                            stations[line, name][1],
                            stations[line, following][1],
                        ],
                    )

    for service, rows in patterns.items():
        line, headway = SERVICES[service]
        add_service(line, rows, headway)
    for first, second in SHARED_SERVICES:
        other_pairs = {(start, end) for start, end, *_ in patterns[second]}
        common = [row for row in patterns[first] if row[:2] in other_pairs]
        if common:
            add_service(
                SERVICES[first][0],
                common,
                1 / (1 / SERVICES[first][1] + 1 / SERVICES[second][1]),
            )

    offsets = [0]
    targets, costs, types, ride_edges = [], [], [], {}
    for a in range(len(xyz)):
        for b, cost, kind, detail in links[a]:
            if detail is not None:
                ride_edges[len(targets)] = detail
            targets.append(b)
            costs.append(cost)
            types.append(kind)
        offsets.append(len(targets))

    output.mkdir(parents=True, exist_ok=True)
    with (output / "taipei.bin.gz").open("wb") as raw, gzip.GzipFile(
        fileobj=raw, mode="wb", mtime=0, compresslevel=5
    ) as out:
        out.write(struct.pack("<4I", len(xyz), len(targets), len(roads), len(cells)))
        for values, dtype in (
            (xyz, "<f4"),
            (offsets, "<u4"),
            (targets, "<u4"),
            (roads, "<u4"),
            (cells, "<u4"),
            (costs, "<u4"),
            (types, "u1"),
        ):
            out.write(np.asarray(values, dtype=dtype).tobytes())
    stats = {
        "streetNodes": len(street_xy),
        "roadSegments": len(roads),
        "directedEdges": len(targets),
        "stations": len({name for _, name in stations}) + 1,
        "entrancesUsed": len(entrances_used),
        "estimatedTrackLinks": fallback_tracks,
        "estimatedEntrances": fallback_entrances,
    }
    metadata = {
        "origin": ORIGIN,
        "scale": SCALE,
        "bounds": BOUNDS,
        "grid": grid,
        "walkCost": WALK_COST,
        "snapMeters": SNAP_METERS,
        "lines": {
            code: {"name": name, "color": color}
            for code, (name, color, _) in LINES.items()
        },
        "stations": [
            {
                "line": line,
                "name": label,
                "nameZh": name,
                "coordinates": geographic(*point),
            }
            for (line, name), (point, label) in stations.items()
        ],
        "shapes": shapes,
        "rideEdges": ride_edges,
        "stats": stats,
    }
    (output / "taipei.json").write_text(
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False), flush=True)
    print(f"Generated {output} in {time.perf_counter() - started:.1f}s", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache")
    parser.add_argument("--output", type=Path, default=ROOT / "public" / "data")
    parser.add_argument(
        "--osm-extract", type=Path, help="Use a local OSM PBF covering Greater Taipei"
    )
    args = parser.parse_args()
    download_sources(args.cache, args.osm_extract)
    build(args.cache, args.output, args.osm_extract or args.cache / "taiwan.osm.pbf")
