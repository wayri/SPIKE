// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { assemblyHarnessDocument, retainAssemblyHarnessDocument, ASSEMBLY_CONDUCTORS_KEY } = await importTestTypescript("assemblyHarnessConductors");
const row = { id: "loom", endpoint_a: "occ-a::J1", endpoint_b: "occ-b::J1", name: "Power and data", length_mm: 400,
  pin_map: { "1": "3", "2": "4", "3": "1", "4": "2" }, extensions: { vendor: { retained: true }, "spike.harness-routing": { route_mm: [[0,0,0],[0,5,0],[15,5,0]] } } };
const document = assemblyHarnessDocument(row);
assert.equal(document.wires.length, 4);
assert.deepEqual(document.connectors.map(c => c.board_binding.board_id), ["occ-a", "occ-b"]);
assert.equal(document.wires[0].from.pin, "1"); assert.equal(document.wires[0].to.pin, "3");
assert.equal(document.wires[0].role, undefined, "roles cannot be inferred from pin names");
document.wires[0].role = "power"; document.wires[1].role = "return";
document.wires[0].return_wire_id = document.wires[1].id;
document.wires[0].electrical = { resistance_ohm: 0.1 };
document.wires[2].role = "signal"; document.wires[3].role = "signal";
document.pairs = [{id:"data",kind:"differential",wire_ids:document.wires.slice(2).map(w=>w.id),twisted:true,twist_pitch_mm:20}];
document.connectors[0].properties = { contact_resistance_ohm: 0.02 };
document.extensions = { "spike.harness-si": { source:"explicit measured model" } };
const saved = retainAssemblyHarnessDocument(row, document);
assert.deepEqual(saved.extensions.vendor, row.extensions.vendor);
assert.deepEqual(saved.extensions["spike.harness-routing"], row.extensions["spike.harness-routing"]);
assert.deepEqual(assemblyHarnessDocument(saved), document, "complete wire/pair/contact/setup state survives assembly bridge");
document.wires[0].electrical.resistance_ohm = 20;
assert.equal(saved.extensions[ASSEMBLY_CONDUCTORS_KEY].wires[0].electrical.resistance_ohm, .1, "retained values are detached copies");
assert.throws(()=>retainAssemblyHarnessDocument(saved,{...assemblyHarnessDocument(saved),wires:[]}),/pin-map/);
assert.throws(()=>assemblyHarnessDocument({...saved,pin_map:{"1":"4"}}),/no longer match/);
assert.throws(()=>assemblyHarnessDocument({...row,pin_map:{"1":"2","2":"2"}}),/unique/);
assert.throws(()=>retainAssemblyHarnessDocument(saved,{...assemblyHarnessDocument(saved),routes:[]}),/physical routes/);
for (const corrupt of [saved.extensions[ASSEMBLY_CONDUCTORS_KEY].wires.slice(1),
  [saved.extensions[ASSEMBLY_CONDUCTORS_KEY].wires[0], ...saved.extensions[ASSEMBLY_CONDUCTORS_KEY].wires.slice(0,3)]]) {
  const broken = structuredClone(saved); broken.extensions[ASSEMBLY_CONDUCTORS_KEY].wires = corrupt;
  assert.throws(()=>assemblyHarnessDocument(broken),/no longer match/, "missing/duplicated saved conductors must not be silently regenerated");
}
console.log("Assembly harness roles, pairs, electrical values, contacts and setup survive explicit pin-map bridge.");
