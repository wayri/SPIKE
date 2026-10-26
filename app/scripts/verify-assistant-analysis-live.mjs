// SPDX-License-Identifier: Apache-2.0
// Opt-in real-provider acceptance for the reviewed desktop analysis conversation.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { build } from "esbuild";

const app = resolve(import.meta.dirname, ".."), repository = resolve(app, "..");
const provider = process.argv[2], model = process.argv[3];
if (provider !== "lmstudio" || !model) throw new Error("Usage: node scripts/verify-assistant-analysis-live.mjs lmstudio EXACT_LOCAL_MODEL_ID");
const outputRoot = resolve(repository, "build/assistant-analysis-live");
mkdirSync(outputRoot, { recursive: true });
const receiptPath = resolve(outputRoot, "acceptance.json");
const python = process.env.SPIKE_PYTHON || resolve(repository, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const fixturePath = resolve(repository, "examples/tutorial_pi_si/straight_trace.design.json");
const design = JSON.parse(readFileSync(fixturePath, "utf8"));
const scenario = { contract: "spike/thermal/v1", mode: "steady_state", ambient_temperature_c: 25,
  heat_sources: [{ id: "board-total", power_w: 2, theta_ja_c_per_w: 10, thermal_capacitance_j_per_c: 20 }] };

const importTs = async path => {
  const bundle = await build({ entryPoints: [resolve(app, path)], bundle: true, write: false, format: "esm", platform: "node" });
  return import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].contents).toString("base64")}`);
};
const [{ runAssistantConversation }, { createMcpAnalysisConversation }, { assistantAssemblyContext }, { savedThermalEntries, thermalResultEvidence }] = await Promise.all([
  importTs("src/assistantConversation.ts"), importTs("src/mcpAnalysisConversation.ts"), importTs("src/assistantAssemblyTools.ts"), importTs("src/thermalSavedResultModel.ts"),
]);

const workerCalls = [];
const worker = request => {
  workerCalls.push({ method: request.method, id: request.id ?? null });
  const code = "import json,sys; from python.spike_core.service import handle; r=json.load(sys.stdin); print(json.dumps(handle(r),allow_nan=False))";
  const child = spawnSync(python, ["-c", code], { cwd: repository, input: JSON.stringify(request), encoding: "utf8",
    timeout: request.method === "assistant_turn" ? 180000 : 30000, maxBuffer: 32 * 1024 * 1024, windowsHide: true });
  if (child.error || child.status !== 0) throw new Error(`Worker ${request.method} failed: ${child.error?.message || child.stderr}`);
  return Promise.resolve(JSON.parse(child.stdout));
};

const assembly = { assembly_id: "assistant-analysis-fixture", frame: { frame_id: "root", parent_frame_id: null, units: "mm", handedness: "right",
  transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1] },
  boards: [{ id: "board-1", name: design.name, design_id: design.design_id, frame: { frame_id: "board-frame", parent_frame_id: "root", units: "mm", handedness: "right",
    transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1] } }], parts: [], harnesses: [], thermal_contacts: [], electrical_bonds: [] };
const context = { design, canonicalDesign: null, assembly, assemblyDesigns: null, assemblyScope: { board_instance_id: "board-1", design_id: design.design_id },
  activeDesignId: design.design_id, boardFile: fixturePath, extensions: [], results: [] };
const published = [], reviews = [], evidence = [], views = [], reports = [];
let thermalState = { name: "Live compact thermal fixture", ...scenario };
const analysis = createMcpAnalysisConversation({
  getContext: () => context,
  callWorker: worker,
  admitScope: async () => ({ admitted: true, fixture: true }),
  publishResult: (result, meta) => { published.push({ result, meta }); context.results.push(result); thermalState = { ...thermalState, result }; },
});
const retained = () => savedThermalEntries(thermalState, []).map(row => ({ ...row, label: row.name, domain: "thermal" }));
const appContext = () => ({ projectName: "Synthetic assistant analysis acceptance", boardLoaded: true, activeDesignId: design.design_id,
  studyCount: 0, resultIds: retained().map(row => row.id), assemblyId: assembly.assembly_id });
const onCommand = async (command, args) => {
  if (command === "status") return appContext();
  if (command === "assembly_context") return assistantAssemblyContext(assembly, null, args);
  if (["analysis_context", "analysis_describe", "analysis_prepare", "analysis_patch", "analysis_preflight", "analysis_run", "analysis_job", "analysis_evidence"].includes(command)) return analysis.handle(command, args);
  if (command === "assistant_saved_results") return { results: retained().map(row => ({ id: row.id, label: row.label, domain: row.domain,
    status: row.result.status ?? null, modelStatus: row.result.model_status ?? null, fields: Object.keys(row.result), evidence: thermalResultEvidence(row) })) };
  if (command === "analysis_view_result") {
    const row = retained().find(item => item.id === args.resultId); if (!row) throw new Error("Choose an actual retained result ID.");
    views.push({ resultId: row.id }); return { status: "result_opened", resultId: row.id, contract: row.result.contract };
  }
  if (command === "analysis_generate_report") {
    if (Object.keys(args).length) throw new Error("Report generation takes no arguments.");
    reports.push({ resultIds: retained().map(row => row.id) });
    return { status: "report_preview_ready", saved: false, message: "Fixture report callback opened; no file exported." };
  }
  throw new Error(`Unsupported live fixture command: ${command}`);
};
const exactMutation = proposal => {
  if (proposal.name === "spike_prepare") return proposal.arguments.kind === "thermal" && proposal.arguments.scope === "active_board"
    && JSON.stringify(proposal.arguments.parameters) === JSON.stringify({ scenario });
  if (proposal.name === "spike_preflight" || proposal.name === "spike_run") return typeof proposal.arguments.caseId === "string" && proposal.arguments.caseId.length > 0;
  return false;
};

let messages = [], failure = null;
const stepEvidence = [];
const runStep = async (name, prompt, requiredTool) => {
  const before = evidence.length;
  messages = await runAssistantConversation({ provider, model, allowCloud: false, shareProjectContext: true,
    messages: [...messages, { role: "user", content: prompt }], getContext: appContext, getRevision: () => analysis.getRevision(), runWorker: worker, onCommand,
    review: async proposal => { const accepted = exactMutation(proposal); reviews.push({ ...proposal, accepted }); return accepted; },
    onEvidence: item => { evidence.push(item); console.log(`${name}: ${item.toolCall.name} ${item.state}`); },
  });
  const rows = evidence.slice(before); stepEvidence.push({ name, rows });
  assert.ok(rows.some(item => item.state === "completed" && item.toolCall.name === requiredTool), `Model skipped ${requiredTool} during ${name}`);
};

try {
  await runStep("inspect", "Call spike_assembly once with offset 0 limit 10. Report only retained occurrence identity, units and whether explicit links exist.", "spike_assembly");
  await runStep("capability", "Call spike_capabilities with kind thermal. State that the compact estimate is approximate and does not solve PCB spreading, CFD, airflow or radiation.", "spike_capabilities");
  await runStep("prepare", `Call spike_prepare exactly once with kind thermal, scope active_board, and parameters ${JSON.stringify({ scenario })}. Do not change or add fields.`, "spike_prepare");
  await runStep("preflight", "Use the exact caseId returned above and call spike_preflight once. Then poll its job with spike_job until it is no longer running. Do not run the solve yet.", "spike_preflight");
  await runStep("solve", "Use the same admitted caseId and call spike_run once. Poll the solve with spike_job until it is no longer running. Do not invent results.", "spike_run");
  await runStep("evidence", "For the completed solve job, call spike_evidence for path summary with offset 0 limit 20, then path sources with offset 0 limit 20, then path provenance with offset 0 limit 20, then path issues with offset 0 limit 20. Compare actual maximum temperature against 25 + 2*10 = 45 degrees C and preserve the approximate-model warning.", "spike_evidence");
  await runStep("retain", "Call spike_saved_results. Use its exact live result ID to call spike_show_result. Then call spike_report with no arguments. State that preview is not an export.", "spike_saved_results");

  assert.equal(published.length, 1, "Exactly one genuine solver result must be published");
  const result = published[0].result?.data?.analysis_result ?? published[0].result?.analysis_result ?? published[0].result;
  assert.equal(result.contract, "spike/thermal-result/v1"); assert.equal(result.status, "completed"); assert.equal(result.model_status, "approximate");
  assert.equal(result.summary.source_count, 1); assert.equal(result.summary.total_power_w, 2); assert.equal(result.summary.max_steady_temperature_c, 45);
  assert.equal(result.sources[0].steady_temperature_c, 45); assert.equal(result.sources[0].temperature_rise_c, 20);
  assert.ok(result.issues.some(issue => issue.code === "COMPACT_THERMAL_MODEL"));
  assert.ok(evidence.some(item => item.toolCall.name === "spike_evidence" && item.state === "completed"));
  assert.equal(views.length, 1); assert.equal(reports.length, 1);
  assert.ok(!JSON.stringify(messages).toLowerCase().includes("production qualified"), "Conversation made an unsupported production qualification claim");
  console.log("Live assistant analysis acceptance passed with actual compact-thermal worker evidence.");
} catch (error) { failure = error instanceof Error ? { message: error.message, stack: error.stack } : { message: String(error) }; throw error; }
finally {
  writeFileSync(receiptPath, JSON.stringify({ provider, model, fixturePath, scenario, oracle: { max_steady_temperature_c: 45 },
    workerCalls, reviews, evidence, published, views, reports, messages, failure,
    scope: "real LM Studio provider + actual assistantConversation + actual mcpAnalysisConversation + actual Python worker; native presentation replaced by bounded fixture callbacks" }, null, 2));
  console.log(`Evidence: ${receiptPath}`);
}
