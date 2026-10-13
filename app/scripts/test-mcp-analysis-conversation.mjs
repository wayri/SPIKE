// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const bundle = await build({ entryPoints: [fileURLToPath(new URL("../src/mcpAnalysisConversation.ts", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node" });
const { createMcpAnalysisConversation } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].contents).toString("base64")}`);
let context = { design: { design_id: "board", nets: { 1: "CLK", 2: "DATA", 3: "GND" }, tracks: [], pads: [], stackup: [] }, canonicalDesign: { contract: "spike/spider/v2", nets: [{ name: "CLK" }, { name: "DATA" }, { name: "GND" }] }, extensions: [], results: [] };
const calls = [], published = [];
let release;
const pending = new Promise(resolve => { release = resolve; });
const helper = createMcpAnalysisConversation({ getContext: () => context, callWorker: async request => { calls.push(request); if (request.method === "preflight_analysis") { await pending; return { ok: true, result: { can_solve: true, issues: [] } }; } return { ok: true, result: { status: "completed", model_status: "unvalidated", analysis_result: { status: "completed", model_status: "unvalidated", fields: { samples: [1, 2, 3] }, issues: [], provenance: { solver: "fixture" } } } }; }, publishResult: (result, meta) => published.push({ result, meta }) });
const initialRevision = helper.getRevision();
const status = await helper.handle("analysis_context", {});
assert.deepEqual(status.nets, ["CLK", "DATA", "GND"]);
assert.equal(status.boardLoaded, true);
const described = await helper.handle("analysis_describe", {});
assert.equal(described.analyses.si.schema, "si-uniform-channel-request-v1.schema.json");
assert.match(described.analyses.multiboard_em.description, /not full-wave/);
assert.equal(helper.getRevision(), initialRevision, "Read-only discovery must not invalidate a pending review");
const prepared = await helper.handle("analysis_prepare", { kind: "pi", scope: "active_board", parameters: { spec: { solver_id: "fixture", mode: "dc", net_names: ["CLK"], sources: [], loads: [], return_path: {} } } });
assert.notEqual(helper.getRevision(), initialRevision, "Preparing a case changes the broker revision");
const preparedRevision = helper.getRevision();
const reviewedCase = helper.reviewCase(prepared.caseId);
assert.deepEqual(reviewedCase.parameters, prepared.parameters);
reviewedCase.parameters.spec.sources.push({ injected: true });
assert.equal(helper.reviewCase(prepared.caseId).parameters.spec.sources.length, 0, "Review evidence cannot mutate the executable case");
assert.equal(prepared.solved, false);
assert.equal(calls.length, 0);
await assert.rejects(helper.handle("analysis_run", { caseId: prepared.caseId }), /passing preflight/);
const preflight = await helper.handle("analysis_preflight", { caseId: prepared.caseId });
assert.notEqual(helper.getRevision(), preparedRevision, "Starting admission invalidates earlier reviews");
const pendingRevision = helper.getRevision();
assert.equal(preflight.status, "running");
assert.equal((await helper.handle("analysis_preflight", { caseId: prepared.caseId })).jobId, preflight.jobId);
await assert.rejects(helper.handle("analysis_patch", { caseId: prepared.caseId, patch: { spec: {} } }), /active job/);
release();
async function finished(jobId) { for (let i = 0; i < 100; i++) { const row = await helper.handle("analysis_job", { jobId }); if (row.status !== "running") return row; await new Promise(resolve => setTimeout(resolve, 1)); } throw new Error("Fixture job did not finish"); }
assert.equal((await finished(preflight.jobId)).result.ready, true);
assert.notEqual(helper.getRevision(), pendingRevision, "Completed preflight changes executable admission state");
const admittedRevision = helper.getRevision();
const running = await helper.handle("analysis_run", { caseId: prepared.caseId });
assert.notEqual(helper.getRevision(), admittedRevision, "Dispatching a reviewed solve changes job state");
const runningRevision = helper.getRevision();
await finished(running.jobId);
assert.notEqual(helper.getRevision(), runningRevision, "Completed jobs invalidate prior action reviews");
assert.equal(published.length, 1);
assert.equal((await helper.handle("analysis_run", { caseId: prepared.caseId })).jobId, running.jobId);
assert.equal(calls.filter(row => row.method === "run_preflighted_analysis").length, 1);
const evidence = await helper.handle("analysis_evidence", { jobId: running.jobId, query: { path: "analysis_result.fields.samples", offset: 1, limit: 1 } });
assert.deepEqual(evidence.value, [2]);
assert.equal(evidence.total, 3);
await assert.rejects(helper.handle("analysis_evidence", { jobId: running.jobId, query: { path: "__proto__" } }), /safe evidence/);
await assert.rejects(helper.handle("analysis_evidence", { jobId: running.jobId, query: { path: "fields.not_present" } }), /not returned/);
const beforeExternalPatch = helper.getRevision();
await helper.handle("analysis_patch", { caseId: prepared.caseId, patch: { spec: { solver_id: "fixture", mode: "dc", net_names: ["CLK"], sources: [], loads: [], return_path: {} } } });
assert.notEqual(helper.getRevision(), beforeExternalPatch, "An external MCP patch must invalidate assistant review bindings even when React state is unchanged");
await assert.rejects(helper.handle("analysis_run", { caseId: prepared.caseId }), /passing preflight/);
context = { ...context, design: { ...context.design, nets: { 1: "CHANGED" } } };
await assert.rejects(helper.handle("analysis_preflight", { caseId: prepared.caseId }), /design or assembly changed/);
await assert.rejects(helper.handle("analysis_prepare", { kind: "pi", scope: "active_board", parameters: { method: "run_python_script" } }), /Unknown analysis parameter/);
await assert.rejects(helper.handle("analysis_prepare", { kind: "pi", scope: "full_assembly", parameters: {} }), /explicit matching scope/);
await assert.rejects(helper.handle("arbitrary_method", {}), /Unsupported desktop/);
const si = await helper.handle("analysis_prepare", { kind: "si", scope: "active_board", parameters: { request: { contract: "spike/si-uniform-channel-request/v1", signal_net: "UNLOADED", victim_net: "DATA", reference_net: "GND", reference_layer: "B.Cu", frequencies_hz: [0, 1e9, 2e9], reference_impedance_ohm: 50 } } });
assert.ok(si.missing.some(path => path.includes("not present")));
const thermal = await helper.handle("analysis_prepare", { kind: "thermal", scope: "active_board", parameters: { scenario: { mode: "steady_state", ambient_temperature_c: 25, heat_sources: [{ id: "U1", theta_ja_c_per_w: 10 }] } } });
assert.ok(thermal.missing.some(path => path.includes("power_w")));
const missingJob = await helper.handle("analysis_preflight", { caseId: si.caseId });
assert.equal((await finished(missingJob.jobId)).result.ready, false);
await assert.rejects(helper.handle("analysis_run", { caseId: si.caseId }), /passing preflight/);

const script = "print('prepared fixture')\n";
const scriptHash = Buffer.from(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(script))).toString("hex");
const extensionCalls = [];
const ext = createMcpAnalysisConversation({ getContext: () => ({ ...context, extensions: [{ id: "spike.emerge-suite", trusted: true, contributes: { analyses: [{ id: "emerge-radiation", input_schema: { required: ["signal_net"] } }] } }] }), callWorker: async request => { extensionCalls.push(request); return { ok: true, result: request.params.contribution_id === "emerge-preview" ? { data: { script, script_sha256: scriptHash, case_sha256: "a".repeat(64) } } : { status: "completed", data: { analysis_result: { status: "completed", model_status: "unvalidated" } } } }; } });
const extCase = await ext.handle("analysis_prepare", { kind: "extension", scope: "active_board", parameters: { extension_id: "spike.emerge-suite", contribution_id: "emerge-radiation", parameters: { signal_net: "CLK" } } });
const extPreflight = await ext.handle("analysis_preflight", { caseId: extCase.caseId });
async function finishExt(jobId) { for (let i = 0; i < 100; i++) { const row = await ext.handle("analysis_job", { jobId }); if (row.status !== "running") return row; await new Promise(resolve => setTimeout(resolve, 1)); } throw new Error("Extension fixture did not finish"); }
assert.equal((await finishExt(extPreflight.jobId)).result.ready, true);
assert.equal(extensionCalls[0].params.context.parameters.preview_radiation, true);
const extRun = await ext.handle("analysis_run", { caseId: extCase.caseId });
await finishExt(extRun.jobId);
assert.equal(extensionCalls[1].params.context.parameters.expected_generated_script_sha256, scriptHash);
for (const status of ["unsupported", "partial"]) {
  const forwarded = [];
  const guarded = createMcpAnalysisConversation({ getContext: () => context, publishResult: result => forwarded.push(result), callWorker: async request => ({ ok: true, result: request.method === "validate_thermal" ? { valid: true } : { status, model_status: "approximate", summary: { scope: "fixture" } } }) });
  const c = await guarded.handle("analysis_prepare", { kind: "thermal", scope: "active_board", parameters: { scenario: { mode: "steady_state", ambient_temperature_c: 25, heat_sources: [{ id: "U1", power_w: 1, theta_ja_c_per_w: 10 }] } } });
  const wait = async jobId => { for (let i = 0; i < 100; i++) { const value = await guarded.handle("analysis_job", { jobId }); if (value.status !== "running") return value; await new Promise(resolve => setTimeout(resolve, 1)); } throw new Error("Guard fixture timed out"); };
  await wait((await guarded.handle("analysis_preflight", { caseId: c.caseId })).jobId);
  const final = await wait((await guarded.handle("analysis_run", { caseId: c.caseId })).jobId);
  assert.equal(final.status, status === "unsupported" ? "blocked" : "partial");
  assert.equal(forwarded.length, status === "unsupported" ? 0 : 1);
}
console.log("MCP analysis conversation: loaded identity, missing inputs, async admission/solve, duplicate job reuse, exact script binding, bounded evidence and forbidden dispatch checks passed.");

for (const kind of ["constructor", "__proto__", "toString"]) {
  await assert.rejects(helper.handle("analysis_describe", { kind }), /Unknown/);
  await assert.rejects(helper.handle("analysis_prepare", { kind, scope: "active_board" }), /supported/);
}
const nestedThermal = await helper.handle("analysis_prepare", { kind: "board_thermal", scope: "active_board", parameters: { request: { board: { model: "layered", include_vias: true }, components: [{ component_ref: "U1" }], ambient_temperature_c: 25, transient: {} } } });
for (const field of ["request.board.thickness_mm", "request.board.convection_top_w_m2k", "request.board.dielectric_conductivity_w_mk", "request.board.via_plating_thickness_mm", "request.components.0.power_w", "request.components.0.r_junction_case_k_w", "request.transient.time_step_s"]) assert.ok(nestedThermal.missing.includes(field), field);
for (const kind of ["pi", "em"]) {
  const forwarded = [];
  const actual = createMcpAnalysisConversation({ getContext: () => context, publishResult: result => forwarded.push(result), callWorker: async request => ({ ok: true, result: request.method === "preflight_analysis" ? { can_solve: true } : request.method === "emi_preflight" ? { can_screen: true } : kind === "pi" ? { contract: "spike/preflighted-analysis/v1", status: "blocked", analysis_result: { contract: "spike/v1", status: "completed_with_warnings", model_status: "approximate" } } : { status: "completed_screening_only", model_status: "approximate" } }) });
  const parameters = kind === "pi" ? { spec: { solver_id: "fixture", mode: "dc", net_names: ["CLK"], sources: [], loads: [], return_path: {} } } : { setup: { ...Object.fromEntries(["contract", "selected_nets", "return_nets", "requested_analyses", "frequency", "environment", "mesh", "max_solver_time_s", "excitation", "net_metrics"].map(key => [key, {}])) } };
  const c = await actual.handle("analysis_prepare", { kind, scope: "active_board", parameters });
  const wait = async jobId => { for (let i = 0; i < 100; i++) { const row = await actual.handle("analysis_job", { jobId }); if (row.status !== "running") return row; await new Promise(resolve => setTimeout(resolve, 1)); } throw new Error("Actual envelope fixture timed out"); };
  const preflight = await wait((await actual.handle("analysis_preflight", { caseId: c.caseId })).jobId);
  assert.equal(preflight.result.ready, true, JSON.stringify(preflight));
  const final = await wait((await actual.handle("analysis_run", { caseId: c.caseId })).jobId);
  assert.equal(final.status, kind === "em" ? "completed_screening_only" : "completed"); assert.equal(forwarded.length, 1);
}

const assemblyBound = await helper.handle("analysis_prepare", { kind: "thermal", scope: "active_board", parameters: { scenario: { mode: "steady_state", ambient_temperature_c: 25, heat_sources: [{ id: "U1", power_w: 1, theta_ja_c_per_w: 10 }] } } });
context = { ...context, assemblyDesigns: { designs: [{ design_id: "other-board", nets: [] }] } };
await assert.rejects(helper.handle("analysis_preflight", { caseId: assemblyBound.caseId }), /changed/);

// Explicit AC diagnostics retain the same input/preflight/job gates as other workflows.
{
  const submitted = [], returned = [];
  const acContext = { design: { design_id: "ac-board", nets: [] }, results: [] };
  const ac = createMcpAnalysisConversation({ getContext: () => acContext, callWorker: async call => {
    submitted.push(call); return { ok: true, result: { contract: "spike/ac-pi-result/v1", status: "completed_with_warnings", model_status: "experimental", samples: [{ frequency_hz: 1e6, status: "computed" }] } };
  }, publishResult: (value, meta) => returned.push({ value, meta }) });
  const empty = await ac.handle("analysis_prepare", { kind: "ac_pi", scope: "active_board", parameters: {} });
  assert.ok(empty.missing.includes("request.length_m"));
  const request = { contract: "spike/ac-pi-request/v1", frequencies_hz: [1e6], length_m: 10, R_ohm_per_m: 0, L_h_per_m: 250e-9, G_s_per_m: 0, C_f_per_m: 100e-12, source_impedance_ohm: [0, 0], load_impedance_ohm: null };
  const ready = await ac.handle("analysis_prepare", { kind: "ac_pi", scope: "active_board", parameters: { request } });
  await assert.rejects(ac.handle("analysis_run", { caseId: ready.caseId }), /preflight/);
  const wait = async id => { for (let i=0; i<100; i++) { const row = await ac.handle("analysis_job", { jobId: id }); if (row.status !== "running") return row; await new Promise(resolve => setTimeout(resolve, 1)); } throw new Error("AC job timed out"); };
  const preflight = await wait((await ac.handle("analysis_preflight", { caseId: ready.caseId })).jobId);
  assert.equal(preflight.result.ready, true);
  assert.equal((await wait((await ac.handle("analysis_run", { caseId: ready.caseId })).jobId)).status, "completed");
  assert.equal(submitted.length, 1); assert.equal(submitted[0].method, "analyze_ac_power_integrity");
  assert.deepEqual(submitted[0].params.request, request);
  assert.equal(returned[0].meta.kind, "ac_pi"); assert.deepEqual(returned[0].meta.parameters.request, request);
}
