// SPDX-License-Identifier: Apache-2.0
import { persistedEnginePython } from "./persistedEnginePython";
/** UI admission of solved source metadata; numerical interpretation stays in the adapter. */
export function optycalRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export type OptycalSource = {
  payload: Record<string, unknown>; radiation: Record<string, unknown>;
  frequencies: number[]; port: string; analysisId: string;
};

export type OptycalSetup = {
  step_path: string; frequency_hz: string; mesh_size_mm: string; observation_radius_m: string;
  theta_step_deg: string; phi_step_deg: string; python_executable: string;
  antenna_aperture_mm: string; source_phase_acknowledged: boolean;
  antenna_translation_mm: [string, string, string]; antenna_rotation_deg: [string, string, string];
  structure_translation_mm: [string, string, string]; structure_rotation_deg: [string, string, string];
};
export const defaultOptycalSetup = (): OptycalSetup => ({ step_path: "", frequency_hz: "", mesh_size_mm: "25", observation_radius_m: "100", theta_step_deg: "15", phi_step_deg: "30", python_executable: persistedEnginePython(), antenna_aperture_mm: "100", source_phase_acknowledged: false, antenna_translation_mm: ["0", "0", "0"], antenna_rotation_deg: ["0", "0", "0"], structure_translation_mm: ["0", "0", "1000"], structure_rotation_deg: ["0", "0", "0"] });

export function optycalParameters(setup: OptycalSetup, sourceResult: unknown): Record<string, unknown> {
  const source = admitOptycalSource(sourceResult);
  if (!source) throw new Error("Choose a completed EMerge radiation solve with complex 3D fields and recorded excitation metadata.");
  const number = (text: string, label: string, low: number, high: number) => {
    const value = Number(text);
    if (!text.trim() || !Number.isFinite(value) || value < low || value > high) throw new Error(`${label} must be between ${low} and ${high}.`);
    return value;
  };
  const frequency = Number(setup.frequency_hz || source.frequencies[0]);
  if (!source.frequencies.includes(frequency)) throw new Error("Choose an actually solved EMerge frequency.");
  if (!/\.(step|stp)$/i.test(setup.step_path.trim())) throw new Error("Select a local STEP or STP structure file.");
  if (!setup.source_phase_acknowledged) throw new Error("Acknowledge the explicit EMerge far-field phase convention assumption before generating this study.");
  const output: Record<string, unknown> = { emerge_analysis_result: source.payload, frequency_hz: frequency, step_path: setup.step_path.trim(), mesh_size_mm: number(setup.mesh_size_mm, "Structure mesh size (mm)", 0.1, 1000), observation_radius_m: number(setup.observation_radius_m, "Observation radius (m)", 0.01, 100000) };
  output.antenna_aperture_mm = number(setup.antenna_aperture_mm, "Largest antenna physical extent (mm)", 0.001, 10000);
  output.source_phase_assumption = "emerge_farfield_coefficient_e_plus_jwt";
  for (const key of ["theta_step_deg", "phi_step_deg"] as const) {
    const step = Number(setup[key]);
    if (![5, 10, 15, 30].includes(step)) throw new Error("Angular steps must be 5, 10, 15 or 30 degrees.");
    output[key] = step;
  }
  for (const key of ["antenna_translation_mm", "structure_translation_mm", "antenna_rotation_deg", "structure_rotation_deg"] as const) {
    const rotation = key.endsWith("rotation_deg");
    output[key] = setup[key].map((text, axis) => number(text, `${key.startsWith("antenna") ? "Antenna" : "Structure"} ${rotation ? "rotation" : "translation"} ${"XYZ"[axis]}`, rotation ? -360 : -100000, rotation ? 360 : 100000));
  }
  if (setup.python_executable.trim()) output.python_executable = setup.python_executable.trim();
  return output;
}

export function admitOptycalSource(value: unknown): OptycalSource | null {
  const envelope = optycalRecord(value);
  const payload = optycalRecord(optycalRecord(envelope.data).analysis_result ?? envelope.analysis_result ?? value);
  if (payload.contract !== "spike/v1" || !["completed", "completed_with_warnings"].includes(String(payload.status)) || !["unvalidated", "approximate", "validated", "reference_validated"].includes(String(payload.model_status))
      || typeof payload.analysis_id !== "string" || !payload.analysis_id.trim()) return null;
  const provenance = optycalRecord(payload.provenance);
  const digest = (value: unknown) => typeof value === "string" && /^[a-f0-9]{64}$/i.test(value);
  if (typeof provenance.solver !== "string" || !provenance.solver.startsWith("EMerge/") || provenance.extension_id !== "spike.emerge-suite"
      || typeof provenance.design_id !== "string" || !provenance.design_id.trim() || !digest(provenance.design_digest_sha256)
      || !digest(provenance.board_case_sha256) || !digest(provenance.generated_script_sha256)) return null;
  const radiation = optycalRecord(optycalRecord(payload.fields).radiation);
  const frequencies = radiation.frequencies_hz;
  const patterns = radiation.patterns_3d;
  if (radiation.contract !== "spike/emerge-radiation-cuts/v1" || !Array.isArray(frequencies) || frequencies.length < 1 || frequencies.length > 64
      || frequencies.some((frequency, index) => typeof frequency !== "number" || !Number.isFinite(frequency) || frequency <= 0 || index > 0 && frequency <= frequencies[index - 1])
      || !Array.isArray(patterns) || patterns.length !== frequencies.length
      || typeof radiation.excitation_port !== "string" || !radiation.excitation_port) return null;
  let total = 0;
  const pair = (value: unknown) => Array.isArray(value) && value.length === 2 && value.every(part => typeof part === "number" && Number.isFinite(part));
  const ports = radiation.excitation_ports, coefficients = radiation.excitation_coefficients;
  if (!Array.isArray(ports) || ports.length < 1 || ports.length > 32 || !ports.every(port => typeof port === "string" && port.length > 0)
      || new Set(ports).size !== ports.length || !ports.includes(radiation.excitation_port)
      || !Array.isArray(coefficients) || coefficients.length !== ports.length
      || coefficients.some((value, index) => !pair(value) || value[0] !== (ports[index] === radiation.excitation_port ? 1 : 0) || value[1] !== 0)) return null;
  for (let i = 0; i < patterns.length; i++) {
    const pattern = optycalRecord(patterns[i]);
    const theta = pattern.theta_deg, phi = pattern.phi_deg;
    const grid = (value: unknown, minimum: number, end: number): value is number[] => Array.isArray(value) && value.length >= minimum && value[0] === 0 && value[value.length - 1] === end && value.every((angle, index) => typeof angle === "number" && Number.isFinite(angle) && (index === 0 || angle > value[index - 1]));
    if (pattern.frequency_hz !== frequencies[i] || !grid(theta, 3, 180) || !grid(phi, 4, 360)) return null;
    const count = theta.length * phi.length;
    total += count;
    if (total > 100000 || !Array.isArray(pattern.e_theta_v_m) || !Array.isArray(pattern.e_phi_v_m)
        || pattern.e_theta_v_m.length !== count || pattern.e_phi_v_m.length !== count
        || !pattern.e_theta_v_m.every(pair) || !pattern.e_phi_v_m.every(pair)) return null;
  }
  return { payload, radiation, frequencies: frequencies as number[], port: radiation.excitation_port, analysisId: String(payload.analysis_id ?? "EMerge source") };
}

export type OptycalComparison = { theta: number[]; phi: number[]; series: Record<string, number[]>; complex: Record<string, [number, number][][]> };
export function admitOptycalComparison(value: Record<string, unknown>): OptycalComparison | null {
  if (value.contract !== "spike/optycal-pattern-comparison/v1" || typeof value.frequency_hz !== "number" || !Number.isFinite(value.frequency_hz) || value.frequency_hz <= 0) return null;
  const theta = value.theta_deg, phi = value.phi_deg;
  const grid = (input: unknown, end: number): input is number[] => Array.isArray(input) && input.length >= 3 && input[0] === 0 && input[input.length - 1] === end && input.every((angle, index) => typeof angle === "number" && Number.isFinite(angle) && (index === 0 || angle > input[index - 1]));
  if (!grid(theta, 180) || !grid(phi, 360) || theta.length * phi.length > 100000) return null;
  const series: Record<string, number[]> = {};
  for (const key of ["bare_relative_db", "structure_relative_db", "delta_db", "interference_cross_term"]) {
    const array = value[key];
    if (!Array.isArray(array) || array.length !== theta.length * phi.length || !array.every(item => typeof item === "number" && Number.isFinite(item) && (key === "interference_cross_term" || Math.abs(item) <= 600))) return null;
    series[key] = array as number[];
  }
  const complex: Record<string, [number, number][][]> = {};
  for (const key of ["direct_e_xyz", "scattered_e_xyz", "total_e_xyz"]) {
    const array = value[key];
    if (!Array.isArray(array) || array.length !== theta.length * phi.length || !array.every(vector => Array.isArray(vector) && vector.length === 3 && vector.every(pair => Array.isArray(pair) && pair.length === 2 && pair.every(part => typeof part === "number" && Number.isFinite(part))))) return null;
    complex[key] = array as [number, number][][];
  }
  return { theta, phi, series, complex };
}
