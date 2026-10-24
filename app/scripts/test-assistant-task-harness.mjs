// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";

const root = resolve(import.meta.dirname, "..");
const compile = path => ts.transpileModule(readFileSync(resolve(root, path), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const load = (path, require) => { const module = { exports: {} }; new Function("module", "exports", "require", compile(path))(module, module.exports, require); return module.exports; };
let folder = { path: "C:/work", fileName: "work" }, pending, identity = "p1", waiting = false;
const requests = [], drafts = [];
const api = load("src/assistantTaskHarness.ts", name => {
  assert.equal(name, "./workerBridge");
  return { selectNativeImportFile: async () => folder, runLocalWorker: async request => {
    requests.push(request);
    if (waiting) return new Promise(resolve => { pending = resolve; });
    return { ok: true, result: { source: { relativeName: "data.csv", sha256: "source-hash" }, statistics: { count: 3, mean: 3.3 } } };
  } };
});
const harness = api.createAssistantTaskHarness();
const command = (name, args = {}) => harness.command(name, args, identity, draft => drafts.push(draft), () => identity);
await assert.rejects(command(api.WORK_FILES_COMMAND, { action: "list" }), /Choose a work folder/);
await command(api.WORK_FOLDER_COMMAND);
assert.equal(harness.context(identity).workFolderSelected, true);
const result = await command(api.WORK_FILES_COMMAND, { action: "csv_summary", relativeName: "data.csv", column: "value_V", units: "V" });
assert.equal(requests[0].params.root, "C:/work");
assert.equal(result.statistics.mean, 3.3);
await assert.rejects(command(api.WORK_FILES_COMMAND, { action: "list", root: "C:/private" }), /cannot choose/);
await command(api.SCRIPT_DRAFT_COMMAND, { title: "Read data", source: "print('review me')" });
assert.equal(drafts.length, 1); assert.equal(drafts[0].workingDirectory, "C:/work");
const staged = await command(api.SCRIPT_DRAFT_COMMAND, { title: "Summary", source: "print(3.3)" });
assert.equal(staged.executed, false); assert.equal(staged.saved, false); assert.match(staged.sha256, /^[a-f0-9]{64}$/);
assert.equal(requests.length, 1, "staging code does not launch a Python worker");
await assert.rejects(command(api.SCRIPT_DRAFT_COMMAND, { title: "../../overwrite", source: "print(1)" }), /simple draft/);
waiting = true;
const read = command(api.WORK_FILES_COMMAND, { action: "read", relativeName: "data.csv" });
folder = { path: "C:/other", fileName: "other" };
await command(api.WORK_FOLDER_COMMAND);
pending({ ok: true, result: { text: "old evidence" } });
await assert.rejects(read, /changed during file inspection/);
identity = "p2";
assert.equal(harness.context(identity).workFolderSelected, false);

// Exercise the real catalog and conversation broker: source is inert until review.
const skills = load("src/assistantSkills.ts", () => assert.fail("unexpected dependency"));
const chat = load("src/assistantConversation.ts", name => { assert.equal(name, "./assistantSkills"); return skills; });
for (const accepted of [false, true]) {
  let turn = 0, reviewed = 0;
  const applied = [], evidence = [];
  await chat.runAssistantConversation({ provider: "lmstudio", model: "fixture", allowCloud: false, shareProjectContext: true,
    messages: [{ role: "user", content: "Draft a script" }], getContext: () => ({}), getRevision: () => "r1",
    runWorker: async () => ({ ok: true, result: { message: turn++ ? { role: "assistant", content: "Draft handled", tool_calls: [] }
      : { role: "assistant", content: "", tool_calls: [{ id: "draft", name: "spike_python_draft", arguments: { title: "Inspect", source: "print(1)" } }] } } }),
    review: async proposal => { reviewed++; assert.equal(proposal.arguments.source, "print(1)"); return accepted; },
    onCommand: async (name, args) => { applied.push({ name, args }); return { executed: false, saved: false }; }, onEvidence: item => evidence.push(item),
  });
  assert.equal(reviewed, 1); assert.equal(applied.length, accepted ? 1 : 0);
  assert.equal(evidence[0].state, accepted ? "completed" : "blocked");
}
// Recoverable schema errors reach the model as tool evidence without dispatch.
let turn = 0;
const dispatches = [], evidence = [];
await chat.runAssistantConversation({ provider: "ollama", model: "fixture", allowCloud: false, shareProjectContext: true,
  messages: [{ role: "user", content: "List files" }], getContext: () => ({}), getRevision: () => "r1", review: async () => assert.fail("read-only"),
  runWorker: async request => {
    if (turn === 1) assert.match(request.params.messages.at(-1).content, /Invalid action/);
    if (turn === 2) assert.match(request.params.messages.at(-1).content, /identical request already failed/);
    return { ok: true, result: { message: turn++ < 3 ? { role: "assistant", content: "", tool_calls: [{ id: `call-${turn}`, name: "spike_work_files", arguments: { action: turn <= 2 ? "invented" : "list" } }] } : { role: "assistant", content: "Listed", tool_calls: [] } } };
  }, onCommand: async name => { dispatches.push(name); return { entries: [] }; }, onEvidence: item => evidence.push(item),
});
assert.deepEqual(dispatches, ["assistant_work_files"]);
assert.deepEqual(evidence.map(item => item.state), ["failed", "blocked", "completed"]);
console.log("Assistant task harness: folder authority, revision drift, inert drafts, review and schema recovery passed.");
