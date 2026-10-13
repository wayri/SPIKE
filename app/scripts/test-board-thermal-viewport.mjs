// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { boardThermalViewportGrid, boardThermalCuts, boardThermalCellGeometry, boardThermalAxisEdges } = await importTestTypescript("boardThermalViewport");
const grid = { origin_mm: [50, 100], spacing_mm: [2, 3], shape: [2, 2], temperatures_c: [30, 40, 50, 60], order: "x-fast" };
const result = { contract: "spike/board-thermal-result/v1", status: "completed", model_status: "approximate", grid };
assert.deepEqual(boardThermalViewportGrid(result), grid);
assert.equal(boardThermalViewportGrid({ ...result, status: "blocked" }), null);
assert.equal(boardThermalViewportGrid({ ...result, grid: { ...grid, temperatures_c: [30, NaN, 50, 60] } }), null);
assert.equal(boardThermalViewportGrid({ ...result, grid: { ...grid, order: "y-fast" } }), null);
const cuts = boardThermalCuts(grid, [53, 104], [
  { thickness_mm: 0.1, temperatures_c: [31, 41, 51, 61] },
  { thickness_mm: 0.9, temperatures_c: [32, 42, 52, 62] },
]);
assert.deepEqual(cuts.horizontal, [[51, 50], [53, 60]]);
assert.deepEqual(cuts.vertical, [[101.5, 40], [104.5, 60]]);
assert.deepEqual(cuts.throughStack, [[0.05, 61], [0.55, 62]]);
console.log("board thermal viewport grid and exact cuts passed");
const localized = { origin_mm: [50, 100], x_edges_mm: [50, 51, 55], y_edges_mm: [100, 101, 106], shape: [2, 2], temperatures_c: [30, 40, 50, 60], order: 'x-fast' };
assert.deepEqual(boardThermalViewportGrid({ ...result, grid: localized }), localized);
assert.deepEqual(boardThermalCellGeometry(localized, 3), { center_mm: [53, 103.5], size_mm: [4, 5] });
assert.deepEqual(boardThermalAxisEdges(localized, 0), [50, 51, 55]);
assert.deepEqual(boardThermalCuts(localized, [51.5, 101.5]).horizontal, [[50.5, 50], [53, 60]]);
for (const broken of [{ ...localized, spacing_mm: [1, 1] }, { ...localized, x_edges_mm: [50, 50, 55] }, { ...localized, y_edges_mm: [99, 100, 101] }]) {
  assert.equal(boardThermalViewportGrid({ ...result, grid: broken }), null);
}

const { boardThermalViewportResult, boardThermalDisplaySurfaces, boardThermalCellProbe } = await importTestTypescript("boardThermalViewportProbe");
const layered = boardThermalViewportResult({ ...result, layer_grids: [
  { name: "F.Cu", thickness_mm: 0.035, temperatures_c: [31, 41, 51, 61] },
  { name: "dielectric", thickness_mm: 1.53, temperatures_c: [32, 42, 52, 62] },
  { name: "B.Cu", thickness_mm: 0.035, temperatures_c: [33, 43, 53, 63] },
] });
const surfaces = boardThermalDisplaySurfaces(layered, 1.6);
assert.deepEqual(surfaces.map(row => [row.layerIndex, row.face, row.z_mm]),
  [[0, "top", 0.8], [2, "bottom", -0.8]], "normal view follows both physical board faces");
assert.strictEqual(surfaces[0].temperatures_c, layered.layers[0].temperatures_c,
  "top face uses the saved top-layer field without interpolation");
assert.strictEqual(surfaces[1].temperatures_c, layered.layers[2].temperatures_c,
  "bottom face uses the independent saved bottom-layer field without mirroring the top");
assert.ok(surfaces.every(row => row.opacity >= 0.85), "saved temperature colors remain legible over an opaque PCB");
for (const separation of [NaN, Infinity, -1, 0, 0.001]) assert.deepEqual(
  boardThermalDisplaySurfaces(layered, 1.6, { inspectInternalLayers: true, separationMm: separation }), surfaces);
const exploded = boardThermalDisplaySurfaces(layered, 1.6,
  { inspectInternalLayers: true, separationMm: 2, visibility: { "F.Cu": false } });
assert.deepEqual(exploded.map(row => [row.layerIndex, row.face, row.z_mm]),
  [[0, "top", 0.8], [2, "bottom", -0.8], [1, "internal", 2.8]]);
assert.strictEqual(exploded[2].temperatures_c, layered.layers[1].temperatures_c);
assert.equal(boardThermalCellProbe(layered, exploded[2].layerIndex, 0, exploded[2].face).depth_mm, 0.8,
  "visual explosion must not alter physical saved depth");
const plate = boardThermalViewportResult(result);
assert.equal(plate.bottomSurfaceAvailable, false);
assert.deepEqual(boardThermalDisplaySurfaces(plate, 1.6).map(row => [row.layerIndex, row.face, row.z_mm]),
  [[-1, "top", 0.8]], "a plate field must not be mirrored onto an unsolved underside");
assert.deepEqual(boardThermalDisplaySurfaces(layered, 0), [], "invalid physical board thickness is rejected");
console.log("Physical thermal faces, explicit internal inspection, visibility and saved-value probes passed.");
