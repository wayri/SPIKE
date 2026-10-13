// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/traceValuePopupModel.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { traceSparklinePoints, traceValuePopupModel } = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);
const trace = { id: "track-a", net: "VCC", layer: "F.Cu", position: [1, 2] };
const result = {
  scalar_fields: {
    voltage_v: [{ element_id: "track-a", net: "VCC", layer: "F.Cu", x_mm: 1, y_mm: 2, value: 3.3 }],
    current_a: [{ element_id: "other", net: "VCC", layer: "B.Cu", x_mm: 1, y_mm: 2, value: 99 }],
  },
  time_series: {
    layouts: { voltage_v: [{ element_id: "track-a", net: "VCC", layer: "F.Cu", x_mm: 1, y_mm: 2 }] },
    frames: Array.from({ length: 20 }, (_, index) => ({ time_s: index * .1, scalar_values: { voltage_v: [index] } })),
  },
};
let model = traceValuePopupModel(result, trace, 6);
assert.equal(model.series[0].unit, "V");
assert.equal(model.series[0].value, 3.3);
assert.equal(model.series[0].source, "trace_id");
assert.equal(model.series[0].history.length, 6, "saved history is bounded");
assert.equal(model.series[0].history[0].value, 0);
assert.equal(model.series[0].history.at(-1).value, 19, "bounded history preserves the final sample");
assert.deepEqual(model.unavailable, ["Current unavailable"], "another layer must not supply a picked trace value");

model = traceValuePopupModel({ scalar_fields: { voltage_v: [{ element_id: "other", net: "VCC", layer: "F.Cu", x_mm: 1.2, y_mm: 2, value: 3.2 }] } }, trace);
assert.equal(model.series[0].source, "nearby", "bounded fallback must be explicitly distinguished from trace identity");

model = traceValuePopupModel({ scalar_fields: { voltage_v: [{ element_id: "x", net: "VCC", layer: "F.Cu", x_mm: 20, y_mm: 20, value: 4 }] } }, trace);
assert.deepEqual(model.series, [], "a distant same-net sample must not be inferred as local data");
assert.deepEqual(model.unavailable, ["Voltage unavailable", "Current unavailable"]);

model = traceValuePopupModel({ scalar_fields: { voltage_v: [{ element_id: "track-a", net: "VCC", layer: "F.Cu", x_mm: 1, y_mm: 2, value: Number.NaN }] } }, trace);
assert.deepEqual(model.series, [], "invalid solver values must remain unavailable");

model = traceValuePopupModel({ time_series: { frames: [
  { time_s: 0, scalar_fields: { current_a: [{ element_id: "track-a", net: "VCC", layer: "F.Cu", x_mm: 1, y_mm: 2, value: 0.1 }] } },
  { time_s: 1, scalar_fields: { current_a: [{ element_id: "track-a", net: "VCC", layer: "F.Cu", x_mm: 1, y_mm: 2, value: 0.2 }] } },
] } }, trace);
assert.equal(model.series[0].unit, "A");
assert.equal(model.series[0].history.length, 2, "explicit per-frame fields form actual saved history");
assert.equal(model.series[0].source, "trace_id");
const uneven = traceSparklinePoints([{ timeS: 0, value: 0 }, { timeS: 1, value: 1 }, { timeS: 9, value: 2 }]);
assert.equal(uneven[1][0], 92 / 9, "sparkline x coordinates must use actual saved timestamps");
assert.equal(uneven[2][0], 92);
console.log("Trace popup exact identity, units, missing/invalid data, layer isolation and bounded saved history passed.");
