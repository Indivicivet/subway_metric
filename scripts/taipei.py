"""Sources and typical weekday service for Taipei Metro."""

import csv
import itertools
import json
import math
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

import city_bundle
import pyproj
import shapely

AREA = city_bundle.MapArea(
    "taipei", (121.52, 25.05), (121.354, 24.908, 121.666, 25.187), 0.034, 90
)
PORTAL = "https://data.taipei/api/frontstage/tpeod/dataset/resource.download?rid="
SOURCES = {
    "runtimes.csv": PORTAL + "c32998fa-c9b2-4324-9016-e19fbe0815f1",
    "entrances.csv": PORTAL + "307a7f61-e302-4108-a817-877ccbfca7c1",
    "stations.geojson": PORTAL + "a63e3278-9d10-4916-9f24-e5a4d78afb31",
    "lines.geojson": PORTAL + "1139b06e-8128-4a07-8148-f27f038bd8b4",
    "station-labels.json": "https://metroly.zzxxccvv.com/data/taipei-v1.json",
    "taiwan.osm.pbf": "https://download.geofabrik.de/asia/taiwan/taiwan-latest.osm.pbf",
}
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


def track_paths(cache: Path, convert):
    source = json.loads((cache / "lines.geojson").read_text(encoding="utf-8-sig"))
    by_name = defaultdict(list)
    for feature in source["features"]:
        for line in shapely.get_parts(
            shapely.from_geojson(json.dumps(feature["geometry"]))
        ):
            by_name[feature["properties"]["RouteName"]].append(
                shapely.LineString(
                    [AREA.project(*convert(*p)) for p in line.coords]
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
            AREA.project(*convert(*feature["geometry"]["coordinates"]))
        )
    stations = {}
    for service, rows in patterns.items():
        line = SERVICES[service][0]
        for start, end, *_ in rows:
            for name in (start, end):
                station = labels[name]
                xy = AREA.project(station["lon"], station["lat"])
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
        exits[name].append((AREA.project(float(lon), float(lat)), number))
    return exits


def service_patterns(line, rows, headway):
    stops = (rows[0][0], *(end for _, end, *_ in rows))
    runs = tuple(run for _, _, run, _ in rows)
    dwell = {start: wait for start, _, _, wait in rows}
    return [
        city_bundle.TrainPattern(line, stops, runs, dwell, headway),
        city_bundle.TrainPattern(line, stops[::-1], runs[::-1], dwell, headway),
    ]


def build(cache: Path, output: Path, custom_extract: Path | None):
    download_sources(cache, custom_extract)
    patterns = load_patterns(cache)
    convert = pyproj.Transformer.from_crs(3826, 4326, always_xy=True).transform
    paths = track_paths(cache, convert)
    stations = station_data(cache, patterns, convert, paths)
    exits = access_points(cache, stations)
    entrances = {}
    for line, stop in stations:
        candidates = exits[stop]
        if stop == "板橋":
            own = stations[line, stop][0]
            other = stations["Y" if line == "BL" else "BL", stop][0]
            candidates = [
                (xy, number)
                for xy, number in candidates
                if math.dist(xy, own) <= math.dist(xy, other)
            ]
        entrances[line, stop] = candidates

    services = []
    for service, rows in patterns.items():
        line, headway = SERVICES[service]
        services.extend(service_patterns(line, rows, headway))
    for first, second in SHARED_SERVICES:
        other_pairs = {(start, end) for start, end, *_ in patterns[second]}
        common = [row for row in patterns[first] if row[:2] in other_pairs]
        if common:
            services.extend(
                service_patterns(
                    SERVICES[first][0],
                    common,
                    1 / (1 / SERVICES[first][1] + 1 / SERVICES[second][1]),
                )
            )

    city_bundle.build_bundle(
        AREA,
        cache=cache,
        output=output,
        extract=custom_extract or cache / "taiwan.osm.pbf",
        lines={code: config[:2] for code, config in LINES.items()},
        stations=stations,
        entrances=entrances,
        tracks=paths,
        services=services,
        transfer_overrides={("Y", "板橋"): "板橋 Y"},
        transfer_seconds=65,
    )
