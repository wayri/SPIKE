// SPDX-License-Identifier: Apache-2.0
import type { FieldObject } from "./assemblyFieldStudyPresentation";

/** Presentation/request authoring only; the worker owns volume and power mapping. */
export function bodyPowerParameters(request: FieldObject, problem: FieldObject, handoff: FieldObject,
  occurrenceId: string, watts: string, replaceExisting: boolean): FieldObject {
  if (watts.trim() === "" || !Number.isFinite(Number(watts)) || Number(watts) < 0) {
    throw new Error("Enter finite, nonnegative dissipated power in watts.");
  }
  if (!handoff.request_digest || !handoff.source_traceability?.some((body: FieldObject) => body.occurrence_id === occurrenceId)) {
    throw new Error("Validate the retained volumes and select a meshed occurrence first.");
  }
  if (problem.heat_sources?.some((source: FieldObject) => source.occurrence_id === occurrenceId) && !replaceExisting) {
    throw new Error("Review replacement of existing sources on this body.");
  }
  return { request, problem, occurrence_id: occurrenceId, power_w: Number(watts),
    expected_request_digest: handoff.request_digest, replace_existing: replaceExisting };
}
