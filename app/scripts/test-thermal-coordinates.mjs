import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../src/thermalCoordinates.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const module = { exports: {} };
vm.runInNewContext(compiled, { module, exports: module.exports });
const { thermalScenePointMm } = module.exports;
const board = { width: 46, height: 31, bounds: { minX: 119.5, maxX: 165.5, minY: 66, maxY: 97 } };
const volume = { x: 160, y: 100, z: 60 };

assert.deepEqual(Array.from(thermalScenePointMm([23, 15.5, 0], "board_local", volume, board)), [0, 0, 0]);
assert.deepEqual(Array.from(thermalScenePointMm([142.5, 81.5, 1], "board_absolute", volume, board)), [0, 0, 1]);
assert.deepEqual(Array.from(thermalScenePointMm([80, 50, 30], "domain_local", volume, board)), [0, 0, 30]);
assert.deepEqual(Array.from(thermalScenePointMm([0, 0, 0], "board_local", volume, board)), [-23, 15.5, 0]);
console.log("thermal coordinate frame contract passed");
