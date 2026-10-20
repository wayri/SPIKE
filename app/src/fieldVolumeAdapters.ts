// SPDX-License-Identifier: Apache-2.0
import type { FieldVolumeData } from "./fieldVolumeModel";
import type { CavityResult } from "./nativeCfdPresentation";

type Row = Record<string, any>;
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const pointKey = (point: number[], region: unknown) => `${String(region ?? "")}\0${point.join("\0")}`;

/** Adapt the admitted 2-D cavity cells to a display-only one-cell-thick sheet. */
export function nativeCavityFieldVolume(result: CavityResult): FieldVolumeData | null {
  const fields = result.fields, n = result.settings.n;
  if (result.status !== "converged" || !fields || n < 1) return null;
  const count = n * n, width = 1 / n;
  if (["x_m", "y_m", "u_m_s", "v_m_s", "pressure_pa"].some(key => !Array.isArray(fields[key]) || fields[key].length !== count)) return null;
  const centers: [number, number, number][] = [], sizes: [number, number, number][] = [];
  const speed: number[] = [], pressure: number[] = [], vectors: [number, number, number][] = [];
  for (let i = 0; i < count; i++) {
    const x = fields.x_m[i], y = fields.y_m[i], u = fields.u_m_s[i], v = fields.v_m_s[i], p = fields.pressure_pa[i];
    if (![x, y, u, v, p].every(finite)) return null;
    centers.push([x, y, 0]); sizes.push([width, width, width]);
    speed.push(Math.hypot(u, v)); pressure.push(p); vectors.push([u, v, 0]);
  }
  return { contract: "spike/field-volume-view/v1", id: `native-cavity-${n}-${result.settings.reynolds}`,
    label: "Native cavity returned fields", lengthUnit: "m",
    geometryNote: "The solver is two-dimensional. Z thickness is a one-cell display sheet and has no physical 3D meaning.",
    cells: { centers, sizes }, quantities: [
      { id: "speed_m_s", label: "Velocity magnitude", unit: "m/s" },
      { id: "pressure_pa", label: "Gauge pressure", unit: "Pa" },
    ], frames: [{ timeS: result.diagnostics.time, scalars: { speed_m_s: speed, pressure_pa: pressure }, vectors }] };
}

/** Adapt aligned, solver-returned fluid cell-centre samples without inventing cell sizes. */
export function assemblyAirflowFieldVolume(result: Row): FieldVolumeData | null {
  if (result?.contract !== "spike/thermal-field-result/v1" || result?.status !== "completed" || result?.model_status !== "experimental"
      || result?.qualification?.production_qualified !== false) return null;
  const temperature = result.fields?.temperature_k, velocity = result.fields?.velocity_m_s;
  if (temperature?.unit !== "K" || velocity?.unit !== "m/s" || !Array.isArray(temperature.samples) || !Array.isArray(velocity.samples)) return null;
  const temperatures = new Map<string, number>();
  for (const sample of temperature.samples) {
    if (!Array.isArray(sample?.point_mm) || sample.point_mm.length !== 3 || !sample.point_mm.every(finite) || !finite(sample.value)) return null;
    temperatures.set(pointKey(sample.point_mm, sample.region), sample.value);
  }
  const centers: [number, number, number][] = [], vectors: [number, number, number][] = [], temperatureK: number[] = [], speed: number[] = [];
  for (const sample of velocity.samples) {
    if (!Array.isArray(sample?.point_mm) || sample.point_mm.length !== 3 || !sample.point_mm.every(finite)
        || !Array.isArray(sample.value) || sample.value.length !== 3 || !sample.value.every(finite)) return null;
    const thermal = temperatures.get(pointKey(sample.point_mm, sample.region));
    if (!finite(thermal)) return null;
    const point = sample.point_mm as [number, number, number], vector = sample.value as [number, number, number];
    centers.push([...point]); vectors.push([...vector]); temperatureK.push(thermal); speed.push(Math.hypot(...vector));
  }
  if (!centers.length) return null;
  return { contract: "spike/field-volume-view/v1", id: String(result.job_id || result.plan_digest || "assembly-airflow"),
    label: "Assembly airflow returned fluid samples", lengthUnit: "mm",
    geometryNote: "Returned fluid cell centres only; cell sizes and interpolated volume geometry were not supplied by this result.",
    cells: { centers }, quantities: [
      { id: "temperature_k", label: "Temperature", unit: "K" },
      { id: "speed_m_s", label: "Velocity magnitude", unit: "m/s" },
    ], frames: [{ timeS: 0, scalars: { temperature_k: temperatureK, speed_m_s: speed }, vectors }] };
}
