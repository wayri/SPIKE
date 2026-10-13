// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const history = await importTestTypescript("thermalProbeHistory");
const board = { contract: "spike/board-thermal-result/v1", status: "completed",
  layer_grids: [{ name: "F.Cu", temperatures_c: [31, 32] }, { name: "B.Cu", temperatures_c: [29, 30] }],
  transient: [{ time_s: 0, layer_temperatures_c: [[20, 21], [20, 20]] }, { time_s: 2, layer_temperatures_c: [[31, 32], [29, 30]] }] };
assert.deepEqual(history.boardCellThermalHistory(board, 1, 0), { identity: "board-cell:0:1", label: "F.Cu cell 1", unit: "C",
  samples: [{ time_s: 0, temperature: 21 }, { time_s: 2, temperature: 32 }] });
assert.equal(history.boardCellThermalHistory(board, 2, 0), null);
const plate = { contract: "spike/board-thermal-result/v1", status: "completed",
  grid: { temperatures_c: [27, 28] }, transient: [
    { time_s: 0, layer_temperatures_c: [[20, 20]] }, { time_s: 3, layer_temperatures_c: [[27, 28]] }] };
assert.deepEqual(history.boardCellThermalHistory(plate, 1, 0)?.samples.map(sample => sample.temperature), [20, 28]);

const compact = { nodes: [{ id: "junction:u1", component_ref: "U1" }, { id: "case:u1", component_ref: "U1" }],
  transient: [{ time_s: 0, temperatures_c: { "junction:u1": 25, "case:u1": 25 } }, { time_s: 1, temperatures_c: { "junction:u1": 42, "case:u1": 35 } }] };
assert.deepEqual(history.componentThermalHistory(compact, { nodeId: "junction:u1" })?.samples.map(sample => sample.temperature), [25, 42]);
assert.equal(history.componentThermalHistory(compact, { componentRef: "U1" }), null, "duplicate component nodes require an exact node identity");
assert.equal(history.componentThermalHistory({ ...compact, transient: compact.transient.map(({ time_s }) => ({ time_s, temperatures_c: {} })) }, { nodeId: "junction:u1" }), null);

const handoff = { mesh: { vertices: Array.from({ length: 5 }, () => [0, 0, 0]) }, source_traceability: [
  { occurrence_id: "board:a", vertex_range: [0, 2] }, { occurrence_id: "part:a", vertex_range: [2, 5] }] };
const solid = { contract: "spike/assembly-field-transient-result/v1", mode: "transient", field_result: { temperature_units: "K", frames: [
  { time_s: 0, node_temperatures_k: [300, 301, 310, 311, 312] },
  { time_s: 4, node_temperatures_k: [302, 303, 330, 331, 332] },
] } };
assert.deepEqual(history.solidNodeThermalHistory(solid, handoff, "part:a", 3)?.samples.map(sample => sample.temperature), [311, 331]);
assert.equal(history.solidNodeThermalHistory(solid, handoff, "board:a", 3), null, "node ownership is occurrence specific");
assert.deepEqual(history.solidBodyThermalHistories(solid, handoff, "part:a").map(series => series.identity),
  ["solid-node:part:a:2", "solid-node:part:a:3", "solid-node:part:a:4"]);
assert.deepEqual(history.solidBodyThermalHistories(solid, handoff, "missing"), []);

// A board grid is never accepted as a compact or solved-solid body history.
assert.equal(history.componentThermalHistory(board, { componentRef: "U1" }), null);
assert.deepEqual(history.solidBodyThermalHistories(board, handoff, "part:a"), []);
assert.deepEqual(history.thermalProbeHistory({ board_thermal_result: { ...board, grid: { shape: [2, 1], origin_mm: [0, 0], spacing_mm: [1, 1] } } },
  { cell: { column: 1, row: 0, layer: "F.Cu" } }).traces[0].samples.map(sample => sample.temperature), [21, 32]);
assert.match(history.thermalProbeHistory({ board_thermal_result: { ...board, transient: undefined, grid: { shape: [2, 1] } } },
  { cell: { column: 0, row: 0, layer: "F.Cu" } }).unavailableReason, /steady state/);
const compactTraces = history.thermalProbeHistory({ component_result: compact }, { componentRef: "U1" }).traces;
assert.deepEqual(compactTraces.map(trace => trace.identity), ["component-node:junction:u1", "component-node:case:u1"]);
assert.deepEqual(compactTraces.map(trace => trace.label), ["U1 · junction:u1", "U1 · case:u1"]);
assert.match(history.thermalProbeHistory({ component_result: { ...compact, nodes: [...compact.nodes, compact.nodes[0]] } },
  { componentRef: "U1" }).unavailableReason, /duplicate solver node identities/);
const oneComponent = { nodes: [{ id: "u1", component_ref: "U1" }], transient: [
  { time_s: 0, temperatures_c: { u1: 25 } }, { time_s: 1, temperatures_c: { u1: 30 } }] };
assert.match(history.thermalProbeHistory({ component_result: oneComponent, board_thermal_occurrence_id: "board:a" },
  { componentRef: "U1", occurrenceId: "board:b", cell: { column: 0, row: 0 } }).unavailableReason, /another board/);
assert.equal(history.thermalProbeHistory({ component_result: oneComponent, board_thermal_occurrence_id: "board:a" },
  { componentRef: "U1", occurrenceId: "board:a" }).traces.length, 1);
assert.deepEqual(history.thermalProbeHistory({ assembly_field_handoff: handoff, assembly_field_transient_result: solid },
  { occurrenceId: "part:a" }).traces.map(trace => trace.identity), ["solid-node:part:a:2", "solid-node:part:a:3", "solid-node:part:a:4"]);
assert.match(history.thermalProbeHistory({ board_thermal_result: board }, { occurrenceId: "part:a" }).unavailableReason, /not substituted/);
assert.match(history.thermalProbeHistory({ board_thermal_result: { ...board, grid: { shape: [2, 1] } } },
  { partId: "part:a", cell: { column: 0, row: 0 } }).unavailableReason, /not substituted/);
assert.deepEqual(history.thermalProbeHistory({ board_thermal_result: { ...plate, grid: { ...plate.grid, shape: [2, 1], origin_mm: [0, 0], spacing_mm: [1, 1] } } },
  { cell: { column: 1, row: 0, layer: "Board plate" } }).traces[0].samples.map(sample => sample.temperature), [20, 28]);
const scopedPlate = { board_thermal_result: { ...plate, grid: { ...plate.grid, shape: [2, 1], origin_mm: [0, 0], spacing_mm: [1, 1] } }, board_thermal_occurrence_id: "board:a" };
assert.deepEqual(history.thermalProbeHistory(scopedPlate,
  { occurrenceId: "board:a", pointMm: [1.5, 0.5] }).traces[0].samples.map(sample => sample.temperature), [20, 28], "occurrence-scoped 2D point stays on board history");
assert.match(history.thermalProbeHistory(scopedPlate,
  { occurrenceId: "board:b", pointMm: [1.5, 0.5] }).unavailableReason, /different occurrence/);
assert.match(history.thermalProbeHistory({ ...scopedPlate, assembly_field_handoff: handoff, assembly_field_transient_result: solid },
  { occurrenceId: "board:a", partId: "part:a", cell: { column: 1, row: 0 } }).label, /part:a/, "part identity overrides focused board occurrence");
console.log("exact thermal cell, component-node, solid-node, and occurrence history extraction passed");
