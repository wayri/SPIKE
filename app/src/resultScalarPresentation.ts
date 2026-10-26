// SPDX-License-Identifier: Apache-2.0
import type { ScalarSample, SolverResultBundle } from "./analysisResults";
import { resultDatumLayers, resultLayerMatchesSelection } from "./resultLayerSelection";

export type ResultScalarPresentation = {
  samples: ScalarSample[];
  sortedFiniteValues: number[];
  minimum: number | undefined;
  maximum: number | undefined;
  mean: number | undefined;
  p95: number | undefined;
  hotspots: ScalarSample[];
};

const cache = new WeakMap<ScalarSample[], Map<string, ResultScalarPresentation>>();
const layerInventoryCache = new WeakMap<SolverResultBundle, Map<string, string[]>>();
const MAX_LAYER_SELECTIONS_PER_FIELD = 8;

/**
 * Preserves the Results panel's exact filtering and stable sort semantics while
 * reusing the immutable solver field summary across unrelated UI updates.
 */
export function resultScalarPresentation(
  source: ScalarSample[],
  selectedLayers: string[],
  boardLayers: string[],
): ResultScalarPresentation {
  const key = JSON.stringify([selectedLayers, boardLayers]);
  let entries = cache.get(source);
  const cached = entries?.get(key);
  if (cached) {
    entries!.delete(key);
    entries!.set(key, cached);
    return cached;
  }

  const samples = source.filter(sample => resultLayerMatchesSelection(sample.layer, selectedLayers, boardLayers));
  const sortedFiniteValues = samples.map(sample => sample.value).filter(Number.isFinite).sort((left, right) => left - right);
  const minimum = sortedFiniteValues[0];
  const maximum = sortedFiniteValues.length ? sortedFiniteValues[sortedFiniteValues.length - 1] : undefined;
  const mean = sortedFiniteValues.length
    ? sortedFiniteValues.reduce((sum, value) => sum + value, 0) / sortedFiniteValues.length
    : undefined;
  const p95 = sortedFiniteValues.length
    ? sortedFiniteValues[Math.min(sortedFiniteValues.length - 1, Math.floor(sortedFiniteValues.length * 0.95))]
    : undefined;
  const value = {
    samples, sortedFiniteValues, minimum, maximum, mean, p95,
    hotspots: [...samples].sort((left, right) => right.value - left.value).slice(0, 12),
  };
  if (!entries) { entries = new Map(); cache.set(source, entries); }
  entries.set(key, value);
  while (entries.size > MAX_LAYER_SELECTIONS_PER_FIELD) entries.delete(entries.keys().next().value!);
  return value;
}

/** Reuses the exact layer inventory while the immutable result bundle is active. */
export function resultLayerInventory(result: SolverResultBundle | null, activeScalars: ScalarSample[], boardLayers: string[]): string[] {
  if (!result) return [];
  const activeField = Object.entries(result.scalar_fields).find(([, samples]) => samples === activeScalars)?.[0] ?? "none";
  const key = JSON.stringify([activeField, boardLayers]);
  let entries = layerInventoryCache.get(result);
  const cached = entries?.get(key);
  if (cached) return cached;
  const layers = [...new Set([
    ...activeScalars.flatMap(sample => resultDatumLayers(sample.layer, boardLayers)),
    ...result.mesh.flatMap(cell => resultDatumLayers(cell.layer, boardLayers)),
    ...result.vector_fields.current_density.flatMap(sample => resultDatumLayers(sample.layer, boardLayers)),
    ...result.vector_fields.electric_field.flatMap(sample => resultDatumLayers(sample.layer, boardLayers)),
    ...result.vector_fields.magnetic_field.flatMap(sample => resultDatumLayers(sample.layer, boardLayers)),
  ].filter(layer => Boolean(layer) && layer !== "through"))]
    .sort((left, right) => boardLayers.indexOf(left) - boardLayers.indexOf(right));
  if (!entries) { entries = new Map(); layerInventoryCache.set(result, entries); }
  entries.set(key, layers);
  return layers;
}
