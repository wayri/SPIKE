// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";

const root = resolve(import.meta.dirname, "..");
const source = readFileSync(resolve(root, "src", "thermalEnvironments.ts"), "utf8");
const module = { exports: {} };
new Function("module", "exports", ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText)(module, module.exports);
const { screenThermalEnvironment, thermalEnvironmentProfiles } = module.exports;
assert.deepEqual(thermalEnvironmentProfiles.map(profile => profile.id), ["open_air", "closed_box", "forced_air"]);
const input = { boardWidthMm: 100, boardHeightMm: 80, ambientC: 25, powerW: 8 };
const open = screenThermalEnvironment("open_air", input);
const closed = screenThermalEnvironment("closed_box", input);
const forced = screenThermalEnvironment("forced_air", input);
assert.equal(open.modelStatus, "approximate");
assert.ok(closed.estimatedBoardTemperatureC > open.estimatedBoardTemperatureC);
assert.ok(open.estimatedBoardTemperatureC > forced.estimatedBoardTemperatureC);
assert.ok(Math.abs(forced.idealBulkAirRiseC - 8 / (1.204 * 1005 * 0.012)) < 1e-12);
assert.equal(screenThermalEnvironment("open_air", { ...input, powerW: 0 }).estimatedBoardTemperatureC, 25);
assert.throws(() => screenThermalEnvironment("open_air", { ...input, boardWidthMm: 0 }), /Board width/);
assert.throws(() => screenThermalEnvironment("forced_air", { ...input, airflowM3s: -1 }), /Airflow/);
console.log("thermal environment profiles and numerical screens passed");
