// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
const require = createRequire(import.meta.url);
export default function loadSolverSetupSteps(react = require("react")) {
  const module = { exports: {} };
  const code = ts.transpileModule(readFileSync(new URL("../src/SolverSetupSteps.tsx", import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  new Function("require", "module", "exports", code)(name => name === "react" ? react : name.endsWith(".css") ? {} : require(name), module, module.exports);
  return module.exports;
}
