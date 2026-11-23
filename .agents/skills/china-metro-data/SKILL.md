---
name: china-metro-data
description: Gather reusable topology, geographic tracks, stops, and entrances for a mainland Chinese city in Subway Metric.
---

1. Start with the operator's current passenger map and opening notices. List active lines and termini. Check branches, loops, skipped stations, and trial-running extensions explicitly.
2. Use the Geofabrik regional `.osm.pbf` as the redistributable source. Find the city network and its `route_master` children via `https://api.openstreetmap.org/api/0.6/relation/<id>/full.json`. Inspect `route=subway` members for ordered stop nodes and track ways. Check both directions, branches, express variants, and loop closure. Track adjacency alone does not establish service.
3. Check OSM line and terminal coverage against the operator list. Record missing sections. Join `railway=subway_entrance` nodes conservatively and record station-centre fallbacks. Keep OSM coordinates in WGS84. Do not copy Amap/Baidu data into the bundle without explicit redistribution rights.
4. Prefer the existing OSM walking graph. If publishable timetable data is unavailable, estimate running time from track length and keep waits, dwell, and transfers explicit. Check one cross-river trip and one branch or loop trip against the operator planner.
5. Follow `scripts/guangzhou.py`. Register the city in `scripts/build_city.py`, `src/cities.js`, and `.github/workflows/pages.yml`. Run `python scripts/build_city.py --city <id> --osm-extract <path>`. Check `public/data/<id>.json` and `<id>.bin.gz`. Add fixtures to `scripts/benchmark.mjs`, run `npm run benchmark -- <id>` and `npm run build`. Credit data and label estimates in `public/data-sources.html`.
