// SPDX-License-Identifier: Apache-2.0
/** Restore GUI shape only. Worker preflight remains the physical admission gate. */
import { defaultOpenEMSSetup, openEMSFields, type OpenEMSSetup, type OpenEMSPort, type OpenEMSNumericKey } from "./openEMSSetup";
import { defaultEMergeSetup, type EMergeSetup } from "./EMergeExtension";

const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const text = (value: unknown, maximum = 1024): value is string => typeof value === "string" && value.length <= maximum;
function numeric(value: unknown, minimum = -Infinity, maximum = Infinity, integer = false): value is string {
  if (!text(value,128)) return false;
  if (!value.trim()) return true; // Preserve unfinished inputs; running still requires preflight.
  if (!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(value)) return false;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= minimum && parsed <= maximum && (!integer || Number.isInteger(parsed));
}
function triple(value: unknown): value is [string,string,string] {
  return Array.isArray(value) && value.length === 3 && value.every(v => numeric(v,-1e9,1e9));
}
function restoreScalars<T extends object>(defaults: T, value: unknown): T {
  const source = record(value), output = { ...defaults };
  for (const key of Object.keys(defaults) as (keyof T)[]) {
    const candidate = source[String(key)], fallback = defaults[key];
    if ((typeof fallback === "string" && text(candidate, String(key) === "python_executable" ? 4096 : String(key) === "shorting_via_ids" ? 2048 : 1024))
        || (typeof fallback === "boolean" && typeof candidate === "boolean")) output[key] = candidate as T[keyof T];
  }
  return output;
}

/** Oversized/malformed arrays reset whole fields, never truncate solver inputs. */
export function normalizeOpenEMSSetup(value: unknown): OpenEMSSetup {
  const source = record(value), defaults = defaultOpenEMSSetup();
  const output = restoreScalars(defaults,source);
  for (const key of Object.keys(openEMSFields) as OpenEMSNumericKey[]) {
    const field = openEMSFields[key];
    output[key] = numeric(source[key],field[2],field[3],field.length === 5) ? source[key] : defaults[key];
  }
  const nets = source.net_names;
  if (Array.isArray(nets) && nets.length <= 4096 && nets.every(net => text(net) && !!net.trim()) && new Set(nets).size === nets.length) output.net_names = [...nets];
  const boundaries = source.boundary_conditions;
  if (Array.isArray(boundaries) && boundaries.length === 6 && boundaries.every(v => text(v,16) && /^(PEC|PMC|MUR|PML_[1-9][0-9]?)$/.test(v))) output.boundary_conditions = [...boundaries];
  if (triple(source.center_mm)) output.center_mm = [...source.center_mm];
  const ports = source.ports;
  if (Array.isArray(ports) && ports.length <= 8) {
    const valid = ports.every(port => {
      const p = record(port);
      return triple(p.start) && triple(p.stop) && typeof p.direction === "string" && ["x","y","z"].includes(p.direction)
        && numeric(p.impedance_ohm,0,1e9) && typeof p.excite === "boolean";
    });
    if (valid) output.ports = ports.map(port => {
      const p = record(port);
      return {start:[...p.start as [string,string,string]], stop:[...p.stop as [string,string,string]],
        direction:p.direction as OpenEMSPort["direction"],impedance_ohm:p.impedance_ohm as string,excite:p.excite as boolean};
    });
  }
  const fieldBounds = {radius_m:[1e-6,1e6],theta_start_deg:[0,180],theta_stop_deg:[0,180],theta_points:[2,721],
    phi_start_deg:[-360,360],phi_stop_deg:[-360,360],phi_points:[2,1441],max_far_field_samples:[1,1000000]} as const;
  for (const key of Object.keys(fieldBounds) as (keyof typeof fieldBounds)[]) {
    const [minimum,maximum] = fieldBounds[key];
    output[key] = numeric(source[key],minimum,maximum,key.endsWith("points") || key.endsWith("samples")) ? source[key] : defaults[key];
  }
  const frequencyText = source.far_field_frequencies_hz;
  if (text(frequencyText,8192)) {
    const tokens = frequencyText.split(/[ ,;\n]+/).filter(Boolean);
    output.far_field_frequencies_hz = tokens.length <= 64 && tokens.every(v => numeric(v,0)) ? frequencyText : defaults.far_field_frequencies_hz;
  }
  return output;
}

export function normalizeEMergeSetup(value: unknown): EMergeSetup {
  const defaults = defaultEMergeSetup(), source = record(value), output = restoreScalars(defaults,source);
  const enums = {geometry_source:["board","gerber"],geometry_backend:["emerge","emcad"],sparse_solver:["auto","superlu"],
    field_excited_port:["1","2"],radiation_theta_step_deg:["5","10","15","30"],radiation_phi_step_deg:["5","10","15","30"]} as const;
  for (const key of Object.keys(enums) as (keyof typeof enums)[]) {
    if (!(enums[key] as readonly unknown[]).includes(source[key])) Object.assign(output,{[key]:defaults[key]});
  }
  const textKeys = new Set(["signal_net","return_net","signal_pad_id","return_pad_id","receive_signal_pad_id","receive_return_pad_id","python_executable","shorting_via_ids"]);
  const enumKeys = new Set(Object.keys(enums));
  for (const key of Object.keys(defaults) as (keyof EMergeSetup)[]) {
    if (typeof defaults[key] === "string" && !textKeys.has(key) && !enumKeys.has(key) && !numeric(source[key])) Object.assign(output,{[key]:defaults[key]});
  }
  return output;
}
