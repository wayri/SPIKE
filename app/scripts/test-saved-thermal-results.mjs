// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { savedThermalEntries, thermalResultEvidence } = await importTestTypescript("thermalSavedResultModel");

const grid = {
  origin_mm: [0, 0], spacing_mm: [1, 2], shape: [2, 2],
  temperatures_c: [25, 26, 27, 28], order: "x-fast",
};
const recordedRequest = {
  study_scope: "Steady-state board conduction with declared boundary conditions.",
  board: { include_zones: false, include_tracks: true },
};
const workspaceResult = {
  contract: "spike/board-thermal-result/v1",
  status: "completed",
  model_status: "approximate",
  grid,
  convergence: { linear_residual: 1e-14 },
  provenance: {
    solver_id: "board-thermal-reference",
    design_id: "board-a",
    board_model: "layered structured board",
    request: recordedRequest,
  },
};
const scenario = {
  contract: "spike/thermal-scenario/v1",
  name: "Board thermal review",
  board_thermal_request: {
    study_scope: recordedRequest.study_scope,
    board: { include_zones: true, include_tracks: true },
  },
  board_thermal_result: workspaceResult,
};
const caseResult = {
  ...workspaceResult,
  provenance: { ...workspaceResult.provenance, design_id: "board-case", request: recordedRequest },
};
const runResult = {
  ...workspaceResult,
  provenance: { ...workspaceResult.provenance, design_id: "board-run", request: recordedRequest },
};
const studies = [{
  version: 1, id: "study-a", name: "Thermal captures", notes: "", tags: [], archived: false, datasets: [],
  cases: [
    {
      id: "case-a", type: "thermal", mode: "steady", name: "Nominal", notes: "",
      scenario: { board_thermal_request: recordedRequest }, settings: {}, resultSnapshot: caseResult,
      datasetIds: [], runs: [{
        id: "run-a", capturedAt: "2026-10-05T08:30:00.000Z", association: "workspace-capture",
        caseType: "thermal", mode: "steady", scenario: { board_thermal_request: recordedRequest },
        settings: {}, facts: { status: "completed" }, resultSnapshot: runResult,
      }],
    },
    {
      id: "case-b", type: "pi", mode: "dc", name: "Not thermal", notes: "",
      scenario: {}, settings: {}, resultSnapshot: workspaceResult, datasetIds: [], runs: [],
    },
  ],
}];

const scenarioBefore = structuredClone(scenario);
const studiesBefore = structuredClone(studies);
const entries = savedThermalEntries(scenario, studies);

assert.deepEqual(entries.map(entry => [entry.id, entry.name, entry.source]), [
  ["workspace:board_thermal_result", "Board thermal review - board thermal", "Saved project thermal scenario"],
  ["study-a:case-a:thermal", "Thermal captures / Nominal", "Captured case result"],
  ["study-a:case-a:run-a:thermal", "Thermal captures / Nominal / 2026-10-05T08:30:00.000Z", "Retained run history"],
]);
assert.strictEqual(entries[0].result, workspaceResult, "browsing retains the immutable saved result object");
assert.strictEqual(entries[0].request, recordedRequest, "recorded provenance is the evidence-bearing request");
assert.deepEqual(scenario, scenarioBefore, "entry discovery does not update configured inputs or results");
assert.deepEqual(studies, studiesBefore, "entry discovery does not update captured cases or run history");
assert.equal(entries[0].inputsChanged, true, "configured and recorded requests are compared structurally");
assert.equal(entries[1].inputsChanged, false);

const evidence = thermalResultEvidence(entries[0]);
assert.equal(evidence.status, "completed", "status comes from the actual thermal result");
assert.equal(evidence.modelStatus, "approximate");
assert.equal(evidence.solverId, "board-thermal-reference");
assert.equal(evidence.designId, "board-a");
assert.equal(evidence.meshConverged, false, "a tiny linear residual is not mesh convergence evidence");
assert.strictEqual(evidence.grid, grid);
assert.ok(evidence.warnings.includes("zones excluded from the saved thermal model"));
assert.ok(evidence.warnings.includes("Mesh/grid convergence is not established by this saved result."));
assert.ok(evidence.warnings.some(message => message.includes("assembly cooling contacts")));

const noResult = savedThermalEntries({
  name: "Inputs only", board_thermal_request: recordedRequest,
}, []);
assert.deepEqual(noResult, [], "a configured request without a result is not presented as completed evidence");

const malformed = structuredClone(entries[0]);
malformed.result.grid.temperatures_c = [25, 26, 27];
assert.equal(thermalResultEvidence(malformed).grid, null, "malformed saved grids are rejected");

console.log("saved thermal result inventory, provenance, evidence, immutability, and grid admission passed");
