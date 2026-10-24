// SPDX-License-Identifier: Apache-2.0
import { emergeAnalysisPayload, reviewEMergeNetwork } from "./emergeNetworkReview";

/** Transport-only draft: deliberately not executable until the user reviews it. */
export function exportEMergeCosimulationDraft(value: unknown): { name: string; text: string } {
  const review = reviewEMergeNetwork(value);
  if (review.issue || !review.ports.length) throw new Error(review.issue ?? "No network to transfer.");
  const result = emergeAnalysisPayload(value);
  const provenance = result.provenance as Record<string, unknown> | undefined;
  if (!provenance || typeof provenance.solver !== "string" || !provenance.solver.startsWith("EMerge/") ||
      !["completed", "completed_with_warnings"].includes(String(result.status))) {
    throw new Error("Co-simulation requires a completed EMerge result with source provenance.");
  }
  for (const name of ["design_digest_sha256", "board_case_sha256", "generated_script_sha256"]) {
    if (typeof provenance[name] !== "string" || !/^[0-9a-f]{64}$/.test(provenance[name] as string)) {
      throw new Error(`Missing source identity: ${name}. Rerun the current EMerge adapter.`);
    }
  }
  if (typeof provenance.design_id !== "string" || !provenance.design_id.trim()) throw new Error("Missing design identity.");
  if (!Array.isArray(result.issues) || result.issues.some(issue =>
    issue && typeof issue === "object" && (issue as Record<string, unknown>).severity === "error")) {
    throw new Error("Blocking source issues prevent co-simulation transfer.");
  }
  const request = { result,
    binding: { design_id: provenance.design_id, digest_sha256: provenance.design_digest_sha256 },
    expected_case_sha256: provenance.board_case_sha256,
    expected_script_sha256: provenance.generated_script_sha256,
    port_bindings: Object.fromEntries(review.ports.map(({ port }) => [port,
      { positive_node: "", negative_node: "", reference_plane: "" }])),
    wave_convention: "REQUIRES_EXPLICIT_RMS_POWER_WAVE_DECLARATION" };
  const text = JSON.stringify({ request }, (_key, field) => {
    if (typeof field === "number" && !Number.isFinite(field)) throw new Error("Source contains nonfinite numbers.");
    return field;
  }, 2) + "\n";
  if (new TextEncoder().encode(text).byteLength > 8 * 1024 * 1024) throw new Error("Co-simulation draft exceeds 8 MiB.");
  return { name: "emerge-cosimulation.draft.json", text };
}
