import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const { importTestTypescript } = await import("./import-test-typescript.mjs");
const powerTree = await importTestTypescript("powerTree");
const piPathSource = readFileSync(new URL("../src/piPath.ts", import.meta.url), "utf8")
  .replace(/^import type .*$/m, "");
const piPathTranspiled = ts.transpileModule(piPathSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const piPath = await import(`data:text/javascript;base64,${Buffer.from(piPathTranspiled).toString("base64")}`);

const model = {
  contract: "spike/topology/v1",
  domain: "pi",
  name: "12 V rail fixture",
  scenarios: powerTree.defaultTopologyScenarios(),
  nodes: [
    { id: "source", kind: "source", label: "Input", ref: "J1", voltageV: 12, x: 0, y: 0, origin: "user" },
    { id: "rail", kind: "rail", label: "12V", net: "+12V", voltageV: 12, maxCurrentA: 4, x: 200, y: 0, origin: "user" },
    { id: "load", kind: "load", label: "Controller", ref: "U1", net: "+12V", loadCurrentA: 2, operatingPoints: { maximum: { currentA: 3 } }, x: 400, y: 0, origin: "user" },
  ],
  edges: [
    { id: "source-rail", from: "source", to: "rail", net: "+12V", kind: "power", origin: "user" },
    { id: "rail-load", from: "rail", to: "load", net: "+12V", kind: "power", origin: "user" },
  ],
  extraction: { source: "manual", generatedAt: "2026-08-11T00:00:00Z", warnings: [] },
};

const typical = powerTree.calculatePowerTree(model, "typical");
assert.equal(typical.status, "complete");
assert.equal(typical.loadPowerW, 24);
assert.equal(typical.rails[0].currentA, 2);

const maximum = powerTree.calculatePowerTree(model, "maximum");
assert.equal(maximum.loadPowerW, 36, "explicit scenario demand must not be multiplied twice");
assert.equal(maximum.nodes.load.currentA, 3);

const numericMultiplier = powerTree.calculatePowerTree({ ...model, nodes: model.nodes.map(node => node.id === "load" ? { ...node, operatingPoints: undefined } : node) }, 1.25);
assert.equal(numericMultiplier.loadPowerW, 30, "legacy numeric multipliers remain supported");

const converterCase = (converterKind, efficiencyPercent) => powerTree.calculatePowerTree({
  ...model,
  nodes: [model.nodes[0], { id: "converter", kind: "regulator", label: "3.3 V stage", converterKind, voltageRatio: 3.3 / 12, efficiencyPercent, x: 100, y: 0, origin: "user" },
    { ...model.nodes[1], voltageV: undefined, net: "+3.3V" }, { ...model.nodes[2], loadCurrentA: 0.15, operatingPoints: undefined, net: "+3.3V" }],
  edges: [{ id: "source-converter", from: "source", to: "converter", kind: "power", origin: "user" },
    { id: "converter-rail", from: "converter", to: "rail", kind: "power", origin: "user" }, model.edges[1]],
}, "typical");
const ldo = converterCase("ldo");
assert.equal(ldo.status, "complete");
assert.ok(Math.abs(ldo.nodes.converter.voltageV - 3.3) < 1e-12);
assert.ok(Math.abs(ldo.nodes.converter.lossW - (12 - 3.3) * 0.15) < 1e-12);
assert.ok(Math.abs(ldo.nodes.converter.inputCurrentA - 0.15) < 1e-12);
const buck = converterCase("buck", 90);
assert.equal(buck.status, "complete");
assert.ok(Math.abs(buck.nodes.converter.lossW - (3.3 * 0.15 / 0.9 - 3.3 * 0.15)) < 1e-12);
assert.ok(Math.abs(buck.nodes.converter.inputCurrentA - (3.3 * 0.15 / 0.9 / 12)) < 1e-12);
assert.ok(Math.abs(buck.sourcePowerW - buck.loadPowerW - buck.lossW) < 1e-12);
assert.equal(converterCase("ldo", undefined).warnings.length, 0);
assert.equal(converterCase("buck", undefined).status, "incomplete", "buck efficiency must be supplied");
const stepUpLdo = powerTree.calculatePowerTree({ ...model,
  nodes: [model.nodes[0], { id: "ldo", kind: "regulator", label: "Invalid LDO", converterKind: "ldo", voltageV: 15, x: 100, y: 0, origin: "user" }, model.nodes[2]],
  edges: [{ id: "source-ldo", from: "source", to: "ldo", kind: "power", origin: "user" }, { id: "ldo-load", from: "ldo", to: "load", kind: "power", origin: "user" }],
}, "typical");
assert.equal(stepUpLdo.status, "invalid", "an LDO cannot step voltage up");

const plan = powerTree.buildPowerTreeAnalysisPlan(model, "maximum");
assert.equal(plan.contract, "spike/power-tree-analysis-plan/v1");
assert.equal(plan.status, "ready");
assert.equal(plan.jobs.length, 1);
assert.deepEqual(plan.jobs[0].sourceNodeIds, ["source"]);
assert.deepEqual(plan.jobs[0].loadNodeIds, ["load"]);
assert.equal(plan.jobs[0].totalCurrentA, 3);

const legacy = { ...model, scenarios: undefined };
assert.deepEqual(powerTree.topologyScenarios(legacy).map(item => item.id), ["typical", "maximum", "standby"]);

const incomplete = powerTree.buildPowerTreeAnalysisPlan({ ...model, nodes: model.nodes.filter(node => node.id !== "source"), edges: model.edges.filter(edge => edge.from !== "source") }, "typical");
assert.equal(incomplete.status, "invalid");

const board = {
  nets: { "1": "VIN", "2": "VOUT", "3": "GND" },
  components: [
    { id: "source", ref: "J1", value: "INPUT" },
    { id: "series", ref: "R1", value: "10m" },
    { id: "shunt", ref: "C1", value: "10u" },
    { id: "load", ref: "J2", value: "LOAD" },
  ],
  pads: [
    { id: "J1.1", ref: "J1", name: "1", net: "VIN", layer: "F.Cu", layers: ["F.Cu"] },
    { id: "R1.1", ref: "R1", name: "1", net: "VIN", layer: "F.Cu", layers: ["F.Cu"] },
    { id: "R1.2", ref: "R1", name: "2", net: "VOUT", layer: "F.Cu", layers: ["F.Cu"] },
    { id: "C1.1", ref: "C1", name: "1", net: "VOUT", layer: "F.Cu", layers: ["F.Cu"] },
    { id: "C1.2", ref: "C1", name: "2", net: "GND", layer: "F.Cu", layers: ["F.Cu"] },
    { id: "J2.1", ref: "J2", name: "1", net: "VOUT", layer: "F.Cu", layers: ["F.Cu"] },
  ],
};
const focused = powerTree.extractPowerPathFromBoard(board, "J1.1", "J2.1");
assert.equal(focused.nodes.find(node => node.ref === "R1")?.orientation, "series");
assert.equal(focused.nodes.find(node => node.ref === "R1")?.circuitModel?.pins?.length, 2);
assert.equal(focused.nodes.find(node => node.ref === "C1")?.orientation, "shunt");
assert.ok(focused.nodes.some(node => node.kind === "return" && node.net === "GND"));
assert.ok(focused.edges.some(edge => edge.kind === "return"));
const compiledPaths = piPath.compilePiPaths(focused);
assert.equal(compiledPaths.length, 1);
assert.deepEqual(compiledPaths[0].segments.map(segment => segment.net), ["VIN", "VOUT"]);
assert.equal(compiledPaths[0].source_terminal.pad_id, "J1.1");
assert.equal(compiledPaths[0].load_terminal.pad_id, "J2.1");
assert.equal(compiledPaths[0].transitions[0].component_ref, "R1");
assert.equal(compiledPaths[0].transitions[0].input_pad_id, "R1.1");
assert.equal(compiledPaths[0].transitions[0].output_pad_id, "R1.2");
assert.deepEqual(compiledPaths[0].issues, []);

const largeComponentCount = 4_000;
const largeBoard = {
  nets: Object.fromEntries(Array.from({ length: 32 }, (_, index) => [String(index + 1), `DATA_${index}`])),
  components: Array.from({ length: largeComponentCount }, (_, index) => ({
    id: `component-${index}`,
    ref: `U${index + 1}`,
    value: "receiver",
    library: "large-board-fixture",
  })),
  pads: Array.from({ length: largeComponentCount * 4 }, (_, index) => ({
    id: `pad-${index}`,
    ref: `U${Math.floor(index / 4) + 1}`,
    name: String(index % 4 + 1),
    net: `DATA_${index % 32}`,
    layer: "F.Cu",
    layers: ["F.Cu"],
  })),
};
const largeStarted = performance.now();
powerTree.extractTopologyFromBoard(largeBoard, "pi");
powerTree.extractTopologyFromBoard(largeBoard, "si");
const largeElapsed = performance.now() - largeStarted;
assert.ok(largeElapsed < 2_000, `large-board PI+SI topology extraction took ${largeElapsed.toFixed(2)} ms`);

console.log(`SPIKE power-tree assertions passed; large-board topology=${largeElapsed.toFixed(2)}ms for ${largeComponentCount} components/${largeBoard.pads.length} pads`);
