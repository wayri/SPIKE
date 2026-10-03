// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";

const require = createRequire(import.meta.url);
const cache = new Map();
export function loadTableModule(name, react) {
  if (!react && cache.has(name)) return cache.get(name);
  const file = name === "spreadsheetGrid" ? `${name}.ts` : `${name}.tsx`;
  const compiled = ts.transpileModule(readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  const module = { exports: {} };
  new Function("require", "module", "exports", compiled)(dependency => {
    if (dependency.endsWith(".css")) return {};
    if (dependency === "react" && react) return react;
    if (dependency.startsWith("./")) return loadTableModule(dependency.slice(2), react);
    return require(dependency);
  }, module, module.exports);
  if (!react) cache.set(name, module.exports);
  return module.exports;
}
export default function loadDataTable() { return loadTableModule("DataTable").default; }
