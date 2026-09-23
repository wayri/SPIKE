// SPDX-License-Identifier: MIT
import type { ParasiticResult, ScalarSample, SolverResultBundle } from "./analysisResults";
import { resultFaceTriangleIndices } from "./resultGeometryMask";
import { sharedVertexValues } from "./resultSurfaceInterpolation";

export type ResultPlotField = { key: string; label: string; unit: string; scale: number; samples: ScalarSample[]; impedance?: ParasiticResult[] };
export type TraceGroup = { id: string; net: string; layer: string; elementId: string; label: string; count: number };
export type TracePlot = { data: Record<string, unknown>[]; layout: Record<string, unknown>; shown: number; total: number };
const traceIdentity = (sample: ScalarSample) => sample.source_id || sample.element_id || "";
export const traceGroupId = (sample: ScalarSample) => JSON.stringify([sample.net ?? "", sample.layer ?? "", traceIdentity(sample)]);
const valid = (sample: ScalarSample) => [sample.x_mm, sample.y_mm, sample.value].every(Number.isFinite)
  && (sample.z_mm === undefined || Number.isFinite(sample.z_mm));
const escape = (value: string) => value.replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]!);

export function resultPlotFields(result: SolverResultBundle | null, domain: "pi" | "si"): ResultPlotField[] {
  if (!result) return [];
  // Partial arrays on a failed solve are diagnostic evidence, not plot data.
  // Leave the authoritative bundle (including failure provenance) untouched.
  const rejected = /^(failed(?:_.*)?|blocked|error|cancelled|canceled|unsupported)$/i;
  const admission = [result, result.summary, result.provenance] as (Record<string, unknown> | undefined)[];
  if (rejected.test(result.status ?? "") || rejected.test(result.model_status ?? "")
    || admission.some(record => record?.solved === false || Boolean(record?.failure_stage))) return [];
  const fields: ResultPlotField[] = [];
  const sourceIds = new Map((result.mesh ?? []).filter(cell => cell.source_id).map(cell => [JSON.stringify([cell.id, cell.net ?? "", cell.layer ?? ""]), cell.source_id!]));
  const identify = (sample: ScalarSample): ScalarSample => sample.source_id ? sample : { ...sample,
    source_id: sourceIds.get(JSON.stringify([sample.element_id, sample.net ?? "", sample.layer ?? ""])) };
  const definitions = domain === "pi" ? [
    ["voltage_drop_v", "Voltage drop", "mV", 1000], ["voltage_v", "Voltage", "V", 1],
    ["current_a", "Current", "A", 1], ["current_density_a_mm2", "Current density", "A/mm2", 1],
    ["power_loss_w", "Copper loss", "W", 1], ["via_current_density_a_mm2", "Via current density", "A/mm2", 1],
    ["operating_point_impedance_ohm", "Operating-point impedance", "ohm", 1],
  ] : [["operating_point_impedance_ohm", "Operating-point impedance", "ohm", 1]];
  for (const [key, label, unit, scale] of definitions) {
    const samples = (result.scalar_fields?.[key as keyof SolverResultBundle["scalar_fields"]] ?? []).filter(valid).map(identify);
    if (samples.length) fields.push({ key: String(key), label: String(label), unit: String(unit), scale: Number(scale), samples });
  }
  if (domain === "si") for (const [key, label, unit] of [["electric_field", "Electric field", "V/m"], ["magnetic_field", "Magnetic field", "A/m"]]) {
    const samples = (result.vector_fields?.[key as "electric_field" | "magnetic_field"] ?? []).map(sample => ({ ...sample, value: sample.magnitude })).filter(valid).map(identify);
    if (samples.length) fields.push({ key, label, unit, scale: 1, samples });
  }
  const impedance = (result.parasitics ?? []).filter(network => network.impedance?.some(point => Number.isFinite(point.frequency_hz) && point.frequency_hz > 0 && Number.isFinite(point.magnitude_ohm)));
  if (impedance.length) fields.push({ key: "impedance_sweep", label: "Impedance sweep", unit: "ohm", scale: 1, samples: [], impedance });
  return fields;
}

export function resultTraceGroups(samples: readonly ScalarSample[]): TraceGroup[] {
  const groups = new Map<string, TraceGroup>();
  for (const sample of samples) {
    if (!valid(sample)) continue;
    const id = traceGroupId(sample);
    const current = groups.get(id);
    if (current) current.count++;
    else groups.set(id, { id, net: sample.net ?? "", layer: sample.layer ?? "", elementId: traceIdentity(sample),
      label: `${traceIdentity(sample) || "Unassigned samples"} · ${sample.layer || "Layer unspecified"}`, count: 1 });
  }
  return [...groups.values()];
}

/** Display decimation only: preserve extrema and report the shown/total count. */
function boundedSamples(samples: ScalarSample[], budget: number): ScalarSample[] {
  if (samples.length <= budget) return samples;
  let low = 0, high = 0;
  for (let index = 1; index < samples.length; index++) {
    if (samples[index].value < samples[low].value) low = index;
    if (samples[index].value > samples[high].value) high = index;
  }
  const indices = new Set([0, samples.length - 1, low, high]);
  for (let index = 0; indices.size < budget && index < budget; index++) indices.add(Math.round(index * (samples.length - 1) / (budget - 1)));
  return [...indices].sort((a, b) => a - b).map(index => samples[index]);
}

export function buildTracePlot(samples: readonly ScalarSample[], options: {
  net: string; groupIds?: string[]; mode: "spatial" | "height" | "samples"; label: string; unit: string; scale?: number; maxSamples?: number;
}): TracePlot {
  const selected = options.groupIds?.length ? new Set(options.groupIds) : null;
  const filtered = samples.filter(sample => valid(sample) && (sample.net ?? "") === options.net && (!selected || selected.has(traceGroupId(sample))));
  const budget = Math.max(4, Math.min(20_000, Math.floor(options.maxSamples ?? 20_000)));
  const shown = boundedSamples(filtered, Number.isFinite(budget) ? budget : 20_000);
  const scale = Number.isFinite(options.scale) ? options.scale! : 1;
  const title = `${escape(options.label)} (${escape(options.unit)})`;
  const layout: Record<string, unknown> = {
    margin: { l: 65, r: 35, t: 35, b: 60 }, paper_bgcolor: "#14212b", plot_bgcolor: "#14212b", font: { color: "#dce8ee", size: 12 },
    uirevision: JSON.stringify([options.net, options.mode]), hovermode: "closest", legend: { orientation: "h", y: -0.15 },
    colorway: ["#49d4e8", "#ffbf69", "#81e6b2", "#c5a3ff"],
  };
  const data: Record<string, unknown>[] = [];
  const hover = `<b>%{customdata[0]}</b><br>%{customdata[1]}<br>Source sample: %{customdata[2]:.6g} ${escape(options.unit)}<br>x=%{customdata[3]:.6g}, y=%{customdata[4]:.6g} mm<extra></extra>`;
  const meta = (sample: ScalarSample) => [escape(sample.net || "Unassigned net"), escape(`${sample.element_id || "Unassigned element"} · ${sample.layer || "Layer unspecified"}`), sample.value * scale, sample.x_mm, sample.y_mm];
  if (options.mode === "samples") {
    // Markers preserve source order without inventing a connected trace path.
    const groups = new Map<string, ScalarSample[]>();
    for (const sample of shown) {
      const id = traceGroupId(sample);
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id)!.push(sample);
    }
    // One combined series in net overview avoids a draw call per mesh element.
    const series = selected && groups.size <= 16 ? [...groups.entries()] : [["overview", shown] as const];
    for (const [id, values] of series) data.push({ type: "scattergl", mode: "markers", name: id === "overview" ? escape(options.net || "Unassigned net") : escape(values[0]?.element_id || "Unassigned samples"),
      x: values.map((_, index) => index + 1), y: values.map(sample => sample.value * scale), customdata: values.map(meta), hovertemplate: hover, marker: { size: 6 } });
    layout.xaxis = { title: { text: "Returned sample order (not path distance)" }, zeroline: false };
    layout.yaxis = { title: { text: title }, zeroline: false };
  } else {
    let vertexBudget = 100_000;
    const safeFaces = shown.filter(sample => {
      const vertices = sample.vertices_mm;
      if (!vertices || vertices.length > 256 || vertices.length > vertexBudget
        || !vertices.every(vertex => Array.isArray(vertex) && vertex.length === 3 && vertex.every(Number.isFinite))) return false;
      vertexBudget -= vertices.length;
      return true;
    });
    const admittedFaces = new Set(safeFaces);
    const colors = sharedVertexValues(safeFaces);
    const x: number[] = [], y: number[] = [], z: number[] = [], intensity: number[] = [];
    const i: number[] = [], j: number[] = [], k: number[] = [], customdata: unknown[][] = [];
    const markers: ScalarSample[] = [];
    for (const sample of shown) {
      const vertices = sample.vertices_mm;
      const indices = vertices && admittedFaces.has(sample) ? resultFaceTriangleIndices(vertices) : [];
      if (!indices.length || !vertices) { markers.push(sample); continue; }
      const offset = x.length;
      vertices.forEach((vertex, index) => { const value = (colors.get(sample)?.[index] ?? sample.value) * scale; x.push(vertex[0]); y.push(vertex[1]); z.push(options.mode === "height" ? value : vertex[2]); intensity.push(value); customdata.push(meta(sample)); });
      for (let index = 0; index < indices.length; index += 3) { i.push(offset + indices[index]); j.push(offset + indices[index + 1]); k.push(offset + indices[index + 2]); }
    }
    let low = Infinity, high = -Infinity;
    for (const sample of shown) { low = Math.min(low, sample.value * scale); high = Math.max(high, sample.value * scale); }
    const color = { colorscale: "Viridis", cmin: Number.isFinite(low) ? low : 0, cmax: Number.isFinite(high) ? high : 1, colorbar: { title: { text: title } } };
    if (i.length) data.push({ type: "mesh3d", x, y, z, i, j, k, intensity, intensitymode: "vertex", customdata, hovertemplate: hover,
      ...color, opacity: 1, flatshading: false, lighting: { ambient: 1, diffuse: 0, specular: 0 }, name: "Solver faces", showscale: true });
    if (markers.length) data.push({ type: "scatter3d", mode: "markers", x: markers.map(sample => sample.x_mm), y: markers.map(sample => sample.y_mm), z: markers.map(sample => options.mode === "height" ? sample.value * scale : sample.z_mm ?? 0),
      customdata: markers.map(meta), hovertemplate: hover, name: "Source samples", marker: { ...color, color: markers.map(sample => sample.value * scale), size: 4, opacity: 1, showscale: !i.length } });
    layout.scene = { aspectmode: options.mode === "height" ? "manual" : "data", ...(options.mode === "height" ? { aspectratio: { x: 1.4, y: 1, z: .8 } } : {}), camera: { eye: { x: 1.4, y: 1.4, z: 1.4 } },
      xaxis: { title: { text: "X (mm)" } }, yaxis: { title: { text: "Y (mm)" } }, zaxis: { title: { text: options.mode === "height" ? title : "Z (mm; unspecified = 0)" } } };
  }
  return { data, layout, shown: shown.length, total: filtered.length };
}

export function buildImpedancePlot(networks: ParasiticResult[], net: string, targetOhm?: number): TracePlot {
  let total = 0;
  let minimumFrequency = Infinity;
  let maximumFrequency = 0;
  const data: Record<string, unknown>[] = networks.filter(network => network.net === net).map((network, index) => {
    const points = (network.impedance ?? []).filter(point => point.frequency_hz > 0 && Number.isFinite(point.frequency_hz) && Number.isFinite(point.magnitude_ohm)).sort((a, b) => a.frequency_hz - b.frequency_hz);
    total += points.length;
    if (points.length) {
      minimumFrequency = Math.min(minimumFrequency, points[0].frequency_hz);
      maximumFrequency = Math.max(maximumFrequency, points[points.length - 1].frequency_hz);
    }
    return { type: "scatter", mode: "lines+markers", name: escape(`${net} · ${index + 1}`), x: points.map(point => point.frequency_hz), y: points.map(point => point.magnitude_ohm),
      customdata: points.map(point => [point.resistance_ohm ?? null, point.reactance_ohm ?? null, point.phase_deg]),
      hovertemplate: "f=%{x:.6g} Hz<br>|Z|=%{y:.6g} ohm<br>R=%{customdata[0]:.6g} ohm<br>X=%{customdata[1]:.6g} ohm<br>Phase=%{customdata[2]:.6g} deg<extra></extra>" };
  });
  if (Number.isFinite(targetOhm) && Number(targetOhm) > 0 && total) {
    data.push({ type: "scatter", mode: "lines", name: "PDN screening target",
      x: [minimumFrequency, maximumFrequency], y: [targetOhm!, targetOhm!],
      line: { color: "#ffbf69", width: 2, dash: "dash" },
      hovertemplate: "Target=%{y:.6g} ohm<extra></extra>" });
  }
  return { data, shown: total, total, layout: { paper_bgcolor: "#14212b", plot_bgcolor: "#14212b", font: { color: "#dce8ee" }, margin: { l: 65, r: 25, t: 35, b: 60 },
    colorway: ["#49d4e8", "#ffbf69", "#81e6b2", "#c5a3ff"], xaxis: { type: "log", title: { text: "Frequency (Hz)" } }, yaxis: { title: { text: "Impedance magnitude (ohm)" } }, uirevision: net, hovermode: "closest" } };
}
