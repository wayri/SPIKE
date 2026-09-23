import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/piPathCircuit.ts", import.meta.url), "utf8")
  .replace(/^import type .*$/gm, "");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const {
  createPiPathSegmentExtractionRequests,
  combinePiPathSegmentExtractions,
  combinePiPathPreflights,
  attachPiPathComponentBridges,
} = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);

const path = {
  contract: "spike/pi-path/v1",
  id: "power-chain",
  label: "VIN to VOUT",
  source_terminal: { net: "VIN", pad_id: "J1.1" },
  load_terminal: { net: "VOUT", pad_id: "J2.1" },
  segments: [
    { id: "s1", net: "VIN", rail_node_id: "vin" },
    { id: "s2", net: "VMID", rail_node_id: "mid" },
    { id: "s3", net: "VOUT", rail_node_id: "out" },
  ],
  transitions: [
    { id: "r1", component_ref: "R1", component_node_id: "r1", from_segment_id: "s1", to_segment_id: "s2", input_pad_id: "R1.1", output_pad_id: "R1.2", model: { primitive: "resistor", dc_resistance_ohm: 0.01 } },
    { id: "r2", component_ref: "R2", component_node_id: "r2", from_segment_id: "s2", to_segment_id: "s3", input_pad_id: "R2.1", output_pad_id: "R2.2", model: { primitive: "resistor", dc_resistance_ohm: 0.02 } },
  ],
  issues: [],
};
const pads = [
  ["J1.1", "VIN", 0], ["R1.1", "VIN", 2], ["R1.2", "VMID", 3],
  ["R2.1", "VMID", 6], ["R2.2", "VOUT", 7], ["J2.1", "VOUT", 9],
].map(([id, net_name, x]) => ({ id, net_name, at: [x, 0], layers: ["F.Cu"] }));
const request = {
  contract: "spike/analysis-request/v1",
  design: { pads, nets: [], tracks: [], vias: [], zones: [], components: [], layers: [], stackup: [] },
  spec: {
    mode: "transient",
    solver_id: "auto",
    formulation: "auto",
    sources: [{ id: "source-1", net: "VIN", voltage_v: 12, terminal_role: "source_positive" }],
    loads: [{ id: "load-1", net: "VOUT", current_a: 1, terminal_role: "load_positive" }],
    frequency_start_hz: 1e3,
    frequency_stop_hz: 1e7,
    frequency_points: 51,
    options: { pi_path: path, loop_extractions: [{ id: "unrelated" }], coupling: { enabled: true } },
  },
};

const segments = createPiPathSegmentExtractionRequests(request, path);
assert.equal(segments.length, 3);
assert.deepEqual(segments.map(item => item.request.spec.net_names), [["VIN"], ["VMID"], ["VOUT"]]);
assert.deepEqual(segments.map(item => item.request.spec.sources[0].geometry_anchor.id), ["J1.1", "R1.2", "R2.2"]);
assert.deepEqual(segments.map(item => item.request.spec.loads[0].geometry_anchor.id), ["R1.1", "R2.1", "J2.1"]);
assert.deepEqual(segments.map(item => item.request.spec.sources[0].position_mm), [[0, 0], [3, 0], [7, 0]]);
assert.ok(segments.every(item => item.request.spec.mode === "ac" && item.request.spec.solver_id === "spike.peec_2_5d"));
assert.ok(segments.every(item => !("pi_path" in item.request.spec.options)));

const extraction = (net, id) => ({
  analysis_id: id,
  model_status: "approximate",
  networks: { parasitics: [{ contract: "spike/rlgc-network/v1", net, resistance_ohm: 0.01, inductance_h: 1e-9, capacitance_f: 1e-12, conductance_s: 0 }] },
});
const combined = combinePiPathSegmentExtractions(path, [extraction("VIN", "a"), extraction("VMID", "b"), extraction("VOUT", "c")]);
assert.equal(combined.extraction_result.networks.parasitics.length, 3);
assert.deepEqual(combined.segment_mappings.map(item => [item.segment_id, item.from_pad_id, item.to_pad_id]), [
  ["s1", "J1.1", "R1.1"], ["s2", "R1.2", "R2.1"], ["s3", "R2.2", "J2.1"],
]);
assert.throws(() => combinePiPathSegmentExtractions(path, [extraction("VIN", "a")]), /Expected 3/);
assert.throws(() => combinePiPathSegmentExtractions(path, [extraction("VIN", "a"), extraction("OTHER", "b"), extraction("VOUT", "c")]), /exactly one/);

const preview = combinePiPathPreflights([
  { can_solve: true, issues: [], mesh: { cells: [{ id: 1 }] } },
  { can_solve: true, issues: [{ severity: "warning", message: "review" }], mesh: { cells: [{ id: 2 }, { id: 3 }] } },
], {
  can_solve: true,
  issues: [{ severity: "warning", message: "review" }],
  summary: { selected_geometry_count: 8 },
  mesh: {
    cells: [{ id: "full-1" }, { id: "full-2" }, { id: "full-3" }],
    component_bridges: [
      { id: "bridge-r1", kind: "line2", input_pad_id: "R1.1", output_pad_id: "R1.2", resistance_ohm: 0.01 },
      { id: "bridge-r2", kind: "line2", input_pad_id: "R2.1", output_pad_id: "R2.2", resistance_ohm: 0.02 },
    ],
  },
});
assert.equal(preview.can_solve, true);
assert.equal(preview.summary.mesh_cell_count, 3);
assert.equal(preview.summary.segment_count, 2);
assert.equal(preview.summary.component_bridge_count, 2);
assert.equal(preview.summary.selected_geometry_count, 8);
assert.deepEqual(preview.mesh.cells.map(cell => cell.id), ["full-1", "full-2", "full-3"]);
assert.deepEqual(preview.mesh.component_bridges.map(bridge => bridge.id), ["bridge-r1", "bridge-r2"]);
assert.equal(preview.issues.length, 1);

const persisted = attachPiPathComponentBridges({
  fields: { visualization: { spatial_fields_available: false } },
  provenance: { topology_inference: false },
}, preview);
assert.deepEqual(persisted.fields.visualization.component_bridges.map(bridge => bridge.id), ["bridge-r1", "bridge-r2"]);
assert.equal(persisted.fields.visualization.spatial_fields_available, false);
assert.equal(persisted.provenance.component_bridge_contract, "spike/pi-path-interface-elements/v1");
assert.equal(persisted.provenance.reviewed_component_bridge_count, 2);
assert.equal(persisted.provenance.component_bridge_spatial_field_inferred, false);

console.log("PI path circuit orchestration: all assertions passed");
