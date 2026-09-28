// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import { registerHooks } from "node:module";

registerHooks({ resolve(specifier, context, nextResolve) {
  if (specifier.startsWith(".") && !specifier.endsWith(".ts")) return nextResolve(`${specifier}.ts`, context);
  return nextResolve(specifier, context);
} });
const { emergeRadiationPatterns, savedEmergeRadiationPreview } = await import("../src/emergeRadiationView.ts");
const solved = JSON.parse(fs.readFileSync(new URL("../../examples/esp32/evidence/rf_surrogate_result.json", import.meta.url), "utf8"));
const envelope = { status: "completed", data: { analysis_result: solved } };
const patterns = emergeRadiationPatterns(envelope);
assert.equal(patterns.length, 3, "all ESP32 solved-frequency radiation grids should be offered in EM");
assert.equal(patterns[1].frequency_hz, 2.45e9);
assert.equal(patterns[1].relative_amplitude_db.length, patterns[1].theta_deg.length * patterns[1].phi_deg.length);
assert.deepEqual(emergeRadiationPatterns({ ...envelope, data: { analysis_result: { ...solved, status: "failed" } } }), []);
assert.deepEqual(emergeRadiationPatterns({ ...envelope, data: { analysis_result: { ...solved, mode: "si" } } }), []);
assert.deepEqual(emergeRadiationPatterns({ ...envelope, data: { analysis_result: { ...solved, provenance: { ...solved.provenance, solver: "other" } } } }), []);
const bad = structuredClone(solved);
bad.fields.radiation.patterns_3d[0].relative_amplitude_db.pop();
assert.deepEqual(emergeRadiationPatterns({ status: "completed", data: { analysis_result: bad } }), []);
const sourceDesignId = "kicad-3199ce0a25f8987020e716d8";
const saved = savedEmergeRadiationPreview(solved, sourceDesignId);
assert.equal(saved?.surrogate, true);
assert.equal(emergeRadiationPatterns(saved?.envelope).length, 3);
assert.equal(savedEmergeRadiationPreview(solved, "different-board"), null, "saved surrogate must not attach to another board");
assert.equal(savedEmergeRadiationPreview({ ...solved, status: "failed" }, sourceDesignId), null);
console.log("EM workspace: three admitted ESP32 radiation grids and invalid-result gates passed");
