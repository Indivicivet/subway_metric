# Subway Metric

Explore typical subway and walking times in Taipei and London. Choose a city in the map header. Hover to see the travel-time heatmap. Click to pin a starting point and hover elsewhere for the route and time breakdown. Click again to move the pin or press Escape to clear it. On touch screens, tap to pin and tap a destination.

## Run locally

Use Node.js 22+ and Python 3.12+. The data build downloads public source files into the ignored `.cache` directory. Place a London OpenStreetMap PBF covering **0.675°W to 0.320°E and 51.335°N to 51.764°N** at `.cache/london.osm.pbf`, or pass its path with `--osm-extract`. The GitHub Actions workflow shows how to assemble it from Geofabrik downloads.

```sh
npm ci
python -m pip install -r requirements.txt
python scripts/build_city.py
python scripts/build_city.py --city london
npm run build
python -m http.server 8137 --bind 127.0.0.1 --directory dist
```

Open [the local map](http://127.0.0.1:8137/) or [London directly](http://127.0.0.1:8137/?city=london). To use a smaller Taipei extract, pass `--osm-extract path/to/greater-taipei.osm.pbf` to the Taipei build. It must cover 121.320°E to 121.700°E and 24.874°N to 25.221°N. Run `npm run benchmark` for Taipei or `npm run benchmark -- london` to check sample trips and measure warm routing and heatmap computation.

## GitHub Pages

Set the repository's Pages source to **GitHub Actions**, then run **Deploy to GitHub Pages** from the Actions tab. The workflow generates and uploads `dist/`. Keep the inputs, generated data, and build output out of Git. The site uses relative asset URLs, including when hosted at a project path.

## Travel-time model

- Taipei includes the core MRT, the Circular Line, and the two MRT shuttles. Official data supplies running and dwell times in one direction per service pattern. The model applies those running times in both directions.
- London uses the 11 Underground lines. TfL schedules from 10:00 to 16:00 supply typical running times and frequencies, including branch destinations. Published NaPTAN entrances connect trains to the street network. Where entrance data is missing, the graph uses the station point.
- Typical waits use half the representative off-peak headway. Where short-turn trains share the same corridor, the model uses their combined frequency for trips inside that corridor.
- Walking follows OpenStreetMap topology. The app estimates the short connections between arbitrary map points and the nearest walkable segments, and between station entrances and platforms. Banqiao’s separate lines connect via the street network.
- Both heatmaps use a fixed 60-minute color scale. Grid spacing is 90 m in Taipei and 120 m in London. Pinned routes use the full routing graph. Track segments with incomplete geographic shapes are drawn using the station coordinates.

The data pipeline is in `scripts/build_city.py`. It produces a compact binary graph and geographic metadata. The worker in `src/worker.js` loads these static assets and solves routes locally. The basemap loads on demand from OpenFreeMap. Data credits and license links are included in the app.
