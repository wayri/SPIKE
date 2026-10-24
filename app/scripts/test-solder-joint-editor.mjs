// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import ts from "typescript";

const require = createRequire(import.meta.url);
function compile(path, jsx = false) {
  return ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: jsx ? ts.JsxEmit.ReactJSX : undefined } }).outputText;
}
function execute(source, resolve) {
  const module = { exports: {} };
  new Function("require", "module", "exports", source)(resolve, module, module.exports);
  return module.exports;
}
const model = execute(compile("../src/solderJointModel.ts"), specifier => specifier.startsWith("./") ? {} : require(specifier));
const Editor = execute(compile("../src/SolderJointEditor.tsx", true), specifier => {
  if (specifier === "./solderJointModel") return model;
  if (specifier === "./SectionHelpButton") return { default: () => React.createElement("button", null, "Help") };
  if (specifier.endsWith(".css")) return {};
  return require(specifier);
}).default;

function descendants(node) {
  if (Array.isArray(node)) return node.flatMap(descendants);
  if (!React.isValidElement(node)) return [];
  if (typeof node.type === "function") return descendants(node.type(node.props));
  return [node, ...descendants(node.props.children)];
}
const bond = { id: "bond-1", reference: "U1", pad: "3", boardInstanceId: "main-board", solderVisual: undefined };
const changes = [];
let nodes = descendants(Editor({ bond, onChange: value => changes.push(value) }));
const enable = nodes.find(node => node.type === "button" && node.props.children === "Enable solder visual");
assert.ok(enable, "missing visuals have an explicit enable action");
enable.props.onClick();
assert.deepEqual(changes.pop(), model.DEFAULT_SOLDER_JOINT_VISUAL, "enable action applies the shared visual default");
assert.ok(nodes.some(node => node.type === "output" && node.props.children.join("").includes("main-board")), "assigned board occurrence is visible read-only");

bond.solderVisual = model.DEFAULT_SOLDER_JOINT_VISUAL;
nodes = descendants(Editor({ bond, onChange: value => changes.push(value) }));
nodes.find(node => node.props?.["aria-label"] === "Solder joint height in millimeters").props.onChange({ target: { value: "200" } });
assert.equal(changes.pop().heightMm, 20, "height input clamps to the model maximum");
nodes.find(node => node.props?.["aria-label"] === "Solder joint opacity").props.onChange({ target: { value: "0" } });
assert.equal(changes.pop().opacity, 0.05, "opacity input clamps to the model minimum");
nodes.find(node => node.type === "button" && node.props.children === "Remove visual").props.onClick();
assert.equal(changes.pop(), undefined, "remove action deletes only presentation geometry");

console.log("Solder joint editor enable, occurrence, bounds, and removal controls passed");
