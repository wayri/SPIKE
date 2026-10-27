// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";

const source = readFileSync(resolve(import.meta.dirname, "../src/geometryPiHandler.ts"), "utf8");
const module = { exports: {} };
new Function("module", "exports", ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText)(module, module.exports);
const { buildGeometryPiRequest, runGeometryPi, geometryPiVisualization } = module.exports;

const design = { design_id: "board-A", units: "mm", pads: [{ id: "supply-pad", net_name: "VCC" }] };
const reviewedSpec = {
  mode: "dc", solver_id: "auto", formulation: "auto", net_names: ["VCC", "GND"],
  sources: [{ id: "source", voltage_v: 3.3, geometry_anchor: { id: "supply-pad", type: "pad" } }],
  loads: [{ id: "load", current_a: 1.2, geometry_anchor: { id: "load-pad", type: "pad" } }],
  return_path: { mode: "explicit", net: "GND" }, mesh: { target_size_mm: 0.5 },
  options: { pi_path: { id: "reviewed-path" }, include_branch_results: true },
};
const assemblyScope = { contract: "spike/assembly-analysis-scope/v1", active_board_id: "occurrence-A" };
const input = { design, reviewedSpec, assemblyScope };
const before = JSON.stringify(input);
const request = buildGeometryPiRequest(input);
assert.equal(request.method, "run_preflighted_analysis");
assert.equal(request.params.design, design);
assert.equal(request.params.assembly_scope, assemblyScope);
assert.deepEqual(request.params.spec, { ...reviewedSpec, solver_id: "spike.routed_dc", formulation: "resistive_network" });
assert.equal(request.params.spec.sources, reviewedSpec.sources);
assert.equal(request.params.spec.loads, reviewedSpec.loads);
assert.equal(request.params.spec.options, reviewedSpec.options);
assert.equal(JSON.stringify(input), before, "reviewed geometry, terminals, return path and options are not mutated");
assert.equal(buildGeometryPiRequest({ ...input, assemblyScope: null }).params.assembly_scope, null);
assert.throws(() => buildGeometryPiRequest({ ...input, design: { source_path: "arbitrary.step" } }), /normalized PCB/);
assert.throws(() => buildGeometryPiRequest({ ...input, reviewedSpec: { ...reviewedSpec, mode: "ac" } }), /reviewed DC/);
assert.throws(() => buildGeometryPiRequest({ ...input, reviewedSpec: { ...reviewedSpec, solver_id: "external.fem" } }), /existing SPIKE/);
assert.throws(() => buildGeometryPiRequest({ ...input, reviewedSpec: { ...reviewedSpec, formulation: "fem" } }), /resistive-network/);

const visualization = {
  schema: "spike/result-visualization/v1",
  mesh: [{ id: "face-1", source_id: "trace-1", vertices_mm: [[0, 0, 0], [1, 0, 0], [1, 1, 0]] }],
  scalar_fields: { voltage_v: [{ element_id: "face-1", value: 3.29 }], current_density_a_mm2: [], power_loss_w: [] },
  vector_fields: {},
};
const analysisResult = {
  mode: "dc", status: "completed", model_status: "approximate", fields: { visualization },
  issues: [{ code: "CONVERGENCE_REQUIRED", status: "approximate" }], provenance: { solver: "spike-hybrid-dc/v4" },
};
const transaction = { contract: "spike/preflighted-analysis/v1", status: "completed", preflight: { can_solve: true }, analysis_result: analysisResult };
const response = { ok: true, result: transaction, meta: { retained: true } };
let dispatched;
assert.equal(await runGeometryPi(input, async value => { dispatched = value; return response; }), response);
assert.deepEqual(dispatched, request);
assert.equal(geometryPiVisualization(transaction), visualization, "retained faces and fields are returned unchanged");
assert.equal(response.result.analysis_result, analysisResult, "issues, provenance and approximate status are preserved");
const blocked = { ok: true, result: { contract: transaction.contract, status: "blocked", preflight: { can_solve: false, issues: [{ message: "unmapped terminal" }] }, analysis_result: null } };
assert.equal(await runGeometryPi(input, async () => blocked), blocked);
assert.equal(geometryPiVisualization(blocked.result), null);
const failed = { ok: false, error: "trusted worker unavailable", error_code: "WORKER_FAILURE" };
assert.equal(await runGeometryPi(input, async () => failed), failed);
await assert.rejects(runGeometryPi(input, async () => ({ ok: true, result: {} })), /preflighted geometry PI/);
await assert.rejects(runGeometryPi(input, async () => { throw new Error("admission failed"); }), /admission failed/);
assert.equal(geometryPiVisualization(undefined), null);
assert.equal(geometryPiVisualization({ ...transaction, analysis_result: { ...analysisResult, mode: "ac" } }), null);
assert.equal(geometryPiVisualization({ ...transaction, analysis_result: { ...analysisResult, status: "failed" } }), null);
assert.equal(geometryPiVisualization({ ...transaction, analysis_result: { ...analysisResult, fields: {} } }), null);
assert.equal(geometryPiVisualization({ ...transaction, analysis_result: { ...analysisResult, fields: { visualization: { scalar_fields: {} } } } }), null);
console.log("Geometry PI handoff: reviewed setup, exact DC route, unchanged fields/provenance and blocked/error results passed.");
