import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const resultsSource = readFileSync(new URL("../src/analysisResults.ts", import.meta.url), "utf8");
const viewportSource = readFileSync(new URL("../src/BoardViewport.tsx", import.meta.url), "utf8");

assert.match(resultsSource, /export type ComponentBridge = \{/);
assert.match(resultsSource, /representation: "electrical_equivalent_line"/);
assert.match(resultsSource, /current_density_supported: false/);
assert.match(resultsSource, /componentBridges\(visualization\.component_bridges\)/);
assert.match(resultsSource, /vertices_mm: \[start, end\]/);

assert.match(viewportSource, /const bridgePosition = \(vertex: \[number, number, number\], layer\?: string\) =>/);
assert.match(viewportSource, /vertex\[2\] \* scale \+ explodedOffset\(layer\) \+ 0\.14/);
assert.match(viewportSource, /new THREE\.LineDashedMaterial\(/);
assert.match(viewportSource, /physicalGeometry: false/);
assert.match(viewportSource, /currentDensitySupported: false/);

console.log("component bridge result contract and overlay policy: all assertions passed");
