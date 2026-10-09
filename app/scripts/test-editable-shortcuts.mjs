// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const transpile = source => ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
}).outputText;
const context = await import(`data:text/javascript;base64,${Buffer.from(transpile(readFileSync(new URL("../src/shortcutContext.ts", import.meta.url), "utf8"))).toString("base64")}`);
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8").replace(/\r\n/g, "\n");
const handler = app.match(/const onKey = \(event: KeyboardEvent\) => \{([\s\S]*?)\n    \};\n    document\.addEventListener\("keydown", onKey\)/);
assert.ok(handler, "exercise the application command handler itself");
const calls = [];
const names = ["undo", "redo", "newProject", "saveProject", "openProject", "copySelection", "pasteSelection"];
const onKey = new Function("ownsKeyboardInput", ...names, "projectFileName", "projectName",
  `${transpile(`const onKey = (event: KeyboardEvent) => {${handler[1]}\n};`)}\nreturn onKey;`)(
  context.ownsKeyboardInput, ...names.map(name => () => calls.push(name)), name => name, "fixture");
const event = (key, patch = {}) => ({
  key, ctrlKey: true, metaKey: false, shiftKey: false, altKey: false, isComposing: false,
  defaultPrevented: false, target: null, preventDefault() { this.defaultPrevented = true; }, ...patch,
});

for (const target of [{ isContentEditable: true }, { closest: () => ({ tagName: "INPUT" }) }]) {
  for (const key of ["c", "v", "z", "y", "n", "s", "o"]) {
    const inputEvent = event(key, { target });
    onKey(inputEvent);
    assert.equal(inputEvent.defaultPrevented, false, `${key} remains with the focused editor`);
  }
}
assert.deepEqual(calls, [], "editing must not invoke board clipboard, undo, or project commands");
for (const patch of [{ defaultPrevented: true }, { isComposing: true }, { altKey: true }, { shiftKey: true }]) onKey(event("c", patch));
assert.deepEqual(calls, [], "handled, composed, or unrelated modified keys are ignored");
for (const [key, expected] of [["c", "copySelection"], ["v", "pasteSelection"], ["z", "undo"], ["y", "redo"], ["s", "saveProject"], ["o", "openProject"]]) {
  const workspaceEvent = event(key);
  onKey(workspaceEvent);
  assert.equal(calls.at(-1), expected);
  assert.equal(workspaceEvent.defaultPrevented, true, "workspace commands claim their browser default");
}
onKey(event("z", { shiftKey: true }));
assert.equal(calls.at(-1), "redo");
assert.equal(context.ownsKeyboardInput(null), false);
assert.equal(context.ownsKeyboardInput({ closest: () => null }), false);

const searchHandler = app.match(/const openSearch = \(event: KeyboardEvent\) => \{([\s\S]*?)\n    \};\n    window\.addEventListener\("keydown", openSearch\)/);
assert.ok(searchHandler, "exercise universal search's actual global shortcut handler");
const searchCalls = [];
const openSearch = new Function("ownsKeyboardInput", "setMenu", "setGlobalSearchOpen",
  `${transpile(`const openSearch = (event: KeyboardEvent) => {${searchHandler[1]}\n};`)}\nreturn openSearch;`)(
  context.ownsKeyboardInput, value => searchCalls.push(["menu", value]), value => searchCalls.push(["search", value]));
for (const patch of [{ target: { isContentEditable: true } }, { target: { closest: () => ({ tagName: "INPUT" }) } },
  { defaultPrevented: true }, { isComposing: true }, { altKey: true }]) {
  openSearch(event("k", patch));
}
assert.deepEqual(searchCalls, [], "search respects editor ownership, composition and handled keys");
openSearch(event("k"));
assert.deepEqual(searchCalls, [["menu", null], ["search", true]], "workspace search remains available");

const navigation = app.match(/const onNavigationKey = \(event: KeyboardEvent\) => \{([\s\S]*?)\n    \};\n    document\.addEventListener\("keydown", onNavigationKey\)/);
assert.ok(navigation);
const closed = [];
const onNavigationKey = new Function("ownsKeyboardInput", "shortcutsOpen", "setShortcutsOpen",
  `${transpile(`const onNavigationKey = (event: KeyboardEvent) => {${navigation[1]}\n};`)}\nreturn onNavigationKey;`)(
  context.ownsKeyboardInput, true, value => closed.push(value));
onNavigationKey(event("Escape", { ctrlKey: false, target: { isContentEditable: true } }));
assert.deepEqual(closed, [false], "Escape retains the shortcut dialog's dismissal even from its editor");
console.log("editable and workspace shortcut assertions passed");
