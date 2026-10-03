// SPDX-License-Identifier: Apache-2.0
// Presentation-only exchange. Imported samples never enter an AnalysisResult.
export const MAX_PLOT_CLIPBOARD_BYTES = 2_000_000;
export const MAX_PLOT_CLIPBOARD_POINTS = 50_000;
export type PlotTrace = Record<string, unknown>;
type Row = Record<string, unknown>;
const record = (value: unknown): Row => value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
export const plotAxisLabel = (axis: unknown): string => {
  const title = record(axis).title;
  return typeof title === "string" ? title : String(record(title).text ?? "");
};
const plain = (value: unknown) => String(value ?? "").replace(/<[^>]*>/g, "").replace(/[\t\r\n]/g, " ").slice(0, 200);
const spreadsheetLabel = (value: unknown) => plain(value).replace(/^[=+@-]/, character => `'${character}`);
const safeName = (value: unknown) => plain(value).replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]!));
const values = (value: unknown): unknown[] => Array.isArray(value) ? value : ArrayBuffer.isView(value) ? Array.from(value as unknown as ArrayLike<number>) : [];
const numberOrGap = (value: unknown): number | null => value === null || value === "" ? null : typeof value === "number" && Number.isFinite(value) ? value : (() => { throw new Error("Plot data must contain finite numbers or blank gaps."); })();
const copySamples = (samples: unknown[]) => samples.map(value => Array.isArray(value) || ArrayBuffer.isView(value) ? values(value).map(numberOrGap) : numberOrGap(value));
const sampleCount = (samples: unknown[]) => samples.reduce<number>((sum, value) => sum + (Array.isArray(value) || ArrayBuffer.isView(value) ? values(value).length : 1), 0);
export const isCartesianPlot = (data: readonly PlotTrace[]) => data.every(trace => ["scatter", "scattergl", "heatmap", "contour", "bar"].includes(String(trace.type ?? "scatter")));

export function copyPlotData(data: readonly PlotTrace[], layout: Row, title: string): string {
  const traces = data.filter(trace => trace.visible !== false && trace.visible !== "legendonly");
  let points = 0;
  const series = traces.map((trace, index) => {
    const x = values(trace.x), y = values(trace.y), z = values(trace.z);
    points += Math.max(sampleCount(x), sampleCount(y), sampleCount(z));
    if (points > MAX_PLOT_CLIPBOARD_POINTS) throw new Error("Too many samples to copy. Select fewer traces or copy the image.");
    const field = Object.fromEntries(["intensity", "surfacecolor", "i", "j", "k"].filter(key => trace[key] !== undefined).map(key => [key, copySamples(values(trace[key]))]));
    return { name: plain(trace.name || `Trace ${index + 1}`), type: String(trace.type ?? "scatter"),
      x: copySamples(x), y: copySamples(y), ...(z.length ? { z: copySamples(z) } : {}), ...field,
      ...(Object.keys(field).length || z.length ? { valueLabel: plain(plotAxisLabel(trace.colorbar)) } : {}) };
  });
  // Long TSV is directly usable in spreadsheets and supports differently sampled traces.
  if (series.every(trace => ["scatter", "scattergl"].includes(trace.type) && !trace.z && trace.x.length === trace.y.length)) {
    const lines = [`Series\t${spreadsheetLabel(plotAxisLabel(layout.xaxis) || "X")}\t${spreadsheetLabel(plotAxisLabel(layout.yaxis) || "Y")}`];
    for (const trace of series) for (let i = 0; i < trace.x.length; i++) lines.push(`${spreadsheetLabel(trace.name)}\t${trace.x[i] ?? ""}\t${trace.y[i] ?? ""}`);
    return boundText(lines.join("\n"));
  }
  const scene = record(layout.scene);
  return boundText(JSON.stringify({ contract: "spike/plot-clipboard/v1", title: plain(title), xLabel: plain(plotAxisLabel(layout.xaxis ?? scene.xaxis)), yLabel: plain(plotAxisLabel(layout.yaxis ?? scene.yaxis)), zLabel: plain(plotAxisLabel(scene.zaxis)), traces: series }));
}
function boundText(text: string) {
  if (new TextEncoder().encode(text).length > MAX_PLOT_CLIPBOARD_BYTES) throw new Error("Plot clipboard data exceeds 2 MB. Select fewer samples or copy the image.");
  return text;
}
const unit = (label: string) => label.match(/\(([^()]*)\)\s*$/)?.[1].trim().toLowerCase() ?? (/^(?:V|mV|A|mA|ohm|Ω|dB|Hz|kHz|MHz|GHz|s|ms|us|µs|ns|ps|m|mm)$/i.test(label.trim()) ? label.trim().toLowerCase() : "");
export function pastePlotTraces(text: string, layout: Row): PlotTrace[] {
  boundText(text);
  let traces: Row[], xLabel = "", yLabel = "";
  if (text.trimStart().startsWith("{")) {
    let payload: Row;
    try { payload = record(JSON.parse(text)); } catch { throw new Error("Clipboard contains malformed plot JSON."); }
    if (payload.contract !== "spike/plot-clipboard/v1" || !Array.isArray(payload.traces)) throw new Error("Use SPIKE plot data or a tab-separated X/Y table.");
    traces = payload.traces.map(record); xLabel = String(payload.xLabel ?? ""); yLabel = String(payload.yLabel ?? "");
  } else {
    const rows = text.split(/\r?\n/).filter(line => line.includes("\t") || line.trim()).map(line => line.split("\t"));
    if (!rows.length || rows.length > MAX_PLOT_CLIPBOARD_POINTS + 1) throw new Error("Paste up to 50,000 tab-separated samples.");
    const grouped = rows[0][0].trim().toLowerCase() === "series";
    const columns = grouped ? 3 : 2;
    if (rows.some(row => row.length !== columns)) throw new Error("Use two columns X/Y, or three columns Series/X/Y, separated by tabs.");
    const numeric = (value: string) => value.trim() === "" ? null : Number(value);
    const header = grouped || rows[0].every(value => value.trim() !== "" && Number.isNaN(Number(value)) && !/^[+-]?(?:nan|infinity)$/i.test(value.trim()));
    if (header) { const labels = rows.shift()!; xLabel = labels[columns - 2]; yLabel = labels[columns - 1]; }
    const groups = new Map<string, Row>();
    for (const row of rows) {
      const name = grouped ? row[0] : "Pasted trace";
      if (!groups.has(name)) groups.set(name, { name, type: "scatter", x: [], y: [] });
      const trace = groups.get(name)!;
      (trace.x as unknown[]).push(numeric(row[columns - 2])); (trace.y as unknown[]).push(numeric(row[columns - 1]));
    }
    traces = [...groups.values()];
  }
  for (const [given, axis] of [[xLabel, layout.xaxis], [yLabel, layout.yaxis]] as const) {
    const incoming = unit(given), current = unit(plotAxisLabel(axis));
    if (incoming && current && incoming !== current) throw new Error(`Pasted unit ${incoming} differs from ${current}. Convert units before comparing.`);
  }
  if (!traces.length || traces.length > 24) throw new Error("Paste between 1 and 24 comparison traces.");
  let total = 0;
  return traces.map((trace, index) => {
    if (!["scatter", "scattergl"].includes(String(trace.type ?? "scatter")) || trace.z !== undefined) throw new Error("Paste comparisons into a 2D X/Y plot. Spatial and field-grid data can be copied, but cannot be overlaid as traces.");
    const x = values(trace.x).map(numberOrGap), y = values(trace.y).map(numberOrGap);
    total += x.length;
    if (!x.length || x.length !== y.length || total > MAX_PLOT_CLIPBOARD_POINTS || !x.some((value, i) => value !== null && y[i] !== null)) throw new Error("Trace coordinates must have equal lengths and at least one finite X/Y pair (50,000 samples maximum).");
    for (const [axis, samples] of [[layout.xaxis, x], [layout.yaxis, y]] as const) {
      if (record(axis).type === "log" && samples.some(value => value !== null && value <= 0)) throw new Error("Logarithmic axes require positive pasted coordinates.");
    }
    return { type: "scatter", mode: "lines+markers", name: `Clipboard: ${safeName(trace.name || `Trace ${index + 1}`)}`, x, y, connectgaps: false,
      line: { dash: "dash", width: 2 }, marker: { size: 4 }, meta: { importedComparison: true } };
  });
}
