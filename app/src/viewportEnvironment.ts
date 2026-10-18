// SPDX-License-Identifier: Apache-2.0
export type ViewportBackground = "dark" | "light" | "amoled";
export function viewportBackgroundColor(mode: ViewportBackground): string {
  return mode === "amoled" ? "#000000" : mode === "light" ? "#edf2f4" : "#0b141a";
}
/** Display-only ground plane; it never contributes to camera fit or picking. */
export function worldGridSize(width: number, height: number): number {
  const extent = Math.max(Number.isFinite(width) && width > 0 ? width : 0, Number.isFinite(height) && height > 0 ? height : 0, 40);
  return Math.min(extent * 4, 100000);
}
