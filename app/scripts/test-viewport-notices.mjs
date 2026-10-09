// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
const code = ts.transpileModule(readFileSync(new URL("../src/ViewportNotifications.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
}).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", code)(name => {
  if (name === "./icons") return new Proxy({}, { get: () => () => null });
  return name.endsWith(".css") ? {} : require(name);
}, module, module.exports);
const { default: Notifications, ViewportNoticeCorner } = module.exports;
const notice = { level: "error", title: "A very long model scene warning ".repeat(12), detail: "Detailed diagnostic stays outside the canvas" };
let details = 0, dismissed = 0, retried = 0;
const chip = ViewportNoticeCorner({ notice, boardSummary: "2/2 board layouts loaded", onDetails: () => details++, onDismiss: () => dismissed++ });
const markup = renderToStaticMarkup(chip);
assert.equal((markup.match(/viewport-notice-chip/g) ?? []).length, 2, "at most two compact corner messages");
assert.ok(!markup.includes(notice.detail), "long diagnostics cannot expand into the canvas");
chip.props.children[0].props.children[0].props.onClick();
chip.props.children[0].props.children[1].props.onClick();
assert.equal(details, 1); assert.equal(dismissed, 1);
assert.equal(ViewportNoticeCorner({ notice: null, onDetails() {}, onDismiss() {} }), null);
const actions = [];
const props = { notice, boards: [{ name: "Shield", designId: "design-shield", detail: "Unresolved source model" }], harnessDiagnostics: ["Missing connector endpoint"], importReview: { label: "Import needs attention", issueCount: 2 }, metrics: "Load statistics", open: false, onToggle() {}, onClose: () => actions.push("close"), onRetry: () => retried++, onResolveModels: id => actions.push(id ?? "models"), onReviewImport: () => actions.push("import"), onReviewLinks: () => actions.push("links"), onReviewIssues: () => actions.push("issues") };
assert.ok(!renderToStaticMarkup(React.createElement(Notifications, props)).includes(notice.detail), "full details are shown only on request");
const triggerOnly = Notifications({ ...props, open: true, mode: "button" });
assert.ok(!renderToStaticMarkup(triggerOnly).includes(notice.detail), "the header trigger opens the reserved dock rather than an overlapping popover");
const docked = Notifications({ ...props, open: true, mode: "dock" });
assert.ok(renderToStaticMarkup(docked).includes(notice.detail), "docked notices retain the complete diagnostic");
assert.equal(elements(docked).filter(node => node.type === "button" && node.props["aria-label"] === "Notifications").length, 0, "the dock uses its existing tab for collapse, without a duplicate trigger");
const panel = Notifications({ ...props, open: true });
const panelMarkup = renderToStaticMarkup(panel);
for (const value of [notice.detail, "Shield", "Unresolved source model", "Missing connector endpoint", "Retry 3D models"]) assert.ok(panelMarkup.includes(value));
function elements(node) {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!React.isValidElement(node)) return [];
  return [node, ...elements(node.props.children)];
}
const button = (tree, label) => elements(tree).find(node => node.type === "button" && renderToStaticMarkup(node).includes(label));
actions.length = 0;
button(docked, "Resolve this board&#x27;s models").props.onClick();
assert.deepEqual(actions, ["close", "design-shield"], "board repair from the dock retains occurrence-specific routing");
button(panel, "Retry 3D models").props.onClick(); assert.equal(retried, 1, "error recovery remains available");
for (const [label, destination] of [["Resolve models", "models"], ["Resolve this board&#x27;s models", "design-shield"], ["Review import", "import"], ["Review connector links", "links"], ["Review all issues", "issues"]]) {
  actions.length = 0;
  button(panel, label).props.onClick();
  assert.deepEqual(actions, ["close", destination], `${label} closes the popover and opens the correct repair workflow`);
}
actions.length = 0;
button(panel, notice.title).props.onClick();
assert.deepEqual(actions, ["close", "models"], "the notification heading itself opens the resolver");
const unavailable = Notifications({ ...props, open: true, canResolveModels: false });
assert.equal(button(unavailable, "Resolve models").props.disabled, true, "model actions stay unavailable until board geometry is ready");
const warning = Notifications({ ...props, notice: { ...notice, level: "warning" }, open: true });
assert.ok(button(warning, "Resolve models"), "unresolved-model warnings offer repair, not only failed scenes");
assert.ok(!button(warning, "Retry 3D models"), "warnings are not presented as conversion failures");
const css = readFileSync(new URL("../src/viewportNotifications.css", import.meta.url), "utf8");
assert.match(css, /width: min\(280px, calc\(100% - 16px\)\)/);
assert.match(css, /height: 28px/);
assert.match(css, /text-overflow: ellipsis/);
console.log("Bounded viewport notices, actionable warning headings, scoped repair destinations and error recovery passed");
