"""Build a static city routing bundle from public source data."""

import argparse
from pathlib import Path

import china_metro
import guangzhou
import london
import taipei

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cities = {"taipei": taipei, "london": london, "guangzhou": guangzhou}
    parser.add_argument(
        "--city", choices=(*cities, *china_metro.SPECS), default="taipei"
    )
    parser.add_argument(
        "--all", action="store_true", help="Build every registered city"
    )
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache")
    parser.add_argument("--output", type=Path, default=ROOT / "public" / "data")
    parser.add_argument("--osm-extract", type=Path, help="Use a local regional OSM PBF")
    args = parser.parse_args()
    targets = (*cities, *china_metro.SPECS) if args.all else (args.city,)
    for city in targets:
        if city in china_metro.SPECS:
            china_metro.build(city, args.cache, args.output, args.osm_extract)
        else:
            cities[city].build(args.cache, args.output, args.osm_extract)


if __name__ == "__main__":
    main()
