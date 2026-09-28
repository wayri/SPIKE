// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { boardThermalViewportResult, boardThermalCellProbe } = await importTestTypescript("boardThermalViewportProbe");
const saved = {
  contract: "spike/board-thermal-result/v1", status: "completed", model_status: "approximate",
  grid: { order: "x-fast", origin_mm: [10, 20], spacing_mm: [2, 4], shape: [2, 1], temperatures_c: [30, 40] },
  layer_grids: [
    { name: "F.Cu", thickness_mm: 0.04, temperatures_c: [31, 41] },
    { name: "Core", thickness_mm: 1.2, temperatures_c: [32, 42] },
  ],
};
const result = boardThermalViewportResult(saved);
assert.ok(result);
assert.deepEqual(boardThermalCellProbe(result, -1, 1), {
  column: 1, row: 0, center_mm: [13, 22], temperature_c: 40,
  layer: "Top surface", depth_mm: null, modelStatus: "approximate",
});
assert.deepEqual(boardThermalCellProbe(result, 1, 0), {
  column: 0, row: 0, center_mm: [11, 22], temperature_c: 32,
  layer: "Core", depth_mm: 0.64, modelStatus: "approximate",
});
assert.equal(boardThermalCellProbe(result, 1, 2), null);
assert.equal(boardThermalViewportResult({ ...saved, status: "blocked" }), null);
assert.equal(boardThermalViewportResult({ ...saved, layer_grids: [{ ...saved.layer_grids[0], temperatures_c: [31] }] }), null);
assert.equal(boardThermalViewportResult({ ...saved, model_status: undefined }), null);
console.log("board thermal viewport cell probe passed");
