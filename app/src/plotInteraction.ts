// SPDX-License-Identifier: Apache-2.0
export type PlotRange = readonly [number, number];
export function zoomPlotRange(range: PlotRange, factor: number, fraction = .5): [number, number] {
  if (!range.every(Number.isFinite) || !Number.isFinite(factor) || factor <= 0) throw new Error("Invalid plot zoom range.");
  const anchor = range[0] + (range[1] - range[0]) * Math.max(0, Math.min(1, fraction));
  const result: [number, number] = [anchor + (range[0] - anchor) * factor, anchor + (range[1] - anchor) * factor];
  return result.every(Number.isFinite) && result[0] !== result[1] ? result : [range[0], range[1]];
}
export function panPlotRange(range: PlotRange, fraction: number): [number, number] {
  const shift = (range[1] - range[0]) * fraction;
  const result: [number, number] = [range[0] + shift, range[1] + shift];
  return result.every(Number.isFinite) ? result : [range[0], range[1]];
}
export function wheelPlotFactor(delta: number, mode: number) {
  const pixels = delta * (mode === 1 ? 16 : mode === 2 ? 240 : 1);
  return Math.exp(Math.max(-.7, Math.min(.7, pixels * .0015)));
}
