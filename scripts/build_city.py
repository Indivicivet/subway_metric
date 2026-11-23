"""Build a static city routing bundle from public source data."""

import argparse
from pathlib import Path

import london
import taipei

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", choices=("taipei", "london"), default="taipei")
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache")
    parser.add_argument("--output", type=Path, default=ROOT / "public" / "data")
    parser.add_argument("--osm-extract", type=Path, help="Use a local regional OSM PBF")
    args = parser.parse_args()
    city = {"taipei": taipei, "london": london}[args.city]
    city.build(args.cache, args.output, args.osm_extract)


if __name__ == "__main__":
    main()
