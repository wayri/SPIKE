// SPDX-License-Identifier: Apache-2.0
export type SolverParameters = Record<string, unknown>;
export interface ExternalSolverProps {
  parameters: SolverParameters;
  onParameters: (parameters: SolverParameters) => void;
  result?: unknown;
  busy?: boolean;
  disabled?: boolean;
  onExecute: (contributionId: string, parameters: SolverParameters) => void | Promise<void>;
  onCancel?: () => void;
}
export const solverRecord = (value: unknown): SolverParameters => value && typeof value === "object" && !Array.isArray(value) ? value as SolverParameters : {};
export function solverResultData(value: unknown): SolverParameters {
  const envelope = solverRecord(value);
  return envelope.data && typeof envelope.data === "object" ? solverRecord(envelope.data) : envelope;
}
export function parseSolverJson(text: string, label: string): SolverParameters {
  let parsed: unknown;
  try { parsed = JSON.parse(text); } catch { throw new Error(`${label} must be valid JSON.`); }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(`${label} must be a JSON object.`);
  return parsed as SolverParameters;
}
export async function readSolverText(file: File, limit = 8 * 1024 * 1024): Promise<string> {
  if (file.size > limit) throw new Error(`File exceeds the ${limit / 1024 / 1024} MiB import limit.`);
  return file.text();
}
export function xyceParameters(value: SolverParameters, operation: string): SolverParameters {
  if (operation !== "preflight" && operation !== "inspect" && !String(value.netlist ?? "").trim()) throw new Error("Enter or import a Xyce netlist before preparing, validating or running.");
  const options = solverRecord(value.engine_options);
  for (const key of ["timeout_seconds", "memory_limit_mib"]) {
    const number = Number(options[key]);
    if (!Number.isFinite(number) || number <= 0) throw new Error(`${key} must be a positive finite number.`);
  }
  return { ...value, operation, engine_options: { ...options, executable: String(options.executable ?? "").trim() || undefined, timeout_seconds: Number(options.timeout_seconds), memory_limit_mib: Number(options.memory_limit_mib) } };
}
export function defaultXyceParameters(): SolverParameters {
  return { operation: "prepare", netlist: "", libraries: [], engine_options: { executable: "", timeout_seconds: 300, memory_limit_mib: 2048 } };
}
export function defaultPalaceParameters(): SolverParameters {
  return { config: { Problem: { Type: "Driven" }, Model: {}, Domains: {}, Boundaries: {}, Solver: {} }, mesh_path: "", expected_mesh_sha256: "", runtime_path: "", timeout_s: 180, memory_limit_mb: 2048, threads: 1 };
}
export function palaceParameters(value: SolverParameters, operation: string): SolverParameters {
  if (operation !== "discover") {
    if (!String(value.mesh_path ?? "").trim()) throw new Error("Choose an absolute local mesh path.");
    const config = solverRecord(value.config);
    for (const section of ["Problem", "Model", "Domains", "Boundaries", "Solver"]) if (!config[section] || typeof config[section] !== "object" || Array.isArray(config[section])) throw new Error(`Native config requires a ${section} object.`);
    if (operation === "run" && !/^[a-fA-F0-9]{64}$/.test(String(value.expected_mesh_sha256 ?? ""))) throw new Error("Review and accept the prepared mesh SHA-256 before running.");
  }
  for (const [key, low, high] of [["timeout_s", 1, 3300], ["memory_limit_mb", 256, 32768], ["threads", 1, 1]] as const) {
    const number = Number(value[key]);
    if (!Number.isInteger(number) || number < low || number > high) throw new Error(`${key} must be an integer between ${low} and ${high}.`);
  }
  return { ...value, runtime_path: String(value.runtime_path ?? "").trim() || undefined, expected_mesh_sha256: String(value.expected_mesh_sha256 ?? "").trim() || undefined, timeout_s: Number(value.timeout_s), memory_limit_mb: Number(value.memory_limit_mb), threads: Number(value.threads) };
}
export interface SolverTable { name: string; columns: { name: string; unit: string }[]; rows: number[][] }
export function solverTables(value: unknown): SolverTable[] {
  const data = solverResultData(value);
  const source = Array.isArray(data.waveforms) ? data.waveforms : Array.isArray(data.tables) ? data.tables : [];
  return source.flatMap(item => {
    const table = solverRecord(item);
    const rawColumns = Array.isArray(table.columns) ? table.columns : table.headers;
    if (!Array.isArray(rawColumns) || !Array.isArray(table.rows)) return [];
    const columns = rawColumns.map(column => typeof column === "string" ? { name: column, unit: "" } : { name: String(solverRecord(column).name ?? ""), unit: String(solverRecord(column).unit ?? "") });
    const rows = table.rows.flatMap(row => {
      if (!Array.isArray(row) || row.length !== columns.length || row.some(value => (typeof value === "string" && !value.trim()) || value === null || (typeof value !== "number" && typeof value !== "string"))) return [];
      const values = row.map(Number);
      return values.every(Number.isFinite) ? [values] : [];
    });
    return columns.length ? [{ name: String(table.name ?? "Returned samples"), columns, rows }] : [];
  });
}
