// SPDX-License-Identifier: Apache-2.0
import type { ParsedBoard, Point } from "./boardTypes";
import type { VirtualBoardVisual, VirtualHarnessVisual } from "./harnessVisualization";

export type AssemblyViewBox = { x: number; y: number; width: number; height: number };

export function projectAssemblyPoint(transform: readonly number[], point: readonly [number, number, number?]): [number, number, number] {
  const [x, y, z = 0] = point;
  return [transform[0] * x + transform[1] * y + transform[2] * z + transform[3], transform[4] * x + transform[5] * y + transform[6] * z + transform[7], transform[8] * x + transform[9] * y + transform[10] * z + transform[11]];
}

/** SVG's six-value matrix uses the first two rows of the row-major assembly transform. */
export function assemblySvgMatrix(transform: readonly number[]): string {
  return `matrix(${transform[0]} ${transform[4]} ${transform[1]} ${transform[5]} ${transform[3]} ${transform[7]})`;
}

export function assemblyBoardBounds(visual: VirtualBoardVisual, board: ParsedBoard): AssemblyViewBox {
  const source = board.bounds;
  const projected = ([[source.minX, source.minY], [source.maxX, source.minY], [source.maxX, source.maxY], [source.minX, source.maxY]] as Point[]).map(point => projectAssemblyPoint(visual.transform, point));
  let x = Infinity, y = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const point of projected) { x = Math.min(x, point[0]); y = Math.min(y, point[1]); maxX = Math.max(maxX, point[0]); maxY = Math.max(maxY, point[1]); }
  return { x, y, width: maxX - x, height: maxY - y };
}

export function harnessAssemblyPoints(harness: VirtualHarnessVisual): readonly (readonly [number, number, number])[] {
  return harness.routeMm.length >= 2 ? harness.routeMm : [harness.endpointA.positionMm, harness.endpointB.positionMm];
}

export function assemblyContentBounds(visuals: readonly VirtualBoardVisual[], designs: Readonly<Record<string, ParsedBoard>>, harnesses: readonly VirtualHarnessVisual[] = []): AssemblyViewBox {
  const points: Point[] = [];
  for (const visual of visuals) {
    const board = designs[visual.designId];
    if (!board) continue;
    const bounds = assemblyBoardBounds(visual, board);
    points.push([bounds.x, bounds.y], [bounds.x + bounds.width, bounds.y + bounds.height]);
  }
  for (const harness of harnesses) for (const point of harnessAssemblyPoints(harness)) points.push([point[0], point[1]]);
  if (!points.length) return { x: -5, y: -5, width: 10, height: 10 };
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const point of points) { minX = Math.min(minX, point[0]); minY = Math.min(minY, point[1]); maxX = Math.max(maxX, point[0]); maxY = Math.max(maxY, point[1]); }
  const margin = Math.max(2, Math.max(maxX - minX, maxY - minY) * 0.06);
  return { x: minX - margin, y: minY - margin, width: Math.max(maxX - minX + margin * 2, 1), height: Math.max(maxY - minY + margin * 2, 1) };
}

export function boardAssemblyZ(visual: VirtualBoardVisual): number {
  return projectAssemblyPoint(visual.transform, visual.localCenterMm)[2];
}

/** Parsed objects carry names; assembly selection carries stable canonical IDs. */
export function canonicalNetId(board: ParsedBoard, nameToId: Readonly<Record<string, string>> | undefined, parsedNetName: string | undefined): string | null {
  if (!parsedNetName) return null;
  if (nameToId?.[board.nets[parsedNetName] ?? parsedNetName]) return nameToId[board.nets[parsedNetName] ?? parsedNetName];
  return Object.entries(board.nets).find(([, name]) => name === parsedNetName)?.[0] ?? parsedNetName;
}
