// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import BoardViewport from "./BoardViewport";
import type { BoardObject } from "./BoardViewport";
import { assemblyDisplayHarnesses, assemblyExplodeOffsets } from "./assemblyDisplayState";
import { extractAssemblySnapTargets, type AssemblySnapTarget } from "./assemblySnapTargets";
import { buildVirtualBoardVisualization, buildVirtualHarnessVisualization, type VirtualBoardVisual } from "./harnessVisualization";
import type { AssemblyDesigns, AssemblyIr } from "./mcadAssembly";
import type { AssemblyToolViewportData } from "./assemblyToolWindowModel";
import "./AssemblyWorkspaceViewport.css";
import AssemblyIconToolbar from "./AssemblyIconToolbar";
import AssemblyViewportHelp from "./AssemblyViewportHelp";
import { Boxes, CircuitBoard, Focus, Maximize, Orbit, Hand, Eye, Layers, PanelRight, CircleHelp, ZoomIn, ArrowDownToLine } from "./icons";

type Props = {
  assembly: AssemblyIr;
  designs: AssemblyDesigns;
  viewport: AssemblyToolViewportData | null;
  selectedBoardId: string | null;
  visibility: Record<string, boolean>;
  layerVisibility: Record<string, Record<string, boolean>>;
  layerOpacity: Record<string, Record<string, number>>;
  layerFocus: Record<string, string>;
  linkedNets: Record<string, string[]>;
  explodedDistanceMm: number;
  moveMode: "translate" | "rotate" | null;
  snapMode: "off" | "hole" | "edge";
  onSelectBoard: (boardId: string) => void;
  onSelectNet: (boardId: string, netId: string) => void;
  onPlacement: (boardId: string, transform: number[]) => void;
  onLayerFocus: (boardId: string, layer: string) => void;
  onSnapTarget: (target: AssemblySnapTarget) => void;
};

const EMPTY_LAYERS: Record<string, boolean> = {};
const EMPTY_OPACITY: Record<string, number> = {};

export default function AssemblyWorkspaceViewport(props: Props) {
  const [viewMode, setViewMode] = useState<"2D" | "3D">("3D");
  const [cameraCommand, setCameraCommand] = useState("");
  const [navigationMode, setNavigationMode] = useState<"orbit" | "pan">("orbit");
  const [showModels, setShowModels] = useState(true);
  const [showVias, setShowVias] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);
  const virtualBoards = useMemo(() => buildVirtualBoardVisualization(props.assembly, props.designs).visuals, [props.assembly, props.designs]);
  const explodeOffsets = useMemo(() => assemblyExplodeOffsets(virtualBoards, props.explodedDistanceMm), [virtualBoards, props.explodedDistanceMm]);
  const harnesses = useMemo(() => assemblyDisplayHarnesses(buildVirtualHarnessVisualization(props.assembly).visuals, props.visibility, explodeOffsets), [props.assembly, props.visibility, explodeOffsets]);
  const snapTargets = useMemo(() => {
    if (props.snapMode === "off" || !props.viewport) return [];
    return virtualBoards.filter(board => props.visibility[board.id] !== false).flatMap(board => {
      const source = props.viewport?.boards[board.designId];
      if (!source) return [];
      try { return extractAssemblySnapTargets(board, source).filter(target => target.kind === props.snapMode); }
      catch { return []; }
    });
  }, [props.snapMode, props.viewport, props.visibility, virtualBoards]);
  const selected = virtualBoards.find(board => board.id === props.selectedBoardId) ?? null;
  const activeBoard = props.viewport?.boards[props.designs.active_design_id] ?? Object.values(props.viewport?.boards ?? {})[0] ?? null;
  const command = (name: string) => setCameraCommand(`${name}:${crypto.randomUUID()}`);

  useEffect(() => {
    const partId = props.selectedBoardId ? `board:${props.selectedBoardId}` : "";
    window.dispatchEvent(new CustomEvent("spike-mcad-gizmo-config", { detail: {
      partId,
      enabled: Boolean(partId && props.moveMode && props.visibility[props.selectedBoardId!] !== false),
      mode: props.moveMode ?? "translate",
      translationSnapMm: 0,
      rotationSnapDeg: 0,
    } }));
    return () => { window.dispatchEvent(new CustomEvent("spike-mcad-gizmo-config", { detail: { partId, enabled: false } })); };
  }, [props.moveMode, props.selectedBoardId, props.visibility, props.viewport?.revision]);
  useEffect(() => {
    const commit = (event: Event) => {
      const detail = (event as CustomEvent<{ partId?: unknown; assemblyTransform?: unknown }>).detail;
      if (!detail || detail.partId !== `board:${props.selectedBoardId}` || !Array.isArray(detail.assemblyTransform)
        || detail.assemblyTransform.length !== 16 || !detail.assemblyTransform.every(value => typeof value === "number" && Number.isFinite(value))) return;
      props.onPlacement(props.selectedBoardId!, detail.assemblyTransform);
    };
    window.addEventListener("spike-mcad-transform-commit", commit);
    return () => window.removeEventListener("spike-mcad-transform-commit", commit);
  }, [props.onPlacement, props.selectedBoardId]);

  return <section className="assembly-workspace-viewport" aria-label="Assembly viewport">
    <div className="assembly-workspace-viewport-toolbar" role="toolbar" aria-label="Assembly viewport controls">
      <AssemblyIconToolbar label="Assembly viewport controls" actions={[
        {id:"2d",label:"2D separated layout",text:"2D",icon:CircuitBoard,pressed:viewMode === "2D",onClick:() => {setViewMode("2D");command("fit");}},
        {id:"3d",label:"3D physical assembly",text:"3D",icon:Boxes,pressed:viewMode === "3D",onClick:() => {setViewMode("3D");command("fit");}},
        {id:"fit",label:"Fit assembly",text:"Fit",icon:Maximize,onClick:() => command("fit")},
        {id:"focus",label:"Focus board",text:"Focus",icon:Focus,disabled:!selected,onClick:() => command("focus-selection")},
        {id:"top",label:"Top view",text:"Top",icon:ArrowDownToLine,onClick:() => command("view-top")},
        {id:"iso",label:"Isometric view",text:"Iso",icon:Boxes,onClick:() => command("view-isometric")},
        {id:"zoom",label:"Zoom in",text:"Zoom",icon:ZoomIn,onClick:() => command("zoom-in")},
        ...(viewMode === "3D" ? [
          {id:"orbit",label:"Orbit: left drag to rotate the camera",text:"Orbit",icon:Orbit,pressed:navigationMode === "orbit",onClick:() => setNavigationMode("orbit")},
          {id:"pan",label:"Pan: drag to move the camera",text:"Pan",icon:Hand,pressed:navigationMode === "pan",onClick:() => setNavigationMode("pan")},
          {id:"models",label:"Show 3D models",text:"Models",icon:Eye,pressed:showModels,onClick:() => setShowModels(value => !value)},
        ] : [{id:"vias",label:"Show vias",text:"Vias",icon:Layers,pressed:showVias,onClick:() => setShowVias(value => !value)}]),
        {id:"help",label:"Assembly viewport help and CLI commands",text:"Help",icon:CircleHelp,pressed:helpOpen,onClick:() => setHelpOpen(value => !value)},
      ]}/>
      <span className="assembly-workspace-viewport-selection" title={selected ? `${selected.name} (${selected.id})` : "All boards"}>{selected?.name ?? "All boards"}</span>
    </div>
    <div className="assembly-workspace-viewport-body">
    <div className="assembly-workspace-viewport-stage">
      {!props.viewport ? <div className="assembly-workspace-viewport-empty" role="status"><b>Preparing retained board graphics…</b><span>The workspace remains connected while the source-bound viewport loads.</span></div> : <BoardViewport
        board={activeBoard}
        viewMode={viewMode}
        visibleLayers={selected ? props.layerVisibility[selected.id] ?? EMPTY_LAYERS : EMPTY_LAYERS}
        layerOpacity={selected ? props.layerOpacity[selected.id] ?? EMPTY_OPACITY : EMPTY_OPACITY}
        layerSeparation={0}
        showVias={showVias}
        showModels={showModels}
        showSmdModels={showModels}
        showThtModels={showModels}
        assemblyModels={props.viewport.assemblyModels ?? []}
        virtualBoards={virtualBoards}
        assemblyBoardDesigns={props.viewport.boards}
        assemblyLayerVisibility={props.layerVisibility}
        assemblyLayerOpacity={props.layerOpacity}
        assemblyLayerFocus={props.layerFocus}
        onAssemblyLayerFocus={props.onLayerFocus}
        assemblyBoardVisibility={props.visibility}
        assemblyExplodeOffsets={explodeOffsets}
        assemblySnapTargets={snapTargets}
        selectedBoardInstanceId={props.selectedBoardId}
        onBoardInstanceSelect={(board: VirtualBoardVisual) => props.onSelectBoard(board.id)}
        onAssemblyNetSelect={props.onSelectNet}
        onShowAllAssemblyBoards={() => { /* All-board framing does not clear the parent editing scope. */ }}
        linkedAssemblyNets={props.linkedNets}
        virtualHarnesses={harnesses}
        onAssemblySnapTarget={props.onSnapTarget}
        navigationMode={navigationMode}
        navigationInertia
        cameraCommand={cameraCommand}
        selectionFilter="all"
        selectedId={null}
        onSelect={(_object: BoardObject) => {}}
        onCamera={() => {}}
      />}
    </div>
    {helpOpen && <aside className="assembly-workspace-viewport-help"><button type="button" className="spike-control--compact" title="Close viewport help" onClick={() => setHelpOpen(false)}><PanelRight size={14}/> Close help</button><AssemblyViewportHelp/></aside>}
    </div>
  </section>;
}
