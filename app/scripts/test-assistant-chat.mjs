// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const appRoot = resolve(import.meta.dirname, "..");
const nodeRequire = createRequire(import.meta.url);
const catalog = [
  { name: "inspect", description: "Inspect selected design context.", parameters: { type: "object" }, command: "analysis_context", effect: "read" },
  { name: "apply", description: "Apply a reviewed change.", parameters: { type: "object" }, command: "prepare_patch", effect: "edit" },
  { name: "simulate", description: "Run a reviewed analysis.", parameters: { type: "object" }, command: "run", effect: "run" },
];

function compile(path, jsx = false) {
  return ts.transpileModule(readFileSync(resolve(appRoot, path), "utf8"), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: jsx ? ts.JsxEmit.ReactJSX : undefined,
  } }).outputText;
}

function loadConversation() {
  const loaded = { exports: {} };
  new Function("require", "module", "exports", compile("src/assistantConversation.ts"))(name => {
    if (name === "./assistantSkills") return { assistantSystemPrompt: "fixture prompt", assistantToolCatalog: catalog, validateAssistantToolCall(toolName, args) {
      if (!catalog.some(tool => tool.name === toolName) || !args || typeof args !== "object") throw new Error("invalid tool call");
    } };
    return nodeRequire(name);
  }, loaded, loaded.exports);
  return loaded.exports;
}

const api = loadConversation();
const user = { role: "user", content: "Inspect the selected board" };
const answer = content => ({ ok: true, result: { message: { role: "assistant", content, tool_calls: [] }, provider: "openai", model: "fixture" } });
const turn = tool_calls => ({ ok: true, result: { message: { role: "assistant", content: "", tool_calls }, provider: "openai", model: "fixture" } });

// Cloud conversation consent does not imply project-context disclosure.
const cloudRequests = [];
const cloudMessages = await api.runAssistantConversation({
  provider: "openai", model: "fixture", allowCloud: true, shareProjectContext: false, messages: [user],
  getContext: () => ({ privateBoard: { nets: ["SECRET"] } }), getRevision: () => "r1",
  runWorker: async request => { cloudRequests.push(structuredClone(request)); return answer("General guidance"); },
  onCommand: async () => assert.fail("tools must be disabled"), review: async () => assert.fail("review must not open"),
});
assert.equal(cloudMessages.at(-1).content, "General guidance");
assert.equal(cloudRequests[0].params.allow_cloud, true);
assert.equal(cloudRequests[0].params.share_project_context, false);
assert.deepEqual(cloudRequests[0].params.tools, []);
assert.ok(!("context" in cloudRequests[0].params));
await assert.rejects(() => api.runAssistantConversation({
  provider: "anthropic", model: "fixture", allowCloud: false, shareProjectContext: false, messages: [user],
  getContext: () => ({}), getRevision: () => "r1", runWorker: async () => answer("bad"), onCommand: async () => ({}), review: async () => true,
}), /Allow cloud conversation/);

async function toolScenario({ effectName = "apply", approve = true, drift = false, driftBeforeReply = false, commandError = false } = {}) {
  const workerRequests = [], commands = [], proposals = [], evidence = [];
  let revision = "r1", count = 0;
  const messages = await api.runAssistantConversation({
    provider: "ollama", model: "local", endpoint: "http://127.0.0.1:11434", allowCloud: false, shareProjectContext: true, messages: [user],
    getContext: () => ({ selected: { boards: 1 } }), getRevision: () => revision,
    runWorker: async request => { workerRequests.push(structuredClone(request)); if (count++ === 0) { if (driftBeforeReply) revision = "r2"; return turn([{ id: "call-1", name: effectName, arguments: { value: 3 } }]); } return answer("Finished"); },
    review: async proposal => { proposals.push(proposal); if (drift) revision = "r2"; return approve; },
    onCommand: async (command, args) => { commands.push({ command, args }); if (commandError) throw new Error("solver fixture failed"); return { ok: true, changed: true }; },
    onEvidence: item => evidence.push(item),
  });
  return { workerRequests, commands, proposals, evidence, messages };
}

const approved = await toolScenario();
assert.equal(approved.proposals.length, 1);
assert.equal(approved.proposals[0].revision, "r1");
assert.deepEqual(approved.commands, [{ command: "prepare_patch", args: { value: 3 } }]);
assert.equal(approved.evidence[0].state, "completed");
assert.match(approved.workerRequests[1].params.messages.at(-1).content, /"changed":true/);
assert.match(approved.workerRequests[0].params.messages[1].content, /SPIKE UNTRUSTED PROJECT EVIDENCE/);
assert.doesNotMatch(JSON.stringify(approved.messages), /SPIKE UNTRUSTED PROJECT EVIDENCE/, "context envelope stays out of the visible transcript");

const rejected = await toolScenario({ approve: false });
assert.equal(rejected.commands.length, 0);
assert.equal(rejected.evidence[0].state, "blocked");
assert.match(rejected.workerRequests[1].params.messages.at(-1).content, /user rejected/);

const drifted = await toolScenario({ drift: true });
assert.equal(drifted.commands.length, 0);
assert.match(drifted.evidence[0].detail, /project changed/i);

const staleReply = await toolScenario({ driftBeforeReply: true });
assert.equal(staleReply.proposals.length, 0, "stale model plans are blocked before review");
assert.equal(staleReply.commands.length, 0);
assert.match(staleReply.evidence[0].detail, /changed after the assistant request/i);

const failed = await toolScenario({ effectName: "simulate", commandError: true });
assert.equal(failed.evidence[0].state, "failed");
assert.match(failed.workerRequests[1].params.messages.at(-1).content, /solver fixture failed/);

let unknownRound = 0;
const unknownEvidence = [];
await api.runAssistantConversation({
  provider: "ollama", model: "local", allowCloud: false, shareProjectContext: true, messages: [user], getContext: () => ({}), getRevision: () => "r1",
  runWorker: async () => unknownRound++ === 0 ? turn([{ id: "unknown-1", name: "invented_shell", arguments: {} }]) : answer("Could not run it"),
  onCommand: async () => assert.fail("unknown tools must not reach the broker"), review: async () => assert.fail("unknown tools must not be reviewed"),
  onEvidence: item => unknownEvidence.push(item),
});
assert.equal(unknownEvidence[0].state, "blocked");
assert.match(unknownEvidence[0].detail, /Unknown tool/);

const cyclic = {}; cyclic.self = cyclic;
assert.throws(() => api.jsonSafeContext(cyclic), /cycle/);
assert.throws(() => api.jsonSafeContext({ large: "x".repeat(api.ASSISTANT_CONTEXT_MAX_BYTES) }), /byte limit/);

await assert.rejects(() => api.runAssistantConversation({
  provider: "ollama", model: "local", allowCloud: false, shareProjectContext: true, messages: [user], getContext: () => ({}), getRevision: () => "r1",
  runWorker: async () => turn([{ id: "bad", name: "apply", arguments: { filePath: "C:/secret" } }]), onCommand: async () => ({}), review: async () => true,
}), /not accepted from a model/);
await assert.rejects(() => api.runAssistantConversation({
  provider: "ollama", model: "local", allowCloud: false, shareProjectContext: true, messages: [user], getContext: () => ({}), getRevision: () => "r1",
  runWorker: async () => turn(Array.from({ length: 17 }, (_, i) => ({ id: `c${i}`, name: "inspect", arguments: {} }))), onCommand: async () => ({}), review: async () => true,
}), /16-tool-call limit/);

const controller = new AbortController(); controller.abort();
await assert.rejects(() => api.runAssistantConversation({
  provider: "ollama", model: "local", allowCloud: false, shareProjectContext: false, messages: [user], getContext: () => ({}), getRevision: () => "r1",
  runWorker: async () => assert.fail("cancelled request reached worker"), onCommand: async () => ({}), review: async () => true, signal: controller.signal,
}), /cancelled/);

// Render the actual panel with worker and skill dependencies mocked.
const panelModule = { exports: {} };
new Function("require", "module", "exports", compile("src/AssistantChatPanel.tsx", true))(name => {
  if (name === "react") return React;
  if (name === "react/jsx-runtime") return nodeRequire("react/jsx-runtime");
  if (name === "./workerBridge") return { runLocalWorker: async request => request.method === "assistant_provider_status" ? { ok: true, result: { status: "ready", credential_configured: false } } : answer("ok"), cancelLocalWorker: async () => true };
  if (name === "./assistantSkills") return { assistantToolCatalog: catalog, toolCapabilityStates: { inspect: "available" } };
  if (name === "./assistantConversation") return api;
  if (name === "./AssistantChatPanel.css") return {};
  return nodeRequire(name);
}, panelModule, panelModule.exports);
const markup = renderToStaticMarkup(React.createElement(panelModule.exports.default, { onClose() {}, onCommand: async () => ({}), getContext: () => ({ boards: [1], nets: [1, 2] }), getRevision: () => "rev-1" }));
assert.match(markup, /SPIKE Assistant/);
assert.match(markup, /OpenAI \(ChatGPT models\)/);
assert.match(markup, /Allow sending this conversation/);
assert.match(markup, /Project context is not selected/);
assert.match(markup, /Available SPIKE skills \(3\)/);
assert.match(markup, /type="password"/);
assert.doesNotMatch(markup, /SECRET/);

const panelSource = readFileSync(resolve(appRoot, "src", "AssistantChatPanel.tsx"), "utf8");
assert.match(panelSource, /setAllowCloud\(false\)/, "provider changes reset cloud consent");
assert.match(panelSource, /setMessages\(\[\]\)/, "provider and consent changes clear prior conversation evidence");
assert.match(panelSource, />Clear conversation<\/button>/, "the user can clear transient conversation state");
assert.match(panelSource, /setCredential\(""\)/, "credentials are cleared from component state");
assert.match(panelSource, /cancelWorker\(operation\.current\)/, "unmount cancels the owned request");
assert.doesNotMatch(panelSource, /localStorage|sessionStorage/, "chat and credentials are not persisted by the panel");

const states = [], refs = [], effects = [], pendingSetups = [], cancellations = [];
let stateCursor = 0, refCursor = 0, effectCursor = 0, cancelReject = false;
const hookReact = {
  useEffect(effect) { const index = effectCursor++; effects[index] = effect; },
  useMemo(factory) { return factory(); },
  useRef(initial) { const index = refCursor++; if (!(index in refs)) refs[index] = { current: initial }; return refs[index]; },
  useState(initial) { const index = stateCursor++; if (!(index in states)) states[index] = typeof initial === "function" ? initial() : initial;
    return [states[index], value => { states[index] = typeof value === "function" ? value(states[index]) : value; }]; },
};
const interactivePanel = { exports: {} };
new Function("require", "module", "exports", compile("src/AssistantChatPanel.tsx", true))(name => {
  if (name === "react") return hookReact;
  if (name === "react/jsx-runtime") return nodeRequire("react/jsx-runtime");
  if (name === "./workerBridge") return {
    runLocalWorker: request => request.method === "assistant_provider_status" ? Promise.resolve({ ok: true, result: { cloud: true, credential_configured: false, credential_store_supported: true } }) : new Promise(resolve => pendingSetups.push({ request, resolve })),
    cancelLocalWorker: async id => { cancellations.push(id); if (cancelReject) throw new Error("bridge disconnected"); return true; },
  };
  if (name === "./assistantSkills") return { assistantToolCatalog: catalog, toolCapabilityStates: {} };
  if (name === "./assistantConversation") return api;
  if (name === "./AssistantChatPanel.css") return {};
  return nodeRequire(name);
}, interactivePanel, interactivePanel.exports);
const mount = () => { stateCursor = 0; refCursor = 0; effectCursor = 0; return interactivePanel.exports.default({ onClose() {}, onCommand: async () => ({}), getContext: () => ({}), getRevision: () => "r1" }); };
function find(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) { const found = find(child, predicate); if (found) return found; }
  return null;
}
const flush = async () => { await new Promise(done => setImmediate(done)); await new Promise(done => setImmediate(done)); };
let tree = mount();
const unmount = effects[2]();
effects[3]();
await flush();
tree = mount();
find(tree, node => node.type === "button" && node.props.children === "Probe models").props.onClick();
assert.equal(pendingSetups.length, 1);
const probeId = pendingSetups[0].request.id;
tree = mount();
assert.equal(find(tree, node => node.type === "select").props.disabled, true, "provider switching is disabled during model discovery");
find(tree, node => node.type === "button" && node.props["aria-label"] === "Close SPIKE Assistant").props.onClick();
unmount();
await flush();
assert.ok(cancellations.includes(probeId), "closing cancels the owned model discovery request");
const beforeLateProbe = JSON.stringify(states);
pendingSetups[0].resolve({ ok: true, result: { models: ["late-model"] } });
await flush();
assert.equal(JSON.stringify(states), beforeLateProbe, "late model discovery callbacks do not update the closed panel");
// Remote cancellation failure must still settle local UI state.
states.length = 0; refs.length = 0; effects.length = 0;
tree = mount(); const cancelUnmount = effects[2]();
find(tree, node => node.type === "select").props.onChange({ target: { value: "ollama" } });
tree = mount();
find(tree, node => node.type === "input" && node.props.placeholder === "Enter or probe a model").props.onChange({ target: { value: "fixture" } });
find(tree, node => node.type === "textarea").props.onChange({ target: { value: "Explain this feature" } });
tree = mount();
find(tree, node => node.type === "button" && node.props.children === "Send").props.onClick();
await flush(); tree = mount();
cancelReject = true;
find(tree, node => node.type === "button" && node.props.children === "Cancel").props.onClick();
await flush(); tree = mount();
assert.equal(find(tree, node => node.type === "textarea").props.disabled, false, "failed remote cancellation still releases the composer");
assert.ok(states.some(value => typeof value === "string" && value.includes("cancellation was not confirmed")), "failed cancellation is visible");
cancelUnmount(); cancelReject = false;
console.log("assistant chat tests passed");

// Model-authored extension code cannot be admitted through otherwise valid tools.
await assert.rejects(() => api.runAssistantConversation({
 provider: "ollama", model: "local", allowCloud: false, shareProjectContext: true, messages: [user],
 getContext: () => ({}), getRevision: () => "r1", review: async () => assert.fail("No review for arbitrary code"),
 runWorker: async () => turn([{id:"code-1",name:"apply",arguments:{parameters:{script:"print(1)"}}}]),
 onCommand: async () => assert.fail("No arbitrary code dispatch"),
}), /not accepted/);
