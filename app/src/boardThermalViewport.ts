// SPDX-License-Identifier: Apache-2.0
import { thermalFieldColor } from "./thermalResultFields";

export type BoardThermalGrid = {
  origin_mm: [number, number];
  spacing_mm?: [number, number];
  x_edges_mm?: number[];
  y_edges_mm?: number[];
  shape: [number, number];
  temperatures_c: number[];
};

export function boardThermalViewportGrid(raw: unknown): BoardThermalGrid | null {
  if (!raw || typeof raw !== "object") return null;
  const result = raw as Record<string, unknown>;
  if (result.contract !== "spike/board-thermal-result/v1" || result.status !== "completed") return null;
  const grid = result.grid as Record<string, unknown> | undefined;
  if (!grid || grid.order !== "x-fast" || !Array.isArray(grid.origin_mm)
    || !Array.isArray(grid.shape) || !Array.isArray(grid.temperatures_c)) return null;
  const [nx, ny] = grid.shape;
  if (!Number.isInteger(nx) || !Number.isInteger(ny) || nx < 1 || ny < 1 || nx * ny > 8192
    || grid.origin_mm.length !== 2 || grid.temperatures_c.length !== nx * ny
    || !grid.origin_mm.every(Number.isFinite)
    || !grid.temperatures_c.every(Number.isFinite)) return null;
  if (grid.x_edges_mm !== undefined || grid.y_edges_mm !== undefined) {
    if (grid.spacing_mm !== undefined) return null;
    for (const [edges, count, origin] of [[grid.x_edges_mm, nx, grid.origin_mm[0]], [grid.y_edges_mm, ny, grid.origin_mm[1]]] as const) {
      if (!Array.isArray(edges) || edges.length !== count + 1 || edges[0] !== origin
        || !edges.every((value: unknown, index: number) => typeof value === 'number' && Number.isFinite(value)
          && (index === 0 || (Number.isFinite(value - edges[index - 1]) && value - edges[index - 1] >= 1e-6)))) return null;
    }
  } else if (!Array.isArray(grid.spacing_mm) || grid.spacing_mm.length !== 2
    || !grid.spacing_mm.every((value: number) => Number.isFinite(value) && value > 0)
    || ![0, 1].every(axis => Number.isFinite((grid.origin_mm as number[])[axis] + (grid.shape as number[])[axis] * (grid.spacing_mm as number[])[axis]))) return null;
  return grid as BoardThermalGrid;
}

export function boardThermalAxisEdges(grid: BoardThermalGrid, axis: 0 | 1): number[] {
  return (axis === 0 ? grid.x_edges_mm : grid.y_edges_mm)
    ?? Array.from({ length: grid.shape[axis] + 1 }, (_, i) => grid.origin_mm[axis] + i * grid.spacing_mm![axis]);
}

export function boardThermalCellGeometry(grid: BoardThermalGrid, index: number) {
  const x = index % grid.shape[0], y = Math.floor(index / grid.shape[0]);
  const x0 = grid.x_edges_mm?.[x] ?? grid.origin_mm[0] + x * grid.spacing_mm![0];
  const x1 = grid.x_edges_mm?.[x + 1] ?? x0 + grid.spacing_mm![0];
  const y0 = grid.y_edges_mm?.[y] ?? grid.origin_mm[1] + y * grid.spacing_mm![1];
  const y1 = grid.y_edges_mm?.[y + 1] ?? y0 + grid.spacing_mm![1];
  return { center_mm: [(x0 + x1) / 2, (y0 + y1) / 2] as [number, number],
    size_mm: [x1 - x0, y1 - y0] as [number, number] };
}

export function boardThermalCellColor(value: number, minimum: number, maximum: number): string {
  const [red, green, blue] = thermalFieldColor(value, minimum, maximum);
  return `rgb(${Math.round(red * 255)},${Math.round(green * 255)},${Math.round(blue * 255)})`;
}

export function boardThermalCuts(grid: BoardThermalGrid, position: [number, number], layers?: Array<{ thickness_mm: number; temperatures_c: number[] }>) {
  const [nx, ny] = grid.shape;
  const xe = boardThermalAxisEdges(grid, 0), ye = boardThermalAxisEdges(grid, 1);
  const containing = (edges: number[], value: number) => {
    let low = 0, high = edges.length - 1;
    while (high - low > 1) { const mid = Math.floor((low + high) / 2); if (value < edges[mid]) high = mid; else low = mid; }
    return Math.min(edges.length - 2, low);
  };
  const column = containing(xe, position[0]), row = containing(ye, position[1]);
  const horizontal = Array.from({ length: nx }, (_, x) => [(xe[x] + xe[x + 1]) / 2, grid.temperatures_c[row * nx + x]] as [number, number]);
  const vertical = Array.from({ length: ny }, (_, y) => [(ye[y] + ye[y + 1]) / 2, grid.temperatures_c[y * nx + column]] as [number, number]);
  let depth = 0;
  const throughStack = layers?.filter(layer => Number.isFinite(layer.thickness_mm) && layer.thickness_mm > 0 && layer.temperatures_c.length === nx * ny)
    .map(layer => { const point: [number, number] = [depth + layer.thickness_mm / 2, layer.temperatures_c[row * nx + column]]; depth += layer.thickness_mm; return point; }) ?? [];
  return { column, row, horizontal, vertical, throughStack };
}
