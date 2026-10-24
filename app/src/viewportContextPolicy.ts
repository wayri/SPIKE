// SPDX-License-Identifier: Apache-2.0
import type { ContextMenuAction, ContextMenuGroup } from "./ViewportActionMenu";

/** Facts used to reduce the viewport menu before it reaches presentation/search. */
export type ViewportContextPolicyContext = {
  activeWorkspace: string;
  selectionType: string | null;
  selectionHasNet: boolean;
  selectionOwnedByActiveBoard: boolean;
  hasSavedResult: boolean;
  hasThermalTarget: boolean;
  hasAssembly: boolean;
};

const GENERAL_GROUPS = new Set(["appearance", "workspace", "view", "edit", "navigation", "camera-views"]);
const COPPER_SELECTIONS = new Set(["trace", "zone", "via", "pad", "terminal"]);
const CIRCUIT_SELECTION_ACTIONS = new Set([
  "isolate-net", "schematic", "probe", "focus-layer", "pi-net", "return-path",
  "spice", "power-tree", "em-net", "delete-terminal",
]);
const SAVED_RESULT_ACTIONS = new Set(["result-plots", "trace-plots", "playback"]);

function isMechanicalSelection(context: ViewportContextPolicyContext) {
  return context.selectionType === "mechanical" || context.selectionType === "assembly-part";
}

function hasCopperNetContext(context: ViewportContextPolicyContext) {
  return context.selectionOwnedByActiveBoard
    && context.selectionHasNet
    && COPPER_SELECTIONS.has(context.selectionType ?? "");
}

function actionRelevant(action: ContextMenuAction, context: ViewportContextPolicyContext) {
  const { id } = action;
  const workspace = context.activeWorkspace;
  const mechanical = isMechanicalSelection(context);
  const copperNet = hasCopperNetContext(context);
  const hasSelection = Boolean(context.selectionType);
  if (id.startsWith("background-") || id.startsWith("workspace-")) return false;
  if (id === "open-project" || id === "import-board") return !hasSelection && workspace === "Home";
  if (["inspect-object", "focus-object", "clear-selection"].includes(id)) return hasSelection;
  if (id === "isolate-net") return copperNet;
  if (id === "probe") return hasSelection && context.selectionOwnedByActiveBoard && !mechanical;
  if (id === "schematic") return context.selectionOwnedByActiveBoard && !mechanical;
  if (["layer-manager", "stackup", "models"].includes(id)) return context.selectionOwnedByActiveBoard && !mechanical;
  if (id === "focus-layer") return copperNet;
  if (id === "validate") return context.selectionOwnedByActiveBoard && !mechanical && ["Home", "Mesh", "PI", "Solve"].includes(workspace);
  if (id === "assistant" || id === "script" || id === "copy-context") return hasSelection;
  if (id === "delete-terminal") return context.selectionType === "terminal";

  if (mechanical && (CIRCUIT_SELECTION_ACTIONS.has(id) || id.startsWith("pi-") || id.startsWith("si-"))) return false;

  if (id === "pi-net" || id === "return-path" || id.startsWith("pi-") || id === "spice" || id === "power-tree") {
    return ["PI", "Mesh", "Solve"].includes(workspace) && copperNet;
  }
  if (id.startsWith("si-")) return workspace === "HF / SI" && copperNet;
  if (id.startsWith("thermal-")) return workspace === "Thermal" || context.hasThermalTarget;
  if (id === "em-net") return workspace === "EM" && copperNet;
  if (id === "model-resolver") return workspace === "Thermal" || workspace === "EM" || mechanical;
  if (id === "engines") return ["Mesh", "Solve", "PI", "HF / SI", "Thermal", "EM"].includes(workspace);

  if (id.startsWith("result-") || SAVED_RESULT_ACTIONS.has(id)) {
    return context.hasSavedResult || workspace === "Results";
  }
  if (["cancel-run", "studies", "report"].includes(id)) return workspace === "Results";

  if (["assembly-workspace", "links", "harness", "tetra-mesh"].includes(id)) {
    return context.hasAssembly || mechanical;
  }
  return true;
}

/**
 * Returns the complete searchable menu inventory for the current viewport context.
 * Disabled actions remain when they are relevant; the policy only removes unrelated
 * actions, so presentation search cannot rediscover the hidden global inventory.
 */
export function scopeViewportContextGroups(
  groups: readonly ContextMenuGroup[],
  context: ViewportContextPolicyContext,
): ContextMenuGroup[] {
  const scopedById = new Map<string, ContextMenuAction[]>();
  for (const group of groups) {
    if (group.id === "suggested") continue;
    const actions = group.actions.filter(action => actionRelevant(action, context));
    if (actions.length && (GENERAL_GROUPS.has(group.id) || group.id === "inspect" || group.id === "automation"
      || group.id === "pi-si" || group.id === "thermal-em" || group.id === "results" || group.id === "assembly")) {
      scopedById.set(group.id, actions);
    }
  }

  return groups.flatMap(group => {
    if (group.id === "suggested") {
      const allowedIds = new Set([...scopedById.values()].flat().map(action => action.id));
      const actions = group.actions.filter(action => allowedIds.has(action.id));
      return actions.length ? [{ ...group, actions }] : [];
    }
    const actions = scopedById.get(group.id);
    const label=group.id==="pi-si" ? (context.activeWorkspace==="HF / SI"?"Signal integrity":"Power integrity") : group.id==="thermal-em" ? (context.activeWorkspace==="Thermal"?"Thermal and airflow":context.activeWorkspace==="EM"?"Electromagnetics":"Geometry and materials") : group.label;
    return actions ? [{ ...group, label, actions }] : [];
  });
}
