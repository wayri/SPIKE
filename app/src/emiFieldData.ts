import type { EmiFarFieldResult } from "./EmiWorkbench";

export const fieldDbUvM = (value: number) => value > 0 && Number.isFinite(value) ? 20 * Math.log10(value) + 120 : null;

export function validEmiFarField(raw: unknown): raw is EmiFarFieldResult {
  if (!raw || typeof raw !== "object") return false;
  const f = raw as EmiFarFieldResult;
  const finite = (v: unknown, length?: number): v is number[] => Array.isArray(v) && (length === undefined || v.length === length) && v.every(n => typeof n === "number" && Number.isFinite(n));
  if (f.contract !== "spike/openems-far-field-result/v1" || !finite(f.frequencies_hz) || !finite(f.theta_deg) || !finite(f.phi_deg)) return false;
  const [nf, nt, np] = [f.frequencies_hz.length, f.theta_deg.length, f.phi_deg.length];
  const count = nf * nt * np;
  if (!nf || nt < 2 || np < 2 || count > 250000 || !finite(f.shape, 3) || f.shape.some((v, i) => v !== [nf, nt, np][i])) return false;
  if (!f.frequencies_hz.every((v, i, a) => v > 0 && (!i || v > a[i - 1]))) return false;
  if (![f.theta_deg, f.phi_deg].every(a => a.every((v, i) => !i || v > a[i - 1]))) return false;
  if (!finite(f.e_field_v_m?.magnitude, count) || f.e_field_v_m.magnitude.some(v => v < 0)) return false;
  if (!finite(f.directivity?.linear, count) || f.directivity.linear.some(v => v < 0) || !finite(f.directivity?.maximum_linear, nf)) return false;
  if (!finite(f.radiated_power?.total_w, nf) || f.radiated_power.total_w.some(v => v < 0)) return false;
  if (!Number.isFinite(f.radius_m) || f.radius_m <= 0 || !finite(f.center_mm, 3) || typeof f.validation_status !== "string") return false;
  return true;
}

export function emiSpectrum(field: EmiFarFieldResult) {
  const angularCount = field.theta_deg.length * field.phi_deg.length;
  return field.frequencies_hz.map((frequency, index) => {
    let peak = 0, peakIndex = 0;
    for (let j = 0; j < angularCount; j++) {
      const value = field.e_field_v_m.magnitude[index * angularCount + j];
      if (value > peak) { peak = value; peakIndex = j; }
    }
    return { frequency, peak, db: fieldDbUvM(peak), theta: field.theta_deg[Math.floor(peakIndex / field.phi_deg.length)], phi: field.phi_deg[peakIndex % field.phi_deg.length] };
  });
}
