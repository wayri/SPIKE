import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(specifier, context, nextResolve) {
  if (specifier.startsWith(".") && !specifier.endsWith(".ts")) return nextResolve(`${specifier}.ts`, context);
  return nextResolve(specifier, context);
} });
const { extensionAnalysisResult } = await import("../src/extensionAnalysisResult.ts");
const result = {
  contract: "spike/v1", analysis_id: "external-1", status: "completed", mode: "dc", model_status: "experimental",
  summary: { maximum_voltage_drop_v: 0.003 }, fields: { visualization: { scalar_fields: { voltage_v: [{ x_mm: 1, y_mm: 2, net: "VCC", value: 12 }] } } },
  networks: {}, probes: [], issues: [], provenance: { solver: "test.adapter", design_id: "board-1", design_digest_sha256: "abc" },
};
const data = { analysis_result: result, input_design_sha256: "abc" };
const bundle = extensionAnalysisResult("analyses", "spike/v1", data);
assert.equal(bundle?.analysis_id, "external-1");
assert.equal(bundle?.model_status, "experimental");
assert.equal(bundle?.provenance.solver, "test.adapter");
assert.equal(bundle?.scalar_fields.voltage_v[0].value, 12);
assert.deepEqual(bundle?.scalar_fields.voltage_drop_v, []);
assert.equal(extensionAnalysisResult("panels", "spike/v1", data), null);
assert.equal(extensionAnalysisResult("analyses", "other", data), null);
assert.equal(extensionAnalysisResult("analyses", "spike/v1", { ...data, input_design_sha256: "wrong" }), null);
console.log("extension analysis result: all assertions passed");
