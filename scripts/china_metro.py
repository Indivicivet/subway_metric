"""Build mainland metro bundles from OpenStreetMap route relations."""

import itertools
import math
import urllib.request
from collections import defaultdict
from pathlib import Path

import city_bundle
import guangzhou
import osmium
import shapely

SPECS = {
    "zhengzhou": {
        "region": "henan",
        "origin": (113.65, 34.75),
        "bounds": (112.95, 33.95, 114.25, 35.05),
        "masters": [
            7871046,
            7846276,
            13317992,
            13317505,
            10387105,
            14642983,
            18492618,
            18492773,
            7871541,
            16441473,
            16848925,
            10131355,
            12925063,
        ],
    },
    "shanghai": {
        "region": "shanghai",
        "origin": (121.47, 31.23),
        "bounds": (120.90, 30.72, 122.00, 31.72),
        "masters": [
            6800211,
            207417,
            6817204,
            7448424,
            6806165,
            6840940,
            228608,
            7451833,
            7451835,
            7452119,
            396879,
            7451887,
            7451890,
            10557252,
            12231218,
            6803864,
            7845847,
            10095918,
            8167022,
            9786759,
        ],
    },
    "chongqing": {
        "region": "chongqing",
        "origin": (106.55, 29.56),
        "bounds": (105.95, 29.05, 107.00, 30.15),
        "masters": [
            8300611,
            2336458,
            2353579,
            2341151,
            9609521,
            8300867,
            2768662,
            14004564,
            8300873,
            17259489,
            15749314,
            14434654,
            17136842,
        ],
    },
    "chengdu": {
        "region": "sichuan",
        "origin": (104.06, 30.66),
        "bounds": (103.65, 30.05, 104.85, 31.05),
        "masters": [
            2381769,
            8298113,
            8297273,
            8298132,
            10526316,
            12039115,
            8297146,
            12086373,
            13088859,
            8298254,
            19975040,
            12095438,
            11697795,
            16494769,
            18436265,
            13367011,
            18168636,
        ],
    },
    "beijing": {
        "region": "hebei",
        "origin": (116.40, 39.90),
        "bounds": (115.75, 39.35, 117.15, 40.35),
        "masters": [
            415571,
            414866,
            18420551,
            420838,
            420836,
            4625142,
            4624900,
            420837,
            2674584,
            420835,
            13623628,
            18444658,
            417951,
            4624915,
            2688949,
            8324250,
            13625147,
            20010806,
            13625329,
            1350576,
            1350671,
            1350622,
            8469061,
            1354082,
            10136967,
            8008813,
        ],
    },
    "qingdao": {
        "region": "shandong",
        "origin": (120.38, 36.07),
        "bounds": (119.65, 35.50, 121.10, 36.65),
        "masters": [
            13067815,
            7844345,
            7883242,
            15051229,
            17518162,
            13068450,
            10467354,
            10467728,
        ],
    },
    "shenzhen": {
        "region": "guangdong",
        "origin": (114.06, 22.55),
        "bounds": (113.70, 22.40, 114.70, 22.95),
        "masters": [
            7913936,
            21771804,
            9629887,
            7713538,
            9645952,
            11583149,
            14953717,
            9629866,
            9699772,
            11583622,
            9318442,
            14944729,
            18470806,
            14764338,
            15059918,
            13620411,
        ],
    },
}

# The OSM Line 18 route relations omit five open stops. These OSM station
# nodes follow the operator's published station order and use OSM coordinates.
# https://www.mtr.bj.cn/service/line/distable/line-18.html
BEIJING_18_STOPS = (
    13413286351,
    13410014896,
    13410014897,
    13354529561,
    13410014898,
    13410014899,
    13410014900,
    13413286345,
    9669538801,
    13397177863,
    13413286349,
)

# OSM's Line 30 relations omit six open stations and include two closed ones.
# The association's opening notice identifies the closed stations:
# https://infosharingp2-oss.camet.org.cn/resources/manual/2026/01/04/759313381470277.pdf
CHENGDU_30_STOPS = (
    13386320278,
    13386884906,
    13386320276,
    13392617776,
    13392617778,
    13392617780,
    13392617773,
    13392617771,
    13389068139,
    13380485910,
    13380485918,
    13380485921,
    13389068140,
    13380485923,
    13380485924,
    13380485925,
    13380485926,
    13389068144,
    13389068142,
    13389068148,
    13386320281,
    13386320282,
)


def download_extract(cache: Path, region: str) -> Path:
    extract = cache / f"{region}.osm.pbf"
    if not extract.exists():
        cache.mkdir(parents=True, exist_ok=True)
        partial = extract.with_suffix(".partial")
        with urllib.request.urlopen(
            f"https://download.geofabrik.de/asia/china/{region}-latest.osm.pbf",
            timeout=120,
        ) as source, partial.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        partial.replace(extract)
    return extract


def build(city: str, cache: Path, output: Path, custom_extract: Path | None):
    spec = SPECS[city]
    area = city_bundle.MapArea(
        city, spec["origin"], spec["bounds"], 0.04, 200, min_component=12
    )
    extract = custom_extract or download_extract(cache, spec["region"])
    if city == "shanghai" and custom_extract is None:
        # Line 11 extends into Jiangsu; include its stops and walking network.
        jiangsu = download_extract(cache, "jiangsu")
        merged = cache / "shanghai-jiangsu.osm.pbf"
        if not merged.exists() or merged.stat().st_mtime < max(
            extract.stat().st_mtime, jiangsu.stat().st_mtime
        ):
            partial = cache / "shanghai-jiangsu.partial.osm.pbf"
            partial.unlink(missing_ok=True)
            updates = osmium.MergeInputReader()
            updates.add_file(str(extract))
            reader = osmium.io.Reader(str(jiangsu))
            writer = osmium.io.Writer(str(partial))
            try:
                updates.apply_to_reader(reader, writer)
            finally:
                reader.close()
                writer.close()
            partial.replace(merged)
        extract = merged

    print(f"Reading {city} route relations", flush=True)
    relations = {}
    for relation in osmium.FileProcessor(extract, osmium.osm.RELATION).with_filter(
        osmium.filter.TagFilter(
            ("type", "route_master"),
            ("route", "subway"),
            ("route", "light_rail"),
            ("route", "monorail"),
        )
    ):
        relations[relation.id] = (
            dict(relation.tags),
            [(m.type, m.ref, m.role) for m in relation.members],
        )
    lines = {}
    routes = defaultdict(list)
    for master in spec["masters"]:
        if master not in relations:
            raise ValueError(f"Missing route master {master} in {extract}")
        tags, members = relations[master]
        line = tags.get("ref") or str(master)
        lines[line] = (f"Line {line}", tags.get("colour", "#555555"))
        for kind, ref, _ in members:
            if kind != "r" or ref not in relations:
                continue
            route, children = relations[ref]
            if route.get("route") not in {"subway", "light_rail", "monorail"}:
                continue
            if any(
                word in route.get("name", "")
                for word in ("号线快线", "快速", "大站", "直达", "特快")
            ):
                continue
            stops = [
                ref
                for kind, ref, role in children
                if kind == "n" and role.startswith("stop")
            ]
            if city == "beijing" and ref in {20010805, 20010820}:
                stops = BEIJING_18_STOPS if ref == 20010805 else BEIJING_18_STOPS[::-1]
            if city == "chengdu" and ref in {19970753, 19970754}:
                stops = CHENGDU_30_STOPS if ref == 19970753 else CHENGDU_30_STOPS[::-1]
            ways = {
                ref
                for kind, ref, role in children
                if kind == "w" and role in {"", "forward", "backward"}
            }
            if len(stops) >= 2:
                routes[line].append((ref, stops, ways))
        if not routes[line]:
            raise ValueError(f"No mapped service for {city} line {line}")

    stop_ids = {
        stop
        for variants in routes.values()
        for _, stops, _ in variants
        for stop in stops
    }
    track_ids = {
        way for variants in routes.values() for _, _, ways in variants for way in ways
    }
    nodes, ways, exits = {}, {}, []
    unnamed, named_stations = {}, []
    processor = (
        osmium.FileProcessor(extract, osmium.osm.NODE | osmium.osm.WAY)
        .with_locations()
        .with_filter(osmium.filter.IdFilter(track_ids).enable_for(osmium.osm.WAY))
        .with_filter(osmium.filter.EmptyTagFilter().enable_for(osmium.osm.NODE))
    )
    for obj in processor:
        if obj.is_node():
            if obj.id in stop_ids:
                name = (
                    obj.tags.get("name:zh-Hans")
                    or obj.tags.get("name:zh")
                    or obj.tags.get("name")
                )
                if name:
                    english = obj.tags.get("name:en")
                    nodes[obj.id] = (
                        area.project(obj.lon, obj.lat),
                        name.removesuffix("站"),
                        f"{english} ({name})" if english and english != name else name,
                    )
                else:
                    unnamed[obj.id] = area.project(obj.lon, obj.lat)
            if (
                obj.tags.get("railway") == "station"
                and obj.tags.get("station") == "subway"
            ):
                name = (
                    obj.tags.get("name:zh-Hans")
                    or obj.tags.get("name:zh")
                    or obj.tags.get("name")
                )
                if name:
                    named_stations.append(
                        (area.project(obj.lon, obj.lat), name, obj.tags.get("name:en"))
                    )
            if obj.tags.get("railway") == "subway_entrance" and obj.tags.get(
                "access"
            ) not in {"no", "private"}:
                exits.append((area.project(obj.lon, obj.lat), str(obj.id)))
        else:
            points = [
                area.project(node.lon, node.lat)
                for node in obj.nodes
                if node.location.valid()
            ]
            if len(points) >= 2:
                ways[obj.id] = shapely.LineString(points)

    if unnamed and named_stations:
        tree = shapely.STRtree([shapely.Point(point) for point, _, _ in named_stations])
        for stop, point in unnamed.items():
            matches = [
                named_stations[int(index)]
                for index in tree.query(
                    shapely.Point(point), predicate="dwithin", distance=40
                )
            ]
            if len({name for _, name, _ in matches}) == 1:
                _, name, english = matches[0]
                nodes[stop] = (
                    point,
                    name.removesuffix("站"),
                    f"{english} ({name})" if english and english != name else name,
                )

    grouped, stations, paths, patterns = defaultdict(list), {}, {}, defaultdict(set)
    missing = set()
    for line, variants in routes.items():
        track_ids = {way for _, _, refs in variants for way in refs if way in ways}
        merged = shapely.line_merge(
            shapely.MultiLineString([ways[way] for way in sorted(track_ids)])
        )
        paths[line] = [path.simplify(2.5) for path in shapely.get_parts(merged)]
        for relation, stops, _ in variants:
            sequence = []
            for stop in stops:
                if stop not in nodes:
                    missing.add((relation, stop))
                    if len(sequence) >= 2:
                        patterns[line].add(
                            tuple(key for key, _ in itertools.groupby(sequence))
                        )
                    sequence = []
                    continue
                point, name, label = nodes[stop]
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
            if len(sequence) >= 2:
                patterns[line].add(tuple(key for key, _ in itertools.groupby(sequence)))
    if missing:
        print(f"Missing stops in {city}: {sorted(missing)}", flush=True)
    services = []
    for line, variants in patterns.items():
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
        for path in longest:
            if path[0] == path[-1]:
                path = path + path[1:-1]
            runs = []
            for start, end in itertools.pairwise(path):
                track, _ = city_bundle.matched_track(
                    area, paths[line], stations[line, start][0], stations[line, end][0]
                )
                meters = sum(
                    math.dist(area.project(*a), area.project(*b))
                    for a, b in itertools.pairwise(track)
                )
                runs.append(max(35, round(meters * 3.6 / 52 + 20)))
            services.append(
                city_bundle.TrainPattern(
                    line, path, tuple(runs), dict.fromkeys(path, 25), 360
                )
            )
    city_bundle.build_bundle(
        area,
        cache=cache,
        output=output,
        extract=extract,
        lines=lines,
        stations=stations,
        entrances=guangzhou.published_entrances(stations, exits),
        tracks=paths,
        services=services,
        transfer_overrides={},
        transfer_seconds=120,
        station_snap_meters=400,
    )
