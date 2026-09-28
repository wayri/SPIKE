// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { boardThermalViewportGrid, boardThermalCuts } = await importTestTypescript("boardThermalViewport");
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
