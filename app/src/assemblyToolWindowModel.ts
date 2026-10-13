// SPDX-License-Identifier: Apache-2.0
import type { AssemblyDesigns, AssemblyIr, AssemblySceneModel } from "./mcadAssembly";
import type { ParsedBoard } from "./boardParser";

export const assemblyToolKinds = ["workspace", "placement", "managers"] as const;
export type AssemblyToolKind = typeof assemblyToolKinds[number];
export const assemblyToolLabels: Record<AssemblyToolKind, string> = {
  workspace: "spike-assembly-workspace", placement: "spike-assembly-placement", managers: "spike-assembly-managers",
};
export function isAssemblyToolKind(value: unknown): value is AssemblyToolKind {
  return assemblyToolKinds.includes(value as AssemblyToolKind);
}
export type AssemblyToolSnapshot = {
  revision: string; assembly: AssemblyIr | null; designs: AssemblyDesigns | null;
  visuals: Record<string, { boardModelUrl?: string; componentModelUrl?: string }>;
  diagnostics: Record<string, string>; projectPath: string | null; manifestDigest: string | null;
  projectDirty: boolean; desktop: boolean; boardAvailable: boolean; selectedBoardId: string | null;
  visibility: Record<string, boolean>; layerVisibility: Record<string, Record<string, boolean>>;
  layerOpacity: Record<string, Record<string, number>>; layerFocus: Record<string, string>; explodedDistanceMm: number;
  linkedNets: Record<string, string[]>;
  showNetNames?: boolean;
  moveMode: "translate" | "rotate" | null; snapMode: "off" | "hole" | "edge"; snapGapMm: number;
  snapSourceLabel?: string; passThroughHighlight: boolean; overlayMessages: string[];
  managerTab: "layers" | "nets" | "links";
  draftOwner?: AssemblyToolKind | null;
  /** Explicit user navigation request, independent of changing geometry snapshots. */
  thermalStudyRequest?: string | null;
  /** Identifies the retained renderer inputs held by the parent session. */
  viewportRevision?: string | null;
};

/**
 * CPU-side renderer inputs for the dedicated workspace viewport.  This payload
 * deliberately excludes Three.js scenes, GPU buffers and renderer ownership.
 * The parent holds it behind the token-bound window session and the child asks
 * for it only when viewportRevision changes.
 */
export type AssemblyToolViewportData = {
  revision: string;
  boards: Record<string, ParsedBoard>;
  assemblyModels?: AssemblySceneModel[];
};
export function validAssemblyToolViewportData(value: unknown): value is AssemblyToolViewportData {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const raw = value as Record<string, unknown>;
  if (typeof raw.revision !== "string" || !raw.revision || raw.revision.length > 512
    || !raw.boards || typeof raw.boards !== "object" || Array.isArray(raw.boards)
    || Object.keys(raw.boards as object).length > 30) return false;
  if (Object.entries(raw.boards as Record<string, unknown>).some(([id, board]) => !id || id.length > 512 || !board || typeof board !== "object" || Array.isArray(board))) return false;
  if (raw.assemblyModels !== undefined && (!Array.isArray(raw.assemblyModels) || raw.assemblyModels.length > 512)) return false;
  return true;
}
type AssemblyToolActionFields = {
  boardId?: string; value?: string | number | boolean; netId?: string; layer?: string;
  transform?: number[]; assembly?: AssemblyIr;
  layerVisibility?: Record<string, boolean>; layerOpacity?: Record<string, number>;
};
type AssemblyToolActionType = "ready" | "closed" | "close" | "draft-dirty" | "save" | "reload" | "status" | "view" | "manager" | "select-board" |
    "visibility" | "placement" | "move-mode" | "explode" | "snap-mode" | "snap-gap" | "pass-through" | "net-names" |
    "export-diagram" | "load-overlay" | "layer-visibility" | "layer-opacity" | "layer-state" | "layer-focus" | "select-net" | "snap-target" | "update-assembly";
export type AssemblyToolAction = AssemblyToolActionFields & (
  { type: AssemblyToolActionType; mode?: string } |
  { type: "collaboration"; mode: "freecad" | "attachments" }
);
const types = new Set(["ready", "closed", "close", "draft-dirty", "save", "reload", "status", "view", "manager", "select-board", "visibility", "placement", "move-mode", "explode", "snap-mode", "snap-gap", "pass-through", "net-names", "export-diagram", "load-overlay", "layer-visibility", "layer-opacity", "layer-state", "layer-focus", "select-net", "snap-target", "update-assembly", "collaboration"]);
/** Reject malformed cross-window messages before workspace callbacks run. */
export function validAssemblyToolAction(value: unknown): value is AssemblyToolAction {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const raw = value as Record<string, unknown>;
  if (typeof raw.type !== "string" || !types.has(raw.type)) return false;
  for (const key of ["boardId", "mode", "netId", "layer"]) if (raw[key] !== undefined && (typeof raw[key] !== "string" || (raw[key] as string).length > 512)) return false;
  if (raw.value !== undefined && !["string", "number", "boolean"].includes(typeof raw.value)) return false;
  if (typeof raw.value === "number" && !Number.isFinite(raw.value)) return false;
  if (typeof raw.value === "string" && raw.value.length > 2000) return false;
  if (raw.type === "net-names" && typeof raw.value !== "boolean") return false;
  if (raw.type === "layer-focus" && (typeof raw.boardId !== "string" || !raw.boardId || typeof raw.value !== "string" || !raw.value || raw.value.length > 256)) return false;
  if (raw.type === "snap-target" && (typeof raw.boardId !== "string" || !raw.boardId || typeof raw.value !== "string" || !raw.value || raw.value.length > 512)) return false;
  if (raw.type === "collaboration" && !["freecad", "attachments"].includes(String(raw.mode))) return false;
  if (raw.type === "layer-state") {
    if (!raw.boardId || !raw.layerVisibility || typeof raw.layerVisibility !== "object" || Array.isArray(raw.layerVisibility)) return false;
    for (const [key, map] of [["visibility", raw.layerVisibility], ["opacity", raw.layerOpacity]] as const) {
      if (map === undefined) continue;
      if (!map || typeof map !== "object" || Array.isArray(map) || Object.keys(map).length > 512) return false;
      if (Object.entries(map).some(([name, value]) => !name || name.length > 256 || (key === "visibility" ? typeof value !== "boolean" : typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1))) return false;
    }
  }
  if (raw.type === "placement" && (!Array.isArray(raw.transform) || raw.transform.length !== 16 || !raw.transform.every(item => typeof item === "number" && Number.isFinite(item)))) return false;
  if (raw.type === "update-assembly") {
    const assembly = raw.assembly as AssemblyIr | undefined;
    if (assembly?.contract !== "spike/assembly-ir/v1" || !Array.isArray(assembly.boards) || assembly.boards.length > 30 || !Array.isArray(assembly.parts)) return false;
  }
  return true;
}
