import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/topologyPorts.ts", import.meta.url), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const topology = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);

const regulatorPorts = topology.defaultTopologyPorts("regulator", "pi");
assert.deepEqual(regulatorPorts.map(port => port.id), ["vin", "vout", "return", "enable"]);
assert.equal(regulatorPorts.find(port => port.id === "vout").maximumConnections, undefined, "one regulator output may feed multiple branches");

const channelPorts = topology.defaultTopologyPorts("channel", "si");
assert.deepEqual(channelPorts.map(port => port.label), ["IN1", "OUT1", "REF"]);
assert.ok(channelPorts.every(port => !/[+-]$/.test(port.label)), "generic SI blocks must not invent differential signaling");
assert.equal(topology.defaultTopologyPorts("connector", "si").length, 5, "connectors expose multiple side-A/side-B terminals and shield");

const legacy = {
  contract: "spike/topology/v1", domain: "si", name: "Legacy channel",
  nodes: [
    { id: "tx", kind: "driver", label: "TX", x: 0, y: 0, origin: "user" },
    { id: "route", kind: "channel", label: "Route", x: 200, y: 0, origin: "user" },
  ],
  edges: [{ id: "e", from: "tx", to: "route", kind: "signal", origin: "user" }],
  extraction: { source: "manual", generatedAt: "2026-08-30T00:00:00Z", warnings: [] },
};
const normalized = topology.normalizeTopologyPorts(legacy);
assert.equal(normalized.edges[0].portBinding, "inferred");
assert.equal(normalized.edges[0].fromPort, "out_1");
assert.equal(normalized.edges[0].toPort, "in_1");
assert.deepEqual(topology.validateTopologyPorts(normalized).filter(issue => issue.severity === "error"), []);

const explicit = structuredClone(normalized);
explicit.edges[0].portBinding = "explicit";
assert.deepEqual(topology.validateTopologyPorts(explicit), []);
const broken = structuredClone(explicit);
broken.edges[0].toPort = "missing";
assert.ok(topology.validateTopologyPorts(broken).some(issue => issue.code === "missing_port"));
const halfBound = structuredClone(explicit);
delete halfBound.edges[0].toPort;
assert.ok(topology.validateTopologyPorts(halfBound).some(issue => issue.code === "half_bound_edge"));

const withElectricalData = {
  ...explicit,
  scenarios: [{ id: "maximum", label: "Maximum", loadMultiplier: 1.25 }],
  nodes: explicit.nodes.map((node, index) => ({ ...node, x: index * 999, y: index * 333, modelLink: index ? undefined : "model:tx", modelParameters: index ? undefined : { z: 2, a: 1 } })),
};
const text = topology.topologyToText(withElectricalData);
assert.ok(text.startsWith("SPIKE TOPOLOGY TEXT v1\nDOMAIN SI\n"));
assert.ok(text.includes("PORT \"out_1\""));
assert.ok(text.includes("model:tx"));
assert.ok(text.includes("port_binding=explicit"));
assert.ok(!text.includes(" at="), "canvas placement is not part of the semantic text equivalent");
assert.ok(text.endsWith("\n"));

const moved = { ...withElectricalData, nodes: withElectricalData.nodes.map(node => ({ ...node, x: node.x + 77, y: node.y - 55 })) };
assert.equal(topology.topologyToText(moved), text, "moving diagram blocks must not change the semantic description");
const permuted = { ...withElectricalData, nodes: [...withElectricalData.nodes].reverse(), edges: [...withElectricalData.edges].reverse() };
assert.equal(topology.topologyToText(permuted), text, "semantic text must be stable across input ordering");

console.log("SPIKE topology multi-port, migration, validation, and text-equivalent assertions passed");
