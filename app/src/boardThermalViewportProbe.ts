// SPDX-License-Identifier: Apache-2.0
import { boardThermalViewportGrid, boardThermalCellGeometry, type BoardThermalGrid } from "./boardThermalViewport";
import { numericExtent, type NumericExtent } from "./numericRange";

export type BoardThermalLayer = {
  name: string;
  thickness_mm: number;
  depth_mm: number;
  temperatures_c: number[];
};

export type BoardThermalViewportResult = {
  grid: BoardThermalGrid;
  layers: BoardThermalLayer[];
  modelStatus: string;
  bottomSurfaceAvailable: boolean;
};

export type BoardThermalDisplaySurface = {
  temperatures_c: number[];
  layerIndex: number;
  face: "top" | "bottom" | "internal";
  /** Signed display position from the laminate midplane, in source-board mm. */
  z_mm: number;
  opacity: number;
};

export type BoardThermalCellProbe = {
  column: number;
  row: number;
  center_mm: [number, number];
  temperature_c: number;
  layer: string;
  face: BoardThermalDisplaySurface["face"];
  depth_mm: number | null;
  modelStatus: string;
};

export function boardThermalViewportResult(raw: unknown): BoardThermalViewportResult | null {
  const grid = boardThermalViewportGrid(raw);
  if (!grid || !raw || typeof raw !== "object") return null;
  const result = raw as Record<string, unknown>;
  if (typeof result.model_status !== "string" || !result.model_status) return null;
  const inputLayers = result.layer_grids;
  if (inputLayers !== undefined && !Array.isArray(inputLayers)) return null;
  const admittedLayers = Array.isArray(inputLayers) ? inputLayers : [];
  const layers: BoardThermalLayer[] = [];
  let depth = 0;
  for (const input of admittedLayers) {
    if (!input || typeof input !== "object") return null;
    const layer = input as Record<string, unknown>;
    const values = layer.temperatures_c;
    if (typeof layer.name !== "string" || !layer.name
      || typeof layer.thickness_mm !== "number" || !Number.isFinite(layer.thickness_mm) || layer.thickness_mm <= 0
      || !Array.isArray(values) || values.length !== grid.temperatures_c.length
      || !values.every(value => typeof value === "number" && Number.isFinite(value))) return null;
    layers.push({ name: layer.name, thickness_mm: layer.thickness_mm,
      depth_mm: depth + layer.thickness_mm / 2, temperatures_c: values });
    depth += layer.thickness_mm;
  }
  return { grid, layers, modelStatus: result.model_status,
    // A layered solve publishes one actual saved field per depth cell.  A
    // single plate/layer field carries no independent underside samples.
    bottomSurfaceAvailable: layers.length > 1 };
}

/** Global saved-value range used by both board-face materials and their legend. */
export function boardThermalTemperatureExtent(result: BoardThermalViewportResult): NumericExtent {
  function* savedTemperatures(): Generator<number> {
    yield* result.grid.temperatures_c;
    for (const layer of result.layers) yield* layer.temperatures_c;
  }
  return numericExtent(savedTemperatures());
}

export function boardThermalCellProbe(
  result: BoardThermalViewportResult, layerIndex: number, cellIndex: number,
  face: BoardThermalDisplaySurface["face"] = layerIndex < 0 ? "top" : "internal",
): BoardThermalCellProbe | null {
  const [nx] = result.grid.shape;
  if (!Number.isInteger(cellIndex) || cellIndex < 0 || cellIndex >= result.grid.temperatures_c.length
    || !Number.isInteger(layerIndex) || layerIndex < -1 || layerIndex >= result.layers.length) return null;
  const column = cellIndex % nx;
  const row = Math.floor(cellIndex / nx);
  const layer = layerIndex < 0 ? null : result.layers[layerIndex];
  return {
    column, row,
    center_mm: boardThermalCellGeometry(result.grid, cellIndex).center_mm,
    temperature_c: layer ? layer.temperatures_c[cellIndex] : result.grid.temperatures_c[cellIndex],
    layer: layer?.name ?? "Board plate",
    face,
    depth_mm: layer?.depth_mm ?? null,
    modelStatus: result.modelStatus,
  };
}

/** Place saved temperature fields on the physical board faces by default.
 * Internal layer planes are returned only for an explicit inspection request;
 * their offsets are display aids and do not alter the probe's saved depth.
 */
export function boardThermalDisplaySurfaces(
  result: BoardThermalViewportResult, boardThicknessMm: number,
  options: { inspectInternalLayers?: boolean; separationMm?: number; visibility?: Record<string, boolean> } = {},
): BoardThermalDisplaySurface[] {
  if (!Number.isFinite(boardThicknessMm) || boardThicknessMm <= 0) return [];
  const halfThickness = boardThicknessMm / 2;
  const visibility = options.visibility ?? {};
  const topLayer = result.layers[0];
  const bottomLayer = result.bottomSurfaceAvailable ? result.layers[result.layers.length - 1] : undefined;
  const surfaces: BoardThermalDisplaySurface[] = [];
  surfaces.push({
    temperatures_c: topLayer?.temperatures_c ?? result.grid.temperatures_c,
    layerIndex: topLayer ? 0 : -1, face: "top", z_mm: halfThickness, opacity: 0.9,
  });
  if (bottomLayer) surfaces.push({
    temperatures_c: bottomLayer.temperatures_c, layerIndex: result.layers.length - 1,
    face: "bottom", z_mm: -halfThickness, opacity: 0.9,
  });

  const separationMm = options.separationMm ?? 0;
  if (!options.inspectInternalLayers || !Number.isFinite(separationMm) || separationMm <= 0.001) return surfaces;
  result.layers.slice(1, -1).map((layer, offset) => ({ layer, index: offset + 1 }))
    .filter(({ layer }) => visibility[layer.name] !== false)
    .forEach(({ layer, index }, visibleIndex) => surfaces.push({
      temperatures_c: layer.temperatures_c, layerIndex: index, face: "internal",
      z_mm: halfThickness + (visibleIndex + 1) * separationMm, opacity: 0.68,
    }));
  return surfaces;
}
