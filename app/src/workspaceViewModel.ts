// SPDX-License-Identifier: Apache-2.0
import type { VirtualBoardVisual } from "./harnessVisualization";
import type { AssemblyToolViewportData } from "./assemblyToolWindowModel";
import type { Viewport2DState, Viewport3DCameraState } from "./workspaceState";

export const MAX_WORKSPACE_VIEWS = 8;

export type WorkspaceViewScope =
  | Readonly<{ kind: "board-occurrence"; occurrenceId: string; designId: string }>
  | Readonly<{ kind: "assembly-part"; partId: string }>;

export type WorkspaceViewDescriptor = Readonly<{
  id: string;
  title: string;
  scope: WorkspaceViewScope;
  viewMode: "2D" | "3D";
  detached: boolean;
  presentation?: WorkspaceViewPresentation;
}>;

export type WorkspaceViewPresentation = Readonly<{
  viewMode: "2D" | "3D";
  selectionFilter: "all" | "part" | "net";
  selectedObjectId?: string;
  camera3d?: Viewport3DCameraState;
  layout2d?: Viewport2DState;
}>;

export type WorkspaceViewCandidate = Readonly<{ id: string; title: string; scope: WorkspaceViewScope }>;

export type WorkspaceViewSnapshot = Readonly<{
  viewId: string;
  projectSession: string;
  revision: string;
  viewportRevision: string | null;
  descriptor: WorkspaceViewDescriptor;
  valid: boolean;
  invalidReason?: string;
  /** Scope-bound targets only; this is intentionally not the complete assembly. */
  targetBoards: VirtualBoardVisual[];
  sourceDesignId?: string;
  visibility: Record<string, boolean>;
  layerVisibility: Record<string, Record<string, boolean>>;
  layerOpacity: Record<string, Record<string, number>>;
  layerFocus: Record<string, string>;
  linkedNets: Record<string, string[]>;
  analysisDomain?: "pi" | "si" | "em" | "thermal" | "results";
}>;

/** Requested only when viewportRevision changes. GPU resources never cross windows. */
export type WorkspaceViewViewportData = AssemblyToolViewportData;

export type WorkspaceViewAction =
  | { type: "ready" | "closed" | "redock" | "focus-owner" | "lease" }
  | { type: "status"; value: string }
  | { type: "select-object"; occurrenceId?: string; partId?: string; sourceObjectId: string }
  | { type: "select-net"; occurrenceId: string; netId: string }
  | { type: "select-component"; occurrenceId: string; componentId: string }
  | { type: "layer-focus"; occurrenceId: string; layer: string }
  | { type: "layer-visibility"; occurrenceId: string; layer: string; value: boolean }
  | { type: "layer-opacity"; occurrenceId: string; layer: string; value: number }
  | { type: "presentation"; presentation: WorkspaceViewPresentation }
  | { type: "open-analysis"; domain: "pi" | "si" | "em" | "thermal" | "results"; occurrenceId?: string; partId?: string };

const text = (value: unknown, maximum = 512): value is string => typeof value === "string" && value.length > 0 && value.length <= maximum;
const record = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);

export function validWorkspaceViewScope(value: unknown): value is WorkspaceViewScope {
  if (!record(value)) return false;
  return value.kind === "board-occurrence" ? text(value.occurrenceId) && text(value.designId)
    : value.kind === "assembly-part" && text(value.partId);
}

export function validWorkspaceViewDescriptor(value: unknown): value is WorkspaceViewDescriptor {
  if (!record(value)) return false;
  return text(value.id, 128) && text(value.title, 256) && validWorkspaceViewScope(value.scope)
    && (value.viewMode === "2D" || value.viewMode === "3D") && typeof value.detached === "boolean"
    && (value.presentation === undefined || validWorkspaceViewPresentation(value.presentation));
}

export function validWorkspaceViewPresentation(value: unknown): value is WorkspaceViewPresentation {
  if (!record(value) || !["2D", "3D"].includes(String(value.viewMode)) || !["all", "part", "net"].includes(String(value.selectionFilter))) return false;
  if (value.selectedObjectId !== undefined && !text(value.selectedObjectId)) return false;
  const camera = value.camera3d;
  if (camera !== undefined && (!record(camera) || camera.contract !== "spike/viewport-camera/v1"
    || [camera.position, camera.target, camera.up].some(point => !Array.isArray(point) || point.length !== 3 || point.some(item => typeof item !== "number" || !Number.isFinite(item))))) return false;
  const layout = value.layout2d;
  return layout === undefined || record(layout) && layout.contract === "spike/layout-view/v1"
    && [layout.x, layout.y, layout.width, layout.height].every(item => typeof item === "number" && Number.isFinite(item));
}

function validNestedBooleanMap(value: unknown): boolean {
  return record(value) && Object.keys(value).length <= 30 && Object.entries(value).every(([id, map]) => text(id) && record(map)
    && Object.keys(map).length <= 512 && Object.entries(map).every(([name, state]) => text(name, 256) && typeof state === "boolean"));
}

function validNestedOpacityMap(value: unknown): boolean {
  return record(value) && Object.keys(value).length <= 30 && Object.entries(value).every(([id, map]) => text(id) && record(map)
    && Object.keys(map).length <= 512 && Object.entries(map).every(([name, opacity]) => text(name, 256)
      && typeof opacity === "number" && Number.isFinite(opacity) && opacity >= 0 && opacity <= 1));
}

export function validWorkspaceViewSnapshot(value: unknown): value is WorkspaceViewSnapshot {
  if (!record(value) || !text(value.viewId, 128) || !text(value.projectSession) || !text(value.revision)
    || !validWorkspaceViewDescriptor(value.descriptor) || value.descriptor.id !== value.viewId
    || typeof value.valid !== "boolean" || (value.viewportRevision !== null && !text(value.viewportRevision))) return false;
  if (value.invalidReason !== undefined && (typeof value.invalidReason !== "string" || value.invalidReason.length > 2000)) return false;
  if (!Array.isArray(value.targetBoards) || value.targetBoards.length > 8 || value.targetBoards.some(item => !record(item) || !text(item.id) || !text(item.designId) || !Array.isArray(item.transform) || item.transform.length !== 16 || item.transform.some(entry => typeof entry !== "number" || !Number.isFinite(entry)))) return false;
  if (value.sourceDesignId !== undefined && !text(value.sourceDesignId)) return false;
  if (!record(value.visibility) || Object.keys(value.visibility).length > 30 || Object.values(value.visibility).some(item => typeof item !== "boolean")) return false;
  if (!validNestedBooleanMap(value.layerVisibility) || !validNestedOpacityMap(value.layerOpacity)) return false;
  if (!record(value.layerFocus) || Object.keys(value.layerFocus).length > 30 || Object.entries(value.layerFocus).some(([id, layer]) => !text(id) || !text(layer, 256))) return false;
  if (!record(value.linkedNets) || Object.keys(value.linkedNets).length > 512 || Object.entries(value.linkedNets).some(([id, nets]) => !text(id) || !Array.isArray(nets) || nets.length > 512 || nets.some(net => !text(net, 512)))) return false;
  return value.analysisDomain === undefined || ["pi", "si", "em", "thermal", "results"].includes(String(value.analysisDomain));
}

export function validWorkspaceViewViewportData(value: unknown): value is WorkspaceViewViewportData {
  if (!record(value) || !text(value.revision) || !record(value.boards) || Object.keys(value.boards).length > 8) return false;
  if (Object.entries(value.boards).some(([id, board]) => !text(id) || !record(board))) return false;
  return value.assemblyModels === undefined || Array.isArray(value.assemblyModels) && value.assemblyModels.length <= 512;
}

export function validWorkspaceViewAction(value: unknown): value is WorkspaceViewAction {
  if (!record(value) || typeof value.type !== "string") return false;
  if (["ready", "closed", "redock", "focus-owner", "lease"].includes(value.type)) return true;
  if (value.type === "status") return typeof value.value === "string" && value.value.length <= 2000;
  if (value.type === "select-object") return text(value.sourceObjectId) && (value.occurrenceId === undefined || text(value.occurrenceId)) && (value.partId === undefined || text(value.partId));
  if (value.type === "select-net") return text(value.occurrenceId) && text(value.netId);
  if (value.type === "select-component") return text(value.occurrenceId) && text(value.componentId);
  if (value.type === "layer-focus") return text(value.occurrenceId) && text(value.layer, 256);
  if (value.type === "layer-visibility") return text(value.occurrenceId) && text(value.layer, 256) && typeof value.value === "boolean";
  if (value.type === "layer-opacity") return text(value.occurrenceId) && text(value.layer, 256) && typeof value.value === "number" && Number.isFinite(value.value) && value.value >= 0 && value.value <= 1;
  if (value.type === "presentation") return validWorkspaceViewPresentation(value.presentation);
  return value.type === "open-analysis" && ["pi", "si", "em", "thermal", "results"].includes(String(value.domain))
    && (value.occurrenceId === undefined || text(value.occurrenceId)) && (value.partId === undefined || text(value.partId));
}

export function actionMatchesWorkspaceView(action: WorkspaceViewAction, scope: WorkspaceViewScope): boolean {
  const occurrenceId = "occurrenceId" in action ? action.occurrenceId : undefined;
  const partId = "partId" in action ? action.partId : undefined;
  if ((action.type === "select-object" || action.type === "open-analysis") && scope.kind === "board-occurrence") return occurrenceId === scope.occurrenceId && partId === undefined;
  if ((action.type === "select-object" || action.type === "open-analysis") && scope.kind === "assembly-part") return partId === scope.partId && occurrenceId === undefined;
  if (occurrenceId !== undefined && (scope.kind !== "board-occurrence" || occurrenceId !== scope.occurrenceId)) return false;
  if (partId !== undefined && (scope.kind !== "assembly-part" || partId !== scope.partId)) return false;
  return true;
}
