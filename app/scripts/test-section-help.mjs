// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import React from "react";
const require = createRequire(import.meta.url);
const source = name => readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
function load(code, mocks = {}) {
  const compiled = ts.transpileModule(code, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  const module = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => name in mocks ? mocks[name] : require(name), module, module.exports);
  return module.exports;
}
const main = new EventTarget();
globalThis.window = main;
const createDocument = () => ({ defaultView: { document: { createEvent: () => {
  const event = new Event("spike-open-help-section");
  event.initCustomEvent = (_name, _bubbles, _cancelable, detail) => { event.detail = detail; };
  return event;
} } } });
let presentation = {};
const api = load(source("SectionHelpButton.tsx"), { "./panelPresentation": { usePanelPresentation: () => presentation } });
const { default: Button, admitHelpSectionLocation: admit, OPEN_HELP_SECTION_EVENT } = api;
for (const invalid of [null, [], {}, { topic: "" }, { topic: 3 }, { topic: "a", anchor: {} }, { topic: "a\n" }, { topic: "a", anchor: "a".repeat(241) }]) assert.equal(admit(invalid), null);
const topic = "doc:docs/EMERGE_GERBER.md", anchor = "explicit-port-planes";
assert.deepEqual(admit({ topic, anchor, ignored: true }), { topic, anchor });
const app = source("App.tsx");
const listener = app.match(/  useEffect\(\(\) => \{\n    const open = \(event: Event\) => \{\n      const location = admitHelpSectionLocation[\s\S]+?\n  \}, \[setHelpOpen\]\);/);
assert.ok(listener, "App mounts and cleans up the validated help listener");
let location = null, diagnostic = "old diagnostic", opened = 0, cleanup;
const listenerJs = ts.transpileModule(listener[0], { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
new Function("useEffect", "admitHelpSectionLocation", "setHelpLocation", "setHelpDiagnosticCode", "setHelpOpen", "OPEN_HELP_SECTION_EVENT", listenerJs)(effect => { cleanup = effect(); }, admit, update => { location = update(location); }, value => { diagnostic = value; }, value => { if (value) opened++; }, OPEN_HELP_SECTION_EVENT);
for (const detached of [false, true]) {
  const doc = createDocument(); presentation = { ownerDocument: doc, ownerWindow: doc.defaultView, detached };
  const button = Button({ topic, anchor, label: "Port planes" });
  assert.equal(button.props.type, "button"); assert.equal(button.props["aria-label"], "Help: Port planes");
  button.props.onClick({ currentTarget: { ownerDocument: doc } });
}
assert.deepEqual(location, { topic, anchor, request: 2 }); assert.equal(opened, 2); assert.equal(diagnostic, undefined);
const malformed = new Event(OPEN_HELP_SECTION_EVENT); malformed.detail = { topic, anchor: 12 }; main.dispatchEvent(malformed); assert.equal(opened, 2);
cleanup(); const closed = new Event(OPEN_HELP_SECTION_EVENT); closed.detail = { topic, anchor }; main.dispatchEvent(closed); assert.equal(opened, 2);

// Run HelpCenter with persistent hooks, rendering the same component instance across requests.
const states = [], refs = [], memo = [], effects = []; let si = 0, ri = 0, mi = 0, ei = 0, queued = [], changed = false;
const same = (a, b) => a && b && a.length === b.length && a.every((x, i) => Object.is(x, b[i]));
const headings = [{ id: anchor, textContent: "Port planes", closest() { return null; }, scrollIntoView() { scrolls++; } }]; let scrolls = 0;
const article = { querySelectorAll: () => headings, scrollTo() {}, focus() {} };
const hooks = { ...React,
 useState(initial) { const id = si++; if (!(id in states)) states[id] = typeof initial === "function" ? initial() : initial; return [states[id], next => { const value = typeof next === "function" ? next(states[id]) : next; if (!Object.is(value, states[id])) changed = true; states[id] = value; }]; },
 useRef(initial) { const id = ri++; return refs[id] ??= { current: id === 1 ? article : initial }; },
 useMemo(fn, deps) { const id = mi++; if (!same(memo[id]?.deps, deps)) memo[id] = { deps, value: fn() }; return memo[id].value; },
 useEffect(fn, deps) { const id = ei++; if (!same(effects[id], deps)) { effects[id] = deps; queued.push(fn); } },
};
let helpCode = source("HelpCenter.tsx").replace(/import\.meta\.glob\([\s\S]*? as Record<string, string>;/g, "({});");
helpCode = helpCode.replace(/function makeTopics\(\): HelpTopic\[\] \{[\s\S]*?\nexport default/, `function makeTopics() { return [{ id: "home", title: "Home", category: "Start here", keywords: "", body: null }, { id: "${topic}", title: "Gerber", category: "Reference library", keywords: "", body: null }]; }\nexport default`);
const Help = load(helpCode, { react: hooks, "./icons": Object.fromEntries(["ArrowLeft", "ArrowRight", "BookOpen", "Bookmark", "Copy", "Search", "X"].map(name => [name, "span"])), "./appVersion": { APP_VERSION: "test" }, "./HelpTopics": {}, "./HelpMarkdown": { default: "div", CopyCode: "pre", __esModule: true }, "./helpModel": { helpSlug: x => x, searchHelp: items => items }, "./panelPresentation": { usePanelPresentation: () => ({}) }, "./helpReference.generated.json": { commands: [], errors: [] }, "./helpControls.generated.json": [], "./helpCenter.css": {} }).default;
const props = { onClose() {}, initialTopic: topic, initialAnchor: anchor, navigationRequest: 1 };
function render() { let count = 0; do { assert.ok(count++ < 10); changed = false; si = ri = mi = ei = 0; Help(props); const pending = queued; queued = []; pending.forEach(fn => fn()); } while (changed); }
render(); assert.equal(states[0].at(-1), topic); assert.equal(scrolls, 1, "initial topic change retains its pending anchor until the destination renders");
props.navigationRequest++; render(); assert.equal(scrolls, 2, "repeated section requests scroll again without remounting");
props.initialTopic = "missing"; props.navigationRequest++; render(); assert.ok(states.some(value => typeof value === "string" && /not included/.test(value)), "unknown topics produce recoverable help notice");
assert.match(source("HelpCenter.tsx"), /\.\.\/\.\.\/docs\/EMERGE_GERBER\.md/);
console.log("Section help passed: admission, main/detached event routing, repeated requests, cleanup, first-open anchors and missing-topic recovery.");
