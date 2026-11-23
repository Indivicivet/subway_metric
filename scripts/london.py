"""Sources and typical weekday service for London Underground."""

import csv
import json
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from itertools import combinations, pairwise
from pathlib import Path

import city_bundle
import shapely

API = "https://api.tfl.gov.uk/Line"
GEOMETRY = "https://tfl.manglekuo.com/data/geography/tube-geometry.json"
ENTRANCES = (
    "https://naptan.api.dft.gov.uk/v1/access-nodes"
    "?atcoAreaCodes=040,150,210,490&dataFormat=csv"
)
AREA = city_bundle.MapArea(
    "london",
    (-0.12, 51.52),
    (-0.64, 51.365, 0.285, 51.732),
    0.03,
    120,
    min_component=12,
)
DAYTIME_START = 10 * 60
DAYTIME_END = 16 * 60
WEEKDAY = {"Daily", "Monday - Friday", "Monday - Thursday"}
LINES = {
    "bakerloo": ("Bakerloo", "#894e24"),
    "central": ("Central", "#dc241f"),
    "circle": ("Circle", "#aa7a00"),
    "district": ("District", "#007229"),
    "hammersmith-city": ("Hammersmith & City", "#ca6587"),
    "jubilee": ("Jubilee", "#727f88"),
    "metropolitan": ("Metropolitan", "#751056"),
    "northern": ("Northern", "#242528"),
    "piccadilly": ("Piccadilly", "#243588"),
    "victoria": ("Victoria", "#007eae"),
    "waterloo-city": ("Waterloo & City", "#158d80"),
}


def fetch(url: str, target: Path):
    request = urllib.request.Request(url, headers={"User-Agent": "SubwayMetric/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        contents = response.read()
    partial = target.with_suffix(".partial")
    partial.write_bytes(contents)
    partial.replace(target)


def download(cache: Path):
    cache.mkdir(parents=True, exist_ok=True)
    if not (cache / "access-nodes.csv").exists():
        fetch(ENTRANCES, cache / "access-nodes.csv")
    if not (cache / "tube-geometry.json").exists():
        fetch(GEOMETRY, cache / "tube-geometry.json")
    for line in LINES:
        route_file = cache / f"{line}.json"
        if not route_file.exists():
            time.sleep(1.35)
            fetch(f"{API}/{line}/Route/Sequence/all?serviceTypes=Regular", route_file)
        response = json.loads(route_file.read_text(encoding="utf-8"))
        starts = {route["naptanIds"][0] for route in response["orderedLineRoutes"]}
        for station in sorted(starts):
            target = cache / f"{line}-{station}.json"
            if target.exists():
                continue
            time.sleep(1.35)
            try:
                fetch(f"{API}/{line}/Timetable/{station}", target)
            except urllib.error.HTTPError as error:
                if error.code not in {400, 404}:
                    raise
                target.write_text("null", encoding="utf-8")
            print(f"TfL {line} {station}", flush=True)


def contains(path, part):
    return any(
        path[i : i + len(part)] == part for i in range(len(path) - len(part) + 1)
    )


def shared_corridors(paths):
    shared = set()
    for a, b in combinations(paths, 2):
        positions = defaultdict(list)
        for j, stop in enumerate(b):
            positions[stop].append(j)
        for i, stop in enumerate(a):
            for j in positions[stop]:
                if i and j and a[i - 1] == b[j - 1]:
                    continue
                length = 1
                while (
                    i + length < len(a)
                    and j + length < len(b)
                    and a[i + length] == b[j + length]
                ):
                    length += 1
                if length > 1:
                    shared.add(a[i : i + length])
    return shared


def weekday_service(cache: Path, line, starts, stations):
    frequencies = Counter()
    times = defaultdict(list)
    for origin in sorted(starts):
        source = json.loads(
            (cache / f"{line}-{origin}.json").read_text(encoding="utf-8")
        )
        if source is None:
            continue
        timetable = source["timetable"]
        actual_origin = timetable["departureStopId"]
        for route in timetable["routes"]:
            intervals = {
                int(timing["id"]): timing["intervals"]
                for timing in route["stationIntervals"]
            }
            departures = Counter(
                departure["intervalId"]
                for schedule in route["schedules"]
                if schedule["name"] in WEEKDAY
                for departure in schedule.get("knownJourneys", [])
                if DAYTIME_START
                <= int(departure["hour"]) * 60 + int(departure["minute"])
                < DAYTIME_END
            )
            for interval, frequency in departures.items():
                stops = [(actual_origin, 0.0)]
                for item in intervals.get(interval, []):
                    stop = item["stopId"]
                    if (line, stop) not in stations:
                        raise ValueError(f"Unknown TfL timetable stop {line}/{stop}")
                    if stop != stops[-1][0]:
                        stops.append((stop, float(item["timeToArrival"]) * 60))
                if len(stops) < 2 or any(a[1] > b[1] for a, b in pairwise(stops)):
                    continue
                path = tuple(stop for stop, _ in stops)
                frequencies[path] += frequency
                for (start, start_time), (end, end_time) in pairwise(stops):
                    times[start, end].extend(
                        [max(30, end_time - start_time)] * frequency
                    )
    if not frequencies:
        raise ValueError(f"TfL returned no weekday daytime service for {line}")
    typical = {pair: statistics.median(times) for pair, times in times.items()}
    services = []
    # A rider on a shared corridor can board any train that serves the whole
    # segment, while branch-bound riders wait for the appropriate service.
    for path in dict.fromkeys([*frequencies, *sorted(shared_corridors(frequencies))]):
        count = sum(
            frequency for seq, frequency in frequencies.items() if contains(seq, path)
        )
        services.append(
            city_bundle.TrainPattern(
                line,
                path,
                tuple(typical[pair] for pair in pairwise(path)),
                {},
                (DAYTIME_END - DAYTIME_START) * 60 / count,
            )
        )
    return services


def published_entrances(cache: Path, stations):
    by_code = defaultdict(list)
    with (cache / "access-nodes.csv").open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            code = row["ATCOCode"]
            if (
                row["Status"] == "active"
                and row["StopType"] == "TMU"
                and code[4:8] == "ZZLU"
            ):
                by_code["940G" + code[4:11]].append(
                    (
                        AREA.project(float(row["Longitude"]), float(row["Latitude"])),
                        code,
                    )
                )
    return {key: by_code[key[1]] for key in stations}


def track_paths(cache: Path):
    source = json.loads((cache / "tube-geometry.json").read_text(encoding="utf-8"))
    paths = defaultdict(list)
    for feature in source["lines"]["features"]:
        line = feature["properties"]["lineId"]
        if line in LINES:
            paths[line].append(
                shapely.LineString(
                    [
                        AREA.project(*point)
                        for point in feature["geometry"]["coordinates"]
                    ]
                ).simplify(2.5)
            )
    if paths.keys() != LINES.keys():
        raise ValueError("Tube track dataset must contain all eleven Underground lines")
    return paths


def build(cache: Path, output: Path, custom_extract: Path | None):
    extract = custom_extract or cache / "london.osm.pbf"
    if not extract.is_file():
        raise FileNotFoundError(
            f"Provide a Greater London OSM PBF at {extract} or via --osm-extract"
        )
    source = cache / "london"
    download(source)
    stations = {}
    services = []
    for line in LINES:
        response = json.loads((source / f"{line}.json").read_text(encoding="utf-8"))
        # The summary station list uses hub IDs at interchanges. Timetables
        # refer to the underlying Underground stops in the branch sequences.
        for branch in response["stopPointSequences"]:
            for station in branch["stopPoint"]:
                stations[line, station["id"]] = (
                    AREA.project(station["lon"], station["lat"]),
                    station["name"].removesuffix(" Underground Station"),
                )
        starts = {route["naptanIds"][0] for route in response["orderedLineRoutes"]}
        services.extend(weekday_service(source, line, starts, stations))

    city_bundle.build_bundle(
        AREA,
        cache=cache,
        output=output,
        extract=extract,
        lines=LINES,
        stations=stations,
        entrances=published_entrances(source, stations),
        tracks=track_paths(source),
        services=services,
        transfer_overrides={
            key: "940GZZLUBNK" for key in stations if key[1] == "940GZZLUMMT"
        },
        transfer_seconds=120,
    )
