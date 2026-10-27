// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
const require = createRequire(import.meta.url);
const componentSource = readFileSync(new URL("../src/ThermalWorkspaceInspector.tsx", import.meta.url), "utf8");
const module = { exports: {} };
new Function("require", "module", "exports", ts.transpileModule(componentSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText)(require, module, module.exports);
const Inspector = module.exports.default;
const source = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const start = source.indexOf('{rightOpen && !workspaceExtensionRoute && (tab === "EM"');
const end = source.indexOf("</aside>", start);
assert.ok(start > 0 && end > start);
const expression = source.slice(start + 1, end).trim().replace(/\}$/, "");
const code = ts.transpileModule(`return (${expression});`, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2022 } }).outputText;
const render = new Function("React", "rightOpen", "workspaceExtensionRoute", "tab", "ThermalWorkspaceInspector", "savedThermalInventory", "setThermalOpen", "setSavedThermalView", code);
for (const hasResult of [false, true]) {
  const calls = [];
  const element = render(React, true, null, "Thermal", Inspector, hasResult ? [{ id: "saved-thermal" }] : [],
    value => calls.push(["thermal-setup", value]), value => calls.push(["thermal-results", value]));
  assert.equal(element.type, Inspector, "the actual App thermal branch must not fall through to PI setup");
  const html = renderToStaticMarkup(element);
  assert.match(html, /Thermal study controls/);
  assert.doesNotMatch(html, /DC IR Drop|Managed nets|Max voltage drop/i);
  assert.equal(html.includes("Retained thermal results"), hasResult);
  const controls = Inspector(element.props).props.children.props.children.filter(React.isValidElement).filter(child => child.type === "button");
  controls[0].props.onClick();
  assert.deepEqual(calls.shift(), ["thermal-setup", true]);
  assert.equal(controls[1].props.disabled, !hasResult);
  if (hasResult) { controls[1].props.onClick(); assert.deepEqual(calls.shift(), ["thermal-results", {}]); }
}
console.log("Actual App thermal inspector routing, setup/results actions and empty-result state passed.");
