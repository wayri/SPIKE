// SPDX-License-Identifier: Apache-2.0
// UI admission only. Numerical qualification remains in the Python worker.
export const MULTIPORT_INPUT_BYTES = 8 * 1024 * 1024;
type RecordValue = Record<string, unknown>;
export type FixtureNetwork = { id: string; port_names: string[]; reference_impedance_ohm: number; frequencies_hz: number[]; s_parameters: { real: number; imag: number }[][][] };
export type FixtureRequest = { contract: string; measured: FixtureNetwork; fixture: FixtureNetwork; external_ports: string[]; dut_ports: string[] };
export type FixtureResult = { contract: string; model_status: string; production_qualified: false; source_request: FixtureRequest; derived_network: FixtureNetwork; diagnostics: RecordValue[]; limitations: string[]; input_digest: string };
const rec = (v: unknown): v is RecordValue => !!v && typeof v === "object" && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const names = (v: unknown): v is string[] => Array.isArray(v) && v.length > 0 && v.every(x => typeof x === "string" && x.trim().length > 0) && new Set(v).size === v.length;
const keys = (v: RecordValue, expected: string[]) => Object.keys(v).sort().join("|") === expected.sort().join("|");
export function structurallyEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => structurallyEqual(v, b[i]));
  return rec(a) && rec(b) && Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => Object.prototype.hasOwnProperty.call(b, k) && structurallyEqual(a[k], b[k]));
}
function network(v: unknown): v is FixtureNetwork {
  if (!rec(v) || !keys(v, ["id", "port_names", "reference_impedance_ohm", "frequencies_hz", "s_parameters"]) || typeof v.id !== "string" || !v.id.trim() || !names(v.port_names) || !finite(v.reference_impedance_ohm) || v.reference_impedance_ohm <= 0) return false;
  const f = v.frequencies_hz, n = v.port_names.length;
  return Array.isArray(f) && f.length > 0 && f.every((x, i) => finite(x) && x >= 0 && (!i || x > f[i - 1])) && Array.isArray(v.s_parameters) && v.s_parameters.length === f.length && v.s_parameters.every(m => Array.isArray(m) && m.length === n && m.every(row => Array.isArray(row) && row.length === n && row.every(z => rec(z) && keys(z, ["real", "imag"]) && finite(z.real) && finite(z.imag))));
}
export function parseFixtureRequest(text: string): FixtureRequest {
  if (new TextEncoder().encode(text).length > MULTIPORT_INPUT_BYTES) throw new Error("Request exceeds the 8 MiB import limit.");
  const v: unknown = JSON.parse(text);
  if (!rec(v) || !keys(v, ["contract", "measured", "fixture", "external_ports", "dut_ports"]) || v.contract !== "spike/multiport-deembedding-request/v1" || !network(v.measured) || !network(v.fixture) || !names(v.external_ports) || !names(v.dut_ports)) throw new Error("Supply a complete multiport request with finite sampled networks and explicit ordered port sets.");
  const n = v.measured.port_names.length;
  const fixture = v.fixture;
  if (fixture.port_names.length !== 2 * n || v.external_ports.length !== n || v.dut_ports.length !== n || !structurallyEqual(v.external_ports, v.measured.port_names) || new Set([...v.external_ports, ...v.dut_ports]).size !== 2 * n || [...v.external_ports, ...v.dut_ports].some(p => !fixture.port_names.includes(p)) || fixture.id === v.measured.id || fixture.reference_impedance_ohm !== v.measured.reference_impedance_ohm || !structurallyEqual(fixture.frequencies_hz, v.measured.frequencies_hz)) throw new Error("Networks require distinct IDs, identical grids/reference and complete disjoint exterior/DUT sets. Exterior order must match measured order.");
  return v as FixtureRequest;
}
export function admitFixtureResult(value: unknown, source: FixtureRequest): FixtureResult {
  const fields = ["frequency_hz", "transmission_condition_product", "outward_condition", "inward_condition", "recovery_condition", "feedback_condition", "max_solve_backward_residual", "reconstruction_residual", "sampled_smax"];
  if (!rec(value) || value.contract !== "spike/multiport-deembedding-result/v1" || value.model_status !== "experimental" || value.production_qualified !== false || !structurallyEqual(value.source_request, source) || !network(value.derived_network) || !structurallyEqual(value.derived_network.port_names, source.dut_ports) || value.derived_network.reference_impedance_ohm !== source.measured.reference_impedance_ohm || !structurallyEqual(value.derived_network.frequencies_hz, source.measured.frequencies_hz) || typeof value.input_digest !== "string" || !/^[a-f0-9]{64}$/.test(value.input_digest) || !Array.isArray(value.limitations) || !value.limitations.length || !value.limitations.every(x => typeof x === "string" && x.trim()) || !Array.isArray(value.diagnostics) || value.diagnostics.length !== source.measured.frequencies_hz.length || !value.diagnostics.every((d, i) => rec(d) && keys(d, fields.slice()) && fields.every(k => finite(d[k])) && d.frequency_hz === source.measured.frequencies_hz[i])) throw new Error("Worker returned an incomplete, mismatched or unsupported multiport result.");
  return JSON.parse(JSON.stringify(value)) as FixtureResult;
}
