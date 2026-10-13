// SPDX-License-Identifier: Apache-2.0
export type AppUpdatePhase = "idle" | "checking" | "available" | "current" | "downloading" | "ready" | "installing" | "failed" | "unsupported" | "cancelled";
export type AppUpdateSnapshot = {
  contract: "spike/app-update/v1"; status: AppUpdatePhase; current_version?: string;
  latest_version?: string; release_url?: string; asset_name?: string; size?: number;
  received_bytes?: number; total_bytes?: number; message?: string; error?: string;
  unattended_supported?: boolean;
};
export const idleAppUpdate: AppUpdateSnapshot = { contract: "spike/app-update/v1", status: "idle" };
const phases: AppUpdatePhase[] = ["idle","checking","available","current","downloading","ready","installing","failed","unsupported","cancelled"];
export function admittedAppUpdate(value: unknown): AppUpdateSnapshot {
  if (!value || typeof value !== "object") throw new Error("Invalid update response.");
  const row = value as Record<string, unknown>;
  if (row.contract !== idleAppUpdate.contract || !phases.includes(row.status as AppUpdatePhase)) throw new Error("Unsupported update response.");
  const result: AppUpdateSnapshot = { contract: idleAppUpdate.contract, status: row.status as AppUpdatePhase };
  for (const name of ["current_version","latest_version","asset_name","message","error"] as const) if (typeof row[name] === "string") result[name] = (row[name] as string).slice(0,4000);
  if (typeof row.release_url === "string" && /^https:\/\/github\.com\/wayri\/spike\/releases\/tag\/[^?#]+$/i.test(row.release_url)) result.release_url = row.release_url;
  for (const name of ["size","received_bytes","total_bytes"] as const) if (typeof row[name] === "number" && Number.isSafeInteger(row[name]) && row[name] >= 0) result[name] = row[name] as number;
  result.unattended_supported = row.unattended_supported === true;
  return result;
}
export type UpdateWorkspace = { hasProject: boolean; dirty: boolean; busy: boolean; draftOwner?: string | null; editorsOpen: boolean; detachedWindowsOpen?: boolean };
export function appUpdateBlockers(workspace: UpdateWorkspace): string[] {
  return [
    workspace.dirty ? "Save the current project." : "",
    workspace.hasProject ? "Close the current project before installing." : "",
    workspace.busy ? "Finish or cancel running simulations, imports and downloads of solver data." : "",
    workspace.draftOwner ? `Save and close the assembly ${workspace.draftOwner} draft.` : "",
    workspace.editorsOpen ? "Save and close SPICE, Python, harness, topology and assistant windows." : "",
    workspace.detachedWindowsOpen ? "Close detached Results, Probe, Schematic, Report and assembly windows." : "",
  ].filter(Boolean);
}
export function canInstallAppUpdate(snapshot: AppUpdateSnapshot, blockers: readonly string[], acknowledged: boolean, pending: boolean): boolean {
  return snapshot.status === "ready" && !blockers.length && acknowledged && !pending;
}
export function updateDownloadPercent(snapshot: AppUpdateSnapshot): number | undefined {
  if (snapshot.status === "ready") return 100;
  const total = snapshot.total_bytes || snapshot.size || 0;
  if (!total || snapshot.received_bytes === undefined) return undefined;
  return Math.max(0,Math.min(99,Math.floor(snapshot.received_bytes / total * 100)));
}
export function updateBytes(bytes?: number): string {
  if (bytes === undefined) return "Size unavailable";
  if (bytes < 1024*1024) return `${(bytes/1024).toFixed(1)} KiB`;
  return `${(bytes/1024/1024).toFixed(1)} MiB`;
}
