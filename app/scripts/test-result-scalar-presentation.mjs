// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import ts from "typescript";

async function load(path, replacements = []) {
  let source = readFileSync(new URL(path, import.meta.url), "utf8");
  for (const [from, to] of replacements) source = source.replaceAll(from, to);
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);
}

const layers = await load("../src/resultLayerSelection.ts");
const layerOutput = ts.transpileModule(readFileSync(new URL("../src/resultLayerSelection.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const layerUrl = `data:text/javascript;base64,${Buffer.from(layerOutput).toString("base64")}`;
const source = readFileSync(new URL("../src/resultScalarPresentation.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source.replace('"./resultLayerSelection"', JSON.stringify(layerUrl)), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const presentation = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

const boardLayers = ["F.Cu", "In1.Cu", "B.Cu"];
const fixture = [
  { element_id: "front-low", layer: "F.Cu", value: 1 },
  { element_id: "through-high", layer: "through", value: 9 },
  { element_id: "inner", layer: "In1.Cu", value: 4 },
  { element_id: "back", layer: "B.Cu", value: 2 },
  { element_id: "malformed", layer: "F.Cu", value: Number.NaN },
];
const reference = (selectedLayers) => {
  const samples = fixture.filter(sample => layers.resultLayerMatchesSelection(sample.layer, selectedLayers, boardLayers));
  const values = samples.map(sample => sample.value).filter(Number.isFinite).sort((a, b) => a - b);
  return { samples, values, hotspots: [...samples].sort((a, b) => b.value - a.value).slice(0, 12) };
};
for (const selected of [[], ["F.Cu"], ["In1.Cu"], ["F.Cu", "B.Cu"]]) {
  const actual = presentation.resultScalarPresentation(fixture, selected, boardLayers);
  const expected = reference(selected);
  assert.deepEqual(actual.samples.map(sample => sample.element_id), expected.samples.map(sample => sample.element_id), "masked and through-layer sample identities remain exact");
  assert.deepEqual(actual.sortedFiniteValues, expected.values, "finite value ordering remains exact");
  assert.deepEqual(actual.hotspots.map(sample => sample.element_id), expected.hotspots.map(sample => sample.element_id), "hotspot ordering, including malformed cells, remains exact");
  assert.equal(presentation.resultScalarPresentation(fixture, selected, boardLayers), actual, "unchanged result/layer presentation is identity cached");
}
const layerResult = {
  scalar_fields: { voltage_v: fixture, current_density_a_mm2: [{ layer: "User.1", value: 1 }] },
  mesh: [{ layer: "F.Cu->B.Cu" }],
  vector_fields: { current_density: [{ layer: "B.Cu" }], electric_field: [], magnetic_field: [] },
};
const inventory = presentation.resultLayerInventory(layerResult, layerResult.scalar_fields.voltage_v, boardLayers);
assert.deepEqual(inventory, boardLayers, "scalar, vector, mesh, and through-span layers retain board order");
assert.equal(presentation.resultLayerInventory(layerResult, layerResult.scalar_fields.voltage_v, boardLayers), inventory, "unchanged result layer inventory is identity cached");

const dense = Array.from({ length: 100_000 }, (_, index) => ({
  element_id: `cell-${index}`, layer: index % 4 ? "F.Cu" : "B.Cu", value: ((index * 7919) % 100_003) / 100,
}));
const baseline = () => {
  const samples = dense.filter(sample => layers.resultLayerMatchesSelection(sample.layer, ["F.Cu"], boardLayers));
  const values = samples.map(sample => sample.value).filter(Number.isFinite).sort((a, b) => a - b);
  const hotspots = [...samples].sort((a, b) => b.value - a.value).slice(0, 12);
  return [samples.length, values[0], values.at(-1), hotspots.map(sample => sample.element_id)];
};
const elapsed = work => { const start = performance.now(); const value = work(); return { value, ms: performance.now() - start }; };
const before = Array.from({ length: 5 }, () => elapsed(baseline).ms).sort((a, b) => a - b)[2];
const cold = elapsed(() => presentation.resultScalarPresentation(dense, ["F.Cu"], boardLayers));
const warmRuns = Array.from({ length: 20 }, () => elapsed(() => presentation.resultScalarPresentation(dense, ["F.Cu"], boardLayers)).ms).sort((a, b) => a - b);
assert.deepEqual([cold.value.samples.length, cold.value.minimum, cold.value.maximum, cold.value.hotspots.map(sample => sample.element_id)], baseline());
assert.ok(warmRuns[10] < before / 20, `cached repeat ${warmRuns[10].toFixed(3)}ms should avoid baseline ${before.toFixed(2)}ms sort`);
console.log(JSON.stringify({ samples: dense.length, selected: cold.value.samples.length, baselineMedianMs: before, coldMs: cold.ms, warmMedianMs: warmRuns[10] }));
