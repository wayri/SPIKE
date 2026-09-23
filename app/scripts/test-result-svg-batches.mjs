import assert from "node:assert/strict";
import { buildScalarSvgBatches } from "../src/resultSvgBatches.ts";

const samples = Array.from({ length: 21000 }, (_, index) => ({
  x_mm: index % 210,
  y_mm: Math.floor(index / 210),
  value: index / 20999,
  vertices_mm: index % 2 ? undefined : [
    [index % 210, Math.floor(index / 210), 0],
    [index % 210 + 0.5, Math.floor(index / 210), 0],
    [index % 210 + 0.5, Math.floor(index / 210) + 0.5, 0],
    [index % 210, Math.floor(index / 210) + 0.5, 0],
  ],
}));

const batches = buildScalarSvgBatches(samples, {
  minimum: 0,
  maximum: 1,
  cellSize: 0.5,
  smooth: false,
  colorBuckets: 48,
  project: point => point,
});
assert.ok(batches.length <= 48);
assert.equal(batches.reduce((sum, batch) => sum + batch.sampleCount, 0), samples.length);
assert.ok(batches.every(batch => batch.path.includes("M") && batch.color.startsWith("hsl(")));

const smooth = buildScalarSvgBatches(samples.slice(0, 10), {
  minimum: 0,
  maximum: 1,
  cellSize: 0.5,
  smooth: true,
  project: point => point,
});
assert.ok(smooth.some(batch => batch.path.includes("a")));

const verticalFace = buildScalarSvgBatches([{
  x_mm: 4,
  y_mm: 5,
  layer: "F.Cu->B.Cu",
  net: "VDD",
  value: 0.8,
  vertices_mm: [[3.9, 5, 0], [4.1, 5, 0], [4.1, 5, 1.6], [3.9, 5, 1.6]],
}], {
  minimum: 0,
  maximum: 1,
  cellSize: 0.4,
  smooth: false,
  project: point => point,
});
assert.equal(verticalFace.length, 1);
assert.match(verticalFace[0].path, /h0\.4v0\.4h-0\.4Z/,
  "a vertical result face must retain a visible 2D fallback glyph");

console.log("result SVG batching: all assertions passed");
