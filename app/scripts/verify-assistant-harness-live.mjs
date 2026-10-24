// SPDX-License-Identifier: Apache-2.0
// Opt-in live local-model acceptance. It stages an in-memory fixture draft only.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";

const app = resolve(import.meta.dirname, ".."), repository = resolve(app, "..");
const provider = process.argv[2], model = process.argv[3];
if (!["lmstudio", "ollama"].includes(provider) || !model) throw new Error("Usage: node scripts/verify-assistant-harness-live.mjs lmstudio|ollama EXACT_LOCAL_MODEL_ID");
const outputRoot = resolve(repository, "build/assistant-harness-live");
mkdirSync(outputRoot, { recursive: true });
const folder = mkdtempSync(resolve(outputRoot, "case-"));
writeFileSync(resolve(folder, "measurements.csv"), "time_s,value_V\n0,3.2\n1,3.3\n2,3.4\n");
const python = process.env.SPIKE_PYTHON || resolve(repository, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const worker = request => {
  const child = spawnSync(python, ["-c", "import json,sys; from python.spike_core.service_assistant import handle_assistant_request; r=json.load(sys.stdin); print(json.dumps(handle_assistant_request(r['method'],r.get('params',{})),allow_nan=False))"],
    { cwd: repository, input: JSON.stringify(request), encoding: "utf8", timeout: 135000, maxBuffer: 32 * 1024 * 1024, windowsHide: true });
  if (child.error || child.status !== 0) throw new Error(`Fixture worker failed: ${child.error?.message || child.stderr}`);
  return Promise.resolve(JSON.parse(child.stdout));
};
const load = (path, dependencies) => {
  const module = { exports: {} };
  new Function("require", "module", "exports", ts.transpileModule(readFileSync(resolve(app, path), "utf8"),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2021 } }).outputText)(name => {
    if (!(name in dependencies)) throw new Error(`Unexpected fixture dependency: ${name}`);
    return dependencies[name];
  }, module, module.exports);
  return module.exports;
};
const skills = load("src/assistantSkills.ts", {});
const chat = load("src/assistantConversation.ts", { "./assistantSkills": skills });
const harness = load("src/assistantTaskHarness.ts", { "./workerBridge": { runLocalWorker: worker, selectNativeImportFile: async () => ({ path: folder, fileName: "fixture" }) } }).createAssistantTaskHarness();
const drafts = [], evidence = [], reviews = [];
const command = (name, args) => harness.command(name, args, "fixture", draft => drafts.push(draft), () => "fixture");
await command("assistant_choose_work_folder", {});
const context = () => ({ projectName: "Synthetic harness acceptance", boardLoaded: false, studyCount: 0, taskHarness: harness.context("fixture") });
let messages = [];
try {
  // Check each capability as a bounded user step; a model skipping a requested
  // operation fails its step instead of being mistaken for completed work.
  const steps = [
    { action: "list", prompt: "Use spike_work_files with action list to list the selected folder now. Report returned names. Do not calculate, read a file or draft code yet." },
    { action: "read", prompt: "Use spike_work_files with action read and relativeName measurements.csv. Show the actual header, row values and source hash. Do not summarize or draft yet." },
    { action: "csv_summary", prompt: "Use spike_work_files with action csv_summary, relativeName measurements.csv, column value_V and units V. Report the actual count, min, max, mean and source hash. Do not use mental arithmetic or draft code yet." },
    { action: "draft", prompt: "Now call spike_python_draft with title CSV summary to stage a short Python script that reads measurements.csv with the standard library and prints the same statistics after validating inputs. Do not execute or save a file. State that it is staged but unexecuted." },
  ];
  for (const step of steps) {
    const before = evidence.length;
    messages = await chat.runAssistantConversation({ provider, model, allowCloud: false, shareProjectContext: true,
    messages: [...messages, { role: "user", content: step.prompt }],
    getContext: context, getRevision: () => "fixture-revision", runWorker: worker,
    onCommand: (name, args) => name === "status" ? Promise.resolve(context()) : command(name, args),
    review: async proposal => { assert.equal(proposal.name, "spike_python_draft"); reviews.push(proposal); return true; },
    onEvidence: item => { evidence.push(item); console.log(`${item.toolCall.name}: ${item.state}`); },
  });
    assert.ok(evidence.slice(before).some(item => item.state === "completed" && (step.action === "draft" ? item.toolCall.name === "spike_python_draft" : item.toolCall.name === "spike_work_files" && item.toolCall.arguments.action === step.action)), `Model skipped required step ${step.action}`);
  }
  const summary = evidence.find(item => item.toolCall.name === "spike_work_files" && item.toolCall.arguments.action === "csv_summary" && item.state === "completed");
  assert.ok(summary, "Model did not calculate the required deterministic summary");
  const value = JSON.parse(summary.detail);
  assert.equal(value.statistics.count, 3); assert.ok(Math.abs(value.statistics.mean - 3.3) < 1e-12);
  assert.ok(evidence.some(item => item.toolCall.arguments.action === "list" && item.state === "completed"));
  assert.ok(evidence.some(item => item.toolCall.arguments.action === "read" && item.state === "completed"));
  assert.equal(drafts.length, 1); assert.equal(reviews.length, 1);
  assert.equal(drafts[0].workingDirectory, folder);
  console.log("Live harness acceptance passed. Draft remained in memory, unexecuted and unsaved.");
} finally {
  writeFileSync(resolve(folder, "acceptance.json"), JSON.stringify({ provider, model, evidence, reviews, drafts: drafts.map(({ code, ...draft }) => ({ ...draft, sourceBytes: Buffer.byteLength(code), executed: false, saved: false })), messages, scope: "real local provider + actual conversation/harness/services; native picker/editor replaced by fixture callbacks" }, null, 2));
  console.log(`Evidence: ${resolve(folder, "acceptance.json")}`);
}
