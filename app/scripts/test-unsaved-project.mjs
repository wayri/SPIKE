import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const mainWindowCapability = JSON.parse(readFileSync(new URL("../src-tauri/capabilities/main-window.json", import.meta.url), "utf8"));

for (const marker of [
  "projectDirtyRef", "markProjectDirty", "setProjectClean", "requestUnsavedAction",
  "subscribeDesktopCloseRequested", "preventDefault()", 'window.addEventListener("beforeunload"',
  "resolveUnsavedPrompt", "Save changes before you", 'resolveUnsavedPrompt("save")',
  'resolveUnsavedPrompt("discard")', 'resolveUnsavedPrompt("cancel")',
]) assert.ok(source.includes(marker), `Unsaved-project close handling is missing ${marker}`);

assert.ok(styles.includes(".unsaved-project-dialog"), "Unsaved-project dialog styles are missing");
assert.deepEqual(mainWindowCapability.windows, ["main"]);
assert.ok(mainWindowCapability.permissions.includes("core:window:allow-destroy"),
  "Tauri onCloseRequested destroys a permitted close; without this permission the window remains open");
assert.ok(source.includes('setSetup={next => { markProjectDirty(); setPiSetup(next); }}'), 'PI terminal edits must participate in unsaved-project protection');
assert.ok(source.includes('setWorkspace={next => { markProjectDirty(); setSpiceWorkspace(next); }}'), 'SPICE workspace edits must participate in unsaved-project protection');
console.log("SPIKE unsaved-project close, save, discard, and cancel assertions passed");
