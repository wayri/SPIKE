// SPDX-License-Identifier: Apache-2.0
import { thermalFieldColor } from "./thermalResultFields";

export type BoardThermalGrid = {
  origin_mm: [number, number];
  spacing_mm: [number, number];
  shape: [number, number];
  temperatures_c: number[];
};

export function boardThermalViewportGrid(raw: unknown): BoardThermalGrid | null {
  if (!raw || typeof raw !== "object") return null;
  const result = raw as Record<string, unknown>;
  if (result.contract !== "spike/board-thermal-result/v1" || result.status !== "completed") return null;
  const grid = result.grid as Record<string, unknown> | undefined;
  if (!grid || grid.order !== "x-fast" || !Array.isArray(grid.origin_mm) || !Array.isArray(grid.spacing_mm)
    || !Array.isArray(grid.shape) || !Array.isArray(grid.temperatures_c)) return null;
  const [nx, ny] = grid.shape;
  if (!Number.isInteger(nx) || !Number.isInteger(ny) || nx < 1 || ny < 1 || nx * ny > 8192
    || grid.origin_mm.length !== 2 || grid.spacing_mm.length !== 2 || grid.temperatures_c.length !== nx * ny
    || !grid.origin_mm.every(Number.isFinite) || !grid.spacing_mm.every((value: number) => Number.isFinite(value) && value > 0)
    || !grid.temperatures_c.every(Number.isFinite)) return null;
  return grid as BoardThermalGrid;
}

export function boardThermalCellColor(value: number, minimum: number, maximum: number): string {
  const [red, green, blue] = thermalFieldColor(value, minimum, maximum);
  return `rgb(${Math.round(red * 255)},${Math.round(green * 255)},${Math.round(blue * 255)})`;
}

export function boardThermalCuts(grid: BoardThermalGrid, position: [number, number], layers?: Array<{ thickness_mm: number; temperatures_c: number[] }>) {
  const [nx, ny] = grid.shape;
  const column = Math.max(0, Math.min(nx - 1, Math.floor((position[0] - grid.origin_mm[0]) / grid.spacing_mm[0])));
  const row = Math.max(0, Math.min(ny - 1, Math.floor((position[1] - grid.origin_mm[1]) / grid.spacing_mm[1])));
  const horizontal = Array.from({ length: nx }, (_, x) => [grid.origin_mm[0] + (x + 0.5) * grid.spacing_mm[0], grid.temperatures_c[row * nx + x]] as [number, number]);
  const vertical = Array.from({ length: ny }, (_, y) => [grid.origin_mm[1] + (y + 0.5) * grid.spacing_mm[1], grid.temperatures_c[y * nx + column]] as [number, number]);
  let depth = 0;
  const throughStack = layers?.filter(layer => Number.isFinite(layer.thickness_mm) && layer.thickness_mm > 0 && layer.temperatures_c.length === nx * ny)
    .map(layer => { const point: [number, number] = [depth + layer.thickness_mm / 2, layer.temperatures_c[row * nx + column]]; depth += layer.thickness_mm; return point; }) ?? [];
  return { column, row, horizontal, vertical, throughStack };
}
