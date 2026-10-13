// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic

export type ThermalHistorySample = { time_s: number; temperature: number };
export type ThermalHistorySeries = {
  identity: string;
  label: string;
  unit: "C" | "K";
  samples: ThermalHistorySample[];
};
export type ThermalProbeTarget = {
  cell?: { column: number; row: number; layer?: string; face?: string; center_mm?: [number, number] };
  pointMm?: [number, number];
  componentRef?: string;
  occurrenceId?: string;
  partId?: string;
};
export type ThermalProbeHistoryResult = {
  label: string;
  traces: ThermalHistorySeries[];
  unavailableReason?: string;
};

type RecordLike = Record<string, any>;
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

function orderedSamples(frames: unknown, value: (frame: RecordLike) => unknown): ThermalHistorySample[] | null {
  if (!Array.isArray(frames) || frames.length < 2 || frames.length > 1001) return null;
  const samples: ThermalHistorySample[] = [];
  let previous = -1;
  for (const candidate of frames) {
    if (!candidate || typeof candidate !== "object") return null;
    const frame = candidate as RecordLike;
    const temperature = value(frame);
    if (!finite(frame.time_s) || frame.time_s < 0 || frame.time_s <= previous || !finite(temperature)) return null;
    samples.push({ time_s: frame.time_s, temperature });
    previous = frame.time_s;
  }
  return samples;
}

/** Extract a saved board-grid cell. Layer index is the solver layer index, never a component/body proxy. */
export function boardCellThermalHistory(result: unknown, cellIndex: number, layerIndex: number): ThermalHistorySeries | null {
  if (!result || typeof result !== "object" || !Number.isInteger(cellIndex) || cellIndex < 0 ||
      !Number.isInteger(layerIndex) || layerIndex < 0) return null;
  const raw = result as RecordLike;
  if (raw.contract !== "spike/board-thermal-result/v1" || raw.status !== "completed") return null;
  const layers = Array.isArray(raw.layer_grids) && raw.layer_grids.length ? raw.layer_grids
    : raw.grid?.temperatures_c ? [{ name: "Board plate", temperatures_c: raw.grid.temperatures_c }] : [];
  if (layerIndex >= layers.length || typeof layers[layerIndex]?.name !== "string") return null;
  const count = layers[layerIndex].temperatures_c?.length;
  if (!Number.isInteger(count) || cellIndex >= count) return null;
  const samples = orderedSamples(raw.transient, frame => {
    const frameLayers = frame.layer_temperatures_c;
    return Array.isArray(frameLayers) && Array.isArray(frameLayers[layerIndex]) && frameLayers[layerIndex].length === count
      ? frameLayers[layerIndex][cellIndex] : undefined;
  });
  return samples ? { identity: `board-cell:${layerIndex}:${cellIndex}`, label: `${layers[layerIndex].name} cell ${cellIndex}`, unit: "C", samples } : null;
}

/** Match the compact solver's retained node identity. A duplicated component reference is ambiguous and withheld. */
export function componentThermalHistory(result: unknown, selector: { nodeId?: string; componentRef?: string }): ThermalHistorySeries | null {
  if (!result || typeof result !== "object") return null;
  const raw = result as RecordLike, nodes = raw.nodes;
  if (!Array.isArray(nodes) || (!selector.nodeId && !selector.componentRef)) return null;
  const matches = nodes.filter(node => node && typeof node.id === "string" && typeof node.component_ref === "string" &&
    (selector.nodeId ? node.id === selector.nodeId : node.component_ref === selector.componentRef));
  if (matches.length !== 1) return null;
  const node = matches[0];
  const samples = orderedSamples(raw.transient, frame => frame.temperatures_c && typeof frame.temperatures_c === "object"
    ? frame.temperatures_c[node.id] : undefined);
  return samples ? { identity: `component-node:${node.id}`, label: node.id === node.component_ref ? node.component_ref : `${node.component_ref} · ${node.id}`, unit: "C", samples } : null;
}

function solidFrames(result: RecordLike, nodeCount: number): RecordLike[] | null {
  const frames = result.field_result?.frames;
  if (!["spike/assembly-field-transient-result/v1", "spike/calculix-field-transient-result/v1"].includes(result.contract) ||
      result.mode !== "transient" || result.field_result?.temperature_units !== "K" || !Array.isArray(frames)) return null;
  return orderedSamples(frames, frame => Array.isArray(frame.node_temperatures_k) && frame.node_temperatures_k.length === nodeCount
    ? frame.node_temperatures_k[0] : undefined) ? frames : null;
}

function occurrenceRange(handoff: RecordLike, occurrenceId: string): [number, number] | null {
  const count = handoff.mesh?.vertices?.length;
  const traces = handoff.source_traceability;
  if (!Number.isInteger(count) || !Array.isArray(traces)) return null;
  const matches = traces.filter(trace => trace?.occurrence_id === occurrenceId);
  const range = matches.length === 1 ? matches[0].vertex_range : null;
  return Array.isArray(range) && range.length === 2 && range.every(Number.isInteger) && range[0] >= 0 && range[0] < range[1] && range[1] <= count
    ? range as [number, number] : null;
}

/** Extract one retained solid node only when the requested occurrence owns it. */
export function solidNodeThermalHistory(result: unknown, handoff: unknown, occurrenceId: string, nodeIndex: number): ThermalHistorySeries | null {
  if (!result || typeof result !== "object" || !handoff || typeof handoff !== "object" || !Number.isInteger(nodeIndex)) return null;
  const raw = result as RecordLike, geometry = handoff as RecordLike;
  const range = occurrenceRange(geometry, occurrenceId), nodeCount = geometry.mesh?.vertices?.length;
  if (!range || nodeIndex < range[0] || nodeIndex >= range[1]) return null;
  const frames = solidFrames(raw, nodeCount);
  const samples = frames && orderedSamples(frames, frame => frame.node_temperatures_k[nodeIndex]);
  return samples ? { identity: `solid-node:${occurrenceId}:${nodeIndex}`, label: `${occurrenceId} node ${nodeIndex}`, unit: "K", samples } : null;
}

/** Return exact per-node curves for a solved solid occurrence; no board field or spatial interpolation is substituted. */
export function solidBodyThermalHistories(result: unknown, handoff: unknown, occurrenceId: string): ThermalHistorySeries[] {
  if (!result || typeof result !== "object" || !handoff || typeof handoff !== "object") return [];
  const geometry = handoff as RecordLike, range = occurrenceRange(geometry, occurrenceId);
  if (!range) return [];
  const frames = solidFrames(result as RecordLike, geometry.mesh.vertices.length);
  if (!frames) return [];
  const output: ThermalHistorySeries[] = [];
  for (let nodeIndex = range[0]; nodeIndex < range[1]; nodeIndex++) {
    const samples = orderedSamples(frames, frame => frame.node_temperatures_k[nodeIndex]);
    if (!samples) return [];
    output.push({ identity: `solid-node:${occurrenceId}:${nodeIndex}`, label: `${occurrenceId} node ${nodeIndex}`, unit: "K", samples });
  }
  return output;
}

/** Resolve the saved thermal payloads currently retained by an App thermal scenario. */
export function thermalProbeHistory(scenario: unknown, target: ThermalProbeTarget): ThermalProbeHistoryResult {
  const source = scenario && typeof scenario === "object" ? scenario as RecordLike : {};
  const board = source.board_thermal_result;

  if (target.componentRef) {
    const compact = source.component_result ?? source.result;
    const matchingNodes = Array.isArray(compact?.nodes)
      ? compact.nodes.filter((node: RecordLike) => node?.component_ref === target.componentRef) : [];
    const requestedOccurrence = target.occurrenceId;
    const ownedByScenario = typeof source.board_thermal_occurrence_id === "string" && source.board_thermal_occurrence_id === requestedOccurrence;
    const ownedByNode = requestedOccurrence && matchingNodes.length > 0 && matchingNodes.every((node: RecordLike) => node.occurrence_id === requestedOccurrence);
    if (requestedOccurrence && !ownedByScenario && !ownedByNode)
      return { label: target.componentRef, traces: [], unavailableReason: "No saved compact transient for this component occurrence; an equal reference on another board is not reused." };
    const nodeIds = matchingNodes.map((node: RecordLike) => node.id);
    if (new Set(nodeIds).size !== nodeIds.length)
      return { label: target.componentRef, traces: [], unavailableReason: "The compact thermal result contains duplicate solver node identities for this component." };
    const traces = nodeIds.map((nodeId: string) => componentThermalHistory(compact, { nodeId }));
    if (traces.length && traces.every(Boolean)) return { label: target.componentRef, traces: traces as ThermalHistorySeries[] };
    return { label: target.componentRef, traces: [], unavailableReason: "No complete saved compact transient temperature exists for this component." };
  }

  const occurrenceId = target.partId ?? target.occurrenceId;
  if (occurrenceId && (Boolean(target.partId) || (!target.cell && !target.pointMm))) {
    const handoff = source.assembly_field_handoff ?? source.handoff;
    const solidResult = source.assembly_field_transient_result ?? source.field_result ?? source.result;
    const traces = solidBodyThermalHistories(solidResult, handoff, occurrenceId);
    return traces.length ? { label: occurrenceId, traces }
      : { label: occurrenceId, traces: [], unavailableReason: "This body has no retained solved solid transient; board temperatures are not substituted." };
  }

  if (target.cell || target.pointMm) {
    if (!board || typeof board !== "object") return { label: "Board temperature history", traces: [], unavailableReason: "No saved board thermal result is available." };
    if (target.occurrenceId && typeof source.board_thermal_occurrence_id === "string" && source.board_thermal_occurrence_id !== target.occurrenceId)
      return { label: "Board temperature history", traces: [], unavailableReason: "The saved board thermal result belongs to a different occurrence." };
    const grid = board.grid;
    if (!grid || !Array.isArray(grid.shape) || grid.shape.length !== 2) return { label: "Board temperature history", traces: [], unavailableReason: "The saved board result has no admitted grid." };
    let column = target.cell?.column, row = target.cell?.row;
    if ((!Number.isInteger(column) || !Number.isInteger(row)) && target.pointMm) {
      const edges = (axis: 0 | 1) => Array.isArray(axis ? grid.y_edges_mm : grid.x_edges_mm)
        ? (axis ? grid.y_edges_mm : grid.x_edges_mm)
        : Array.from({ length: grid.shape[axis] + 1 }, (_, index) => grid.origin_mm?.[axis] + index * grid.spacing_mm?.[axis]);
      const locate = (values: unknown[], point: number) => values.findIndex((edge, index) => {
        const next = values[index + 1];
        return index < values.length - 1 && finite(edge) && finite(next) && point >= edge && point <= next;
      });
      column = locate(edges(0), target.pointMm[0]); row = locate(edges(1), target.pointMm[1]);
    }
    if (!Number.isInteger(column) || !Number.isInteger(row) || column! < 0 || row! < 0 || column! >= grid.shape[0] || row! >= grid.shape[1])
      return { label: "Board temperature history", traces: [], unavailableReason: "The selected point is outside the saved board grid." };
    const layers = Array.isArray(board.layer_grids) && board.layer_grids.length ? board.layer_grids
      : board.grid?.temperatures_c ? [{ name: "Board plate", temperatures_c: board.grid.temperatures_c }] : [];
    const layerIndex = layers.length ? Math.max(0, target.cell?.layer ? layers.findIndex((layer: RecordLike) => layer?.name === target.cell!.layer) : 0) : -1;
    if (layerIndex < 0 || (target.cell?.layer && layers[layerIndex]?.name !== target.cell.layer))
      return { label: "Board temperature history", traces: [], unavailableReason: "The selected layer has no saved transient cell field." };
    const series = boardCellThermalHistory(board, row! * grid.shape[0] + column!, layerIndex);
    return series ? { label: series.label, traces: [series] }
      : { label: "Board temperature history", traces: [], unavailableReason: Array.isArray(board.transient) ? "The saved board transient does not contain this cell." : "This board result is steady state; no saved temperature history is available." };
  }

  if (occurrenceId) {
    const handoff = source.assembly_field_handoff ?? source.handoff;
    const solidResult = source.assembly_field_transient_result ?? source.field_result ?? source.result;
    const traces = solidBodyThermalHistories(solidResult, handoff, occurrenceId);
    return traces.length ? { label: occurrenceId, traces }
      : { label: occurrenceId, traces: [], unavailableReason: "This body has no retained solved solid transient; board temperatures are not substituted." };
  }
  return { label: "Temperature history", traces: [], unavailableReason: "Select a thermal cell, component, or solved solid body." };
}
