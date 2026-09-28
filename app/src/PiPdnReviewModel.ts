// SPDX-License-Identifier: Apache-2.0
import type { PdnReview, SolverResultBundle } from "./analysisResults";
import { resultSolvedForPresentation } from "./resultAdmission";

export type PdnCandidateDetail = PdnReview["candidate_screening"][number] & {
  capacitance_f?: number;
  esr_ohm?: number;
  esl_h?: number;
  count?: number;
  mounting_resistance_ohm?: number;
  mounting_inductance_h?: number;
  location?: { position_mm?: number[]; layer?: string };
  source_result_id?: string;
  assumptions?: string[];
  response?: { frequency_hz: number; magnitude_ohm: number }[];
};

export type PdnReviewView = {
  reason: string | null;
  review: PdnReview | null;
  candidates: PdnCandidateDetail[];
};

const finitePositive = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value > 0;
const finiteNonnegative = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value >= 0;

export function pdnCandidateUsable(candidate: PdnCandidateDetail, targetOhm: number): boolean {
  if (candidate.status !== "evaluated" || candidate.placement_method === "invalid"
    || /^(failed(?:_.*)?|blocked|error|unsupported)$/i.test(candidate.model_status)) return false;
  if (!candidate.id || !finitePositive(candidate.capacitance_f) || !finiteNonnegative(candidate.esr_ohm)
    || !finiteNonnegative(candidate.esl_h) || !Number.isInteger(candidate.count) || Number(candidate.count) < 1
    || !finiteNonnegative(candidate.mounting_resistance_ohm) || !finiteNonnegative(candidate.mounting_inductance_h)
    || !finiteNonnegative(candidate.worst_impedance_ohm) || !finitePositive(candidate.worst_frequency_hz)
    || !finiteNonnegative(candidate.worst_target_ratio) || !Number.isFinite(candidate.worst_impedance_improvement_percent)
    || !Number.isFinite(candidate.maximum_local_degradation_percent) || !Number.isInteger(candidate.violation_count)
    || Number(candidate.violation_count) < 0 || !Array.isArray(candidate.response) || candidate.response.length < 2
    || (candidate.assumptions !== undefined && (!Array.isArray(candidate.assumptions)
      || candidate.assumptions.some(item => typeof item !== "string")))) return false;
  let previousFrequency = 0;
  for (const point of candidate.response) {
    if (!finitePositive(point.frequency_hz) || point.frequency_hz <= previousFrequency
      || !finiteNonnegative(point.magnitude_ohm)) return false;
    previousFrequency = point.frequency_hz;
  }
  const responseMaximum = candidate.response.reduce((maximum, point) => Math.max(maximum, point.magnitude_ohm), 0);
  if (Math.abs(responseMaximum - Number(candidate.worst_impedance_ohm)) > Math.max(1e-12, responseMaximum * 1e-8)
    || (responseMaximum <= targetOhm) !== candidate.passes_target
    || candidate.response.filter(point => point.magnitude_ohm > targetOhm).length !== candidate.violation_count) return false;
  if (Math.abs(Number(candidate.worst_target_ratio) - Number(candidate.worst_impedance_ohm) / targetOhm) > 1e-7) return false;
  if (candidate.placement_method === "multiport_impedance_loading") {
    if (!candidate.source_result_id || !Array.isArray(candidate.location?.position_mm)
      || candidate.location.position_mm.length !== 2
      || !candidate.location.position_mm.every(Number.isFinite)) return false;
  }
  return true;
}

export function pdnReviewView(
  source: SolverResultBundle | null,
  review: PdnReview | null,
  selectedNet: string,
  reviewSourceId: string | null,
): PdnReviewView {
  if (!review) return { reason: "Run a PDN target review to compare candidates.", review: null, candidates: [] };
  if (!source || !resultSolvedForPresentation(source)) return {
    reason: "The source solve failed, was blocked, or has no admissible solved result.", review: null, candidates: [],
  };
  if (!reviewSourceId || reviewSourceId !== source.analysis_id) return {
    reason: "This review has no verified binding to the active source result. Run the review again.", review: null, candidates: [],
  };
  if (review.contract !== "spike/pdn-review/v1" || !selectedNet || review.net !== selectedNet
    || !finitePositive(review.target_ohm) || !finiteNonnegative(review.maximum_impedance_ohm)
    || !Number.isInteger(review.violation_count) || review.violation_count < 0
    || !["pass", "violated"].includes(review.status)
    || !Array.isArray(review.candidate_screening)) return {
    reason: "The PDN review contract, net, or target is invalid for this selection.", review: null, candidates: [],
  };
  const network = source.parasitics?.find(item => item.net === selectedNet && (item.impedance?.length ?? 0) >= 2);
  const grid = network?.impedance;
  if (!grid) return {
    reason: "The active result has no matching impedance sweep for this net.", review: null, candidates: [],
  };
  if (grid.some((point, index) => !finitePositive(point.frequency_hz)
    || (index > 0 && point.frequency_hz <= grid[index - 1].frequency_hz)
    || !finiteNonnegative(point.magnitude_ohm))) return {
    reason: "The active source impedance sweep is invalid.", review: null, candidates: [],
  };
  const sourceMaximum = grid.reduce((maximum, point) => Math.max(maximum, point.magnitude_ohm), 0);
  const sourceViolations = grid.filter(point => point.magnitude_ohm > review.target_ohm).length;
  if (Math.abs(sourceMaximum - review.maximum_impedance_ohm) > Math.max(1e-12, sourceMaximum * 1e-8)
    || sourceViolations !== review.violation_count
    || (sourceViolations === 0) !== (review.status === "pass")) return {
    reason: "The review values do not match the active source sweep. Run the review again.", review: null, candidates: [],
  };
  const candidates = (review.candidate_screening as PdnCandidateDetail[]).map(candidate => {
    if (!pdnCandidateUsable(candidate, review.target_ohm)) return { ...candidate, status: "rejected" as const,
      issues: [...(candidate.issues ?? []), { code: "SPIKE-UI-PI-E-0001", severity: "error", message: "Candidate response or model details are incomplete or invalid." }] };
    if (candidate.placement_method === "multiport_impedance_loading" && candidate.source_result_id !== source.analysis_id) return {
      ...candidate, status: "rejected" as const,
      issues: [...(candidate.issues ?? []), { code: "SPIKE-UI-PI-E-0002", severity: "error", message: "Candidate source result ID does not match the active result." }],
    };
    if (candidate.response?.length !== grid.length || candidate.response.some((point, index) => point.frequency_hz !== grid[index].frequency_hz)) return {
      ...candidate, status: "rejected" as const,
      issues: [...(candidate.issues ?? []), { code: "SPIKE-UI-PI-E-0003", severity: "error", message: "Candidate frequency grid does not match the source sweep." }],
    };
    return candidate;
  });
  return { reason: null, review, candidates };
}
