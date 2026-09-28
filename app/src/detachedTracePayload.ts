// SPDX-License-Identifier: Apache-2.0

import type { MeshCell, ScalarSample, SolverResultBundle, VectorSample } from "./analysisResults";

export const MAX_DETACHED_TRACE_SAMPLES = 100_000;
export const MAX_DETACHED_TRACE_MESH_CELLS = 5_000;
export const MAX_DETACHED_IMPEDANCE_POINTS = 50_000;
const MAX_VERTICES_PER_ITEM = 256;

export type DetachedTracePayload = {
  domain: "pi" | "si";
  result: SolverResultBundle | null;
  targetNet?: string;
  targetOhm?: number;
  notice: string;
  shownSamples: number;
  totalSamples: number;
};

function deterministicSelection<T>(items: readonly T[], budget: number): T[] {
  if (items.length <= budget) return [...items];
  if (budget <= 1) return budget ? [items[0]] : [];
  const selected: T[] = [];
  for (let index = 0; index < budget; index++) selected.push(items[Math.round(index * (items.length - 1) / (budget - 1))]);
  return selected;
}

const boundedVertices = (vertices: [number, number, number][] | undefined) =>
  vertices && vertices.length <= MAX_VERTICES_PER_ITEM ? vertices.map(vertex => [...vertex] as [number, number, number]) : undefined;

const scalar = (sample: ScalarSample): ScalarSample => ({ ...sample, vertices_mm: boundedVertices(sample.vertices_mm) });
const vector = (sample: VectorSample): VectorSample => ({ ...scalar(sample), vector: [...sample.vector], magnitude: sample.magnitude });
const mesh = (cell: MeshCell): MeshCell | null => {
  const vertices = boundedVertices(cell.vertices_mm);
  return vertices ? { ...cell, vertices_mm: vertices } : null;
};

export function buildDetachedTracePayload(result: SolverResultBundle | null, domain: "pi" | "si", targetNet?: string, targetOhm?: number): DetachedTracePayload {
  if (!result) return { domain, result: null, notice: "No completed analysis result.", shownSamples: 0, totalSamples: 0 };
  const scalarEntries = Object.entries(result.scalar_fields) as Array<[keyof SolverResultBundle["scalar_fields"], ScalarSample[]]>;
  const vectorEntries = Object.entries(result.vector_fields) as Array<[keyof SolverResultBundle["vector_fields"], VectorSample[]]>;
  const totalSamples = scalarEntries.reduce((sum, [, items]) => sum + items.length, 0) + vectorEntries.reduce((sum, [, items]) => sum + items.length, 0);
  const groups = [...scalarEntries.map(entry => ({ type: "scalar" as const, entry })), ...vectorEntries.map(entry => ({ type: "vector" as const, entry }))];
  const allocations = groups.map(group => totalSamples <= MAX_DETACHED_TRACE_SAMPLES
    ? group.entry[1].length
    : group.entry[1].length ? Math.max(1, Math.floor(MAX_DETACHED_TRACE_SAMPLES * group.entry[1].length / totalSamples)) : 0);
  let allocated = allocations.reduce((sum, value) => sum + value, 0);
  for (let index = 0; allocated < Math.min(totalSamples, MAX_DETACHED_TRACE_SAMPLES); index = (index + 1) % groups.length) {
    if (allocations[index] < groups[index].entry[1].length) { allocations[index] += 1; allocated += 1; }
  }
  while (allocated > MAX_DETACHED_TRACE_SAMPLES) {
    const index = allocations.findIndex(value => value > 1);
    if (index < 0) break;
    allocations[index] -= 1; allocated -= 1;
  }
  let allocationIndex = 0;
  const boundedScalars = Object.fromEntries(scalarEntries.map(([key, items]) => [key, deterministicSelection(items, allocations[allocationIndex++]).map(scalar)])) as SolverResultBundle["scalar_fields"];
  const boundedVectors = Object.fromEntries(vectorEntries.map(([key, items]) => [key, deterministicSelection(items, allocations[allocationIndex++]).map(vector)])) as SolverResultBundle["vector_fields"];
  const shownSamples = allocated;
  const boundedMesh = deterministicSelection(result.mesh, MAX_DETACHED_TRACE_MESH_CELLS).map(mesh).filter((item): item is MeshCell => item !== null);
  const totalImpedance = result.parasitics.reduce((sum, item) => sum + (item.impedance?.length ?? 0), 0);
  let impedanceRemaining = MAX_DETACHED_IMPEDANCE_POINTS;
  let networksLeft = result.parasitics.length;
  const boundedParasitics = result.parasitics.map(item => {
    const points = item.impedance ?? [];
    const budget = Math.min(points.length, networksLeft ? Math.floor(impedanceRemaining / networksLeft) : 0);
    networksLeft -= 1; impedanceRemaining -= budget;
    return { ...item, parameter_availability: undefined, network_uses: undefined, impedance: deterministicSelection(points, budget) };
  });
  const shownImpedance = MAX_DETACHED_IMPEDANCE_POINTS - impedanceRemaining;
  const bounded: SolverResultBundle = {
    ...result,
    // Keep the admission decision when stripping large result metadata. A
    // detached plot must not resurrect partial fields from a rejected solve.
    summary: result.summary?.solved === false ? { solved: false } : {},
    provenance: {
      ...(result.provenance?.solved === false ? { solved: false } : {}),
      ...(typeof result.provenance?.failure_stage === "string"
        ? { failure_stage: result.provenance.failure_stage.slice(0, 128) } : {}),
    },
    scalar_fields: boundedScalars,
    vector_fields: boundedVectors,
    mesh: boundedMesh,
    parasitics: boundedParasitics,
    component_bridges: [], pdn_multiports: [], loop_parasitics: [], coupling_risks: [], component_stress: [], probes: [], issues: [],
    time_series: { times_s: [], frames: [] },
  };
  const omitted = totalSamples - shownSamples;
  const meshOmitted = result.mesh.length - boundedMesh.length;
  const notice = omitted || meshOmitted || shownImpedance < totalImpedance
    ? `Display-only payload: ${shownSamples} of ${totalSamples} field samples, ${boundedMesh.length} of ${result.mesh.length} mesh cells, and ${shownImpedance} of ${totalImpedance} impedance points. Export and saved results retain the authoritative full result.`
    : `Display-only payload contains all ${totalSamples} field samples, ${boundedMesh.length} mesh cells, and ${shownImpedance} impedance points.`;
  return { domain, result: bounded, notice, shownSamples, totalSamples,
    ...(domain === "pi" && typeof targetNet === "string" && targetNet.length <= 256
      && Number.isFinite(targetOhm) && Number(targetOhm) > 0
      ? { targetNet, targetOhm } : {}) };
}

export function normalizeDetachedTracePayload(value: unknown): DetachedTracePayload | undefined {
  if (!value || typeof value !== "object") return undefined;
  const source = value as Partial<DetachedTracePayload>;
  if (source.domain !== "pi" && source.domain !== "si") return undefined;
  const bounded = buildDetachedTracePayload(source.result ?? null, source.domain, source.targetNet, source.targetOhm);
  if (typeof source.notice === "string") bounded.notice = source.notice.slice(0, 512);
  if (Number.isSafeInteger(source.totalSamples) && Number(source.totalSamples) >= bounded.shownSamples) bounded.totalSamples = Number(source.totalSamples);
  return bounded;
}
