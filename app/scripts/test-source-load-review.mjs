// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/sourceLoadReview.ts", import.meta.url))],
  bundle: true, write: false, format: "esm", platform: "node",
});
const { sourceLoadReview } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].contents).toString("base64")}`);
const normalizerBundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/analysisResults.ts", import.meta.url))],
  bundle: true, write: false, format: "esm", platform: "node",
});
const { normalizeSolverResult } = await import(`data:text/javascript;base64,${Buffer.from(normalizerBundle.outputFiles[0].contents).toString("base64")}`);
const path = { load_id: "J20.2", source_id: "R19.3", supply_net: "/12Vout",
  source_voltage_v: 12, load_voltage_v: 11.997, supply_drop_v: .003, load_current_a: 3.3 };
const result = { mode: "dc", status: "completed", model_status: "approximate", summary: {}, provenance: {},
  source_to_load: { status: "validated", voltage_reference: "source_boundary", source_current_balance_a: 1e-14, paths: [path] } };
const normalized = normalizeSolverResult({ contract: "spike/v1", analysis_id: "real-board", mode: "dc",
  status: "completed", model_status: "approximate", summary: {}, fields: {}, networks: { source_to_load: result.source_to_load } });
assert.deepEqual(normalized.source_to_load, result.source_to_load);
assert.equal(sourceLoadReview(normalized, "/12Vout", 2).paths[0].loadId, "J20.2");
const review = sourceLoadReview(result, "/12Vout", 2);
assert.equal(review.status, "validated");
assert.equal(review.paths[0].limitState, "exceeded");
assert.equal(review.paths[0].loopDropV, null);
assert.equal(sourceLoadReview(result, "GND", 2), null);
assert.equal(sourceLoadReview({ ...result, status: "failed" }, "/12Vout", 2), null);
assert.equal(sourceLoadReview({ ...result, provenance: { solved: false } }, "/12Vout", 2), null);
assert.equal(sourceLoadReview({ ...result, source_to_load: { ...result.source_to_load,
  paths: [{ ...path, supply_drop_v: .0001 }] } }, "/12Vout", 2), null);
assert.equal(sourceLoadReview({ ...result, source_to_load: { ...result.source_to_load,
  paths: [path, { ...path, load_id: "J15.2", supply_drop_v: .0001 }] } }, "/12Vout", 2), null);
const loop = sourceLoadReview({ ...result, source_to_load: { ...result.source_to_load,
  paths: [{ ...path, return_net: "GND", loop_drop_v: .001 }] } }, "/12Vout", 2);
assert.equal(loop.paths[0].limitState, "below limit (screen)");
assert.equal(loop.paths[0].returnNet, "GND");
const reverse = sourceLoadReview({ ...result, source_to_load: { ...result.source_to_load,
  paths: [{ ...path, load_voltage_v: 12.001, supply_drop_v: -.001 }] } }, "/12Vout", 2);
assert.equal(reverse.paths[0].limitState, "reverse");
assert.equal(sourceLoadReview({ ...result, source_to_load: { ...result.source_to_load,
  paths: [{ ...path, return_net: "GND", loop_drop_v: "bad" }] } }, "/12Vout", 2), null);
console.log("Source/load review: exact paths, limits, net scope, and failed evidence admission passed.");
