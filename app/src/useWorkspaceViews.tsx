// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { AssemblySceneModel } from "./mcadAssembly";
import type { ParsedBoard } from "./boardParser";
import type { VirtualBoardVisual } from "./harnessVisualization";
import ScopedWorkspaceView from "./ScopedWorkspaceView";
import WorkspaceViewHost from "./WorkspaceViewHost";
import WorkspaceViewTabs from "./WorkspaceViewTabs";
import { closeAllWorkspaceViewWindows } from "./workspaceViewWindows";
import {
  MAX_WORKSPACE_VIEWS, type WorkspaceViewAction, type WorkspaceViewCandidate, type WorkspaceViewDescriptor,
  actionMatchesWorkspaceView, type WorkspaceViewPresentation, type WorkspaceViewSnapshot, type WorkspaceViewViewportData,
} from "./workspaceViewModel";

export type WorkspaceViewPartCandidate = Readonly<{ partId: string; title: string }>;

export type UseWorkspaceViewsOptions = {
  toolbarHost?: HTMLElement | null;
  projectSession: string;
  revision: string;
  viewportRevision: string;
  boards: Record<string, ParsedBoard>;
  occurrences: readonly VirtualBoardVisual[];
  assemblyModels: readonly AssemblySceneModel[];
  parts: readonly WorkspaceViewPartCandidate[];
  visibility: Record<string, boolean>;
  layerVisibility: Record<string, Record<string, boolean>>;
  layerOpacity: Record<string, Record<string, number>>;
  layerFocus: Record<string, string>;
  linkedNets: Record<string, string[]>;
  analysisDomain?: "pi" | "si" | "em" | "thermal" | "results";
  onAction: (action: WorkspaceViewAction, view: WorkspaceViewDescriptor) => unknown | Promise<unknown>;
  onError?: (message: string) => void;
};

export type WorkspaceViewsController = {
  views: readonly WorkspaceViewDescriptor[];
  activeViewId: string | null;
  setActiveViewId: (viewId: string | null) => void;
  candidates: readonly WorkspaceViewCandidate[];
  tabs: ReactNode;
  /** Mount this in place of the main viewport. Null means Main assembly is active. */
  activeRenderer: ReactNode | null;
  /** Mount once near the application root; hosts render no WebGL content in the owner. */
  hosts: ReactNode;
  addView: (candidate: WorkspaceViewCandidate) => void;
  closeView: (viewId: string) => void;
  detachView: (viewId: string) => void;
};

const safe = (value: string) => value.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-").slice(0, 54) || "scope";
const hash = (value: string) => { let result = 2166136261; for (let i = 0; i < value.length; i++) { result ^= value.charCodeAt(i); result = Math.imul(result, 16777619); } return (result >>> 0).toString(36); };
const scopedId = (prefix: "board" | "part", identity: string) => `${prefix}-${safe(identity)}-${hash(identity)}`;
const pick = <T,>(source: Record<string, T>, id?: string): Record<string, T> => id && source[id] !== undefined ? { [id]: source[id] } : {};
const linkedFor = (source: Record<string, string[]>, occurrenceId?: string) => occurrenceId ? Object.fromEntries(Object.entries(source).filter(([key, values]) => key === occurrenceId || key.startsWith(`${occurrenceId}::`) || values.some(value => value === occurrenceId || value.startsWith(`${occurrenceId}::`)))) : {};
type DerivedWorkspaceView = Pick<WorkspaceViewSnapshot, "targetBoards" | "sourceDesignId" | "visibility" | "layerVisibility" | "layerOpacity" | "layerFocus" | "linkedNets"> & { valid: boolean; invalidReason?: string; viewport: WorkspaceViewViewportData };

/** Pure scope projection used by the hook and focused contract tests. */
export function deriveWorkspaceViewScope(options: Omit<UseWorkspaceViewsOptions, "onAction" | "onError">, view: WorkspaceViewDescriptor): DerivedWorkspaceView {
  const scope = view.scope;
  const occurrence = scope.kind === "board-occurrence" ? options.occurrences.find(item => item.id === scope.occurrenceId && item.designId === scope.designId) : undefined;
  // A fixed board view renders its source board through BoardViewport's
  // primary scene. Mark the projected occurrence active so the assembly scene
  // does not render a second copy of that same design in 3D.
  const targetOccurrence = occurrence ? { ...occurrence, active: true } : undefined;
  const part = scope.kind === "assembly-part" ? options.parts.find(item => item.partId === scope.partId) : undefined;
  const valid = scope.kind === "board-occurrence" ? Boolean(occurrence && options.boards[scope.designId])
    : Boolean(part || options.assemblyModels.some(model => model.partId === scope.partId));
  const identity = scope.kind === "board-occurrence" ? scope.occurrenceId : scope.partId;
  const revision = `${options.viewportRevision.slice(0, 400)}:${scope.kind}:${safe(identity).slice(0, 60)}:${hash(identity)}`;
  return {
    valid, invalidReason: valid ? undefined : scope.kind === "board-occurrence" ? "This board occurrence no longer exists in the active project." : "This assembly part no longer exists in the active project.",
    targetBoards: targetOccurrence ? [targetOccurrence] : [], sourceDesignId: occurrence?.designId,
    visibility: occurrence ? { [occurrence.id]: options.visibility[occurrence.id] !== false } : {},
    layerVisibility: pick(options.layerVisibility, occurrence?.id), layerOpacity: pick(options.layerOpacity, occurrence?.id), layerFocus: pick(options.layerFocus, occurrence?.id),
    linkedNets: linkedFor(options.linkedNets, occurrence?.id),
    viewport: { revision, boards: occurrence && options.boards[occurrence.designId] ? { [occurrence.designId]: options.boards[occurrence.designId] } : {},
      assemblyModels: scope.kind === "assembly-part" ? options.assemblyModels.filter(model => model.partId === scope.partId) : [] },
  };
}

export function useWorkspaceViews(options: UseWorkspaceViewsOptions): WorkspaceViewsController {
  const [views, setViews] = useState<WorkspaceViewDescriptor[]>([]);
  const [activeViewId, setActiveViewId] = useState<string | null>(null);
  const ownedSession = useRef(options.projectSession);
  const latest = useRef(options); latest.current = options;
  const derivedCache = useRef(new Map<string, { inputs: readonly unknown[]; value: DerivedWorkspaceView }>());
  const resultCache = useRef(new Map<string, { inputs: readonly unknown[]; value: { snapshot: WorkspaceViewSnapshot; viewport: WorkspaceViewViewportData } }>());

  useEffect(() => {
    if (ownedSession.current === options.projectSession) return;
    ownedSession.current = options.projectSession; derivedCache.current.clear(); resultCache.current.clear(); setViews([]); setActiveViewId(null); void closeAllWorkspaceViewWindows();
  }, [options.projectSession]);
  useEffect(() => () => { void closeAllWorkspaceViewWindows(); }, []);

  const allCandidates = useMemo<WorkspaceViewCandidate[]>(() => [
    ...options.occurrences.map(board => ({ id: scopedId("board", board.id), title: board.name || board.id, scope: { kind: "board-occurrence" as const, occurrenceId: board.id, designId: board.designId } })),
    ...options.parts.map(part => ({ id: scopedId("part", part.partId), title: part.title || part.partId, scope: { kind: "assembly-part" as const, partId: part.partId } })),
  ].slice(0, 4096), [options.occurrences, options.parts]);
  const candidates = useMemo(() => { const open = new Set(views.map(view => view.id)); return allCandidates.filter(candidate => !open.has(candidate.id)); }, [allCandidates, views]);

  const addView = useCallback((candidate: WorkspaceViewCandidate) => {
    setViews(current => {
      if (current.some(view => view.id === candidate.id)) { setActiveViewId(candidate.id); return current; }
      if (current.length >= MAX_WORKSPACE_VIEWS) { latest.current.onError?.(`At most ${MAX_WORKSPACE_VIEWS} assembly views may be open.`); return current; }
      const descriptor: WorkspaceViewDescriptor = { ...candidate, viewMode: candidate.scope.kind === "board-occurrence" ? "2D" : "3D", detached: false,
        presentation: { viewMode: candidate.scope.kind === "board-occurrence" ? "2D" : "3D", selectionFilter: candidate.scope.kind === "board-occurrence" ? "all" : "part" } };
      setActiveViewId(candidate.id); return [...current, descriptor];
    });
  }, []);
  const closeView = useCallback((viewId: string) => {
    derivedCache.current.delete(viewId); resultCache.current.delete(viewId);
    setViews(current => current.filter(view => view.id !== viewId)); setActiveViewId(current => current === viewId ? null : current);
  }, []);
  const detachView = useCallback((viewId: string) => setViews(current => current.map(view => view.id === viewId ? { ...view, detached: true } : view)), []);
  const dockView = useCallback((viewId: string) => setViews(current => current.map(view => view.id === viewId ? { ...view, detached: false } : view)), []);

  const build = useCallback((view: WorkspaceViewDescriptor): { snapshot: WorkspaceViewSnapshot; viewport: WorkspaceViewViewportData } => {
    const current = latest.current; const scope = view.scope;
    const occurrence = scope.kind === "board-occurrence" ? current.occurrences.find(item => item.id === scope.occurrenceId && item.designId === scope.designId) : undefined;
    const hasPart = scope.kind === "assembly-part" && current.parts.some(item => item.partId === scope.partId);
    const identity = scope.kind === "board-occurrence" ? scope.occurrenceId : scope.partId;
    const scopedViewportRevision = `${current.viewportRevision.slice(0, 400)}:${scope.kind}:${safe(identity).slice(0, 60)}:${hash(identity)}`;
    const derivedInputs = [current.projectSession, current.viewportRevision, scope.kind, identity, occurrence,
      occurrence ? current.boards[occurrence.designId] : undefined, scope.kind === "assembly-part" ? current.assemblyModels : undefined, hasPart,
      occurrence ? current.visibility[occurrence.id] : undefined, occurrence ? current.layerVisibility[occurrence.id] : undefined,
      occurrence ? current.layerOpacity[occurrence.id] : undefined, occurrence ? current.layerFocus[occurrence.id] : undefined,
      occurrence ? current.linkedNets : undefined] as const;
    let derived = derivedCache.current.get(view.id);
    if (!derived || derived.inputs.length !== derivedInputs.length || derived.inputs.some((item, index) => item !== derivedInputs[index])) {
      derived = { inputs: derivedInputs, value: deriveWorkspaceViewScope(current, view) };
      derivedCache.current.set(view.id, derived);
    }
    const admittedRevision = `${current.revision.slice(0, 460)}:${current.analysisDomain ?? "view"}`;
    const resultInputs = [view, current.projectSession, admittedRevision, current.analysisDomain, derived.value] as const;
    const cached = resultCache.current.get(view.id);
    if (cached && cached.inputs.length === resultInputs.length && cached.inputs.every((item, index) => item === resultInputs[index])) return cached.value;
    const snapshot: WorkspaceViewSnapshot = {
      viewId: view.id, projectSession: current.projectSession, revision: admittedRevision, viewportRevision: derived.value.valid ? scopedViewportRevision : null,
      descriptor: view, valid: derived.value.valid, invalidReason: derived.value.invalidReason,
      targetBoards: derived.value.targetBoards, sourceDesignId: derived.value.sourceDesignId,
      visibility: derived.value.visibility, layerVisibility: derived.value.layerVisibility, layerOpacity: derived.value.layerOpacity,
      layerFocus: derived.value.layerFocus, linkedNets: derived.value.linkedNets, analysisDomain: current.analysisDomain,
    };
    const value = { snapshot, viewport: derived.value.viewport }; resultCache.current.set(view.id, { inputs: resultInputs, value }); return value;
  }, []);
  const act = useCallback((view: WorkspaceViewDescriptor, action: WorkspaceViewAction) => {
    const current = latest.current;
    if (current.projectSession !== ownedSession.current) { current.onError?.("The project changed. Review the refreshed assembly before using this view."); return; }
    const scope = view.scope;
    const exists = scope.kind === "board-occurrence"
      ? current.occurrences.some(item => item.id === scope.occurrenceId && item.designId === scope.designId) && Boolean(current.boards[scope.designId])
      : current.parts.some(part => part.partId === scope.partId) || current.assemblyModels.some(model => model.partId === scope.partId);
    if (!exists && !["closed", "redock", "status", "lease"].includes(action.type)) { current.onError?.("This scoped assembly target no longer exists in the active project."); return; }
    if (action.type === "presentation") { const presentation: WorkspaceViewPresentation = action.presentation; setViews(current => current.map(item => item.id === view.id ? { ...item, viewMode: presentation.viewMode, presentation } : item)); return; }
    if (action.type === "closed" || action.type === "redock") { dockView(view.id); return; }
    if (action.type === "lease") return true;
    if (!actionMatchesWorkspaceView(action, view.scope)) { latest.current.onError?.("The requested action does not belong to this fixed assembly view scope."); return; }
    return latest.current.onAction(action, view);
  }, [dockView]);

  const sessionReady = ownedSession.current === options.projectSession;
  const presentedViews = sessionReady ? views : [];
  const presentedActiveId = sessionReady ? activeViewId : null;
  const active = presentedViews.find(view => view.id === presentedActiveId) ?? null;
  const activeData = active ? build(active) : null;
  const tabs = <WorkspaceViewTabs views={presentedViews} activeViewId={presentedActiveId} candidates={sessionReady ? candidates : []} onMain={() => setActiveViewId(null)} onActive={setActiveViewId} onAdd={addView} onClose={closeView} onDetach={(id) => detachView(id)}/>;
  const activeRenderer = active && !active.detached && activeData ? <ScopedWorkspaceView key={`${options.projectSession}:${active.id}`} toolbarHost={options.toolbarHost} snapshot={activeData.snapshot} viewport={activeData.viewport} onAction={action => act(active, action)}/> : null;
  const hosts = <>{presentedViews.filter(view => view.detached).map(view => { const data = build(view); return <WorkspaceViewHost key={`${options.projectSession}:${view.id}`} descriptor={view} snapshot={data.snapshot} viewportData={data.viewport} onAction={action => act(view, action)} onDock={() => dockView(view.id)} onError={options.onError}/>; })}</>;
  return { views: presentedViews, activeViewId: presentedActiveId, setActiveViewId, candidates: sessionReady ? candidates : [], tabs, activeRenderer, hosts, addView, closeView, detachView };
}
