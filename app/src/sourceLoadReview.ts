// SPDX-License-Identifier: MIT
import type { SolverResultBundle } from "./analysisResults";
import { resultSolvedForPresentation } from "./resultAdmission";

export type SourceLoadPath = {
  loadId: string;
  sourceId: string;
  supplyNet: string;
  sourceVoltageV: number;
  loadVoltageV: number;
  supplyDropV: number;
  loadCurrentA: number;
  returnNet: string | null;
  loopDropV: number | null;
  limitState: "below limit (screen)" | "exceeded" | "reverse" | "unconfigured";
};

export type SourceLoadReview = {
  status: "validated" | "approximate";
  paths: SourceLoadPath[];
  sourceCurrentBalanceA: number | null;
  voltageReference: string;
};

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const nonempty = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;

export function sourceLoadReview(
  result: SolverResultBundle | null,
  selectedNet: string | null,
  dropLimitMv: number | null,
): SourceLoadReview | null {
  if (!result || !resultSolvedForPresentation(result) || result.mode !== "dc") return null;
  const evidence = record(result.source_to_load);
  if (!evidence || !["validated", "approximate"].includes(String(evidence.status))
    || !Array.isArray(evidence.paths)) return null;
  const paths: SourceLoadPath[] = [];
  for (const raw of evidence.paths) {
    const path = record(raw);
    if (!path || !nonempty(path.supply_net)) return null;
    if (selectedNet && path.supply_net !== selectedNet) continue;
    if (!nonempty(path.source_id) || !nonempty(path.load_id)
      || !finite(path.source_voltage_v) || !finite(path.load_voltage_v)
      || !finite(path.supply_drop_v) || !finite(path.load_current_a)
      || Math.abs(path.source_voltage_v - path.load_voltage_v - path.supply_drop_v) > 1e-7) return null;
    const returnNet = nonempty(path.return_net) ? path.return_net : null;
    if ((returnNet && !finite(path.loop_drop_v)) || (!returnNet && path.loop_drop_v !== undefined)) return null;
    const loopDropV = returnNet && finite(path.loop_drop_v)
      ? path.loop_drop_v : null;
    const evaluatedDrop = loopDropV ?? path.supply_drop_v;
    paths.push({
      loadId: path.load_id, sourceId: path.source_id, supplyNet: path.supply_net,
      sourceVoltageV: path.source_voltage_v, loadVoltageV: path.load_voltage_v,
      supplyDropV: path.supply_drop_v, loadCurrentA: path.load_current_a,
      returnNet, loopDropV,
      limitState: evaluatedDrop < -1e-9 ? "reverse"
        : dropLimitMv !== null && finite(dropLimitMv) && dropLimitMv > 0
        ? evaluatedDrop * 1000 <= dropLimitMv ? "below limit (screen)" : "exceeded" : "unconfigured",
    });
  }
  if (!paths.length) return null;
  return {
    status: evidence.status as SourceLoadReview["status"], paths,
    sourceCurrentBalanceA: finite(evidence.source_current_balance_a) ? evidence.source_current_balance_a : null,
    voltageReference: nonempty(evidence.voltage_reference) ? evidence.voltage_reference : "unspecified",
  };
}
