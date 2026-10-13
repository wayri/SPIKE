// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
// Presentation of worker-admitted retained fields. No inferred temperatures or flux.
export type ThermalMeshView = "none" | "surface" | "volume";
type Surface = { indices: number[]; x: number[]; y: number[]; z: number[]; i: number[]; j: number[]; k: number[] };
const MAX_EDGES = 20000, MAX_INTERIOR_CELLS = 5000;
const temperatureContracts = ["spike/assembly-field-thermal-result/v1", "spike/calculix-thermal-result/v1", "spike/assembly-field-transient-result/v1", "spike/calculix-field-transient-result/v1"];
const displayTemperature = (t: number, unit: "K" | "C") => unit === "K" ? t : t - 273.15;
// Unlike Array.every, iteration visits sparse entries so missing samples fail closed.
function everyEntry(values: any[], predicate: (value: any) => boolean) {
  for (const value of values) if (!predicate(value)) return false;
  return true;
}

/** Prepared once per handoff; display/unit changes reuse the retained coordinates. */
export function prepareThermalVolumeGeometry(handoff: any) {
  const vertices: number[][] = handoff?.mesh?.vertices, faces: any[] = handoff?.boundary_faces;
  const validIndices = (ids: any, size: number) => Array.isArray(ids) && ids.length === size && new Set(ids).size === size &&
    everyEntry(ids, i => Number.isInteger(i) && i >= 0 && i < vertices.length);
  const error = "A bounded admitted surface mesh in metres is required for the 3D preview.";
  if (handoff?.mesh?.units !== "m" || !Array.isArray(vertices) || !vertices.length || vertices.length > 100000 ||
      !Array.isArray(faces) || !faces.length || faces.length > 200000 ||
      !everyEntry(vertices, p => Array.isArray(p) && p.length === 3 && everyEntry(p, v => typeof v === "number" && Number.isFinite(v * 1000))) ||
      !everyEntry(faces, f => validIndices(f?.vertices, 3) && typeof f.occurrence_id === "string" && Boolean(f.occurrence_id))) return { error };
  const occurrences = [...new Set<string>(faces.map(f => f.occurrence_id))].sort();
  if (occurrences.length > 1000) return { error };
  const owners: string[] = Array(vertices.length).fill("");
  const groups = new Map(occurrences.map(id => [id, new Set<number>()]));
  for (const face of faces) for (const i of face.vertices) {
    if (owners[i] && owners[i] !== face.occurrence_id) return { error: "Mesh occurrence ownership is ambiguous; preview withheld." };
    owners[i] = face.occurrence_id;
    groups.get(face.occurrence_id)!.add(i);
  }
  let volumeOwnership = false;
  if (handoff.source_traceability !== undefined) {
    const traces = handoff.source_traceability;
    if (!Array.isArray(traces) || traces.length !== occurrences.length) return { error: "Invalid retained volume occurrence ranges." };
    const seen = new Set<string>(), assigned = new Uint8Array(vertices.length);
    for (const trace of traces) {
      const id = trace?.occurrence_id, range = trace?.vertex_range;
      if (!groups.has(id) || seen.has(id) || !Array.isArray(range) || range.length !== 2 ||
          !everyEntry(range, Number.isInteger) || range[0] < 0 || range[1] > vertices.length || range[0] >= range[1]) return { error: "Invalid retained volume occurrence ranges." };
      seen.add(id);
      for (let i = range[0]; i < range[1]; i++) {
        if (assigned[i] || (owners[i] && owners[i] !== id)) return { error: "Invalid retained volume occurrence ranges." };
        assigned[i] = 1; owners[i] = id; groups.get(id)!.add(i);
      }
    }
    if (assigned.some(v => !v)) return { error: "Incomplete retained volume occurrence ranges." };
    volumeOwnership = true;
  }
  const cells: any[] = handoff.mesh.cells;
  const interiorAvailable = volumeOwnership && Array.isArray(cells) && cells.length > 0 && cells.length <= MAX_INTERIOR_CELLS &&
    everyEntry(cells, c => c?.kind === "tetrahedron" && validIndices(c?.vertices, 4) && c.vertices.every((i: number) => owners[i] === owners[c.vertices[0]]));
  return { error: "", handoff, vertices, faces, occurrences, owners, groups, volumeOwnership, cells, interiorAvailable };
}
export type ThermalVolumeGeometry = ReturnType<typeof prepareThermalVolumeGeometry>;

/** Validate the full node array before exposing any temperature, including filtered views. */
export function thermalVolumeField(geometry: ThermalVolumeGeometry, result: any) {
  const { handoff, vertices, groups } = geometry;
  const samples = result?.field_result?.node_temperatures_k;
  const mismatchedBindings = ["handoff_digest", "request_digest", "assembly_digest"].filter(key => result?.[key] !== handoff?.[key]);
  const hasTemperature = !geometry.error && temperatureContracts.includes(result?.contract) &&
    ["handoff_digest", "request_digest", "assembly_digest"].every(key => typeof handoff[key] === "string" && handoff[key].length > 0 && result[key] === handoff[key]) &&
    result.model_status === "experimental" && result.production_qualified === false &&
    result.field_result?.temperature_units === "K" && result.field_result?.status === "experimental" &&
    result.field_result?.production_qualified === false && Array.isArray(samples) && samples.length === vertices!.length &&
    everyEntry(samples, t => typeof t === "number" && Number.isFinite(t) && t >= 0);
  let minimum = Infinity, maximum = -Infinity;
  const stats: { occurrence: string; count: number; minimum: number; maximum: number }[] = [];
  if (hasTemperature) {
    for (const t of samples) { minimum = Math.min(minimum, t); maximum = Math.max(maximum, t); }
    for (const [occurrence, ids] of groups!) {
      let low = Infinity, high = -Infinity;
      for (const i of ids) { low = Math.min(low, samples[i]); high = Math.max(high, samples[i]); }
      stats.push({ occurrence, count: ids.size, minimum: low, maximum: high });
    }
  }
  // Plotly needs a nonzero color interval for an isothermal solution.
  const padding = Math.max(.5, Math.abs(minimum) * 1e-6);
  return { hasTemperature, samples: hasTemperature ? samples as number[] : undefined, minimum, maximum, stats,
    colorMinimum: minimum === maximum ? Math.max(0, minimum - padding) : minimum,
    colorMaximum: minimum === maximum ? Math.min(Number.MAX_VALUE, maximum + padding) : maximum,
    notice: result && !hasTemperature ? `Temperature overlay withheld: ${mismatchedBindings.length ? `mismatched ${mismatchedBindings.join(", ")}` : "result contract, status, units or samples do not match this mesh"}.` : "" };
}

/** Topology and optional edge arrays only change with occurrence/mesh controls. */
export function thermalVolumeSurface(geometry: ThermalVolumeGeometry, occurrence = "", edges: ThermalMeshView = "none") {
  if (geometry.error) return { error: geometry.error };
  const { vertices, faces, owners, cells } = geometry;
  const selected = occurrence ? faces!.filter(f => f.occurrence_id === occurrence) : faces!;
  if (!selected.length) return { error: "The selected occurrence has no exterior faces." };
  const indices = [...new Set<number>(selected.flatMap(f => f.vertices))];
  const local = new Map(indices.map((original, index) => [original, index]));
  const coordinates = (ids: number[]) => ({ x: ids.map(i => vertices![i][0] * 1000), y: ids.map(i => vertices![i][1] * 1000), z: ids.map(i => vertices![i][2] * 1000) });
  const surface: Surface = { indices, ...coordinates(indices), i: selected.map(f => local.get(f.vertices[0])!),
    j: selected.map(f => local.get(f.vertices[1])!), k: selected.map(f => local.get(f.vertices[2])!) };
  let edgeNotice = "", edgeTrace: any = null, interior: (ReturnType<typeof coordinates> & { indices: number[] }) | null = null;
  if (edges === "volume" && !geometry.interiorAvailable) edgeNotice = `Interior inspection requires complete occurrence ranges and at most ${MAX_INTERIOR_CELLS.toLocaleString()} retained tetrahedra.`;
  else if (edges !== "none") {
    const pairs = new Map<string, [number, number]>();
    const elements = edges === "volume" ? cells!.filter(c => !occurrence || owners![c.vertices[0]] === occurrence) : selected;
    outer: for (const element of elements) for (let a = 0; a < element.vertices.length; a++) for (let b = a + 1; b < element.vertices.length; b++) {
      const lo = Math.min(element.vertices[a], element.vertices[b]), hi = Math.max(element.vertices[a], element.vertices[b]);
      pairs.set(`${lo}:${hi}`, [lo, hi]);
      if (pairs.size > MAX_EDGES) { edgeNotice = `Mesh edges withheld: more than ${MAX_EDGES.toLocaleString()} unique edges. Select one occurrence to inspect a smaller mesh.`; break outer; }
    }
    if (!edgeNotice) {
      const x: (number | null)[] = [], y: (number | null)[] = [], z: (number | null)[] = [];
      for (const [a, b] of pairs.values()) { x.push(vertices![a][0] * 1000, vertices![b][0] * 1000, null); y.push(vertices![a][1] * 1000, vertices![b][1] * 1000, null); z.push(vertices![a][2] * 1000, vertices![b][2] * 1000, null); }
      edgeTrace = { type: "scatter3d", mode: "lines", x, y, z, line: { color: "#93a6bc", width: 1 }, hoverinfo: "skip", showlegend: false, name: edges === "volume" ? "Tetrahedral edges" : "Surface edges" };
      if (edges === "volume") { const ids = [...new Set<number>(elements.flatMap(c => c.vertices))]; interior = { indices: ids, ...coordinates(ids) }; }
    }
  }
  return { error: "", surface, edgeTrace, edgeNotice, interior, triangles: selected.length };
}

export function renderThermalVolumePlot(geometry: ThermalVolumeGeometry, field: ReturnType<typeof thermalVolumeField>,
  selected: ReturnType<typeof thermalVolumeSurface>, unit: "K" | "C" = "C", mode: "temperature" | "geometry" = "temperature") {
  const occurrences = geometry.occurrences ?? [];
  if (selected.error || !selected.surface) return { error: selected.error, occurrences, traces: [] };
  const { indices, ...surface } = selected.surface;
  const hasTemperature = field.hasTemperature, showTemperature = hasTemperature && mode === "temperature";
  const customdata = (ids: number[]) => ids.map(i => [geometry.owners![i], i, field.samples?.[i], field.samples ? displayTemperature(field.samples[i], unit) : null]);
  const hovertemplate = `Occurrence %{customdata[0]}<br>Node index %{customdata[1]}<br>x %{x:.3f} mm<br>y %{y:.3f} mm<br>z %{z:.3f} mm${showTemperature ? `<br>%{customdata[3]:.3f} ${unit === "K" ? "K" : "deg C"}` : ""}<extra></extra>`;
  const colors = { colorscale: "Inferno", cmin: displayTemperature(field.colorMinimum, unit), cmax: displayTemperature(field.colorMaximum, unit) };
  const traces: any[] = [{ type: "mesh3d", name: showTemperature ? "Surface temperature" : "Retained exterior mesh", ...surface,
    opacity: selected.interior ? .15 : 1, flatshading: false, customdata: customdata(indices), hovertemplate,
    ...(showTemperature ? { intensity: indices.map(i => displayTemperature(field.samples![i], unit)), intensitymode: "vertex", ...colors,
      colorbar: { title: { text: unit === "K" ? "Temperature (K)" : "Temperature (deg C)" } } }
      : { color: "#7d94a8", showscale: false }) }];
  if (selected.edgeTrace) traces.push(selected.edgeTrace);
  if (selected.interior) {
    const { indices: ids, ...points } = selected.interior;
    traces.push({ type: "scatter3d", mode: "markers", name: "Retained volume nodes", ...points, showlegend: false,
      customdata: customdata(ids), hovertemplate, marker: { size: 3, opacity: 1, ...(showTemperature ? { color: ids.map(i => displayTemperature(field.samples![i], unit)), ...colors, showscale: false } : { color: "#b2c5db" }) } });
  }
  return { error: "", occurrences, traces, hasTemperature, showTemperature, triangles: selected.triangles,
    notice: [field.notice, selected.edgeNotice].filter(Boolean).join(" ") };
}

export function assemblyThermalVolumePlot(handoff: any, result: any, occurrence = "", unit: "K" | "C" = "C",
  options: { mode?: "temperature" | "geometry"; edges?: ThermalMeshView } = {}) {
  const geometry = prepareThermalVolumeGeometry(handoff);
  return renderThermalVolumePlot(geometry, thermalVolumeField(geometry, result), thermalVolumeSurface(geometry, occurrence, options.edges), unit, options.mode);
}
