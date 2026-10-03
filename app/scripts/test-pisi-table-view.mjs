// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTableModule } from "./load-data-table.mjs";
const require = createRequire(import.meta.url);
let slots = [], slot = 0;
const hooks = { ...React, useId: () => "fixture", useState: initial => {
  const index = slot++;
  if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
  return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
} };
const mod = { exports: {} };
const compiled = ts.transpileModule(readFileSync(new URL("../src/PiSiTerminalEditor.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;
new Function("require", "module", "exports", compiled)(name => name === "react" ? hooks : name.endsWith(".css") ? {} : name === "./TerminalTable" ? loadTableModule("TerminalTable") : require(name), mod, mod.exports);
const Editor = mod.exports.default;
const visit = n => !n || typeof n !== "object" ? [] : Array.isArray(n) ? n.flatMap(visit) : [n, ...visit(n.props?.children)];
const calls = [];
const rows = [{ id: "source", name: "VCC", x: "1", y: "2", layer: "auto", value: "3.3", contactResistance: "0", packageResistance: "0" }];
const props = { rows, label: "PI sources", layers: ["F.Cu"], valueLabel: "Voltage (V)", onChange() {}, onRemove() {}, renderDetails() {}, addLabel: "Add source", onAdd: () => calls.push("add"), onTogglePick: () => calls.push("pick"), onUseSelection: () => calls.push("selection"), selectionAvailable: true };
const render = props => { slot = 0; return Editor(props); };
let tree = render(props);
assert.match(renderToStaticMarkup(tree), /pisi-terminal-editor__card/);
visit(tree).find(n => n.type === "button" && n.props.children === "Table").props.onClick();
tree = render(props);
const html = renderToStaticMarkup(tree);
assert.match(html, /<table/);
assert.match(html, /Find in PI sources/);
const table = visit(tree).find(n => n.type === loadTableModule("TerminalTable").default);
assert.equal(table.props.rows, rows);
assert.equal(table.props.onChange, props.onChange);
assert.equal(table.props.onRemove, props.onRemove);
const footer = visit(tree).find(n => n.type === "footer");
visit(footer).filter(n => n.type === "button").forEach(n => n.props.onClick());
assert.deepEqual(calls, ["add", "pick", "selection"], "placement actions remain wired in table mode");
slots = [];
assert.match(renderToStaticMarkup(render({ ...props, rows: Array.from({length:7},(_,i)=>({...rows[0],id:String(i)})) })), /<table/, "larger initial terminal sets start in table view");
console.log("PI terminal table/card switching shares records, callbacks, and placement actions.");
