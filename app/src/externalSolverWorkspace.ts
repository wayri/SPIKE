// SPDX-License-Identifier: Apache-2.0
/** GUI persistence only; extensions independently validate every executable input. */
export const externalSolverIds = ["spike.palace-suite", "spike.xyce-suite"] as const;
export type ExternalSolverId = typeof externalSolverIds[number];
export type ExternalSolverWorkflow = { parameters: Record<string, unknown>; result: Record<string, unknown> | null };
export type ExternalSolverWorkflows = Partial<Record<ExternalSolverId, ExternalSolverWorkflow>>;
export const isExternalSolverId = (id: string): id is ExternalSolverId => (externalSolverIds as readonly string[]).includes(id);
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
export function restoreExternalSolverWorkflows(value: unknown): ExternalSolverWorkflows {
  const source = record(value), output: ExternalSolverWorkflows = {};
  for (const id of externalSolverIds) {
    const workflow = record(source[id]);
    if (!Object.keys(workflow).length) continue;
    try {
      const serialized = JSON.stringify(workflow);
      if (serialized.length > 32 * 1024 * 1024) continue;
      const copy = JSON.parse(serialized);
      output[id] = { parameters: record(copy.parameters), result: copy.result && Object.keys(record(copy.result)).length ? record(copy.result) : null };
    } catch { /* Unserializable GUI state is not executable input. */ }
  }
  return output;
}
