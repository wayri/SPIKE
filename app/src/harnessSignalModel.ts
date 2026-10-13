// SPDX-License-Identifier: Apache-2.0
export const HARNESS_SI_KEY = "spike.harness-si";
export const HARNESS_SI_FIELDS = {
  length_m: "Modeled length (m)", resistance_ohm_per_m: "Loop/modal R (Ω/m)", inductance_h_per_m: "Loop/modal L (H/m)",
  capacitance_f_per_m: "Loop/modal C (F/m)", loss_tangent: "Dielectric loss tangent", reference_impedance_ohm: "Port reference (Ω)",
  frequency_stop_hz: "Maximum frequency (Hz)", frequency_points: "Frequency samples",
};
export function harnessSignalRequest(value: Record<string, any>, setup: Record<string, any>) {
  if (typeof setup.source !== "string" || !setup.source.trim()) throw new Error("Record the source of the supplied RLGC model.");
  const harness = structuredClone(value);
  if (harness.extensions) delete harness.extensions[HARNESS_SI_KEY];
  const model: Record<string, any> = { kind: "rlgc", coupled: false, inductive_coupling: 0, capacitive_coupling: 0 };
  for (const key of Object.keys(HARNESS_SI_FIELDS)) {
    const raw = setup.model_input?.[key];
    if (raw === undefined || raw === "" || !Number.isFinite(Number(raw))) throw new Error(`Enter ${HARNESS_SI_FIELDS[key as keyof typeof HARNESS_SI_FIELDS]}.`);
    model[key] = Number(raw);
  }
  return { contract: "spike/harness-si-request/v1", harness, selection: structuredClone(setup.selection ?? {}), model, provenance: { source: setup.source.trim() } };
}
export function validHarnessSiResult(result: any, request: any): boolean {
  if (!request?.model || !result || result.contract !== "spike/harness-si-result/v1" || !result.request_snapshot
    || !sameJson(result.request_snapshot, request) || result.production_qualified !== false
    || result.status !== "completed" || result.model_status !== "experimental" || result.field_coupling_executed !== false
    || !/^[0-9a-f]{64}$/.test(result.request_digest) || !/^[0-9a-f]{64}$/.test(result.harness_digest)
    || !Array.isArray(result.frequency_hz) || result.frequency_hz.length !== request.model.frequency_points
    || result.frequency_hz.length < 3 || result.frequency_hz.length > 2049) return false;
  const pair = request.selection?.pair_id && request.harness?.pairs?.find((p: any) => p?.id === request.selection.pair_id);
  const ids = pair ? pair.wire_ids : [request.selection?.signal_wire_id, request.selection?.return_wire_id];
  if (!Array.isArray(ids) || ids.length !== 2 || ids.some(id => typeof id !== "string") || ids[0] === ids[1]
    || result.mode !== (pair ? "differential" : "single_ended") || !sameJson(result.wire_ids, ids)) return false;
  const selected = ids.map(id => request.harness?.wires?.find((wire: any) => wire?.id === id));
  if (selected.some(wire => !wire?.from?.connector || !wire?.to?.connector)) return false;
  const ports = ["from", "to"].map(end => ({ positive: selected[0][end], negative:
    [selected[1].from, selected[1].to].find(endpoint => endpoint.connector === selected[0][end].connector) }));
  if (!sameJson(result.port_bindings, ports) || !sameJson(result.provenance, request.provenance)
    || !Array.isArray(result.reference_impedance_ohm) || result.reference_impedance_ohm.length !== 2
    || result.reference_impedance_ohm.some((z: unknown) => typeof z !== "number" || !Number.isFinite(z) || z <= 0 || z !== request.model.reference_impedance_ohm)) return false;
  if (result.frequency_hz.some((frequency: unknown, index: number) => typeof frequency !== "number" || !Number.isFinite(frequency)
    || frequency < 0 || index > 0 && frequency <= result.frequency_hz[index - 1]
    || Math.abs(frequency - request.model.frequency_stop_hz * index / (result.frequency_hz.length - 1))
      > Math.max(1, request.model.frequency_stop_hz) * 1e-12)) return false;
  for (const key of ["s_real", "s_imag"]) {
    if (!Array.isArray(result[key]) || result[key].length !== result.frequency_hz.length || result[key].some((matrix: any) =>
      !Array.isArray(matrix) || matrix.length !== 2 || matrix.some((row: any) => !Array.isArray(row) || row.length !== 2
        || row.some((value: unknown) => typeof value !== "number" || !Number.isFinite(value))))) return false;
  }
  return true;
}

// Project JSON sorts object keys. Compare values independently of key order,
// with explicit work/depth bounds for saved payloads; arrays remain ordered.
function sameJson(a: any, b: any): boolean {
  const pending: [any, any, number][] = [[a, b, 0]];
  let remaining = 500000;
  while (pending.length) {
    const [left, right, depth] = pending.pop()!;
    if (--remaining < 0 || depth > 64) return false;
    if (left === right) continue;
    if (!left || !right || typeof left !== "object" || typeof right !== "object"
      || Array.isArray(left) !== Array.isArray(right)) return false;
    const keys = Object.keys(left), other = Object.keys(right);
    if (keys.length !== other.length || keys.length > remaining || keys.some(key => !Object.prototype.hasOwnProperty.call(right, key))) return false;
    for (const key of keys) pending.push([left[key], right[key], depth + 1]);
  }
  return true;
}
