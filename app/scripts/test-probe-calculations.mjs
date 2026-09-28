// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/probeCalculations.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const calculations = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);
const probes = {
  P1: { voltage: { value: 5, unit: "V" }, current: { value: 2, unit: "A" }, drop: { value: 0, unit: "V" } },
  P2: { voltage: { value: 3, unit: "V" } },
};
const evaluate = rows => calculations.evaluateProbeFormulas(rows, probes);
let result = evaluate([
  { id: "C1", name: "Resistance", formula: "P1.voltage / P1.current" },
  { id: "C2", name: "Largest", formula: "max(abs(P1.voltage - P2.voltage), P1.drop)" },
  { id: "C3", name: "Power", formula: "P1.voltage * P1.current" },
]);
assert.deepEqual(result.map(row => row.result), [{ value: 2.5, unit: "ohm" }, { value: 2, unit: "V" }, { value: 10, unit: "W" }]);
assert.equal(evaluate([{ id: "C1", name: "Subtract", formula: "P1.voltage-P2.voltage" }])[0].result.value, 2);
assert.equal(result[1].error, undefined, "numeric zero must remain a valid mapped value");
assert.match(evaluate([{ id: "C1", name: "Bad units", formula: "P1.voltage + P1.current" }])[0].error, /Cannot add V and A/);
assert.match(evaluate([{ id: "C1", name: "Missing", formula: "P1.power" }])[0].error, /no mapped 'power'/);
assert.match(evaluate([{ id: "C1", name: "Unknown", formula: "P9.voltage" }])[0].error, /Unknown probe/);
assert.match(evaluate([{ id: "C1", name: "Zero", formula: "P1.voltage / P1.drop" }])[0].error, /Division by zero/);
result = evaluate([{ id: "C1", name: "One", formula: "C2.value" }, { id: "C2", name: "Two", formula: "C1.value" }]);
assert.ok(result.every(row => /Cyclic reference/.test(row.error)));
result = evaluate([{ id: "C1", name: "One", formula: "1" }, { id: "C1", name: "Duplicate", formula: "2" }]);
assert.ok(result.every(row => /Duplicate/.test(row.error)));
assert.match(evaluate([{ id: "P1", name: "Conflict", formula: "1" }])[0].error, /conflicts with a probe/);
assert.match(evaluate([{ id: "C1", name: "Unsafe", formula: "globalThis.alert(1)" }])[0].error, /Unexpected|Unknown|Expected/);
const displayRows = calculations.buildProbeRows(
  [{ id: "track:1", name: "Rail", probeKind: "voltage", net: "VCC", layer: "F.Cu" }],
  { probes: [{ id: "track:1", status: "unmapped", voltage_v: 5, voltage_drop_v: 0 }] },
);
assert.match(displayRows[0].id, /^P_/); assert.equal(displayRows[0].values.voltage, undefined, "unmapped payload values must not become measurements");
const mappedRows = calculations.buildProbeRows([{ id: "P1", name: "Rail" }], { probes: [{ id: "P1", status: "mapped", voltage_v: 0 }] });
assert.deepEqual(mappedRows[0].values.voltage, { value: 0, unit: "V" });
const csv = calculations.probeResultsCsv([{ id: "P1", name: "Probe, one", kind: "voltage", status: "mapped", values: probes.P1 }], evaluate([{ id: "C1", name: "R", formula: "P1.voltage / P1.current" }]));
assert.match(csv, /"Probe, one"/); assert.match(csv, /"P1.voltage \/ P1.current"/); assert.match(csv, /"2.5","ohm"/);
console.log("Probe formula math, dimensions, zero, invalid/missing/cyclic references and CSV passed.");
