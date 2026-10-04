// SPDX-License-Identifier: Apache-2.0
export type Cell = number | string | boolean | null;
export type SpatialSample = { x:number;y:number;z:number;value_real?:number;value_imag?:number;vector_real?:[number,number,number];vector_imag?:[number,number,number] };
export type DataView = { contract: "spike/data-view/v1"; id: string; kind: "table" | "line" | "scatter" | "polar" | "spatial" | "mesh"; title: string; provenance: string; columns?: string[]; rows?: Cell[][]; units?: string[]; x?: number[]; series?: {name:string;values:(number|null)[]}[]; x_label?:string;y_label?:string;x_unit?:string;y_unit?:string;samples?:SpatialSample[];quantity?:string;coordinate_unit?:string;value_unit?:string;vertices?:[number,number,number][];triangles?:[number,number,number][] };
export type DataRow = { index: number; values: Cell[] };
const rec = (x: unknown): x is Record<string, unknown> => !!x && typeof x === "object" && !Array.isArray(x);
const text = (x: unknown): x is string => typeof x === "string" && x.length <= 2000;
const bytes = (s: string) => new TextEncoder().encode(s).length;
const num = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
export function admitDataViews(value: unknown): DataView[] {
  if (!Array.isArray(value) || value.length > 12) return [];
  let cells = 0, chars = 0;
  const ids = new Set<string>();
  for (const v of value) {
    if (!rec(v) || v.contract !== "spike/data-view/v1" || !text(v.id) || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(v.id) || ids.has(v.id) || !text(v.title) || !text(v.provenance)) return [];
    ids.add(v.id); chars += bytes(v.id + v.title + v.provenance);
    if (v.kind === "table") {
      if (!Array.isArray(v.columns) || !v.columns.length || v.columns.length > 32 || !v.columns.every(text) || !Array.isArray(v.rows) || v.rows.length > 100000) return [];
      if (v.units !== undefined && (!Array.isArray(v.units) || !v.units.every(text) || (v.units.length !== 0 && v.units.length !== v.columns.length))) return [];
      chars += bytes(v.columns.join("") + ((v.units as string[] | undefined)?.join("") ?? ""));
      for (const row of v.rows) {
        if (!Array.isArray(row) || row.length !== v.columns.length || !row.every(c => c === null || typeof c === "boolean" || num(c) || typeof c === "string")) return [];
        cells += row.length; chars += row.reduce((sum, c) => sum + (typeof c === "string" ? bytes(c) : 0), 0);
      }
    } else if (v.kind === "spatial") {
      if (!Array.isArray(v.samples) || !v.samples.length || v.samples.length > 10000 || !text(v.quantity) || !text(v.coordinate_unit) || !text(v.value_unit)) return [];
      for (const sample of v.samples) {
        if (!rec(sample) || !num(sample.x) || !num(sample.y) || !num(sample.z)) return [];
        const keys = Object.keys(sample).sort().join(",");
        if (keys === "value_imag,value_real,x,y,z") {
          if (!num(sample.value_real) || !num(sample.value_imag)) return [];
        } else if (keys === "vector_imag,vector_real,x,y,z") {
          if (![sample.vector_real, sample.vector_imag].every(vector => Array.isArray(vector) && vector.length === 3 && vector.every(num))) return [];
        } else return [];
      }
      cells += v.samples.length * 9; chars += bytes(v.quantity + v.coordinate_unit + v.value_unit);
    } else if (v.kind === "mesh") {
      if (!Array.isArray(v.vertices) || !v.vertices.length || v.vertices.length > 10000 || !Array.isArray(v.triangles) || !v.triangles.length || v.triangles.length > 10000 || !text(v.coordinate_unit)) return [];
      const vertices = v.vertices, triangles = v.triangles;
      if (!vertices.every(vertex => Array.isArray(vertex) && vertex.length === 3 && vertex.every(num))) return [];
      if (!triangles.every(triangle => Array.isArray(triangle) && triangle.length === 3 && new Set(triangle).size === 3 && triangle.every(index => Number.isInteger(index) && index >= 0 && index < vertices.length))) return [];
      cells += vertices.length * 3 + triangles.length * 3; chars += bytes(v.coordinate_unit);
    } else {
      if (!["line", "scatter", "polar"].includes(String(v.kind)) || !Array.isArray(v.x) || v.x.length > 20000 || !v.x.every(num) || !Array.isArray(v.series) || !v.series.length || v.series.length > 12) return [];
      for (const k of ["x_label", "y_label", "x_unit", "y_unit"]) { if (!text(v[k])) return []; chars += bytes(v[k] as string); }
      cells += v.x.length;
      for (const series of v.series) {
        if (!rec(series) || !text(series.name) || !Array.isArray(series.values) || series.values.length !== v.x.length || !series.values.every(c => c === null || num(c))) return [];
        if (v.kind === "polar" && (series.values.some(c => typeof c === "number" && c < 0) || !["", "deg"].includes(String(v.x_unit)))) return [];
        cells += series.values.length; chars += bytes(series.name);
      }
    }
    if (cells > 100000 || chars > 1000000) return [];
  }
  return value as DataView[];
}
export function viewTable(view: DataView): { columns: string[]; units: string[]; rows: DataRow[] } {
  if (view.kind === "table") return { columns: view.columns!, units: view.units ?? [], rows: view.rows!.map((values, index) => ({ index, values })) };
  if (view.kind === "spatial") {
    const vector = "vector_real" in view.samples![0];
    return vector ? { columns: ["x", "y", "z", "real x", "real y", "real z", "imag x", "imag y", "imag z", "magnitude"], units: [view.coordinate_unit!, view.coordinate_unit!, view.coordinate_unit!, ...Array(7).fill(view.value_unit!)], rows: view.samples!.map((sample, index) => { const real = sample.vector_real!, imag = sample.vector_imag!; return { index, values: [sample.x, sample.y, sample.z, ...real, ...imag, Math.hypot(...real, ...imag)] }; }) }
      : { columns: ["x", "y", "z", "real", "imag", "magnitude"], units: [view.coordinate_unit!, view.coordinate_unit!, view.coordinate_unit!, view.value_unit!, view.value_unit!, view.value_unit!], rows: view.samples!.map((sample, index) => ({ index, values: [sample.x, sample.y, sample.z, sample.value_real!, sample.value_imag!, Math.hypot(sample.value_real!, sample.value_imag!)] })) };
  }
  if (view.kind === "mesh") return { columns: ["x", "y", "z"], units: [view.coordinate_unit!, view.coordinate_unit!, view.coordinate_unit!], rows: view.vertices!.map((values, index) => ({ index, values })) };
  return { columns: [view.x_label!, ...view.series!.map(s => s.name)], units: [view.x_unit!, ...view.series!.map(() => view.y_unit!)], rows: view.x!.map((x, index) => ({ index, values: [x, ...view.series!.map(s => s.values[index])] })) };
}
export function dataCsv(columns: string[], rows: DataRow[], units: string[] = []): string {
  const escape = (v: Cell) => {
    let s = v === null ? "" : String(v);
    // Spreadsheet exports must not execute string cells as formulas.
    if (typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  };
  return ["sample_index," + columns.map((c, i) => escape(c + (units[i] ? " [" + units[i] + "]" : ""))).join(","), ...rows.map(r => r.index + "," + r.values.map(escape).join(","))].join("\r\n");
}
