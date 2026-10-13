// SPDX-License-Identifier: Apache-2.0
import { plotAxisLabel, type PlotTrace } from './plotClipboard';
export type PlotProbe = { trace: string; index: number; x: number; y: number; xLabel: string; yLabel: string; xaxis: string; yaxis: string; comparison: boolean };
const axisKey = (ref: unknown, coordinate: string) => typeof ref === 'string' && new RegExp(`^${coordinate}\\d*$`).test(ref) ? `${coordinate}axis${ref.slice(1)}` : `${coordinate}axis`;
const label = (value: unknown, fallback: string) => (plotAxisLabel(value).replace(/<[^>]*>/g, '').trim() || fallback);
/** Pin exact stored Cartesian line samples; never interpolate or select a field cell as a line. */
export function sampleProbe(traces: PlotTrace[], layout: Record<string, unknown>, point: { curveNumber: number; pointNumber: number }, originalCount: number): PlotProbe | null {
  const trace = traces[point.curveNumber];
  if (!trace || !['scatter', 'scattergl'].includes(String(trace.type ?? 'scatter')) || !Number.isInteger(point.pointNumber) || point.pointNumber < 0) return null;
  const x = (trace.x as ArrayLike<unknown> | undefined)?.[point.pointNumber], y = (trace.y as ArrayLike<unknown> | undefined)?.[point.pointNumber];
  if (typeof x !== 'number' || !Number.isFinite(x) || typeof y !== 'number' || !Number.isFinite(y)) return null;
  return { trace: String(trace.name || `Trace ${point.curveNumber + 1}`).replace(/<[^>]*>/g, ''), index: point.pointNumber, x, y,
    xLabel: label(layout[axisKey(trace.xaxis, 'x')], 'X (unit unspecified)'), yLabel: label(layout[axisKey(trace.yaxis, 'y')], 'Y (unit unspecified)'),
    xaxis: typeof trace.xaxis === 'string' ? trace.xaxis : 'x', yaxis: typeof trace.yaxis === 'string' ? trace.yaxis : 'y', comparison: point.curveNumber >= originalCount };
}
export function probeMarkers(probes: PlotProbe[], color: string): PlotTrace[] {
  return probes.map((p, i) => ({ type: 'scatter', mode: 'markers+text', x: [p.x], y: [p.y], xaxis: p.xaxis, yaxis: p.yaxis,
    text: [i ? 'B' : 'A'], textposition: 'top center', textfont: { color, size: 12 }, marker: { size: 10, symbol: 'circle-open', color, line: { width: 2 } },
    showlegend: false, hoverinfo: 'skip', name: 'Pinned probe', cliponaxis: false }));
}
export function probeDelta(probes: PlotProbe[]): { x: number; y: number } | null {
  if (probes.length !== 2 || probes[0].xLabel !== probes[1].xLabel || probes[0].yLabel !== probes[1].yLabel) return null;
  return { x: probes[1].x - probes[0].x, y: probes[1].y - probes[0].y };
}
export function probeTable(probes: PlotProbe[]): string {
  const safe = (text: string) => text.replace(/[\t\r\n]/g, ' ').replace(/^[=+@-]/, char => `'${char}`);
  return ['Probe\tSeries\tSample index\tX quantity\tX value\tY quantity\tY value\tSource', ...probes.map((p, i) => `${i ? 'B' : 'A'}\t${safe(p.trace)}\t${p.index}\t${safe(p.xLabel)}\t${p.x}\t${safe(p.yLabel)}\t${p.y}\t${p.comparison ? 'Pasted comparison' : 'Original trace'}`)].join('\n');
}
