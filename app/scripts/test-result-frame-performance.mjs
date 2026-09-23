import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const transpile = source => ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const numericSource = readFileSync(new URL("../src/numericRange.ts", import.meta.url), "utf8");
const numericUrl = `data:text/javascript;base64,${Buffer.from(transpile(numericSource)).toString("base64")}`;
const resultSource = readFileSync(new URL("../src/analysisResults.ts", import.meta.url), "utf8")
  .replace('from "./numericRange"', `from "${numericUrl}"`);
const resultUrl = `data:text/javascript;base64,${Buffer.from(transpile(resultSource)).toString("base64")}`;
const { resultAtFrame } = await import(resultUrl);

const layout = Array.from({ length: 25_000 }, (_, index) => ({
  x_mm: index % 500,
  y_mm: Math.floor(index / 500),
  layer: "F.Cu",
  net: "VCC",
}));
const base = layout.map(sample => ({ ...sample, value: -1 }));
const values = Array.from({ length: layout.length }, (_, index) => index / layout.length);
const result = {
  analysis_id: "frame-performance",
  mode: "transient",
  model_status: "test",
  summary: {},
  scalar_fields: {
    voltage_v: base,
    voltage_drop_v: base,
    current_a: base,
    operating_point_impedance_ohm: base,
    current_density_a_mm2: base,
    power_loss_w: base,
    via_current_density_a_mm2: base,
  },
  vector_fields: { current_density: [], electric_field: [], magnetic_field: [] },
  mesh: [], parasitics: [], loop_parasitics: [], pdn_multiports: [], coupling_risks: [],
  component_bridges: [], component_stress: [], probes: [], issues: [], provenance: {},
  time_series: {
    times_s: [0],
    layouts: { shared: layout },
    field_layouts: { voltage_v: "shared", current_a: "shared" },
    frames: [{ time_s: 0, scalar_values: { voltage_v: values, current_a: values } }],
  },
};

const started = performance.now();
const voltageOnly = resultAtFrame(result, 0, { scalarFields: ["voltage_v"], vectorFields: [] });
const elapsed = performance.now() - started;
assert.equal(voltageOnly.scalar_fields.voltage_v.length, layout.length);
assert.equal(voltageOnly.scalar_fields.voltage_v[500].value, values[500]);
assert.equal(voltageOnly.scalar_fields.current_a, base,
  "unselected compact fields must retain the immutable base field instead of being expanded");
assert.equal(resultAtFrame(result, 0, { scalarFields: ["voltage_v"], vectorFields: [] }), voltageOnly,
  "repeated playback visits must reuse the bounded materialized frame");
assert.ok(elapsed < 250, `one selected 25k-sample field materialized in ${elapsed.toFixed(2)} ms`);

console.log(`result frame performance: selected=1/2 compact fields; samples=${layout.length}; cold=${elapsed.toFixed(2)}ms; repeat=cached`);

const fieldLayout = Array.from({ length: 70_000 }, (_, i) => ({ x_mm: i, y_mm: 0 }));
const fieldResult = { ...result, time_series: {
  layouts: { em: fieldLayout }, vector_layouts: { electric_field: 'em' },
  vector_directions: { electric_field: fieldLayout.map(() => [1, 0, 0]) },
  times_s: [0, 1, 2], frames: [0, 1, 2].map(time_s => ({ time_s,
    vector_values: { electric_field: fieldLayout.map(() => time_s + 1) } })),
} };
const selection = { scalarFields: [], vectorFields: ['electric_field'] };
const first = resultAtFrame(fieldResult, 0, selection);
const second = resultAtFrame(fieldResult, 1, selection);
assert.equal(second.vector_fields.electric_field[0].vector[0], 2);
assert.equal(resultAtFrame(fieldResult, 1, selection), second, 'active dense EMI frame stays cached');
assert.notEqual(resultAtFrame(fieldResult, 0, selection), first, 'weighted cache evicts older large fields');
assert.equal(fieldResult.time_series.frames[0].vector_values.electric_field[0], 1, 'source samples stay exact');
console.log('Dense EMI frame cache: weighted eviction and immutable source values passed');
