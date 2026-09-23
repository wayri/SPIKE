// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(new URL("../src/designStackup.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source.replace(/^import .*$/m, ""), { compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 } }).outputText;
const { applyStackupToDesignIr } = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);
const design = { contract: "spike/design-ir/v2", materials: [{ id: "m1", name: "old", extensions: {} }], layers: [
  { id: "l1", name: "F.Cu", material_id: "m1", thickness_mm: .035, z_mm: 0, extensions: { "spike.v1.stackup": { thickness: .035 } } },
  { id: "l2", name: "Core", material_id: "m2", thickness_mm: 1.5, z_mm: .035, extensions: {} },
], vendor_extensions: { "spike.v1": { stackup: [{ name: "F.Cu", thickness: .035 }], keep: true } }, metadata: { keep: true } };
const updated = applyStackupToDesignIr(design, [{ name: "F.Cu", type: "copper", thickness: .07, material: "Copper" }, { name: "Core", type: "dielectric", thickness: 1.2, material: "FR-4", epsilonR: 4.2, lossTangent: .018, color: "FR4 natural" }]);
assert.equal(design.layers[0].thickness_mm, .035, "input must stay immutable");
assert.equal(updated.layers[0].thickness_mm, .07);
assert.equal(updated.layers[1].z_mm, .07);
assert.equal(updated.vendor_extensions["spike.v1"].stackup[0].thickness, .07);
assert.equal(updated.vendor_extensions["spike.v1"].stackup[1].color, "FR4 natural");
assert.equal(updated.metadata["spike.v1.stackup"][1].relative_permittivity, 4.2);
assert.equal(updated.materials[0].extensions["spike.v1"].thickness_mm, .07);
assert.equal(updated.materials.find(item => item.id === "m2").relative_permittivity, 4.2);
assert.equal(updated.layers[1].material_id, "m2");
assert.equal(updated.vendor_extensions["spike.v1"].keep, true);
console.log("Authoritative DesignIR stackup synchronization checks passed");
