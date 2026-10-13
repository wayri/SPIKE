// SPDX-License-Identifier: Apache-2.0
import type { AssemblyIr } from "./mcadAssembly";

export type FieldObject = Record<string, any>;
export type FieldRecord = { contract: string; request: FieldObject; problem: FieldObject; result: FieldObject | null; file_digest: string; transient_settings?: FieldObject };
export type FieldSnapshot = { requestText: string; problemText: string; result: FieldObject | null };
const stable = (value: any): any => Array.isArray(value) ? value.map(stable)
  : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;

/** The worker supplies the canonical physical assembly; names never establish identity. */
export function assertFieldAssembly(request: FieldObject, current: FieldObject | null): void {
  if (!current || JSON.stringify(stable(request.assembly)) !== JSON.stringify(stable(current))) {
    throw new Error("ASSEMBLY_FIELD_STALE: this volume setup belongs to a different assembly. Export volumes for the current board and mechanical occurrences.");
  }
}
export const fieldStudyDirty = (current: FieldSnapshot, baseline: FieldSnapshot | null): boolean =>
  baseline !== null && (current.requestText !== baseline.requestText || current.problemText !== baseline.problemText || current.result !== baseline.result);

export function fieldCanRun(request: FieldObject | null, handoff: FieldObject | null, unapplied: boolean): boolean {
  return !!request && request.domain === "thermal" && handoff?.domain === "thermal"
    && Array.isArray(handoff.execution_issues) && handoff.execution_issues.length === 0 && !unapplied;
}
export function fieldOwnerName(assembly: AssemblyIr, id: string): string {
  const owner = [...assembly.boards, ...assembly.parts].find(item => item.id === id);
  return String(owner?.name || (assembly.boards.some(item => item.id === id) ? "Board" : "Mechanical structure"));
}
export function fieldTemperatureRows(result: FieldObject | null, assembly: AssemblyIr): Array<{ name: string; minimum: number; maximum: number }> {
  if (!result || !["spike/assembly-field-thermal-result/v1", "spike/calculix-thermal-result/v1", "spike/assembly-field-transient-result/v1", "spike/calculix-field-transient-result/v1"].includes(result.contract) || result.production_qualified !== false) return [];
  return Object.entries(result.occurrence_temperatures ?? {}).flatMap(([id, raw]) => {
    const value = raw as FieldObject;
    return Number.isFinite(value.minimum_k) && Number.isFinite(value.maximum_k)
      ? [{ name: fieldOwnerName(assembly, id), minimum: value.minimum_k, maximum: value.maximum_k }] : [];
  });
}
