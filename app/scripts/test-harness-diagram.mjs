// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const model = await importTestTypescript("HarnessDiagramModel");
const endpoint = (connector, pin) => ({ connector, pin });
const wire = (id, fromPin, toPin, extra = {}) => ({ id, from: endpoint("J1", fromPin), to: endpoint("J2", toPin), ...extra });
const original = {
  contract: "spike/harness/v1", id: "H1", name: "Harness", provenance: { source: "fixture" },
  connectors: [
    { id: "J1", name: "Source", pins: [{ id: "1", net: "VCC", extensions: { vendor: "kept" } }, { id: "2" }], properties: { family: "A" } },
    { id: "J2", name: "Load", pins: [{ id: "A" }, { id: "B" }], extensions: { vendor: "kept" } },
    { id: "J3", name: "Aux", pins: [{ id: "1" }] },
  ],
  wires: [
    wire("W1", "1", "A", { role: "power", length_mm: 125, route_id: "R1", electrical: { resistance_ohm: .02, inductance_h: 1e-7 }, properties: { gauge: 20 }, extensions: { vendor: "kept" }, return_wire_id: "W2" }),
    wire("W2", "2", "B", { role: "return", color: "black" }),
    wire("W3", "1", "B", { role: "signal" }),
  ],
  cables: [{ id: "C1", wire_ids: ["W1", "W2"], properties: { sleeve: "kept" } }],
  pairs: [{ id: "PAIR1", wire_ids: ["W1", "W2"], kind: "twisted", twisted: true, twist_pitch_mm: 20, extensions: { reviewed: true } }],
  routes: [{ id: "R1", points_mm: [[0, 0, 0], [1, 1, 1]] }],
  extensions: { "spike.harness-pi": { ground: endpoint("J1", "2"), terminals: [{ id: "source", positive: endpoint("J1", "1"), negative: endpoint("J1", "2") }], contacts: [] } },
};

const projection = model.buildHarnessDiagram(original);
assert.equal(projection.nodes.length, 3);
assert.equal(projection.nodes[0].pins[0].label, "VCC", "pin labels prefer retained net labels without changing identity");
assert.equal(projection.wires.length, 3, "each individual wire is projected");
assert.equal(projection.wires.filter(item => !item.unresolved).length, 3);
const duplicateProjection = model.buildHarnessDiagram({ ...original, wires: [original.wires[0], { ...original.wires[0], id: "W1_PARALLEL" }] });
assert.equal(duplicateProjection.wires.length, 2, "multiple individual wires may use the same explicit endpoints");
assert.notEqual(duplicateProjection.wires[0].path, duplicateProjection.wires[1].path, "same-endpoint wires receive separate selectable paths");

const renamed = model.renameHarnessConnector(original, "J1", "J-SOURCE");
assert.equal(renamed.wires[0].from.connector, "J-SOURCE");
assert.equal(renamed.extensions["spike.harness-pi"].ground.connector, "J-SOURCE");
assert.deepEqual(renamed.wires[0].electrical, original.wires[0].electrical, "rename preserves electrical metadata");
assert.deepEqual(renamed.routes, original.routes, "rename preserves route geometry");
assert.deepEqual(renamed.provenance, original.provenance, "rename preserves provenance");
assert.throws(() => model.renameHarnessConnector(original, "J1", "J2"), /already exists/);

const deletedConnector = model.deleteHarnessConnector(original, "J1");
assert.deepEqual(deletedConnector.wires, [], "connector delete cascades every directly referenced wire");
assert.deepEqual(deletedConnector.pairs, [], "connector delete removes invalid pair memberships");
assert.deepEqual(deletedConnector.cables, [], "connector delete removes empty cables");
assert.equal(deletedConnector.extensions["spike.harness-pi"].ground, undefined, "connector delete clears the dependent PI ground");
assert.deepEqual(deletedConnector.extensions["spike.harness-pi"].terminals, [], "connector delete removes dependent PI terminals");

const deletedWire = model.deleteHarnessWire(original, "W2");
assert.equal(deletedWire.wires.find(item => item.id === "W1").return_wire_id, undefined);
assert.deepEqual(deletedWire.wires.find(item => item.id === "W1").electrical, original.wires[0].electrical, "wire delete keeps unrelated electrical fields");
assert.deepEqual(deletedWire.cables[0].wire_ids, ["W1"]);
assert.deepEqual(deletedWire.pairs, []);
const changedReturnRole = model.setHarnessWireRole(original, "W2", "other");
assert.equal(changedReturnRole.wires.find(item => item.id === "W1").return_wire_id, undefined, "changing a return role clears references that would become invalid");
assert.deepEqual(changedReturnRole.wires.find(item => item.id === "W2").color, "black");

const candidates = model.pairCandidateWires(original, "W1");
assert.deepEqual(candidates.map(item => item.id), ["W2"], "pair candidates require the same connector span and cable membership");
const differential = model.assignHarnessPair({ ...original, pairs: [] }, "W1", "W2", "differential", { twisted: true, twistPitchMm: 18 });
assert.equal(differential.pairs[0].kind, "differential");
assert.deepEqual(differential.pairs[0].wire_ids, ["W1", "W2"], "differential order retains selected + then selected mate −");
assert.equal(differential.wires.find(item => item.id === "W1").role, "signal");
assert.equal(differential.wires.find(item => item.id === "W2").role, "signal");
assert.equal(differential.wires.find(item => item.id === "W1").return_wire_id, undefined);
assert.equal(differential.pairs[0].twist_pitch_mm, 18);
const converted = model.assignHarnessPair(original, "W1", "W2", "differential", { twisted: false });
assert.deepEqual(converted.pairs[0].extensions, { reviewed: true }, "editing pair membership preserves extension metadata");
assert.equal(converted.pairs[0].twist_pitch_mm, undefined, "untwisted differential pairs do not retain stale pitch");
assert.deepEqual(converted.wires[0].electrical, original.wires[0].electrical, "pair edits preserve wire electrical data");
assert.throws(() => model.assignHarnessPair(original, "W1", "W3", "twisted"), /same connectors and cable assignment/);

assert.equal(model.nextHarnessId("J", ["J1", "J2", "J4"]), "J3");
const added = model.addHarnessWire(original, "W4", endpoint("J2", "A"), endpoint("J3", "1"));
assert.equal(added.wires.at(-1).id, "W4");
assert.deepEqual(added.wires[0], original.wires[0], "add keeps existing wire route, electrical and provenance fields");
assert.throws(() => model.addHarnessWire(original, "W4", endpoint("J2", "missing"), endpoint("J3", "1")), /existing connector pins/);

const branchHarness = {
  ...original,
  splices: [{ id: "S1", part_number: "SPLICE-3", extensions: { source: "reviewed" } }],
  wires: [
    { id: "W_FEED", from: endpoint("J1", "1"), to: { splice: "S1" }, role: "power", electrical: { resistance_ohm: .01 } },
    { id: "W_BRANCH_A", from: { splice: "S1" }, to: endpoint("J2", "A"), role: "power" },
    { id: "W_BRANCH_B", from: { splice: "S1" }, to: endpoint("J3", "1"), role: "power" },
    wire("W_KEEP", "2", "B", { role: "return", extensions: { keep: true } }),
  ],
  pairs: [{ id: "PAIR_BRANCH", wire_ids: ["W_FEED", "W_BRANCH_A"], kind: "twisted", twisted: true }],
  cables: [{ id: "C_BRANCH", wire_ids: ["W_FEED", "W_BRANCH_A", "W_BRANCH_B", "W_KEEP"], properties: { keep: true } }],
  extensions: { "spike.harness-pi": {
    ground: { splice: "S1" },
    terminals: [{ id: "load", positive: { splice: "S1" }, negative: endpoint("J1", "2") }],
    contacts: [{ id: "contact", from: { splice: "S1" }, to: endpoint("J2", "B") }],
  } },
};
const branchProjection = model.buildHarnessDiagram(branchHarness);
assert.equal(branchProjection.nodes.find(item => item.kind === "splice")?.id, "S1", "retained splice is a first-class diagram node");
assert.equal(branchProjection.wires.filter(item => !item.unresolved).length, 4, "feed and both branches resolve through the splice");
assert.deepEqual(branchProjection.diagnostics, []);
const renamedSplice = model.renameHarnessSplice(branchHarness, "S1", "S_MAIN");
assert.equal(renamedSplice.wires[0].to.splice, "S_MAIN");
assert.equal(renamedSplice.extensions["spike.harness-pi"].ground.splice, "S_MAIN");
assert.deepEqual(renamedSplice.splices[0].extensions, { source: "reviewed" });
const withoutSplice = model.deleteHarnessSplice(branchHarness, "S1");
assert.deepEqual(withoutSplice.wires.map(item => item.id), ["W_KEEP"], "splice delete cascades the feed and both branch wires");
assert.deepEqual(withoutSplice.pairs, [], "splice delete removes invalid pair membership");
assert.deepEqual(withoutSplice.cables[0].wire_ids, ["W_KEEP"], "splice delete prunes cable membership without deleting retained wires");
assert.deepEqual(withoutSplice.wires[0].extensions, { keep: true });
assert.equal(withoutSplice.extensions["spike.harness-pi"].ground, undefined);
assert.deepEqual(withoutSplice.extensions["spike.harness-pi"].terminals, []);
assert.deepEqual(withoutSplice.extensions["spike.harness-pi"].contacts, []);
const withNewSplice = model.addHarnessSplice(original, "S2");
assert.deepEqual(withNewSplice.splices, [{ id: "S2" }]);
assert.throws(() => model.addHarnessWire(branchHarness, "W_BAD", { splice: "S1" }, { splice: "S1" }), /different endpoints/);
const unsupportedProjection = model.buildHarnessDiagram({ ...original, wires: [{ id: "W_UNKNOWN", from: { route: "R1" }, to: endpoint("J2", "A") }] });
assert.equal(unsupportedProjection.wires[0].unresolved, true, "unsupported endpoint geometry remains diagnostic");
assert.equal(unsupportedProjection.diagnostics.length, 1);

console.log("Harness diagram projection, splice branches, explicit wiring, safe identity edits and pair metadata passed.");
