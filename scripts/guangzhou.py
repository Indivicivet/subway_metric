"""Build the Guangzhou Metro graph from the Guangdong OpenStreetMap extract."""

import itertools
import math
import urllib.request
from collections import defaultdict
from pathlib import Path

import city_bundle
import osmium
import shapely

AREA = city_bundle.MapArea(
    "guangzhou",
    (113.33, 23.17),
    (113.03, 22.69, 113.95, 23.65),
    0.04,
    150,
    min_component=12,
)
NETWORK = 13123168
CORE = {str(line) for line in (*range(1, 15), 18, 21, 22)} | {"GF", "APM"}
EXTRACT = "https://download.geofabrik.de/asia/china/guangdong/guangdong-latest.osm.pbf"
CLOSED_STOPS = {"机场南", "机场南（1号航站楼）", "机场南（T1）"}


def relations(extract: Path):
    result = {}
    for relation in osmium.FileProcessor(extract, osmium.osm.RELATION).with_filter(
        osmium.filter.TagFilter(
            ("type", "network"),
            ("type", "route_master"),
            ("route", "subway"),
            ("route", "light_rail"),
        )
    ):
        result[relation.id] = (
            dict(relation.tags),
            [(member.type, member.ref, member.role) for member in relation.members],
        )
    return result


def coordinates(extract: Path, stop_ids, track_ids):
    nodes = {}
    ways = {}
    exits = []
    processor = (
        osmium.FileProcessor(extract, osmium.osm.NODE | osmium.osm.WAY)
        .with_locations()
        .with_filter(osmium.filter.IdFilter(track_ids).enable_for(osmium.osm.WAY))
        .with_filter(osmium.filter.EmptyTagFilter().enable_for(osmium.osm.NODE))
    )
    for obj in processor:
        if obj.is_node():
            if obj.id in stop_ids:
                tags = obj.tags
                name = (
                    tags.get("name:zh-Hans") or tags.get("name:zh") or tags.get("name")
                )
                if name:
                    name = name.removesuffix("站")
                    english = tags.get("name:en")
                    nodes[obj.id] = (
                        AREA.project(obj.lon, obj.lat),
                        name,
                        f"{english} ({name})" if english and english != name else name,
                    )
            if obj.tags.get("railway") == "subway_entrance" and obj.tags.get(
                "access"
            ) not in {"no", "private"}:
                exits.append((AREA.project(obj.lon, obj.lat), str(obj.id)))
        else:
            points = [
                AREA.project(node.lon, node.lat)
                for node in obj.nodes
                if node.location.valid()
            ]
            if len(points) >= 2:
                ways[obj.id] = shapely.LineString(points)
    return nodes, ways, exits


def assemble(extract: Path):
    data = relations(extract)
    lines = {}
    routes = defaultdict(list)
    for kind, master, _ in data[NETWORK][1]:
        if kind != "r" or master not in data:
            continue
        tags, members = data[master]
        line = tags.get("ref")
        if line not in CORE:
            continue
        lines[line] = (
            {"GF": "Guangfo", "APM": "APM"}.get(line, f"Line {line}"),
            tags["colour"],
        )
        for kind, member, _ in members:
            if kind != "r" or member not in data:
                continue
            route, children = data[member]
            if route.get("route") not in {"subway", "light_rail"}:
                continue
            stops = [
                ref
                for kind, ref, role in children
                if kind == "n" and role.startswith("stop")
            ]
            tracks = {
                ref
                for kind, ref, role in children
                if kind == "w" and role in {"", "forward", "backward"}
            }
            if len(stops) >= 2:
                routes[line].append((member, stops, tracks))
    if set(routes) != CORE:
        raise ValueError(f"Missing core metro services: {sorted(CORE - routes.keys())}")

    stop_ids = {
        stop
        for variants in routes.values()
        for _, stops, _ in variants
        for stop in stops
    }
    track_ids = {
        way
        for variants in routes.values()
        for _, _, tracks in variants
        for way in tracks
    }
    nodes, ways, exits = coordinates(extract, stop_ids, track_ids)

    grouped = defaultdict(list)
    stations = {}
    paths = {}
    patterns = defaultdict(set)
    for line, variants in routes.items():
        track_ids = {way for _, _, tracks in variants for way in tracks if way in ways}
        merged = shapely.line_merge(
            shapely.MultiLineString([ways[way] for way in sorted(track_ids)])
        )
        paths[line] = [path.simplify(2.5) for path in shapely.get_parts(merged)]
        for relation, stops, _ in variants:
            sequence = []
            for stop in stops:
                if stop not in nodes:
                    raise ValueError(
                        f"Missing named stop {stop} in OSM relation {relation}"
                    )
                point, name, label = nodes[stop]
                if name in CLOSED_STOPS:
                    continue
                station_id = next(
                    (
                        key
                        for key, representative in grouped[name]
                        if math.dist(point, representative) <= 600
                    ),
                    None,
                )
                if station_id is None:
                    station_id = str(stop)
                    grouped[name].append((station_id, point))
                stations.setdefault((line, station_id), (point, label))
                sequence.append(station_id)
            patterns[line].add(tuple(key for key, _ in itertools.groupby(sequence)))
    return lines, stations, paths, patterns, exits


def services(stations, paths, patterns):
    results = []
    for line, variants in patterns.items():
        # A short turn adds no new connections. Its frequency is unknown, so
        # don't treat every mapped short turn as a separate frequent service.
        longest = [
            path
            for path in sorted(variants)
            if not any(
                len(other) > len(path)
                and any(
                    other[i : i + len(path)] == path
                    for i in range(len(other) - len(path) + 1)
                )
                for other in variants
            )
        ]
        runs = {}
        cruise_kmh = {"APM": 32, "18": 100, "22": 95, "21": 75, "14": 75}.get(line, 52)
        headway = {"18": 480, "22": 480, "3": 420, "12": 480}.get(line, 360)
        for path in longest:
            if len(path) < 2:
                continue
            if path[0] == path[-1]:
                path = path + path[1:-1]
            for start, end in itertools.pairwise(path):
                if (start, end) not in runs:
                    track, _ = city_bundle.matched_track(
                        AREA,
                        paths[line],
                        stations[line, start][0],
                        stations[line, end][0],
                    )
                    meters = sum(
                        math.dist(AREA.project(*a), AREA.project(*b))
                        for a, b in itertools.pairwise(track)
                    )
                    runs[start, end] = max(35, round(meters * 3.6 / cruise_kmh + 20))
            results.append(
                city_bundle.TrainPattern(
                    line,
                    path,
                    tuple(runs[pair] for pair in itertools.pairwise(path)),
                    dict.fromkeys(path, 25),
                    headway,
                )
            )
    return results


def published_entrances(stations, exits):
    # Entrance nodes carry inconsistent station identifiers. Join only to the
    # nearest station footprint, and let distant exits fall back to the centre.
    keys = tuple(stations)
    tree = shapely.STRtree([shapely.Point(stations[key][0]) for key in keys])
    by_station = defaultdict(list)
    for xy, number in exits:
        point = shapely.Point(xy)
        nearest = int(tree.nearest(point))
        if tree.geometries[nearest].distance(point) <= 140:
            by_station[keys[nearest][1]].append((xy, number))
    return {key: by_station[key[1]] for key in keys}


def build(cache: Path, output: Path, custom_extract: Path | None):
    extract = custom_extract or cache / "guangzhou.osm.pbf"
    if custom_extract is None and not extract.exists():
        cache.mkdir(parents=True, exist_ok=True)
        partial = extract.with_suffix(".partial")
        with urllib.request.urlopen(EXTRACT, timeout=120) as source, partial.open(
            "wb"
        ) as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        partial.replace(extract)
    print("Reading Guangzhou Metro route relations", flush=True)
    lines, stations, paths, patterns, exits = assemble(extract)
    city_bundle.build_bundle(
        AREA,
        cache=cache,
        output=output,
        extract=extract,
        lines=lines,
        stations=stations,
        entrances=published_entrances(stations, exits),
        tracks=paths,
        services=services(stations, paths, patterns),
        transfer_overrides={},
        transfer_seconds=120,
        station_snap_meters=400,
    )
