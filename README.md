# Subway Metric

Explore typical subway and walking times in major cities. Choose a city in the map header. Hover to see the travel-time heatmap. Click to pin a starting point, then hover over a destination for the route and time breakdown. Click again to move the pin or press Escape to clear it. On touch screens, tap to pin and tap a destination.

## Run locally

Use Node.js 22+ and Python 3.12+.

```sh
npm ci
python -m pip install -r requirements.txt
npm run build -- --all
python -m http.server --bind 127.0.0.1 --directory dist
```

Adapters cache public inputs in `.cache/`. To build a single city instead, run `python scripts/build_city.py --city <city-id>` (with optional `--osm-extract <path>`) and `npm run build`.

Open [the local map](http://127.0.0.1:8000/). Run `npm run benchmark -- <city-id>` to check sample trips and time warm heatmap computation.

## Travel-time estimates

The heatmap uses a fixed 60-minute colour scale. Walking follows mapped streets and paths, with short estimated connections from pins and entrances to the walking network. Station interiors and transfer walks are estimated. Train times use public schedules where available and track-distance estimates elsewhere. If track geometry is incomplete, the map connects the station coordinates. The app credits each city's sources and documents its timing assumptions under **Data and estimates**.

The build scores each station by summing `max(60 − travel minutes, 0) × cell area` across the city's heatmap grid. Gold, silver, and bronze rings mark the top three station complexes. Run `node scripts/centerpoints.mjs <city-id>` to print a city's results in km²·min from its local routing bundle.

## GitHub Pages

Set the repository's Pages source to **GitHub Actions**, then run **Deploy to GitHub Pages**. The workflow builds the city bundles and publishes `dist/`. Raw inputs, generated bundles, and build output stay out of Git. The browser fetches the selected city's bundle and calculates trips locally. OpenFreeMap serves the basemap tiles on demand.
