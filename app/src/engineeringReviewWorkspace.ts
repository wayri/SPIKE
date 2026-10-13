// SPDX-License-Identifier: Apache-2.0
export type EngineeringReviewWorkspace = {
  contract: "spike/engineering-review-workspace/v1";
  scope_sha256: string;
  overrides: Record<string, unknown>[];
  result: Record<string, unknown> | null;
};

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value)
    .filter(([, item]) => item !== undefined).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value) ?? "null";
}

/** Bind overrides to exact occurrence IDs and normalized source data, independent of key order. */
export async function engineeringReviewScope(boards: {id: string; design: Record<string, unknown>}[]): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(boards.map(board => ({occurrence_id: board.id, design: board.design}))));
  if (bytes.length > 8 * 1024 * 1024) throw new Error("Engineering review source exceeds the 8 MiB limit.");
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, "0")).join("");
}

/** Stored evidence is archival. The UI must rerun the worker before displaying restored totals. */
export function restoreEngineeringReviewWorkspace(value: unknown): EngineeringReviewWorkspace | null {
  if (value == null) return null;
  const raw = value as EngineeringReviewWorkspace;
  if (!raw || typeof raw !== "object" || Array.isArray(raw) || raw.contract !== "spike/engineering-review-workspace/v1" || !/^[a-f0-9]{64}$/.test(raw.scope_sha256)
    || (raw.result !== null && (!raw.result || typeof raw.result !== "object" || Array.isArray(raw.result)))
    || !Array.isArray(raw.overrides) || raw.overrides.length > 20000
    || raw.overrides.some(item => !item || Array.isArray(item) || typeof item !== "object"
      || typeof item.occurrence_id !== "string" || !item.occurrence_id || item.occurrence_id.length > 256
      || typeof item.component_id !== "string" || !item.component_id || item.component_id.length > 256)
    || new TextEncoder().encode(JSON.stringify(raw)).length > 8 * 1024 * 1024) {
    throw new Error("Saved engineering review is invalid or exceeds its storage limits.");
  }
  return structuredClone(raw);
}
