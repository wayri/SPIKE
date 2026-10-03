// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import ts from "typescript";

const sourceUrl = new URL("../src/pythonWorkspaceTemplates.ts", import.meta.url);
const source = readFileSync(sourceUrl, "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  fileName: "pythonWorkspaceTemplates.ts",
  reportDiagnostics: true,
});
assert.equal(transpiled.diagnostics?.length ?? 0, 0, "template catalog must transpile cleanly");
const moduleUrl = `data:text/javascript;base64,${Buffer.from(transpiled.outputText).toString("base64")}`;
const { PYTHON_TEMPLATES, PYTHON_STARTER } = await import(moduleUrl);

assert.ok(Array.isArray(PYTHON_TEMPLATES));
assert.ok(PYTHON_TEMPLATES.length >= 30, "catalog must contain at least 30 templates");
const ids = PYTHON_TEMPLATES.map(template => template.id);
assert.equal(new Set(ids).size, ids.length, "template IDs must be unique");
assert.ok(PYTHON_TEMPLATES.every(template =>
  typeof template.title === "string" && template.title.length > 0 &&
  typeof template.category === "string" && template.category.length > 0 &&
  typeof template.description === "string" && template.description.length > 0 &&
  Array.isArray(template.requirements) && typeof template.code === "string" && template.code.length > 0));

const categories = new Set(PYTHON_TEMPLATES.map(template => template.category));
for (const expected of ["Basics", "Design inspection", "PI - DC", "PI - AC", "Circuits and parasitics",
  "SI - channels", "SI - crosstalk", "SI - protocols", "Thermal - steady", "Thermal - transient",
  "Thermal - board", "Thermal - assembly", "EM and EMI", "Extensions", "Multiboard", "Result review",
  "Export", "Parameter sweeps"]) {
  assert.ok(categories.has(expected), `missing category: ${expected}`);
}
assert.equal(PYTHON_STARTER, PYTHON_TEMPLATES[0].code);

const python = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
for (const template of PYTHON_TEMPLATES) {
  assert.ok(Buffer.byteLength(template.code, "utf8") <= 512 * 1024, `${template.id} exceeds the workspace code limit`);
  const result = spawnSync(python, ["-c", "import sys; compile(sys.stdin.read(), '<template>', 'exec')"], {
    input: template.code, encoding: "utf8",
  });
  assert.equal(result.status, 0, `${template.id} is invalid Python:\n${result.stderr}`);
}

const smokeIds = ["hello-context", "design-summary", "net-inventory", "layer-stackup", "design-issues", "result-overview"];
const fakeContext = `
class Spike:
    design = {"contract": "spike/v1", "design_id": "fixture", "name": "Fixture", "units": "mm",
              "layers": [], "stackup": [], "nets": [], "tracks": [], "vias": [], "pads": [],
              "zones": [], "components": [], "issues": []}
    results = {"contract": "spike/results-context/v1", "complete": True,
               "result": {"contract": "spike/v1", "analysis_id": "fixture-result", "status": "completed",
                          "mode": "dc", "model_status": "unvalidated", "summary": {}, "issues": [],
                          "provenance": {}, "fields": {}, "networks": {}}}
    def call(self, method, params=None):
        if method == "health": return {"contract": "spike/worker-health/v1", "worker_version": "test"}
        raise RuntimeError("unexpected method: " + method)
spike = Spike()
`;
for (const id of smokeIds) {
  const code = PYTHON_TEMPLATES.find(template => template.id === id)?.code;
  const result = spawnSync(python, ["-c", fakeContext + "\n" + code], { encoding: "utf8" });
  assert.equal(result.status, 0, `${id} failed contextual smoke test:\n${result.stderr}`);
}

const executionMethods = new Map([
  ["run-dc-request", { method: "run_analysis", key: "spec", value: { mode: "dc" } }],
  ["run-ac-request", { method: "run_analysis", key: "spec", value: { mode: "ac" } }],
  ["run-si-workflow-request", { method: "run_si_workflow", key: "request", value: {} }],
  ["run-si-channel-request", { method: "run_si_uniform_channel", key: "request", value: {} }],
  ["run-board-thermal-request", { method: "run_board_thermal", key: "request", value: {} }],
  ["run-emi-preflight-request", { method: "emi_preflight", key: "setup", value: {} }],
  ["run-emi-screen-request", { method: "emi_screen", key: "setup", value: {} }],
  ["run-multiboard-circuit-request", { method: "run_multiboard_circuit", key: "request", value: {} }],
  ["run-multiboard-si-request", { method: "run_multiboard_si_independent_batch", key: "request", value: {} }],
  ["run-multiboard-thermal-request", { method: "run_multiboard_thermal", key: "request", value: {} }],
  ["run-multiboard-em-request", { method: "run_multiboard_em", key: "request", value: {} }],
]);
const requestDirectory = mkdtempSync(join(tmpdir(), "spike-python-template-test-"));
try {
for (const [id, fixture] of executionMethods) {
  const code = PYTHON_TEMPLATES.find(template => template.id === id)?.code;
  assert.ok(code, `missing execution template: ${id}`);
  assert.ok(code.includes(`spike.call("${fixture.method}", params)`), `${id} must call verified worker method ${fixture.method}`);
  assert.ok(code.includes("REQUEST_FILE = None"), `${id} must default to no request file`);
  const guardedContext = `
class Spike:
    design = {"contract": "spike/v1", "design_id": "fixture"}
    def call(self, method, params=None):
        raise RuntimeError("worker call must remain guarded while REQUEST_FILE is unset")
    def publish_result(self, result):
        raise RuntimeError("publish must remain guarded while REQUEST_FILE is unset")
spike = Spike()
`;
  const result = spawnSync(python, ["-c", guardedContext + "\n" + code], { encoding: "utf8" });
  assert.equal(result.status, 0, `${id} launched or failed with REQUEST_FILE unset:\n${result.stderr}`);
  assert.match(result.stdout, /nothing was launched/);

  const requestPath = join(requestDirectory, `${id}.json`);
  writeFileSync(requestPath, JSON.stringify({ [fixture.key]: fixture.value }), "utf8");
  const runnable = code.replace("REQUEST_FILE = None", `REQUEST_FILE = ${JSON.stringify(requestPath)}`);
  const dispatchContext = `
class Spike:
    design = {"contract": "spike/v1", "design_id": "fixture"}
    def call(self, method, params=None):
        print("CALLED", method)
        return {"contract": "spike/v1", "status": "completed", "model_status": "unvalidated",
                "issues": [], "provenance": {"design_id": "fixture"}}
    def publish_result(self, result):
        raise RuntimeError("PUBLISH_RESULT defaults to false")
spike = Spike()
`;
  const dispatched = spawnSync(python, ["-c", dispatchContext + "\n" + runnable], { encoding: "utf8" });
  assert.equal(dispatched.status, 0, `${id} fixture dispatch failed:\n${dispatched.stderr}`);
  assert.match(dispatched.stdout, new RegExp(`CALLED ${fixture.method}`));
}
const dc = PYTHON_TEMPLATES.find(template => template.id === "run-dc-request").code;
const conflictPath = join(requestDirectory, "conflicting-design.json");
writeFileSync(conflictPath, JSON.stringify({ spec: { mode: "dc" }, design: { design_id: "other" } }), "utf8");
const conflict = dc.replace("REQUEST_FILE = None", `REQUEST_FILE = ${JSON.stringify(conflictPath)}`);
const conflictRun = spawnSync(python, ["-c", `
class Spike:
    design = {"contract": "spike/v1", "design_id": "fixture"}
    def call(self, method, params=None): raise RuntimeError("must not dispatch")
spike = Spike()
` + conflict], { encoding: "utf8" });
assert.notEqual(conflictRun.status, 0, "conflicting request design must be rejected");
assert.match(conflictRun.stderr, /design_id differs/);
} finally {
  rmSync(requestDirectory, { recursive: true, force: true });
}

console.log(`Python template catalog OK: ${PYTHON_TEMPLATES.length} templates, ${categories.size} categories, ${executionMethods.size} guarded execution runners.`);
