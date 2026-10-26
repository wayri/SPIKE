// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import loadSolverSetupSteps from "./load-solver-setup-steps.mjs";
const { default: Steps, SolverSetupPanel: Panel } = loadSolverSetupSteps({ ...React, useId: () => "step-description" });
const steps = [
  { id: "domain", label: "Geometry and a realistic very long board occurrence domain name", description: "Import geometry first." },
  { id: "loads", label: "Sources and loads", description: "Assign explicit terminals." },
  { id: "review", label: "Review and run", description: "Existing validation is required." },
];
let current = "domain";
const render = (items = steps) => Steps({ label: "PI setup steps", steps: items, current, onChange: id => { current = id; } });
const nodes = tree => !tree || typeof tree !== "object" ? [] : [tree, ...[tree.props?.children].flat(Infinity).flatMap(nodes)];
const button = (tree, text) => nodes(tree).find(node => node.type === "button" && node.props.children === text);
const stepButton = (tree, id) => nodes(tree).find(node => node.type === "button" && node.props.title === steps.find(step => step.id === id)?.description);
let tree = render();
assert.equal(button(tree, "Back").props.disabled, true);
assert.equal(stepButton(tree, "domain").props["aria-current"], "step");
button(tree, "Next").props.onClick(); assert.equal(current, "loads");
tree = render(); assert.equal(button(tree, "Back").props.disabled, false);
button(tree, "Back").props.onClick(); assert.equal(current, "domain");
stepButton(render(), "review").props.onClick(); assert.equal(current, "review", "direct numbered access uses the existing controlled state");
assert.equal(button(render(), "Next").props.disabled, true);
stepButton(render(), "loads").props.onClick(); assert.equal(current, "loads");
const blocked = steps.map(step => ({ ...step, disabled: step.id === "review" }));
tree = render(blocked); assert.equal(button(tree, "Next").props.disabled, true);
button(tree, "Next").props.onClick(); assert.equal(current, "loads", "disabled destination is guarded in handlers too");
stepButton(tree, "review").props.onClick(); assert.equal(current, "loads");
const field = React.createElement("input", { defaultValue: "retained draft 1e-", "aria-label": "Draft value" });
const visible = Panel({ active: true, label: "Sources", children: field });
const hidden = Panel({ active: false, label: "Sources", children: field });
assert.equal(hidden.props.children, visible.props.children, "navigation keeps the original editor subtree mounted");
assert.equal(hidden.props.hidden, true);
const alert = React.createElement("div", { role: "alert" }, "Correct the source voltage");
const markup = renderToStaticMarkup(React.createElement(React.Fragment, null, render(), hidden, alert));
assert.match(markup, /aria-label="PI setup steps"/); assert.match(markup, /retained draft 1e-/); assert.match(markup, /role="alert"/);
const css = readFileSync(new URL("../src/SolverSetupSteps.css", import.meta.url), "utf8");
assert.match(css, /minmax\(min\(100%, 140px\), 1fr\)/, "navigation collapses to one column in narrow panels");
assert.match(css, /white-space: normal/); assert.match(css, /overflow-wrap: anywhere/);
assert.match(css, /\[hidden\].*display: none !important/, "hidden panels cannot be exposed by legacy layout CSS");
for (const file of ["App.tsx", "BoardThermalPanel.tsx", "EmiWorkbench.tsx", "SParameterWorkbench.tsx", "SiWorkflowWorkbench.tsx"]) {
 const source = readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
 assert.match(source, /<SolverSetupSteps /, `${file} exposes working shared navigation`);
 assert.match(source, /<SolverSetupPanel |className="solver-setup-panel"/, `${file} retains editor subtrees`);
}
console.log("Solver setup steps: controlled Back/Next/direct access, boundaries, disabled guards, mounted drafts, alerts and narrow/long-label CSS passed.");
