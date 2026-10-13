import { retainedEmPreview } from "./retainedAssemblyEm";
// SPDX-License-Identifier: Apache-2.0
import { admitEMergeFieldPlanes, type Vector } from "./emergeNearFieldSamples";
import { admitOpenEMSFarfield, openEMSFarfieldVectors } from "./openEMSFarfield";
import { admitOptycalComparison, optycalRecord as rec } from "./optycalStudy";

export type EMViewportRecord = { id: string; label: string; result: Record<string, unknown> };
export type EMViewportSettings = {
  visible: boolean; frequencyIndex: number; quantity: string; component: "norm" | "x" | "y" | "z";
  projection: "magnitude" | "real" | "imaginary" | "phase" | "instantaneous"; phaseDeg: number;
  style: "surface" | "samples" | "vectors" | "contours"; opacity: number; displayRadiusMm: number;
  nodes: boolean; antinodes: boolean; thresholdPct: number; showStructure: boolean; selectedSample: number;
};
export const defaultEMViewportSettings: EMViewportSettings = { visible: true, frequencyIndex: 0, quantity: "far_e", component: "norm", projection: "magnitude", phaseDeg: 0, style: "surface", opacity: .45, displayRadiusMm: 40, nodes: false, antinodes: false, thresholdPct: 5, showStructure: true, selectedSample: 0 };
export type EMViewportData = {
  domain: "spatial" | "angular"; frequencyHz: number; label: string; unit: string;
  positionsMm: [number, number, number][]; indices: number[]; values: (number | null)[];
  directions: ([number, number, number] | null)[]; highlights: ("node" | "antinode" | null)[];
  range: [number, number]; notices: string[]; structure?: { vertices_mm: number[][]; triangles: number[][] };
  angularNeedsBoardAnchor?: boolean; assemblyFrame?: boolean; nativeSampleIndices?: number[];
};
export function emViewportPayload(value: unknown): Record<string, unknown> {
  const envelope = rec(value);
  const payload = rec(rec(envelope.data).analysis_result ?? envelope.analysis_result ?? value);
  return { ...payload, fields: payload.em_fields ?? payload.fields, networks: payload.em_networks ?? payload.networks };
}
export function availableEMQuantities(record: EMViewportRecord): { id: string; label: string }[] {
  const f = rec(emViewportPayload(record.result).fields), result = [];
  if (retainedEmPreview(f.retained_volume, "volume_e")) result.push({id:"volume_e",label:"Assembly electric field"});
  if (retainedEmPreview(f.retained_volume, "volume_h")) result.push({id:"volume_h",label:"Assembly magnetic field"});
  if (Array.isArray(rec(f.radiation).patterns_3d) || admitOpenEMSFarfield(f.openems_far_field)) result.push({ id: "far_e", label: "Far-field E pattern" });
  if (admitEMergeFieldPlanes(f.nearfield).length) result.push({ id: "near_e", label: "Spatial electric field" }, { id: "near_h", label: "Spatial magnetic field" }, { id: "poynting", label: "Time-average Poynting vector" });
  if (admitOptycalComparison(rec(f.comparison))) result.push({ id: "bare_e", label: "Bare antenna" }, { id: "scattered_e", label: "Scattered field" }, { id: "installed_e", label: "Antenna + structure" }, { id: "pattern_delta", label: "Installed / bare change" }, { id: "interference", label: "Coherent interference" });
  return result;
}
export function emResultFrequencies(record: EMViewportRecord): number[] {
  const f = rec(emViewportPayload(record.result).fields);
  const arrays = [[rec(f.retained_volume).frequency_hz], rec(f.radiation).frequencies_hz, rec(f.nearfield).frequencies_hz, admitOpenEMSFarfield(f.openems_far_field)?.frequencies, rec(rec(emViewportPayload(record.result).networks).s_parameters).frequencies_hz];
  return [...new Set(arrays.flatMap(values => Array.isArray(values) ? values.filter((v): v is number => typeof v === "number" && Number.isFinite(v) && v > 0) : []))].sort((a, b) => a - b);
}
function project(v: Vector, s: EMViewportSettings): number | null {
  if (s.component === "norm") return s.projection === "magnitude" ? Math.hypot(...v.flat()) : null;
  const [r, i] = v[{ x: 0, y: 1, z: 2 }[s.component]];
  if (s.projection === "phase") return r === 0 && i === 0 ? null : Math.atan2(i, r) * 180 / Math.PI;
  if (s.projection === "real") return r;
  if (s.projection === "imaginary") return i;
  if (s.projection === "instantaneous") return r * Math.cos(s.phaseDeg * Math.PI / 180) - i * Math.sin(s.phaseDeg * Math.PI / 180);
  return Math.hypot(r, i);
}
function triangles(ny: number, nx: number, values: (number | null)[]): number[] {
  const out: number[] = [];
  for (let y = 0; y < ny - 1; y++) for (let x = 0; x < nx - 1; x++) {
    const a = y * nx + x;
    for (const tri of [[a, a + nx, a + 1], [a + 1, a + nx, a + nx + 1]]) if (tri.every(i => values[i] !== null)) out.push(...tri);
  }
  return out;
}
function poynting(e: Vector, h: Vector): Vector {
  return [0, 1, 2].map(i => { const j = (i + 1) % 3, k = (i + 2) % 3;
    return [.5 * (e[j][0] * h[k][0] + e[j][1] * h[k][1] - e[k][0] * h[j][0] - e[k][1] * h[j][1]), 0];
  });
}
export function buildEMViewportData(record: EMViewportRecord, s: EMViewportSettings): EMViewportData | null {
  const payload = emViewportPayload(record.result);
  if (!["completed", "completed_with_warnings", "solved"].includes(String(payload.status)) || !s.visible || !Number.isInteger(s.frequencyIndex) || s.frequencyIndex < 0
    || !Number.isFinite(s.phaseDeg) || !Number.isFinite(s.displayRadiusMm) || s.displayRadiusMm <= 0 || s.displayRadiusMm > 100000
    || !Number.isFinite(s.thresholdPct) || s.thresholdPct < 0 || s.thresholdPct > 50) return null;
  if (!availableEMQuantities(record).some(q => q.id === s.quantity)) return null;
  const fields = rec(payload.fields), frequencies = emResultFrequencies(record), frequencyHz = frequencies[s.frequencyIndex];
  if (!frequencyHz) return null;
  let domain: "spatial" | "angular" = "angular", unit = "arbitrary coherent units";
  let positionsMm: [number, number, number][] = [], vectors: (Vector | null)[] = [], values: (number | null)[] = [], ny = 0, nx = 0;
  const notices = ["Only returned samples are probed. Surfaces and contours connect samples for display; they do not create solved field data."];
  let angularNeedsBoardAnchor = false;
  if (["volume_e","volume_h"].includes(s.quantity)) {
    const preview=retainedEmPreview(fields.retained_volume,s.quantity);
    if(!preview || preview.frequencyHz!==frequencyHz)return null;
    const values=preview.vectors.map(v=>project(v,s));
    const valid=values.filter((v):v is number=>v!==null&&Number.isFinite(v));
    if(!valid.length || values.some(v=>v!==null&&!Number.isFinite(v)))return null;
    return {domain:"spatial",frequencyHz,label:s.quantity==="volume_e"?"Assembly electric field":"Assembly magnetic field",
      unit:s.projection==="phase"?"degrees":preview.unit,positionsMm:preview.positionsMm,indices:[],values,
      directions:preview.vectors.map(v=>v.map(([r,i])=>r*Math.cos(s.phaseDeg*Math.PI/180)-i*Math.sin(s.phaseDeg*Math.PI/180)) as [number,number,number]),
      highlights:values.map(()=>null),range:[valid.reduce((a,b)=>Math.min(a,b),Infinity),valid.reduce((a,b)=>Math.max(a,b),-Infinity)],assemblyFrame:true,nativeSampleIndices:preview.nativeIndices,
      notices:[`${values.length} retained samples of ${preview.sourceSampleCount}; displayed sampling adds no solved resolution.`,
        "Assembly-frame coordinates; 1 V peak incident phasor normalization. No EMI compliance or hardware qualification.",
        "Volume data is shown as samples/vectors; no interpolated surface is inferred."]};
  }
  if (["near_e", "near_h", "poynting"].includes(s.quantity)) {
    const plane = admitEMergeFieldPlanes(fields.nearfield).find(p => p.frequency_hz === frequencyHz);
    if (!plane) return null;
    domain = "spatial"; [ny, nx] = plane.grid_shape; positionsMm = plane.coordinates_mm as [number, number, number][];
    vectors = plane.valid.map((valid, i) => valid ? s.quantity === "poynting" ? poynting(plane.e_v_m[i]!, plane.h_a_m[i]!) : plane[s.quantity === "near_e" ? "e_v_m" : "h_a_m"][i] : null);
    unit = s.quantity === "near_e" ? "V/m (solver excitation)" : s.quantity === "near_h" ? "A/m (solver excitation)" : "W/m² (solver excitation)";
    notices.push("Physical coordinates are millimetres in the solver/board frame. Invalid FEM samples remain holes; no field is painted onto unrelated CAD surfaces.");
  } else {
    const openems = s.quantity === "far_e" ? admitOpenEMSFarfield(fields.openems_far_field) : null;
    const comparison = rec(fields.comparison).frequency_hz === frequencyHz ? admitOptycalComparison(rec(fields.comparison)) : null;
    const raw = rec((rec(fields.radiation).patterns_3d as unknown[] | undefined)?.find(p => rec(p).frequency_hz === frequencyHz));
    const theta = openems ? openems.theta : comparison ? comparison.theta : raw.theta_deg, phi = openems ? openems.phi : comparison ? comparison.phi : raw.phi_deg;
    if (!openems) {
    if (!Array.isArray(theta) || !Array.isArray(phi) || theta.length < 3 || phi.length < 4 || theta[0] !== 0 || theta[theta.length - 1] !== 180 || phi[0] !== 0 || phi[phi.length - 1] !== 360 || theta.some((v, i) => !Number.isFinite(v) || i > 0 && v <= theta[i - 1]) || phi.some((v, i) => !Number.isFinite(v) || i > 0 && v <= phi[i - 1]) || theta.length * phi.length > 100000) return null;
    }
    if (!Array.isArray(theta) || !Array.isArray(phi)) return null;
    ny = theta.length; nx = phi.length;
    if (openems) {
      vectors = openEMSFarfieldVectors(openems, openems.frequencies.indexOf(frequencyHz)) ?? [];
      if (!vectors.length) return null;
      unit = `V/m peak at ${openems.radiusM} m · 1 W incident`;
      notices.push("OpenEMS NF2FF output remains not validated. Complex fields use the returned normalization; no EMerge source or phase-convention conversion is performed.");
    } else if (comparison && s.quantity !== "far_e") {
      if (s.quantity === "pattern_delta" || s.quantity === "interference") {
        values = comparison.series[s.quantity === "pattern_delta" ? "delta_db" : "interference_cross_term"];
        unit = s.quantity === "pattern_delta" ? "dB / bare" : "cross term / bare peak |E|²";
      } else vectors = comparison.complex[{ bare_e: "direct_e_xyz", scattered_e: "scattered_e_xyz", installed_e: "total_e_xyz" }[s.quantity] ?? "total_e_xyz"];
    } else {
      const et = raw.e_theta_v_m, ep = raw.e_phi_v_m;
      const pair = (v: unknown): v is [number, number] => Array.isArray(v) && v.length === 2 && v.every(n => typeof n === "number" && Number.isFinite(n));
      if (!Array.isArray(et) || !Array.isArray(ep) || et.length !== ny * nx || ep.length !== et.length || !et.every(pair) || !ep.every(pair)) return null;
      vectors = et.map((v, i) => { const t = theta[Math.floor(i / nx)] * Math.PI / 180, p = phi[i % nx] * Math.PI / 180;
        const a = [Math.cos(t) * Math.cos(p), Math.cos(t) * Math.sin(p), -Math.sin(t)], b = [-Math.sin(p), Math.cos(p), 0];
        return a.map((n, k) => [n * v[0] + b[k] * ep[i][0], n * v[1] + b[k] * ep[i][1]]);
      });
    }
    const origin = openems ? openems.centerMm : rec(rec(payload.summary).setup).antenna_translation_mm;
    angularNeedsBoardAnchor = !(Array.isArray(origin) && origin.length === 3 && origin.every(Number.isFinite));
    const center = Array.isArray(origin) && origin.length === 3 && origin.every(Number.isFinite) ? origin : [0, 0, 0];
    const amplitudes = vectors.map(v => v ? Math.hypot(...v.flat()) : 0), peak = amplitudes.reduce((m, v) => Math.max(m, v), 1e-300);
    positionsMm = theta.flatMap(t => phi.map(p => { const tr = t * Math.PI / 180, pr = p * Math.PI / 180;
      return [center[0] + s.displayRadiusMm * Math.sin(tr) * Math.cos(pr), center[1] + s.displayRadiusMm * Math.sin(tr) * Math.sin(pr), center[2] + s.displayRadiusMm * Math.cos(tr)] as [number, number, number];
    }));
    const referencePeak = comparison ? comparison.complex.direct_e_xyz.reduce((m, v) => Math.max(m, Math.hypot(...v.flat())), 1e-300) : peak;
    if (vectors.length) positionsMm = positionsMm.map((p, i) => p.map((v, k) => center[k] + (v - center[k]) * Math.max(.02, amplitudes[i] / referencePeak)) as [number, number, number]);
    notices.push("Far-field radius is a display encoding, not physical distance. Angular minima are radiation null candidates, not spatial standing-wave nodes.");
  }
  if (!values.length) values = vectors.map(v => v ? project(v, s) : null);
  if (values.length !== ny * nx || values.some(v => v !== null && !Number.isFinite(v))) return null;
  const directions = vectors.length ? vectors.map(v => v ? v.map(pair => pair[0] * Math.cos(s.phaseDeg * Math.PI / 180) - pair[1] * Math.sin(s.phaseDeg * Math.PI / 180)) as [number, number, number] : null) : values.map(() => null);
  const finite = values.filter((v): v is number => v !== null), low = finite.reduce((m, v) => Math.min(m, v), Infinity), high = finite.reduce((m, v) => Math.max(m, v), -Infinity);
  if (!finite.length) return null;
  const amplitudes = vectors.map(v => v ? s.component === "norm" ? Math.hypot(...v.flat()) : Math.hypot(...v[{ x: 0, y: 1, z: 2 }[s.component]]) : null);
  const peak = amplitudes.reduce<number>((m, v) => Math.max(m, v ?? 0), 0);
  const highlights = values.map((value, i) => value === null || !peak || s.quantity === "poynting" || s.projection !== "magnitude" || amplitudes[i] === null ? null : amplitudes[i]! <= peak * s.thresholdPct / 100 ? "node" : amplitudes[i]! >= peak * (1 - s.thresholdPct / 100) ? "antinode" : null);
  notices.push("Node/antinode highlights are low/high phasor-amplitude threshold candidates on solved samples, not a proof of standing-wave nodes.");
  const structureRaw = rec(fields.structure_mesh);
  const structure = structureRaw.contract === "spike/optycal-structure-mesh/v1" && Array.isArray(structureRaw.vertices_mm) && Array.isArray(structureRaw.triangles) ? { vertices_mm: structureRaw.vertices_mm as number[][], triangles: structureRaw.triangles as number[][] } : undefined;
  if (s.projection === "phase") unit = "degrees";
  return { domain, frequencyHz, label: availableEMQuantities(record).find(q => q.id === s.quantity)?.label ?? s.quantity, unit, positionsMm, indices: triangles(ny, nx, values), values, directions, highlights, range: [low, high], notices, structure, angularNeedsBoardAnchor };
}
