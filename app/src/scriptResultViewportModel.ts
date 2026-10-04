// SPDX-License-Identifier: Apache-2.0
import { numericExtent } from "./numericRange";
import { admitDataViews, type DataView, type SpatialSample } from "./scriptDataViews";

export type SpatialChoice = {
  view: DataView;
  role: "radiation" | "field" | "mesh";
};

export type SpatialBounds = {
  x: [number, number];
  y: [number, number];
  z: [number, number];
  unit: string;
};

export type ProbeRow = { label: string; value: string; unit?: string };

const searchable = (view: DataView) => `${view.title} ${view.kind === "spatial" ? view.quantity ?? "" : ""} ${view.provenance}`.toLowerCase();
const finiteDisplay = (value: number) => Number(value.toPrecision(7)).toString();

export function admitScriptResultViews(raw: unknown): DataView[] {
  return admitDataViews(raw);
}

export function spatialRole(view: DataView): SpatialChoice["role"] {
  if (view.kind === "mesh") return "mesh";
  return /radiat|far[-_ ]?field|directivity|gain|antenna pattern/.test(searchable(view)) ? "radiation" : "field";
}

export function spatialChoices(views: DataView[]): SpatialChoice[] {
  const priority = { radiation: 0, field: 1, mesh: 2 } as const;
  return views
    .map((view, index) => ({ view, index }))
    .filter(item => item.view.kind === "spatial" || item.view.kind === "mesh")
    .map(item => ({ ...item, role: spatialRole(item.view) }))
    .sort((a, b) => priority[a.role] - priority[b.role] || a.index - b.index)
    .map(({ view, role }) => ({ view, role }));
}

export function plotChoices(views: DataView[]): DataView[] {
  return views.filter(view => view.kind === "line" || view.kind === "polar");
}

export function defaultPlotIds(plots: DataView[]): [string | null, string | null] {
  return [plots[0]?.id ?? null, plots[1]?.id ?? null];
}

export function normalizeViewId<T extends { id: string }>(views: T[], requested: string | null, fallbackIndex = 0): string | null {
  return requested && views.some(view => view.id === requested) ? requested : views[fallbackIndex]?.id ?? null;
}

function spatialPoints(view: DataView): SpatialSample[] {
  if (view.kind === "spatial") return view.samples ?? [];
  if (view.kind === "mesh") return (view.vertices ?? []).map(([x, y, z]) => ({ x, y, z }));
  return [];
}

export function spatialBounds(view: DataView): SpatialBounds | null {
  const points = spatialPoints(view);
  if (!points.length) return null;
  const axis = (key: "x" | "y" | "z"): [number, number] => { const extent = numericExtent(points.map(point => point[key])); return [extent.minimum, extent.maximum]; };
  return { x: axis("x"), y: axis("y"), z: axis("z"), unit: view.coordinate_unit ?? "" };
}

function parseProvenance(value: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null;
  } catch { return null; }
}

export type PhysicalRegion = { name: string; material: string; triangle_start: number; triangle_count: number };
export type PhysicalGeometry = { view: DataView; regions: PhysicalRegion[]; phase: "geometry" | "solved" };

function sceneIdentity(view: DataView): Record<string, unknown> | null {
  const metadata = parseProvenance(view.provenance);
  return metadata && typeof metadata.scene_id === "string" && /^[a-f0-9]{64}$/.test(metadata.scene_id)
    && typeof metadata.run_id === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(metadata.run_id)
    && metadata.coordinate_frame === "emerge-global-xyz" && metadata.coordinate_unit === "m"
    && view.coordinate_unit === "m" ? metadata : null;
}

export function physicalGeometry(view: DataView): PhysicalGeometry | null {
  const metadata = sceneIdentity(view);
  if (view.kind !== "mesh" || !metadata || metadata.scene_role !== "physical_geometry"
    || !["geometry", "solved"].includes(String(metadata.phase)) || !Array.isArray(metadata.regions)
    || !metadata.regions.length || metadata.regions.length > 128) return null;
  const regions: PhysicalRegion[] = [];
  let next = 0;
  for (const raw of metadata.regions) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    const region = raw as Record<string, unknown>;
    if (typeof region.name !== "string" || typeof region.material !== "string"
      || !Number.isInteger(region.triangle_start) || region.triangle_start !== next
      || !Number.isInteger(region.triangle_count) || Number(region.triangle_count) <= 0) return null;
    next += Number(region.triangle_count);
    if (next > (view.triangles?.length ?? 0)) return null;
    regions.push(region as PhysicalRegion);
  }
  return next === view.triangles?.length ? { view, regions, phase: metadata.phase as PhysicalGeometry["phase"] } : null;
}

export function matchingPhysicalGeometry(view: DataView, views: DataView[]): PhysicalGeometry | null {
  const identity = sceneIdentity(view);
  if (!identity) return null;
  for (const candidate of views) {
    const geometry = physicalGeometry(candidate);
    const other = geometry && sceneIdentity(candidate);
    if (geometry && other && other.scene_id === identity.scene_id && other.run_id === identity.run_id) return geometry;
  }
  return null;
}

export function combinedSpatialBounds(view: DataView, overlay: PhysicalGeometry | null): SpatialBounds | null {
  const bounds = spatialBounds(view), other = overlay && spatialBounds(overlay.view);
  if (!bounds || !other || bounds.unit !== other.unit) return bounds;
  const axis = (key: "x" | "y" | "z"): [number, number] => [Math.min(bounds[key][0], other[key][0]), Math.max(bounds[key][1], other[key][1])];
  return { x: axis("x"), y: axis("y"), z: axis("z"), unit: bounds.unit };
}

export function physicalMaterialColor(material: string): number {
  return /(?:copper|\bcu\b|\bpec\b|perfect.*conductor)/i.test(material) ? 0xc88743 : 0x7da8c4;
}

export function provenanceLabel(view: DataView): string {
  const parsed = parseProvenance(view.provenance);
  if (!parsed) return view.provenance;
  return [parsed.model, parsed.solver, parsed.engine, parsed.engine_version, parsed.source, parsed.analysis_id, parsed.run_id]
    .filter(value => typeof value === "string" || typeof value === "number")
    .map(String).join(" · ") || view.provenance;
}

function displayRadiusMetadata(view: DataView): string | null {
  const parsed = parseProvenance(view.provenance);
  if (!parsed) return null;
  const entries: [string, unknown][] = [];
  const visit = (record: Record<string, unknown>, prefix = "", depth = 0) => {
    for (const [key, value] of Object.entries(record)) {
      const path = prefix ? `${prefix}.${key}` : key;
      if (/display.*radius|radius.*display|radial.*scale|coordinate.*scale|display_mapping/i.test(path)) entries.push([path, value]);
      if (depth < 1 && value && typeof value === "object" && !Array.isArray(value)) visit(value as Record<string, unknown>, path, depth + 1);
    }
  };
  visit(parsed);
  const printable = entries.filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)).slice(0, 3);
  return printable.length ? printable.map(([key, value]) => `${key}: ${String(value)}`).join(" · ") : null;
}

export function radiationDisplayNotice(view: DataView, aligned = false): string | null {
  if (spatialRole(view) !== "radiation") return null;
  const metadata = displayRadiusMetadata(view);
  return `Radiation coordinates are the published display shape, not an observation-distance claim. ${aligned ? "The source origin shares the physical model coordinate frame; radial distance is a presentation scale, not a field sample location." : "No matched physical model coordinate frame was published."}${metadata ? ` Display scale metadata: ${metadata}.` : " No separate display-radius metadata was published."}`;
}

export function probeRows(view: DataView, index: number): ProbeRow[] {
  if (!Number.isInteger(index) || index < 0) return [];
  if (view.kind === "mesh") {
    const vertex = view.vertices?.[index];
    if (!vertex) return [];
    return [
      { label: "Sample index", value: String(index) },
      ...vertex.map((value, axis) => ({ label: ["X", "Y", "Z"][axis], value: finiteDisplay(value), unit: view.coordinate_unit }))
    ];
  }
  if (view.kind !== "spatial") return [];
  const sample = view.samples?.[index];
  if (!sample) return [];
  const rows: ProbeRow[] = [
    { label: "Sample index", value: String(index) },
    { label: "X", value: finiteDisplay(sample.x), unit: view.coordinate_unit },
    { label: "Y", value: finiteDisplay(sample.y), unit: view.coordinate_unit },
    { label: "Z", value: finiteDisplay(sample.z), unit: view.coordinate_unit },
  ];
  if (sample.vector_real && sample.vector_imag) {
    for (let component = 0; component < 3; component += 1) {
      const axis = ["X", "Y", "Z"][component];
      rows.push({ label: `${axis} real`, value: finiteDisplay(sample.vector_real[component]), unit: view.value_unit });
      rows.push({ label: `${axis} imaginary`, value: finiteDisplay(sample.vector_imag[component]), unit: view.value_unit });
    }
    rows.push({ label: "Complex vector magnitude", value: finiteDisplay(Math.hypot(...sample.vector_real, ...sample.vector_imag)), unit: view.value_unit });
  } else if (sample.value_real !== undefined && sample.value_imag !== undefined) {
    rows.push({ label: "Real", value: finiteDisplay(sample.value_real), unit: view.value_unit });
    rows.push({ label: "Imaginary", value: finiteDisplay(sample.value_imag), unit: view.value_unit });
    rows.push({ label: "Complex magnitude", value: finiteDisplay(Math.hypot(sample.value_real, sample.value_imag)), unit: view.value_unit });
  }
  return rows;
}

export function plotPresentation(view: DataView): { data: Record<string, unknown>[]; layout: Record<string, unknown> } {
  if (view.kind !== "line" && view.kind !== "polar") return { data: [], layout: {} };
  const polar = view.kind === "polar";
  const indexes = (view.x ?? []).map((_, index) => index);
  const data = (view.series ?? []).map(series => ({
    type: polar ? "scatterpolar" : "scatter",
    name: series.name,
    ...(polar ? { theta: view.x, r: series.values } : { x: view.x, y: series.values }),
    mode: "lines+markers",
    marker: { size: 5 },
    connectgaps: false,
    customdata: indexes,
  }));
  const label = (name: string | undefined, unit: string | undefined) => `${name ?? ""}${unit ? ` [${unit}]` : ""}`;
  return {
    data,
    layout: {
      paper_bgcolor: "#1b1726", plot_bgcolor: "#15111e", font: { color: "#dbcfe7", size: 11 },
      colorway: ["#cd9ffa", "#71e0d8", "#ff9cc9", "#e8c87a"], margin: { l: 58, r: 24, b: 50, t: 30 },
      xaxis: { title: { text: label(view.x_label, view.x_unit) }, gridcolor: "#3c304c", zerolinecolor: "#645077" },
      yaxis: { title: { text: label(view.y_label, view.y_unit) }, gridcolor: "#3c304c", zerolinecolor: "#645077" },
      polar: { bgcolor: "#15111e", angularaxis: { gridcolor: "#4d3e5b" }, radialaxis: { gridcolor: "#4d3e5b", title: { text: label(view.y_label, view.y_unit) } } },
      hovermode: "closest", dragmode: "zoom", uirevision: view.id,
      legend: { orientation: "h", y: 1.12 }, showlegend: (view.series?.length ?? 0) > 1,
    },
  };
}
