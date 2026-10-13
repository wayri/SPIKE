/* SPDX-License-Identifier: Apache-2.0 */
/** Portable history only. Local enrollment and live process handles are never project data. */
export type ParallelWorkspaceRun = {
  id: string;
  request: Record<string, unknown>;
  result: Record<string, unknown> | null;
  status: "completed" | "completed_with_errors" | "cancelled" | "failed" | "interrupted";
  error?: string;
};
export type ParallelWorkspace = {
  contract: "spike/parallel-workspace/v1";
  draft: { jobs_json: string; concurrency: string; threads_per_job: string; timeout_s: string };
  runs: ParallelWorkspaceRun[];
};
export const defaultParallelWorkspace = (): ParallelWorkspace => ({
  contract: "spike/parallel-workspace/v1",
  draft: { jobs_json: "[]", concurrency: "1", threads_per_job: "1", timeout_s: "120" },
  runs: [],
});

/** Native package admission validates requests and digest bindings before this UI projection. */
export function normalizeParallelWorkspace(value: unknown): ParallelWorkspace {
  if (value === undefined || value === null) return defaultParallelWorkspace();
  if (typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid saved parallel workspace.");
  const raw = value as ParallelWorkspace;
  if (raw.contract !== "spike/parallel-workspace/v1" || !raw.draft
      || ![raw.draft.jobs_json, raw.draft.concurrency, raw.draft.threads_per_job, raw.draft.timeout_s].every(item => typeof item === "string")
      || !Array.isArray(raw.runs) || raw.runs.length > 32
      || raw.runs.some(run => !run || typeof run.id !== "string" || !run.request
        || !["completed", "completed_with_errors", "cancelled", "failed", "interrupted"].includes(run.status))) {
    throw new Error("Unsupported or malformed saved parallel workspace.");
  }
  return structuredClone(raw);
}

export function retainParallelRun(workspace: ParallelWorkspace, run: ParallelWorkspaceRun): ParallelWorkspace {
  return { ...workspace, runs: [...workspace.runs.filter(item => item.id !== run.id), run].slice(-32) };
}
