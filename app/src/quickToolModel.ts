// SPDX-License-Identifier: Apache-2.0
import type { ContextMenuAction, ContextMenuGroup } from "./ViewportActionMenu";

/** Preserve the grab point and clamp against available travel, including narrow docks. */
export function quickToolPosition(start: number, delta: number, travel: number): number {
  if (!Number.isFinite(start)) start = .5;
  if (!Number.isFinite(delta) || !Number.isFinite(travel) || travel <= 0) return Math.max(0, Math.min(1, start));
  return Math.max(0, Math.min(1, start + delta / travel));
}

export type QuickToolContext = { workspace: string; kind?: string; hasNet: boolean; hasResult: boolean; hasBoard: boolean; busy: boolean };
export function quickToolActions(groups: readonly ContextMenuGroup[], context: QuickToolContext): ContextMenuAction[] {
  const priorities = context.busy ? ["stop", "result-plots", "inspect-object"]
    : !context.hasBoard ? ["open-project", "import-board"]
    : context.workspace === "Thermal" ? ["thermal-setup", "thermal-history", "thermal-contacts", "probe"]
    : context.workspace === "EM" ? ["em-net", "engines", "model-resolver", "probe"]
    : context.workspace === "HF / SI" ? ["si-channel", "si-eye", "si-crosstalk", "si-ports"]
    : context.hasResult && ["Results", "Reports", "Probes"].includes(context.workspace) ? ["result-plots", "trace-plots", "playback", "probe", "report"]
    : context.kind === "component" ? ["inspect-object", "model-resolver", "thermal-contacts", "schematic"]
    : context.hasNet ? ["inspect-object", "isolate-net", "pi-DC IR Drop", "si-channel", "probe"]
    : ["validate", "stackup", "power-tree", "thermal-setup"];
  const all = groups.flatMap(group => group.actions);
  return [...new Set(["fit", "layer-manager", ...priorities])].flatMap(id => {
    const action = all.find(item => item.id === id); return action ? [action] : [];
  });
}

/** Resolve again at activation: stale or disabled suggestions never execute. */
export async function runQuickTool(id: string, groups: readonly ContextMenuGroup[], onError: (message:string)=>void): Promise<boolean> {
  const action=groups.flatMap(group=>group.actions).find(item=>item.id===id);
  if(!action || action.disabledReason){onError(action?.disabledReason ?? "This action is no longer available for the current selection.");return false;}
  try{await action.run();return true;}catch(error){onError(error instanceof Error ? error.message : String(error));return false;}
}
