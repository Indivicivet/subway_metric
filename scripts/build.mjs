import { access, cp, mkdir } from "node:fs/promises";
import { cities } from "../src/cities.js";

const root = new URL("../", import.meta.url);
const output = new URL("dist/", root);
await Promise.all(
  Object.keys(cities).flatMap((city) => ["json", "bin.gz"].map(
    (extension) => access(new URL(`public/data/${city}.${extension}`, root)),
  )),
);
await mkdir(new URL("vendor/", output), { recursive: true });
await Promise.all([
  cp(new URL("public/", root), output, { recursive: true }),
  cp(new URL("src/", root), new URL("src/", output), { recursive: true }),
  ...["maplibre-gl.mjs", "maplibre-gl-worker.mjs", "maplibre-gl.css"].map((file) => cp(
    new URL(`node_modules/maplibre-gl/dist/${file}`, root),
    new URL(`vendor/${file.replace(/\.mjs$/, ".js")}`, output),
  )),
  cp(new URL("node_modules/maplibre-gl/LICENSE.txt", root), new URL("vendor/LICENSE.txt", output)),
]);
