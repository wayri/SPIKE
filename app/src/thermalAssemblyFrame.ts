// SPDX-License-Identifier: Apache-2.0
import type { VirtualBoardVisual } from "./harnessVisualization";

/** Only retained identities establish ownership; names and geometry never do. */
export function thermalOccurrenceMatchesDesign(board: Pick<VirtualBoardVisual, "designId" | "sourceNativeId">, designId: string | undefined): boolean {
  return Boolean(designId && (board.designId === designId || board.sourceNativeId === designId));
}

/** A design result is not an occurrence assignment when that design is repeated. */
export function thermalResultOccurrence(boards: readonly VirtualBoardVisual[], designId?: string, occurrenceId?: string) {
  if (occurrenceId) return boards.find(board => board.id === occurrenceId && (!designId || thermalOccurrenceMatchesDesign(board, designId))) ?? null;
  const sourceDesign = designId ?? boards.find(board => board.active)?.designId;
  const matches = boards.filter(board => thermalOccurrenceMatchesDesign(board, sourceDesign));
  return matches.length === 1 ? matches[0] : null;
}

/** Native source-board millimetres to native assembly millimetres; no viewport scale. */
export function thermalAssemblyPoint(point: readonly [number, number, number], transform: readonly number[]): [number, number, number] {
  return [0, 1, 2].map(row => transform[row * 4] * point[0] + transform[row * 4 + 1] * point[1]
    + transform[row * 4 + 2] * point[2] + transform[row * 4 + 3]) as [number, number, number];
}

/** Map board-centred viewport coordinates through the native occurrence frame.
 * Transform the complete frame so cell planes, normals and picking agree.
 */
export function thermalOverlayTransform(board: VirtualBoardVisual, center: readonly [number, number], scale: number, midplaneMm: number, explodeMm = 0): number[] {
  const map = (x: number, y: number, z: number) => {
    const p = thermalAssemblyPoint([x / scale + center[0], center[1] - y / scale, z / scale + midplaneMm], board.transform);
    return [(p[0] - center[0]) * scale, (center[1] - p[1]) * scale, (p[2] + explodeMm) * scale];
  };
  const origin = map(0, 0, 0), x = map(1, 0, 0), y = map(0, 1, 0), z = map(0, 0, 1);
  return [x[0] - origin[0], y[0] - origin[0], z[0] - origin[0], origin[0],
    x[1] - origin[1], y[1] - origin[1], z[1] - origin[1], origin[1],
    x[2] - origin[2], y[2] - origin[2], z[2] - origin[2], origin[2], 0, 0, 0, 1];
}

/** Enclose all rotated board envelopes in the existing centred XY, Z>=0 domain.
 * A negative Z extent cannot be represented by that contract and is reported.
 * This is a geometry convenience, never a thermal solve or a case mutation.
 */
export function fitThermalAssemblyVolume(boards: readonly VirtualBoardVisual[], center: readonly [number, number], paddingMm = 5) {
  if (!boards.length || !center.every(Number.isFinite) || !Number.isFinite(paddingMm) || paddingMm < 0) return null;
  const minimum = [Infinity, Infinity, Infinity], maximum = [-Infinity, -Infinity, -Infinity];
  for (const board of boards) {
    if (board.transform.length !== 16 || !board.transform.every(Number.isFinite)
      || !board.localCenterMm.every(Number.isFinite)
      || ![board.widthMm, board.heightMm, board.thicknessMm ?? 1.6].every(value => Number.isFinite(value) && value > 0)) return null;
    for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) {
      const point = thermalAssemblyPoint([
        board.localCenterMm[0] + x * board.widthMm / 2,
        board.localCenterMm[1] + y * board.heightMm / 2,
        // Native KiCad laminate runs upward from Z=0; localCenterMm is
        // the XY recentering anchor, not the laminate midplane.
        (z + 1) * (board.thicknessMm ?? 1.6) / 2,
      ], board.transform);
      point.forEach((value, axis) => { minimum[axis] = Math.min(minimum[axis], value); maximum[axis] = Math.max(maximum[axis], value); });
    }
  }
  return {
    volume: {
      x: Math.ceil(2 * (Math.max(Math.abs(minimum[0] - center[0]), Math.abs(maximum[0] - center[0])) + paddingMm)),
      y: Math.ceil(2 * (Math.max(Math.abs(minimum[1] - center[1]), Math.abs(maximum[1] - center[1])) + paddingMm)),
      z: Math.ceil(Math.max(1, maximum[2] + paddingMm)),
    },
    minimum, maximum, extendsBelowDomain: minimum[2] < -0.001,
  };
}
