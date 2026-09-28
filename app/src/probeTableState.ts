// SPDX-License-Identifier: Apache-2.0
import type { ProbeFormulaRow } from "./probeCalculations";

export function normalizeProbeTableState(value: unknown): {
  calculatedRows: ProbeFormulaRow[]; referenceIds: Record<string, string>;
} {
  const data = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const calculatedRows = Array.isArray(data.calculated_rows) ? data.calculated_rows.slice(0, 2000).flatMap(row =>
    row && typeof row.id === "string" && typeof row.name === "string" && typeof row.formula === "string"
      ? [{ id: row.id.slice(0, 96), name: row.name.slice(0, 512), formula: row.formula.slice(0, 512) }] : []) : [];
  const referenceIds = data.reference_ids && typeof data.reference_ids === "object" && !Array.isArray(data.reference_ids)
    ? Object.fromEntries(Object.entries(data.reference_ids).filter((entry): entry is [string, string] =>
      typeof entry[1] === "string" && /^[A-Za-z_][A-Za-z0-9_]*$/.test(entry[1]))) : {};
  return { calculatedRows, referenceIds };
}

export function assignProbeReferenceIds(probeIds: string[], previous: Record<string, string>, formulas: ProbeFormulaRow[]): Record<string, string> {
  const next = { ...previous };
  const used = new Set([...Object.values(previous), ...formulas.map(row => row.id)]);
  let index = 1;
  for (const id of probeIds) if (!Object.prototype.hasOwnProperty.call(next, id)) {
    while (used.has(`P${index}`)) index++;
    const alias = `P${index++}`;
    Object.defineProperty(next, id, { value: alias, writable: true, enumerable: true, configurable: true });
    used.add(alias);
  }
  return next;
}
