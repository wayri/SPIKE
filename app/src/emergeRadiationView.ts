// SPDX-License-Identifier: Apache-2.0
import type { EMergeAngularPattern } from "./emergePatternInterpolation";

const MAX_PATTERN_SAMPLES = 4096;

/** Extract only completed EMerge EMI grids suitable for the EM workspace. */
export function emergeRadiationPatterns(extensionResult: unknown): EMergeAngularPattern[] {
  if (!extensionResult || typeof extensionResult !== "object") return [];
  const data = (extensionResult as { data?: unknown }).data;
  if (!data || typeof data !== "object") return [];
  const analysis = (data as { analysis_result?: unknown }).analysis_result;
  if (!analysis || typeof analysis !== "object") return [];
  const result = analysis as Record<string, unknown>;
  const provenance = result.provenance as Record<string, unknown> | undefined;
  if (result.status !== "completed" || result.mode !== "emi"
    || typeof provenance?.solver !== "string" || !provenance.solver.startsWith("EMerge/")) return [];
  const radiation = (result.fields as Record<string, unknown> | undefined)?.radiation as Record<string, unknown> | undefined;
  if (!Array.isArray(radiation?.patterns_3d) || !radiation.patterns_3d.length) return [];
  const patterns = radiation.patterns_3d;
  const valid = patterns.every(value => {
    if (!value || typeof value !== "object") return false;
    const pattern = value as Record<string, unknown>;
    const theta = pattern.theta_deg, phi = pattern.phi_deg, db = pattern.relative_amplitude_db;
    return typeof pattern.frequency_hz === "number" && Number.isFinite(pattern.frequency_hz) && pattern.frequency_hz > 0
      && Array.isArray(theta) && theta.length >= 2 && theta.every(item => typeof item === "number" && Number.isFinite(item))
      && Array.isArray(phi) && phi.length >= 2 && phi.every(item => typeof item === "number" && Number.isFinite(item))
      && Array.isArray(db) && db.length === theta.length * phi.length && db.length <= MAX_PATTERN_SAMPLES
      && db.every(item => typeof item === "number" && Number.isFinite(item));
  });
  return valid ? patterns as EMergeAngularPattern[] : [];
}

/** Preview a saved result only beside its source board, with surrogate status explicit. */
export function savedEmergeRadiationPreview(raw: unknown, sourceDesignId: string): { envelope: { title: string; data: { analysis_result: unknown } }; surrogate: boolean } | null {
  if (!raw || typeof raw !== "object" || !sourceDesignId) return null;
  const result = raw as Record<string, unknown>;
  const provenance = result.provenance as Record<string, unknown> | undefined;
  const designId = provenance?.design_id;
  const surrogate = designId === `${sourceDesignId}-rf-two-conductor`;
  if (designId !== sourceDesignId && !surrogate) return null;
  const envelope = { title: surrogate ? "Saved two-conductor EMerge surrogate" : "Saved EMerge radiation result", data: { analysis_result: raw } };
  return emergeRadiationPatterns(envelope).length ? { envelope, surrogate } : null;
}
