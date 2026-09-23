import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/viewportResultFields.ts", import.meta.url), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const fields = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);

const voltage = [
  { x_mm: 10, y_mm: 20, layer: "F.Cu", net: "VDD", element_id: "a", value: 5 },
  { x_mm: 11, y_mm: 20, layer: "F.Cu", net: "VDD", element_id: "b", value: 3 },
];
const current = [
  { x_mm: 10, y_mm: 20, layer: "F.Cu", net: "VDD", element_id: "a", value: 2 },
  { x_mm: 11, y_mm: 20, layer: "B.Cu", net: "VDD", element_id: "b", value: 1 },
  { x_mm: 12, y_mm: 20, layer: "F.Cu", net: "VDD", element_id: "c", value: 0 },
];

const samples = fields.piImpedanceSamples(voltage, current);
assert.equal(samples.length, 1, "only co-located, same-layer samples may form PI V/I impedance");
assert.equal(samples[0].value, 2.5);
assert.equal(fields.viewportResultField("impedance").unit, "ohm");
assert.equal(fields.viewportResultField("impedance").key, "operating_point_impedance_ohm");
assert.match(fields.formatViewportResultTick(0.01234, "ohm"), /ohm$/);
assert.equal(fields.formatViewportAxisTick(12.25), "12.3 mm");
const orderedMeshRows = Array.from({ length: 1000 }, (_, index) => ({
  x_mm: index % 100,
  y_mm: Math.floor(index / 100),
  layer: "F.Cu",
  net: "VDD",
  value: index === 777 ? 100 : 1,
}));
const thinned = fields.spatiallyThinSamples(orderedMeshRows, 100);
assert.ok(thinned.length <= 100, "spatial thinning must honor its viewport budget");
assert.ok(thinned.some(sample => sample.value === 100), "spatial thinning must retain a local hotspot");
assert.ok(new Set(thinned.map(sample => sample.y_mm)).size > 1, "spatial thinning must not expose ordered mesh-row banding");
console.log("viewport result field assertions passed");
