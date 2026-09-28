// SPDX-License-Identifier: Apache-2.0
import { boardThermalViewportGrid, type BoardThermalGrid } from "./boardThermalViewport";

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
};

export type BoardThermalCellProbe = {
  column: number;
  row: number;
  center_mm: [number, number];
  temperature_c: number;
  layer: string;
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
  const layers: BoardThermalLayer[] = [];
  let depth = 0;
  for (const input of inputLayers ?? []) {
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
  return { grid, layers, modelStatus: result.model_status };
}

export function boardThermalCellProbe(
  result: BoardThermalViewportResult, layerIndex: number, cellIndex: number,
): BoardThermalCellProbe | null {
  const [nx] = result.grid.shape;
  if (!Number.isInteger(cellIndex) || cellIndex < 0 || cellIndex >= result.grid.temperatures_c.length
    || !Number.isInteger(layerIndex) || layerIndex < -1 || layerIndex >= result.layers.length) return null;
  const column = cellIndex % nx;
  const row = Math.floor(cellIndex / nx);
  const layer = layerIndex < 0 ? null : result.layers[layerIndex];
  return {
    column, row,
    center_mm: [
      result.grid.origin_mm[0] + (column + 0.5) * result.grid.spacing_mm[0],
      result.grid.origin_mm[1] + (row + 0.5) * result.grid.spacing_mm[1],
    ],
    temperature_c: layer ? layer.temperatures_c[cellIndex] : result.grid.temperatures_c[cellIndex],
    layer: layer?.name ?? "Top surface",
    depth_mm: layer?.depth_mm ?? null,
    modelStatus: result.modelStatus,
  };
}
