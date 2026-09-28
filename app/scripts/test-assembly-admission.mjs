import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { assemblyAdmissionParams, assemblyAnalysisScope, requireAdmittedAssembly, requireSupportedAssemblyPhysics } from "../src/assemblyAdmission.ts";

const assembly = {
  contract: "spike/assembly-ir/v1",
  assembly_id: "fixture",
  name: "Fixture",
  boards: [{ id: "board-a", design_id: "design-a" }],
  parts: [],
};
const design = { contract: "spike/v1", name: "Active board", layers: [] };
const request = assemblyAdmissionParams(assembly, design, "design-a", "pi_dc", 8);
assert.equal(request.workload, "pi_dc");
assert.equal(request.memory_limit_gb, 8);
assert.deepEqual(Object.keys(request.designs), ["design-a"]);
assert.equal(request.designs["design-a"], design);
assert.equal(assemblyAdmissionParams(null, design, "design-a", "pi_dc", 8), null);
assert.deepEqual(assemblyAdmissionParams(assembly, design, "different-design", "pi_dc", 8).designs, {});

const multiBoard = { ...assembly, boards: [...assembly.boards, { id: "board-b", design_id: "design-b" }] };
assert.deepEqual(Object.keys(assemblyAdmissionParams(multiBoard, design, "design-a", "thermal", 8).designs), ["design-a"]);

const retainedDesigns = {
  contract: "spike/assembly-designs/v1",
  active_design_id: "design-a",
  designs: [
    { contract: "spike/design-ir/v2", design_id: "design-a", name: "A" },
    { contract: "spike/design-ir/v2", design_id: "design-b", name: "B" },
  ],
};
assert.deepEqual(
  Object.keys(assemblyAdmissionParams(multiBoard, design, "design-a", "pi_dc", 8, retainedDesigns).designs).sort(),
  ["design-a", "design-b"],
);
const scope = assemblyAnalysisScope(multiBoard, "design-a");
assert.equal(scope.contract, "spike/assembly-analysis-scope/v1");
assert.equal(scope.mode, "active_board_only");
assert.equal(scope.active_board_id, "board-a");
assert.equal(scope.active_design_id, "design-a");
assert.equal(scope.assembly, multiBoard);
assert.throws(() => assemblyAnalysisScope({ ...multiBoard, boards: [...multiBoard.boards, { id: "board-a-2", design_id: "design-a" }] }, "design-a"), /exactly one active board/i);
const repeatedDesign = { ...multiBoard, boards: [...multiBoard.boards, { id: "board-a-2", design_id: "design-a" }] };
assert.equal(assemblyAnalysisScope(repeatedDesign, "design-a", null, "board-a-2").active_board_id, "board-a-2");
assert.throws(() => assemblyAnalysisScope(repeatedDesign, "design-a", null, "board-b"), /must reference the active design/i);

requireAdmittedAssembly({
  contract: "spike/assembly-resource-admission/v1",
  workload: "pi_ac",
  can_admit: true,
  issues: [],
}, "pi_ac");
assert.throws(() => requireAdmittedAssembly({
  contract: "spike/assembly-resource-admission/v1",
  workload: "thermal",
  can_admit: false,
  issues: [{ severity: "error", message: "Board design unavailable." }],
}, "thermal"), /Board design unavailable/);
assert.throws(() => requireAdmittedAssembly(null, "full_wave"), /invalid contract/i);
assert.throws(() => requireAdmittedAssembly({
  contract: "spike/assembly-resource-admission/v1",
  workload: "pi_dc",
  can_admit: true,
}, "pi_ac"), /invalid contract/i);

requireSupportedAssemblyPhysics({ ...assembly, parts: [{ id: "visual-only" }] }, "pi_dc", "design-a");
requireSupportedAssemblyPhysics({ ...multiBoard, harnesses: [{ id: "harness" }], parts: [{ id: "enclosure" }] }, "thermal", "design-a");
assert.throws(() => requireSupportedAssemblyPhysics({ ...multiBoard, boards: [...multiBoard.boards, { id: "board-a-2", design_id: "design-a" }] }, "pi_dc", "design-a"), /exactly one active board/i);

const app = readFileSync(resolve(import.meta.dirname, "..", "src", "App.tsx"), "utf8");
for (const fragment of [
  'method: "estimate_assembly_resources"',
  'const assemblyScope = await requireAssemblyAdmission("full_wave")',
  'const assemblyScope = await onRequireAdmission("thermal")',
  "const assemblyScope = await onRequireAdmission(admissionWorkload)",
  "assembly_scope: assemblyScope",
  'job.mode === "ac" || job.mode === "transient"',
]) assert.ok(app.includes(fragment), `execution-path admission is missing: ${fragment}`);
assert.ok(app.match(/await requireAssemblyAdmission\("full_wave"\)/g)?.length >= 3, "openEMS prepare, EMI prepare, and run must each recheck admission");
assert.ok(app.match(/await onRequireAdmission\("thermal"\)/g)?.length >= 4, "thermal preflight, prepare, run, and compact estimate must each bind scope");

const spice = readFileSync(resolve(import.meta.dirname, "..", "src", "SpiceWorkbench.tsx"), "utf8");
assert.ok(spice.match(/assembly_scope: assemblyScope/g)?.length >= 4, "native MNA, PEEC-MNA, owned SPIKES, and ngspice must each bind scope");

console.log("assembly admission: all assertions passed");
