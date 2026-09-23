// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(new URL("../src/stackupVisual.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source.replace(/^import type .*$/m, ""), { compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 } }).outputText;
const { stackupColor, stackupBandHeight } = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);
assert.equal(stackupColor({ name: "core", type: "dielectric", material: "FR4", color: "green" }), "#75552c", "substrate color stays brown");
assert.equal(stackupColor({ name: "F.Mask", type: "soldermask", color: "blue" }), "#315cb2", "mask inherits source color");
assert.equal(stackupColor({ name: "F.SilkS", type: "silkscreen", color: "#ececec" }), "#ececec", "silkscreen inherits source color");
assert.equal(stackupColor({ name: "F.Cu", type: "copper" }), "#eab559");
assert.ok(stackupBandHeight({ thickness: 1.2 }) > stackupBandHeight({ thickness: .035 }));
console.log("Stackup contrast and imported finish colors passed");
