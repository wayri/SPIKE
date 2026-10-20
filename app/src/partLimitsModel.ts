// SPDX-License-Identifier: Apache-2.0
export const PART_LIMIT_UNITS = { voltage: ["V"], current: ["A"], temperature: ["degC", "K"], power: ["W"], stress: ["Pa", "MPa"], frequency: ["Hz"] } as const;
export type PartLimitRule = {
  id: string; occurrence_id: string; component_id: string; label: string;
  quantity: keyof typeof PART_LIMIT_UNITS; unit: string;
  lower: string | number | null; upper: string | number | null;
  reference: string | number | null; value: string | number | null;
  rating_source: string; measurement_source: string; evidence_status: "reviewed" | "unreviewed";
};
export type PartLimitReport = {
  contract: "spike/part-limit-report/v1"; overall_status: string; statement: string;
  covered_components: number; fitted_components: number;
  rows: (PartLimitRule & { reference_designator: string; status: string; comparison_status: string; stress_percent: string | null; headroom_percent: string | null; percentage_note: string; notes: string[] })[];
  counts: Record<string, number>; unchecked_components: { occurrence_id: string; component_id: string; reference: string }[];
  part_summary?: {occurrence_id:string;component_id:string;reference:string;status:string;declared_checks:number;stress_percent:string|null;headroom_percent:string|null}[];
};
const keys = ["id", "occurrence_id", "component_id", "label", "quantity", "unit", "lower", "upper", "reference", "value", "rating_source", "measurement_source", "evidence_status"];
/** Storage admission only; the Python review worker owns authoritative comparisons. */
export function admitPartLimits(value: unknown): PartLimitRule[] {
  if (!Array.isArray(value) || value.length > 20000 || new TextEncoder().encode(JSON.stringify(value)).length > 8 * 1024 * 1024) throw new Error("Part limits must contain at most 20,000 rules within 8 MiB.");
  const ids = new Set<string>();
  for (const rule of value) {
    if (!rule || typeof rule !== "object" || Array.isArray(rule) || Object.keys(rule).length !== keys.length || keys.some(key => !(key in rule))) throw new Error("Part-limit rule fields are incompatible.");
    for (const key of ["id", "occurrence_id", "component_id", "label", "quantity", "unit"]) if (typeof rule[key] !== "string" || !rule[key].trim() || rule[key].length > 256) throw new Error(`Invalid part-limit ${key}.`);
    if (ids.has(rule.id)) throw new Error("Part-limit rule IDs must be unique."); ids.add(rule.id);
    if (!Object.prototype.hasOwnProperty.call(PART_LIMIT_UNITS, rule.quantity) || !(PART_LIMIT_UNITS[rule.quantity as keyof typeof PART_LIMIT_UNITS] as readonly string[]).includes(rule.unit)) throw new Error("Unsupported part-limit quantity/unit pair.");
    for (const key of ["lower", "upper", "reference", "value"]) if (rule[key] !== null && !((typeof rule[key] === "number" && Number.isFinite(rule[key])) || (typeof rule[key] === "string" && rule[key].length <= 64 && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(rule[key])))) throw new Error(`${key} must be finite decimal text, a number, or null.`);
    for (const key of ["rating_source", "measurement_source"]) if (typeof rule[key] !== "string" || rule[key].length > 2000) throw new Error(`Invalid part-limit ${key}.`);
    if (!["reviewed", "unreviewed"].includes(rule.evidence_status)) throw new Error("Invalid observation review status.");
  }
  return structuredClone(value);
}
export function partLimitsWithoutObservations(value: PartLimitRule[]): PartLimitRule[] {
  return value.map(rule => ({ ...rule, value: null, measurement_source: "", evidence_status: "unreviewed" }));
}
const csv = (value: unknown) => { const text = value == null ? "" : String(value); return `"${(/^[\s]*[=+\-@]/.test(text) ? "'" : "") + text.replace(/"/g, '""')}"`; };
export function partLimitReportCsv(report: PartLimitReport): string {
  const columns = ["occurrence_id", "component_id", "reference_designator", "label", "quantity", "unit", "lower", "upper", "reference", "value", "status", "comparison_status", "stress_percent", "headroom_percent", "rating_source", "measurement_source", "evidence_status", "notes"] as const;
  return [["Overall status", report.overall_status], ["Scope", report.statement], ["Covered parts", `${report.covered_components}/${report.fitted_components}`], columns,
    ...report.rows.map(row => columns.map(key => key === "notes" ? row.notes.join("; ") : row[key])),
    ["Worst declared allowance per part"], ["Board","Part ID","Reference","Status","Checks","Stress %","Headroom %"], ...(report.part_summary??[]).map(part=>[part.occurrence_id,part.component_id,part.reference,part.status,part.declared_checks,part.stress_percent,part.headroom_percent]),
    ["Unchecked parts"], ...report.unchecked_components.map(part => [part.occurrence_id, part.component_id, part.reference])].map(row => row.map(csv).join(",")).join("\r\n");
}
