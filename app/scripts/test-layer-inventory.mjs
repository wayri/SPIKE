import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/layerInventory.ts", import.meta.url), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const inventoryModule = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);

const copperLayerSelectionSource = readFileSync(new URL("../src/copperLayerSelection.ts", import.meta.url), "utf8");
const copperLayerSelectionModule = await import(`data:text/javascript;base64,${Buffer.from(ts.transpileModule(copperLayerSelectionSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText).toString("base64")}`);

for (const count of [2, 10, 32]) {
  const boardLayers = ["F.Cu", ...Array.from({ length: count - 2 }, (_, index) => `In${index + 1}.Cu`), "B.Cu"];
  assert.deepEqual(
    copperLayerSelectionModule.resolveBoardCopperLayers(boardLayers, ["*.Cu"]),
    boardLayers,
    `*.Cu must expand to exactly the ${count}-layer physical copper stack`,
  );
  assert.deepEqual(
    copperLayerSelectionModule.resolveBoardCopperLayers(boardLayers, ["F&B.Cu"]),
    ["F.Cu", "B.Cu"],
    `F&B.Cu must resolve to only the outer copper layers on a ${count}-layer stack`,
  );
}

const compilerOptions = { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 };
const layerVisibility = { 'F.Cu': false, 'In1.Cu': false, 'In2.Cu': true, 'B.Cu': false };
const stack = Object.keys(layerVisibility);
assert.equal(copperLayerSelectionModule.visibleLayoutCopperLayer('F.Cu', stack, layerVisibility), 'In2.Cu',
  'isolating an inner layer must not leave the 2D view on a hidden front layer');
assert.equal(copperLayerSelectionModule.visibleLayoutCopperLayer('All', stack, layerVisibility), 'All');
assert.equal(copperLayerSelectionModule.visibleLayoutCopperLayer('Overview', stack, layerVisibility), 'Overview');
assert.equal(copperLayerSelectionModule.visibleLayoutCopperLayer('In2.Cu', stack, { ...layerVisibility, 'In2.Cu': false }), 'In2.Cu',
  'hiding every copper layer must not silently re-enable one');
const numericRangeSource = readFileSync(new URL("../src/numericRange.ts", import.meta.url), "utf8");
const numericRangeModule = ts.transpileModule(numericRangeSource, { compilerOptions }).outputText;
const numericRangeUrl = `data:text/javascript;base64,${Buffer.from(numericRangeModule).toString("base64")}`;
const parserSource = readFileSync(new URL("../src/boardParser.ts", import.meta.url), "utf8");
const parserModule = ts.transpileModule(parserSource, { compilerOptions }).outputText
  .replace('from "./numericRange";', `from "${numericRangeUrl}";`);
const parser = await import(`data:text/javascript;base64,${Buffer.from(parserModule).toString("base64")}`);

const stackup = [
  { name: "F.SilkS", type: "Top Silk Screen" },
  { name: "F.Paste", type: "Top Solder Paste" },
  { name: "F.Mask", type: "Top Solder Mask", thickness: 0.01 },
  { name: "F.Cu", type: "copper", thickness: 0.07 },
  { name: "dielectric 1", type: "prepreg", thickness: 0.1, material: "FR4", epsilonR: 4.5, lossTangent: 0.02 },
  { name: "In1.Cu", type: "copper", thickness: 0.035 },
  { name: "dielectric 2", type: "core", thickness: 0.535, material: "FR4", epsilonR: 4.5, lossTangent: 0.02 },
  { name: "In2.Cu", type: "copper", thickness: 0.035 },
  { name: "dielectric 3", type: "prepreg", thickness: 0.1, material: "FR4", epsilonR: 4.5, lossTangent: 0.02 },
  { name: "In3.Cu", type: "copper", thickness: 0.035 },
  { name: "dielectric 4", type: "core", thickness: 0.535, material: "FR4", epsilonR: 4.5, lossTangent: 0.02 },
  { name: "In4.Cu", type: "copper", thickness: 0.035 },
  { name: "dielectric 5", type: "prepreg", thickness: 0.1, material: "FR4", epsilonR: 4.5, lossTangent: 0.02 },
  { name: "B.Cu", type: "copper", thickness: 0.07 },
  { name: "B.Mask", type: "Bottom Solder Mask", thickness: 0.01 },
  { name: "B.Paste", type: "Bottom Solder Paste" },
  { name: "B.SilkS", type: "Bottom Silk Screen" },
];
const drawablePhysical = stackup.filter(layer => !layer.name.startsWith("dielectric"));
const definitions = drawablePhysical.map((layer, id) => ({
  id,
  name: layer.name,
  kind: layer.name.endsWith(".Cu") ? "signal" : "user",
}));
definitions.push({ id: 44, name: "Edge.Cuts", kind: "user" });
definitions.push({ id: 48, name: "User.1", kind: "user" });

const inventory = inventoryModule.buildLayerManagerInventory(definitions, stackup);
assert.equal(inventory.physicalCount, 17, "the manager must use the canonical stackup physical count");
assert.equal(inventory.copperCount, 6, "the manager must report copper-layer count independently of stack rows");
assert.equal(inventory.drawableCount, 14, "drawable technical layers must be counted separately");
assert.deepEqual(inventory.entries.slice(0, 17).map(entry => entry.name), stackup.map(layer => layer.name), "physical source order must be preserved");

const groupCounts = Object.fromEntries(inventoryModule.LAYER_INVENTORY_GROUP_ORDER.map(group => [
  group,
  inventory.entries.filter(entry => entry.group === group).length,
]));
assert.equal(groupCounts.Copper, 6);
assert.equal(groupCounts.Dielectric, 5);
assert.equal(groupCounts["Board finish"], 6);
assert.equal(groupCounts.Mechanical, 1);
assert.equal(groupCounts.User, 1);
assert.ok(inventory.entries.find(entry => entry.name === "dielectric 1")?.description.includes("100 µm"));
assert.equal(inventory.entries.find(entry => entry.name === "dielectric 1")?.drawable, false);
assert.equal(inventory.entries.filter(entry => entry.name === "F.Cu").length, 1, "a physical drawable layer must not be duplicated");

const fallback = inventoryModule.buildLayerManagerInventory(definitions, []);
assert.equal(fallback.physicalCount, 0);
assert.equal(fallback.copperCount, 6, "boards without stackup metadata must still report their copper-layer count");
assert.equal(fallback.entries.length, definitions.length, "boards without stackup metadata must retain every drawable layer");

const modularSource = readFileSync(new URL("../public/demo/MODULAR-BUS-NIB.kicad_pcb", import.meta.url), "utf8");
const modularBoard = parser.parseKicadBoard(modularSource);
const modularInventory = inventoryModule.buildLayerManagerInventory(modularBoard.layerDefinitions, modularBoard.stackup);
assert.equal(modularBoard.stackup.length, 17, "the committed large-board fixture must retain all physical stack rows");
assert.equal(modularInventory.physicalCount, modularBoard.stackup.length, "Layer Manager count must match the canonical parser stackup");
assert.deepEqual(
  Object.fromEntries(["Copper", "Dielectric", "Board finish"].map(group => [
    group,
    modularInventory.entries.filter(entry => entry.physical && entry.group === group).length,
  ])),
  { Copper: 6, Dielectric: 5, "Board finish": 6 },
  "the real 17-layer fixture must not drop dielectric rows or misclassify physical finishes",
);

console.log("Layer inventory regression passed: wildcard copper spans resolve to the 2-, 10-, and 32-layer physical stacks; 17 physical = 6 copper + 5 dielectric + 6 board finish.");

const arbitraryCopper = ["TOP", "SIGNAL1", "BOTTOM"];
assert.deepEqual(copperLayerSelectionModule.resolveBoardCopperLayers(arbitraryCopper, ["TOP", "BOTTOM"]), ["TOP", "BOTTOM"]);
const arbitraryInventory = inventoryModule.buildLayerManagerInventory(arbitraryCopper.map((name, id) => ({name, id, kind: "signal"})), []);
assert.equal(arbitraryInventory.copperCount, 3);
assert.ok(arbitraryInventory.entries.every(entry => entry.group === "Copper"));
