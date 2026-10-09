// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const read = path => readFileSync(new URL(path, import.meta.url), "utf8");
const compiled = ts.transpileModule(read("../src/desktopClose.ts"), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const policy = { exports: {} };
new Function("module", "exports", compiled)(policy, policy.exports);
let dirty = false, draft = null, closing = false;
const calls = [];
const close = policy.exports.createDesktopCloseHandler({
  isClosing: () => closing, draftOwner: () => draft, isDirty: () => dirty,
  showDraft: owner => calls.push(["draft", owner]), showUnsaved: () => calls.push(["unsaved"]),
  close: () => { closing = true; calls.push(["close"]); },
});
const request = () => close(() => calls.push(["prevent"]));
request(); request();
assert.deepEqual(calls, [["prevent"], ["close"], ["prevent"]], "clean close commits whole-app shutdown once, and repeated requests cannot destroy only the main window");
closing = false; dirty = true; calls.length = 0; request();
assert.deepEqual(calls, [["prevent"], ["unsaved"]], "dirty close waits for a save/discard decision");
draft = "workspace"; calls.length = 0; request();
assert.deepEqual(calls, [["prevent"], ["draft", "workspace"]], "a detached draft takes precedence and remains protected");
draft = null; dirty = false; calls.length = 0; request();
assert.deepEqual(calls, [["prevent"], ["close"]], "a subsequent clean request can close after draft resolution");

const app = read("../src/App.tsx").replaceAll("\r\n", "\n");
const resolveSource = app.slice(app.indexOf('  const resolveUnsavedPrompt ='), app.indexOf('  useEffect(() => {\n    const onBeforeUnload', app.indexOf('  const resolveUnsavedPrompt =')));
assert.ok(resolveSource.includes('await finishDesktopClose()'));
async function resolveChoice(choice, saveWorks = true) {
  const events = [], pending = { actionLabel: "close SPIKE", closeWindow: true, onCancel: () => events.push("cancel") };
  const code = ts.transpileModule(`${resolveSource}\nreturn resolveUnsavedPrompt;`, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
  const resolve = new Function("unsavedPrompt", "saveProject", "setProjectClean", "setUnsavedPrompt", "setStatus", "finishDesktopClose", code)(
    pending, async () => { events.push("save"); return saveWorks; }, () => events.push("clean"), value => events.push(value === null ? "dismiss" : "prompt"), () => {}, async () => events.push("close"));
  await resolve(choice); return events;
}
assert.deepEqual(await resolveChoice("save", false), ["save"], "failed or canceled save keeps SPIKE and its prompt open");
assert.deepEqual(await resolveChoice("save"), ["save", "dismiss", "close"], "save finishes before close admission");
assert.deepEqual(await resolveChoice("discard"), ["clean", "dismiss", "close"]);
assert.deepEqual(await resolveChoice("cancel"), ["cancel", "dismiss"], "cancel never reaches native shutdown");

const bridge = read("../src/workerBridge.ts");
const bridgeClose = bridge.slice(bridge.indexOf("export async function closeDesktopWindow"), bridge.indexOf("export async function runLocalWorker"));
assert.ok(bridgeClose.includes('invoke<void>("close_desktop_app")'));
assert.ok(!bridgeClose.includes(".destroy()"), "main close must not destroy only one window");
assert.ok(app.includes('if (!desktopShell) window.addEventListener("beforeunload"'), "native close has one save/discard guard instead of a second hidden browser prompt");
assert.ok(app.includes("<DesktopCloseDraftDialog"), "draft-blocked close must have a visible recovery dialog");
console.log("Desktop close: clean, repeated, dirty, draft, save failure, save/discard/cancel and native dispatch checks passed.");
