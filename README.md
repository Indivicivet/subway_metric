# Subway Metric

Explore typical Taipei MRT and walking times on a geographic map. Hover to see the travel-time heatmap. Click to pin a starting point and hover elsewhere for the route and time breakdown. Click again to move the pin or press Escape to clear it. On touch screens, tap to pin and tap a destination.

## Run locally

Use Node.js 22+ and Python 3.12+. The data build downloads public source files, including the Taiwan OpenStreetMap extract, into the ignored `.cache` directory.

```sh
npm ci
python -m pip install -r requirements.txt
python scripts/build_city.py
npm run build
python -m http.server 8137 --bind 127.0.0.1 --directory dist
```

Open [the local map](http://127.0.0.1:8137/). For a smaller initial download, pass `--osm-extract path/to/greater-taipei.osm.pbf`. The extract must cover the map and routing buffer from 121.320°E to 121.700°E and 24.874°N to 25.221°N. Run `npm run benchmark` to check sample trips and measure warm routing and heatmap computation.

## GitHub Pages

Set the repository's Pages source to **GitHub Actions**, then run **Deploy to GitHub Pages** from the Actions tab. The workflow generates and uploads `dist/`. Keep the inputs, generated data, and build output out of Git. The site uses relative asset URLs, including when hosted at a project path.

## Travel-time model

- The core Taipei MRT includes the Circular Line and the two MRT shuttles. Official data supplies running and dwell times in one direction per service pattern. The model applies those running times in both directions.
- Typical waits use half the representative off-peak headway. Where short-turn trains share the same corridor, the model uses their combined frequency for trips inside that corridor.
- Walking follows OpenStreetMap topology. The app estimates the short connections between arbitrary map points and the nearest walkable segments, and between station entrances and platforms. Banqiao’s separate lines connect via the street network.
- The heatmap samples the network on a 90 m grid and uses a fixed 60-minute color scale. Pinned routes use the full routing graph. Track segments with incomplete geographic shapes are drawn using the station coordinates.

The data pipeline is in `scripts/build_city.py`. It produces a compact binary graph and geographic metadata. The worker in `src/worker.js` loads these static assets and solves routes locally. The basemap loads on demand from OpenFreeMap. Data credits and license links are included in the app.
