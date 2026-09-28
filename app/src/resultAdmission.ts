// SPDX-License-Identifier: Apache-2.0
import type { SolverResultBundle } from "./analysisResults";

/** Admission for derived display values; raw failed evidence remains available. */
export function resultSolvedForPresentation(result: SolverResultBundle | null | undefined): boolean {
  if (!result || !["completed", "completed_with_warnings"].includes(result.status)) return false;
  if (["unsupported", "failed", "blocked"].includes(result.model_status)) return false;
  if (result.summary?.solved === false || result.provenance?.solved === false) return false;
  if (result.summary?.failure_stage || result.provenance?.failure_stage) return false;
  return true;
}
