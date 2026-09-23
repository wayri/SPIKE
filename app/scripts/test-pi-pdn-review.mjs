import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/PiPdnReviewModel.ts", import.meta.url), "utf8")
  .replace('import type { PdnReview, SolverResultBundle } from "./analysisResults";', "")
  .replace('import { resultSolvedForPresentation } from "./resultAdmission";',
    'const resultSolvedForPresentation = result => result.status === "completed" && result.summary?.solved !== false && !result.summary?.failure_stage;');
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { pdnReviewView } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);

const grid = [1e6, 2e6];
const result = {
  analysis_id: "solve-1", status: "completed", model_status: "approximate", summary: { solved: true }, provenance: {},
  parasitics: [{ net: "VCC", impedance: grid.map(frequency_hz => ({ frequency_hz, magnitude_ohm: 0.1 })) }],
};
const candidate = {
  id: "C17", status: "evaluated", placement_method: "multiport_impedance_loading", model_status: "approximate",
  source_result_id: "solve-1", location: { position_mm: [42, 18], layer: "F.Cu" },
  capacitance_f: 1e-6, esr_ohm: 0.01, esl_h: 1e-9, count: 2,
  mounting_resistance_ohm: 0.002, mounting_inductance_h: 1e-9,
  worst_impedance_ohm: 0.04, worst_frequency_hz: 2e6, worst_target_ratio: 0.8,
  worst_impedance_improvement_percent: 60, maximum_local_degradation_percent: 4,
  violation_count: 0, passes_target: true,
  response: grid.map(frequency_hz => ({ frequency_hz, magnitude_ohm: 0.04 })),
};
const review = { contract: "spike/pdn-review/v1", net: "VCC", status: "violated", model_status: "approximate",
  target_ohm: 0.05, maximum_impedance_ohm: 0.1, violation_count: 2,
  candidate_screening: [candidate] };

const view = (s = result, r = review, id = "solve-1") => pdnReviewView(s, r, "VCC", id);
assert.equal(view().candidates[0].status, "evaluated");
assert.match(view(result, review, null).reason, /no verified binding/);
assert.match(view({ ...result, status: "failed" }).reason, /source solve failed/);
assert.match(view({ ...result, summary: { solved: false } }).reason, /source solve failed/);
assert.match(view(result, { ...review, net: "GND" }).reason, /contract, net, or target/);
assert.equal(view(result, { ...review, candidate_screening: [{ ...candidate, source_result_id: "other" }] }).candidates[0].status, "rejected");
assert.equal(view(result, { ...review, candidate_screening: [{ ...candidate, response: [{ frequency_hz: 1e6, magnitude_ohm: 0.04 }, { frequency_hz: 3e6, magnitude_ohm: 0.04 }] }] }).candidates[0].status, "rejected");
assert.equal(view(result, { ...review, candidate_screening: [{ ...candidate, worst_impedance_ohm: Number.NaN }] }).candidates[0].status, "rejected");
assert.equal(view(result, { ...review, candidate_screening: [{ ...candidate, status: "rejected", issues: [{ code: "bad", message: "bad port" }] }] }).candidates[0].status, "rejected");
console.log("PI PDN review admission and candidate comparison assertions passed");
