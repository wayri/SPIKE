// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync, unlinkSync, writeFileSync } from "node:fs";
import ts from "typescript";
const source = readFileSync(new URL("../src/emergeRuntimePresentation.ts", import.meta.url), "utf8"), target = new URL(".test-emergeRuntimePresentation.mjs", import.meta.url);
writeFileSync(target, ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText);
let present; try { ({ emergeRuntimePresentation: present } = await import(target.href + `?${Date.now()}`)); } finally { try { unlinkSync(target); } catch {} }
const exercised = present({ available: true, version: "3.2.1", adapter_evidence: "executed_fixture", capabilities: ["si_s_parameters"], api_checks: { mesh_generation: true, mesh_export: false } });
assert.match(exercised.message, /execution evidence/); assert.equal(exercised.checks[0].label, "Engine mesh generation"); assert.equal(exercised.checks[1].present, false);
assert.match(present({ available: true, version: "4.0.0", capabilities: [] }).message, /qualification is pending/);
assert.equal(present({ available: false, reason: "EMerge 2.x is unsupported." }).message, "EMerge 2.x is unsupported.");
assert.deepEqual(present({ available: true, api_checks: [], capabilities: ["mesh", 3] }).capabilities, ["mesh"]);
console.log("EMerge runtime evidence presentation passed.");
