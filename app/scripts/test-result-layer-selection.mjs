import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/resultLayerSelection.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
}).outputText;
const module = await import(`data:text/javascript;base64,${Buffer.from(js).toString("base64")}`);

const boardLayers = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"];
assert.deepEqual(module.resultDatumLayers("F.Cu->B.Cu", boardLayers), boardLayers);
assert.deepEqual(module.selectedDatumLayers("F.Cu->B.Cu", ["In2.Cu"], boardLayers), ["In2.Cu"]);
assert.equal(module.resultLayerMatchesSelection("F.Cu", ["B.Cu"], boardLayers), false);
assert.equal(module.resultLayerMatchesSelection("F.Cu->B.Cu", ["B.Cu"], boardLayers), true);
assert.equal(module.resultLayerIsVisible("F.Cu->B.Cu", ["B.Cu"], boardLayers, { "B.Cu": true }), true);
assert.equal(module.resultLayerIsVisible("F.Cu->B.Cu", ["B.Cu"], boardLayers, { "B.Cu": false }), false);
assert.equal(module.resultLayerIsVisible("F.Cu", ["B.Cu"], boardLayers, { "F.Cu": true, "B.Cu": true }), false);
assert.equal(module.resultLayerWithVisibleData(
  [{ layer: "In2.Cu" }], "F.Cu", boardLayers, [], { "F.Cu": true, "In2.Cu": true },
), "All", "an inner-layer-only result must not remain hidden behind the default F.Cu selection");
assert.equal(module.resultLayerWithVisibleData(
  [{ layer: "F.Cu->B.Cu" }], "F.Cu", boardLayers, [], { "F.Cu": true },
), "F.Cu", "a spanning result must preserve a compatible explicit layer selection");
assert.equal(module.resultLayerWithVisibleData(
  [{ layer: "In2.Cu" }], "F.Cu", boardLayers, ["B.Cu"], { "B.Cu": true },
), "F.Cu", "a result-layer filter with no admitted samples must not mutate the board layer");
console.log("Result layer selection contract passed.");
