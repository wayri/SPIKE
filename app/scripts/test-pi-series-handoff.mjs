import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/piPath.ts", import.meta.url), "utf8")
  .replace(/^import type .*$/gm, "");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { compilePiPaths, compilePiSeriesSolveHandoff } = await import(
  `data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`
);

const pads = [
  { id: "J1.1", ref: "J1", name: "1", net: "VIN", at: [0, 0], layers: ["F.Cu"] },
  { id: "R1.1", ref: "R1", name: "1", net: "VIN", at: [2, 0], layers: ["F.Cu"] },
  { id: "R1.2", ref: "R1", name: "2", net: "VMID", at: [3, 0], layers: ["F.Cu"] },
  { id: "R2.1", ref: "R2", name: "1", net: "VMID", at: [6, 0], layers: ["F.Cu"] },
  { id: "R2.2", ref: "R2", name: "2", net: "VOUT", at: [7, 0], layers: ["F.Cu"] },
  { id: "J2.1", ref: "J2", name: "1", net: "VOUT", at: [9, 0], layers: ["F.Cu"] },
];
const model = {
  contract: "spike/topology/v1",
  domain: "pi",
  name: "Three-net fixture",
  scenarios: [],
  extraction: { source: "manual", generatedAt: "2026-08-21T00:00:00Z", warnings: [] },
  nodes: [
    { id: "source", kind: "source", label: "Input", net: "VIN", terminalPadId: "J1.1", pathGroupId: "path", x: 0, y: 0, origin: "user" },
    { id: "vin", kind: "rail", label: "VIN", net: "VIN", pathGroupId: "path", x: 1, y: 0, origin: "user" },
    { id: "r1", kind: "passive", label: "R1", ref: "R1", orientation: "series", pathGroupId: "path", resistanceOhm: 0.01, modelParameters: { package_resistance_ohm: 0.002 }, circuitModel: { primitive: "resistor", value: "10m", pins: [{ pad_id: "R1.1", circuit_node: "in", role: "input" }, { pad_id: "R1.2", circuit_node: "out", role: "output" }] }, x: 2, y: 0, origin: "user" },
    { id: "mid", kind: "rail", label: "VMID", net: "VMID", pathGroupId: "path", x: 4, y: 0, origin: "user" },
    { id: "r2", kind: "passive", label: "R2", ref: "R2", orientation: "series", pathGroupId: "path", modelParameters: { dc_resistance_ohm: 0.02, inductance_h: 1e-9 }, circuitModel: { primitive: "resistor", value: "20m", pins: [{ pad_id: "R2.1", circuit_node: "in", role: "input" }, { pad_id: "R2.2", circuit_node: "out", role: "output" }] }, x: 6, y: 0, origin: "user" },
    { id: "out", kind: "rail", label: "VOUT", net: "VOUT", pathGroupId: "path", x: 8, y: 0, origin: "user" },
    { id: "load", kind: "load", label: "Load", net: "VOUT", terminalPadId: "J2.1", pathGroupId: "path", x: 9, y: 0, origin: "user" },
  ],
  edges: [
    { id: "1", from: "source", to: "vin", kind: "power", origin: "user" },
    { id: "2", from: "vin", to: "r1", kind: "power", origin: "user" },
    { id: "3", from: "r1", to: "mid", kind: "power", origin: "user" },
    { id: "4", from: "mid", to: "r2", kind: "power", origin: "user" },
    { id: "5", from: "r2", to: "out", kind: "power", origin: "user" },
    { id: "6", from: "out", to: "load", kind: "power", origin: "user" },
  ],
};

const path = compilePiPaths(model)[0];
const handoff = compilePiSeriesSolveHandoff(path, pads);
const solveRequest = {
  spec: {
    net_names: handoff.net_names,
    sources: [{ ...handoff.source_terminal, voltage_v: 12 }],
    loads: [{ ...handoff.load_terminal, current_a: 1 }],
    options: { pi_path: handoff.pi_path },
  },
};

assert.deepEqual(solveRequest.spec.net_names, ["VIN", "VMID", "VOUT"]);
assert.deepEqual(solveRequest.spec.sources[0].geometry_anchor, { id: "J1.1", type: "pad" });
assert.deepEqual(solveRequest.spec.loads[0].geometry_anchor, { id: "J2.1", type: "pad" });
assert.equal(solveRequest.spec.options.pi_path.transitions.length, 2);
assert.equal(solveRequest.spec.options.pi_path.transitions[0].model.dc_resistance_ohm, 0.01);
assert.equal(solveRequest.spec.options.pi_path.transitions[0].model.package_resistance_ohm, 0.002);
assert.equal(solveRequest.spec.options.pi_path.transitions[1].model.dc_resistance_ohm, 0.02);
assert.equal(solveRequest.spec.options.pi_path.transitions[1].model.inductance_h, 1e-9);
assert.throws(() => compilePiSeriesSolveHandoff({ ...path, issues: ["review required"] }, pads), /incomplete/);

console.log("PI series solve handoff: all assertions passed");
