// SPDX-License-Identifier: Apache-2.0
import { createPortal } from "react-dom";
import { Layers3, SlidersHorizontal, X } from "./icons";
import { useEffect, useMemo, useRef, useState } from "react";
import BoardViewport, { type BoardObject, type SelectionFilter } from "./BoardViewport";
import type { Viewport2DState, Viewport3DCameraState } from "./workspaceState";
import type { WorkspaceViewAction, WorkspaceViewPresentation, WorkspaceViewSnapshot, WorkspaceViewViewportData } from "./workspaceViewModel";
import "./WorkspaceViewTabs.css";
import { loadAppSettings } from "./appSettings";
import ViewportEssentialTools from "./ViewportEssentialTools";
import ViewportActionMenu from "./ViewportActionMenu";

const EMPTY: Record<string, boolean> = {};
const EMPTY_OPACITY: Record<string, number> = {};

export default function ScopedWorkspaceView({ snapshot, viewport, connected = true, onAction, toolbarHost }: {
  snapshot: WorkspaceViewSnapshot;
  viewport: WorkspaceViewViewportData | null;
  connected?: boolean;
  toolbarHost?: HTMLElement | null;
  onAction: (action: WorkspaceViewAction) => unknown | Promise<unknown>;
}) {
  const initial = snapshot.descriptor.presentation;
  const [appearance,setAppearance]=useState(loadAppSettings);
  useEffect(()=>{const refresh=()=>setAppearance(loadAppSettings());window.addEventListener("spike-appearance-change",refresh);window.addEventListener("storage",refresh);return()=>{window.removeEventListener("spike-appearance-change",refresh);window.removeEventListener("storage",refresh);};},[]);
  const [viewMode, setViewMode] = useState<"2D" | "3D">(initial?.viewMode ?? snapshot.descriptor.viewMode);
  const [selectionFilter, setSelectionFilter] = useState<SelectionFilter>(initial?.selectionFilter ?? "all");
  const [selected, setSelected] = useState<BoardObject | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(initial?.selectedObjectId ?? null);
  const [navigationMode, setNavigationMode] = useState<"orbit" | "pan">("orbit");
  const [context, setContext] = useState<{x:number;y:number}|null>(null);
  const [layersOpen, setLayersOpen] = useState(false);
  const [actionError, setActionError] = useState("");
  const [cameraCommand, setCameraCommand] = useState("");
  const camera = useRef<Viewport3DCameraState | undefined>(initial?.camera3d);
  const layout = useRef<Viewport2DState | undefined>(initial?.layout2d);
  const lastPresentation = useRef<WorkspaceViewPresentation>({
    viewMode: initial?.viewMode ?? snapshot.descriptor.viewMode,
    selectionFilter: initial?.selectionFilter ?? "all",
    selectedObjectId: initial?.selectedObjectId,
    camera3d: initial?.camera3d,
    layout2d: initial?.layout2d,
  });
  const actionRef = useRef(onAction); actionRef.current = onAction;
  const connectedRef = useRef(connected); connectedRef.current = connected;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scope = snapshot.descriptor.scope;
  const occurrenceId = scope.kind === "board-occurrence" ? scope.occurrenceId : undefined;
  const activeBoard = viewport ? viewport.boards[snapshot.sourceDesignId ?? (scope.kind === "board-occurrence" ? scope.designId : "")]
    ?? Object.values(viewport.boards)[0] ?? null : null;
  const scopedModels = useMemo(() => scope.kind === "assembly-part"
    ? (viewport?.assemblyModels ?? []).filter(model => model.partId === scope.partId) : viewport?.assemblyModels ?? [], [scope, viewport]);
  const layers = occurrenceId ? snapshot.layerVisibility[occurrenceId] ?? EMPTY : EMPTY;
  const opacity = occurrenceId ? snapshot.layerOpacity[occurrenceId] ?? EMPTY_OPACITY : EMPTY_OPACITY;
  const layerNames = useMemo(() => [...new Set([...Object.keys(layers), ...Object.keys(opacity)])].sort(), [layers, opacity]);
  const dispatch = (action: WorkspaceViewAction) => Promise.resolve().then(() => actionRef.current(action)).catch(cause => setActionError(cause instanceof Error ? cause.message : String(cause)));
  const emit = (action: WorkspaceViewAction) => { if (connected) void dispatch(action); };
  const publishPresentation = (next?: Partial<WorkspaceViewPresentation>) => {
    if (timer.current) clearTimeout(timer.current);
    lastPresentation.current = {
      viewMode: next?.viewMode ?? viewMode, selectionFilter: next?.selectionFilter ?? selectionFilter,
      selectedObjectId: next?.selectedObjectId ?? selectedId ?? undefined,
      camera3d: next?.camera3d ?? camera.current, layout2d: next?.layout2d ?? layout.current,
    };
    timer.current = setTimeout(() => { timer.current = null; if (connectedRef.current) void dispatch({ type: "presentation", presentation: lastPresentation.current }); }, 180);
  };
  useEffect(() => () => {
    if (!timer.current) return;
    clearTimeout(timer.current); timer.current = null;
    // Tab switches intentionally unmount inactive WebGL scenes. Flush the last
    // bounded pose first so redocking/remounting cannot lose the user's view.
    if (connectedRef.current) void dispatch({ type: "presentation", presentation: lastPresentation.current });
  }, []);
  const changeMode = (mode: "2D" | "3D") => { setViewMode(mode); publishPresentation({ viewMode: mode }); };
  const changeFilter = (filter: SelectionFilter) => { setSelectionFilter(filter); publishPresentation({ selectionFilter: filter }); };
  const select = (object: BoardObject) => {
    setSelected(object); setSelectedId(object.id); publishPresentation({ selectedObjectId: object.id });
    const id = object.id;
    if (object.assemblyPartId) emit({ type: "select-object", partId: object.assemblyPartId, sourceObjectId: id });
    else if (object.occurrenceId) emit({ type: "select-object", occurrenceId: object.occurrenceId, sourceObjectId: id });
    else if (occurrenceId) emit({ type: "select-object", occurrenceId, sourceObjectId: id });
    if (occurrenceId && object.net) {
      const netId = Object.entries(activeBoard?.nets ?? {}).find(([candidateId, name]) => candidateId === object.net || name === object.net)?.[0] ?? object.net;
      emit({ type: "select-net", occurrenceId, netId });
    }
    if (occurrenceId && object.type === "component") emit({ type: "select-component", occurrenceId, componentId: object.id });
  };
  const command = (name: string) => setCameraCommand(`${name}:${crypto.randomUUID()}`);

  const essentials = <ViewportEssentialTools viewMode={viewMode} navigationMode={navigationMode} selectionFilter={selectionFilter} onMode={changeMode} onNavigation={setNavigationMode} onFilter={changeFilter} onCamera={command}/>;
  const toolbar = <header className="workspace-view-toolbar">
      {essentials}
      <button type="button" disabled={!connected} onClick={() => emit({ type: "open-analysis", domain: snapshot.analysisDomain ?? "results", ...(occurrenceId ? { occurrenceId } : { partId: scope.kind === "assembly-part" ? scope.partId : undefined }) })} className="spike-control--icon" aria-label="Analysis setup" title="Analysis setup"><SlidersHorizontal size={15}/></button>
      {occurrenceId && layerNames.length > 0 && <button type="button" className="spike-control--icon" aria-label="Layer visibility" title="Layer visibility" aria-expanded={layersOpen} onClick={()=>setLayersOpen(value=>!value)}><Layers3 size={15}/></button>}
      <span title={scope.kind === "board-occurrence" ? scope.occurrenceId : scope.partId}>{snapshot.descriptor.title}</span>
    </header>;
  if (!snapshot.valid) return <section className="workspace-view-invalid" role="status"><b>View unavailable</b><span>{snapshot.invalidReason ?? "This assembly scope no longer exists in the active project."}</span></section>;
  return <section className="workspace-view" aria-label={snapshot.descriptor.title}>
    {!connected && <div className="workspace-view-disconnected" role="alert">The owning SPIKE workspace disconnected. This view is read-only; close it and reopen from the project.</div>}
    {actionError && <div className="workspace-view-disconnected" role="alert">{actionError}</div>}
    {toolbarHost ? createPortal(toolbar, toolbarHost) : toolbar}
    {occurrenceId && layerNames.length > 0 && layersOpen && <section className="workspace-view-layers" aria-label="Layer visibility controls"><header><strong>Layers</strong><button type="button" className="spike-control--icon" aria-label="Close layer visibility" onClick={()=>setLayersOpen(false)}><X size={14}/></button></header>{layerNames.map(layer => <div key={layer}>
      <label><input type="checkbox" checked={layers[layer] !== false} disabled={!connected} onChange={event => emit({ type: "layer-visibility", occurrenceId, layer, value: event.target.checked })}/>{layer}</label>
      <input aria-label={`${layer} opacity`} type="range" min="0" max="1" step="0.05" value={opacity[layer] ?? 1} disabled={!connected} onChange={event => emit({ type: "layer-opacity", occurrenceId, layer, value: Number(event.target.value) })}/>
      <button type="button" disabled={!connected} onClick={() => emit({ type: "layer-focus", occurrenceId, layer })}>Focus</button>
    </div>)}</section>}
    <div className="workspace-view-stage">{!viewport ? <div className="workspace-view-loading" role="status">Preparing scoped board graphics…</div> : <BoardViewport
      viewportBackground={appearance.viewportBackground} showWorldGrid={appearance.viewportGrid} renderingQuality={appearance.renderQuality} antialiasing={appearance.antialiasing} maximumFps={appearance.maximumFps}
      board={activeBoard} viewMode={viewMode} visibleLayers={layers} layerOpacity={opacity} layerSeparation={0}
      showVias showModels showSmdModels showThtModels showNetNames={false}
      assemblyModels={scopedModels} virtualBoards={snapshot.targetBoards} assemblyBoardDesigns={viewport.boards}
      assemblyLayerVisibility={snapshot.layerVisibility} assemblyLayerOpacity={snapshot.layerOpacity} assemblyLayerFocus={snapshot.layerFocus}
      onAssemblyLayerFocus={(boardId, layer) => emit({ type: "layer-focus", occurrenceId: boardId, layer })}
      assemblyBoardVisibility={snapshot.visibility} selectedBoardInstanceId={occurrenceId ?? null}
      onBoardInstanceSelect={board => emit({ type: "select-object", occurrenceId: board.id, sourceObjectId: `board:${board.id}` })}
      onAssemblyNetSelect={(boardId, netId) => emit({ type: "select-net", occurrenceId: boardId, netId })}
      onAssemblyComponentSelect={(boardId, componentId) => emit({ type: "select-component", occurrenceId: boardId, componentId })}
      onShowAllAssemblyBoards={() => {}} linkedAssemblyNets={snapshot.linkedNets}
      isolatedAssemblyPartId={scope.kind === "assembly-part" ? scope.partId : null}
      navigationMode={viewMode === "2D" ? "pan" : navigationMode}
      onContextMenu={request=>setContext({x:request.clientX,y:request.clientY})} navigationInertia cameraCommand={cameraCommand}
      viewportRestore={{ token: 1, threeD: initial?.camera3d, twoD: initial?.layout2d }}
      selectionFilter={selectionFilter} selectedId={selectedId} onSelect={select}
      onCamera={value => { camera.current = value; publishPresentation({ camera3d: value }); }}
      onLayoutView={value => { layout.current = value; publishPresentation({ layout2d: value }); }}/>}</div>
    {context && <ViewportActionMenu x={context.x} y={context.y} title={snapshot.descriptor.title} summary={[]} essentialTools={essentials} groups={[{id:"view",label:"View actions",actions:[{id:"fit",label:"Fit scene",run:()=>command("fit")},{id:"focus",label:"Focus selection",disabledReason:!selectedId?"Select an object first":undefined,run:()=>command("focus-selection")}]}]} onClose={()=>setContext(null)}/>}
  </section>;
}
