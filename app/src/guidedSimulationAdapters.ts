// SPDX-License-Identifier: Apache-2.0
import type { GuidedSimulationRequirement } from "./guidedSimulationModel";
import { cancelLocalWorker, runLocalWorker } from "./workerBridge";
export function guidedRequirements(issues: unknown, route: (text: string) => string, prefix = "setup"): GuidedSimulationRequirement[] {
  if (!Array.isArray(issues)) return [];
  return issues.flatMap((raw, index) => {
    if (!raw || typeof raw !== "object" || !["error", "critical", "warning"].includes(raw.severity)) return [];
    const message = String(raw.message ?? "Required setup input is missing.");
    const path = String(raw.path ?? "");
    return [{ id: `${prefix}:${raw.code ?? index}:${path}:${index}`, title: message.length > 100 ? `${message.slice(0,97)}…` : message, detail: [raw.code, message, path && `Input: ${path}`, raw.suggestion].filter(Boolean).join("\n"), severity: raw.severity === "warning" ? "warning" as const : "blocker" as const, route: route(`${path} ${message}`) }];
  });
}
export function guidedBlocker(id: string, detail: string, route = "review"): GuidedSimulationRequirement {
  return { id, title: "Complete simulation setup", detail, severity: "blocker", route };
}
export async function guidedWorkerCheck(method: string, params: Record<string, unknown>, signal: AbortSignal) {
  if (signal.aborted) throw new DOMException("Setup check cancelled", "AbortError");
  const id = crypto.randomUUID();
  const cancel = () => { void cancelLocalWorker(id); };
  signal.addEventListener("abort", cancel, { once: true });
  try {
    const response = await runLocalWorker({ id, method, params });
    if (signal.aborted) throw new DOMException("Setup check cancelled", "AbortError");
    if (!response.ok || !response.result) throw new Error(response.error ?? "The setup validator returned no result.");
    return response.result;
  } finally { signal.removeEventListener("abort", cancel); }
}
export const piGuideRoute = (text: string) => /source|load|terminal|voltage|current|excitation/i.test(text) ? "terminals" : /net|domain|design/i.test(text) ? "domain" : /mesh|material|dielectric|thickness|solver/i.test(text) ? "mesh" : "review";
