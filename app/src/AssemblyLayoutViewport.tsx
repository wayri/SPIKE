import { viewportBackgroundColor } from "./viewportEnvironment";
import { assemblyNetLabels } from "./assemblyNetLabels";
import { navigationPanFraction } from "./viewportKeyboardCamera";
import type { ViewportNetTuneHandler } from "./viewportNetTune";
// SPDX-License-Identifier: Apache-2.0
import { memo, useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from "react";
import type { BoardObject, ViewportContextRequest } from "./BoardViewport";
import type { ParsedBoard } from "./boardParser";
import type { VirtualBoardVisual, VirtualHarnessVisual } from "./harnessVisualization";
import { arrangeAssemblyBoards, assemblyDisplaySvgMatrix, assemblyLayerIsRendered, assemblyLayerOpacity as renderedLayerOpacity, assemblyLayoutSourceFrame, assemblyNetIsSelected, boardAssemblyZ, canonicalNetId, displayContentBounds, displayOffsetByBoard, harnessDisplayPoints, inferAssemblyLayoutBoardToSourceOffset, resolveAssemblyLayerFocus, offsetAssemblyPoint, type AssemblyDisplayOffset, type AssemblyViewBox } from "./assemblyLayout2d";
import { layerCssColor } from "./layerPalette";
import "./AssemblyLayoutViewport.css";
import type { AssemblySnapTarget } from "./assemblySnapTargets";
import { assemblyClientPoint, assemblyPanStarted, focusAssemblyViewBox, panAssemblyViewBox, zoomAssemblyViewBox, type AssemblyViewportRect } from "./assemblyViewportInteraction";

// One source alignment per immutable retained board, shared by repeated occurrences.
const sourceAlignmentCache = new WeakMap<ParsedBoard, Promise<AssemblyDisplayOffset | null>>();

export interface AssemblyLayoutViewportProps {
  designs: Record<string, ParsedBoard>;
  boards: VirtualBoardVisual[];
  harnesses: VirtualHarnessVisual[];
  selectedBoardId: string | null;
  linkedNets: Record<string, string[]>;
  visibleLayers: Record<string, boolean>;
  assemblyLayerVisibility?: Record<string, Record<string, boolean>>;
  assemblyLayerOpacity?: Record<string, Record<string, number>>;
  focusedLayerByBoard?: Record<string, string>;
  onLayerFocus?: (boardId: string, layer: string) => void;
  layerOpacity: Record<string, number>;
  showVias: boolean;
  showNetNames?: boolean;
  viewportBackground?: import("./viewportEnvironment").ViewportBackground;
  showWorldGrid?: boolean;
  selectionFilter?: "all" | "part" | "net";
  onBoardSelect: (board: VirtualBoardVisual) => void;
  onShowAllBoards?: () => void;
  onComponentSelect?: (boardId: string, componentId: string) => void;
  onNetSelect: (boardId: string, canonicalNetId: string) => void;
  onNetTune?: ViewportNetTuneHandler;
  onContextMenu?: (request: ViewportContextRequest) => void;
  cameraCommand?: string;
  snapTargets?: AssemblySnapTarget[];
  selectedSnapTargetId?: string | null;
  onSnapTarget?: (target: AssemblySnapTarget) => void;
}

const safeLayerImage = (url: string) => /^(?:blob:|data:image\/svg\+xml(?:;base64)?,|https?:\/\/|asset:|\/demo\/models\/)/i.test(url);
const visible = (layer: string, layers: Record<string, boolean>) => layers[layer] !== false;

type FocusTarget = { boardId: string; bounds: AssemblyViewBox };

function svgGraphicBounds(element: SVGGraphicsElement, svg: SVGSVGElement): AssemblyViewBox | null {
  try {
    const box = element.getBBox();
    const elementMatrix = element.getScreenCTM();
    const svgMatrix = svg.getScreenCTM();
    if (!elementMatrix || !svgMatrix) return null;
    const toSvg = svgMatrix.inverse().multiply(elementMatrix);
    const corners = [[box.x, box.y], [box.x + box.width, box.y], [box.x + box.width, box.y + box.height], [box.x, box.y + box.height]]
      .map(([x, y]) => new DOMPoint(x, y).matrixTransform(toSvg));
    let x = Infinity, y = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const point of corners) {
      if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
      x = Math.min(x, point.x); y = Math.min(y, point.y);
      maxX = Math.max(maxX, point.x); maxY = Math.max(maxY, point.y);
    }
    return { x, y, width: maxX - x, height: maxY - y };
  } catch {
    return null;
  }
}

const EMPTY_LINKED_NETS: string[] = [];
const EMPTY_LAYER_RECORDS = {};

function NetShape({ board, visual, net, onNetSelect, onFocus, selectable = true, children }: { board: ParsedBoard; visual: VirtualBoardVisual; net?: string; onNetSelect: AssemblyLayoutViewportProps["onNetSelect"]; onFocus?: (boardId: string, element: SVGGraphicsElement) => void; selectable?: boolean; children: ReactElement }) {
  const id = canonicalNetId(board, visual.netIdsByName, net, visual.netNamesById);
  return <g data-canonical-net-id={id ?? undefined} onClick={id && selectable ? event => { event.stopPropagation(); onFocus?.(visual.id, event.currentTarget); onNetSelect(visual.id, id); } : undefined} style={{ cursor: id && selectable ? "pointer" : undefined }}>{children}</g>;
}

const BoardFallback = memo(function BoardFallback({ board, visual, visibleLayers, layerOpacity, showVias, onNetSelect, onFocus, netSelectable }: { board: ParsedBoard; visual: VirtualBoardVisual; onFocus: (boardId: string, element: SVGGraphicsElement) => void; netSelectable: boolean } & Pick<AssemblyLayoutViewportProps, "visibleLayers" | "layerOpacity" | "showVias" | "onNetSelect">) {
  const color = (layer: string) => layerCssColor(layer, Math.max(0, board.layers.indexOf(layer)));
  const opacity = (layer: string) => renderedLayerOpacity(layer, layerOpacity);
  return <>
    {board.zones.filter(item => visible(item.layer, visibleLayers)).map((item, i) => <NetShape key={`z:${item.id}:${i}`} board={board} visual={visual} net={item.net} onNetSelect={onNetSelect} onFocus={onFocus} selectable={netSelectable}><path d={[item.points, ...(item.holes ?? [])].map(loop => `M ${loop.map(p => `${p[0]} ${p[1]}`).join(" L ")} Z`).join(" ")} fill={color(item.layer)} fillOpacity={opacity(item.layer) * .38} fillRule="evenodd" /></NetShape>)}
    {board.drawings.filter(item => visible(item.layer, visibleLayers)).map((item, i) => item.points.length > 1 && (item.filled ? <polygon key={`d:${item.id}:${i}`} points={item.points.map(p => p.join(",")).join(" ")} fill={color(item.layer)} opacity={opacity(item.layer)} /> : <polyline key={`d:${item.id}:${i}`} points={item.points.map(p => p.join(",")).join(" ")} fill="none" stroke={color(item.layer)} strokeWidth={Math.max(item.width, .08)} opacity={opacity(item.layer)} />))}
    {board.tracks.filter(item => visible(item.layer, visibleLayers)).map((item, i) => <NetShape key={`t:${item.id}:${i}`} board={board} visual={visual} net={item.net} onNetSelect={onNetSelect} onFocus={onFocus} selectable={netSelectable}><line x1={item.start[0]} y1={item.start[1]} x2={item.end[0]} y2={item.end[1]} stroke={color(item.layer)} strokeWidth={item.width} strokeLinecap="round" opacity={opacity(item.layer)} /></NetShape>)}
    {showVias && board.vias.filter(item => item.layers.some(layer => visible(layer, visibleLayers))).map((item, i) => <NetShape key={`v:${item.id}:${i}`} board={board} visual={visual} net={item.net} onNetSelect={onNetSelect} onFocus={onFocus} selectable={netSelectable}><circle cx={item.at[0]} cy={item.at[1]} r={item.size / 2} fill="#d9b45c" stroke="#fff1b8" strokeWidth={.08} /></NetShape>)}
    {board.pads.filter(item => item.layers.some(layer => visible(layer, visibleLayers))).map((item, i) => <NetShape key={`p:${item.id}:${i}`} board={board} visual={visual} net={item.net} onNetSelect={onNetSelect} onFocus={onFocus} selectable={netSelectable}><rect x={item.at[0] - item.width / 2} y={item.at[1] - item.height / 2} width={item.width} height={item.height} rx={Math.min(item.width, item.height) * .16} fill="#d8a944" transform={`rotate(${item.rotation} ${item.at[0]} ${item.at[1]})`} /></NetShape>)}
  </>;
});

const ComponentShapes = memo(function ComponentShapes({ board, visual, sourceLayers, onBoardSelect, onComponentSelect, onFocus }: { board: ParsedBoard; visual: VirtualBoardVisual; sourceLayers: boolean; onFocus: (boardId: string, element: SVGGraphicsElement) => void } & Pick<AssemblyLayoutViewportProps, "onBoardSelect" | "onComponentSelect">) {
  return <>{board.components.map((item, i) => <g
    key={`c:${item.id}:${i}`}
    data-component-id={item.id}
    transform={`translate(${item.at[0]} ${item.at[1]}) rotate(${item.rotation})`}
    onClick={event => {
      event.stopPropagation();
      onFocus(visual.id, event.currentTarget);
      onBoardSelect(visual);
      onComponentSelect?.(visual.id, item.id);
    }}
    style={{ cursor: onComponentSelect ? "pointer" : undefined }}
  >
    <rect x={-item.width / 2} y={-item.height / 2} width={item.width} height={item.height} fill={sourceLayers ? "transparent" : "none"} stroke={sourceLayers ? "transparent" : "#e6e9ef"} strokeWidth={sourceLayers ? 0 : .12} pointerEvents="all"><title>{item.ref}</title></rect>
    {!sourceLayers && <text fontSize={Math.max(.8, Math.min(item.width / 4, 1.8))} textAnchor="middle" dominantBaseline="central" fill="#f4f5f7" pointerEvents="none">{item.ref}</text>}
  </g>)}</>;
});

const NetHitShapes = memo(function NetHitShapes({ board, visual, linked, visibleLayers, layerOpacity, showVias, onNetSelect, onFocus }: { board: ParsedBoard; visual: VirtualBoardVisual; linked: string[]; onFocus: (boardId: string, element: SVGGraphicsElement) => void } & Pick<AssemblyLayoutViewportProps, "visibleLayers" | "layerOpacity" | "showVias" | "onNetSelect">) {
  const selected = (net?: string) => assemblyNetIsSelected(board, visual.netIdsByName, linked, net, visual.netNamesById);
  const rendered = (layer: string) => assemblyLayerIsRendered(layer, visibleLayers, layerOpacity);
  return <g className="assembly-layout-net-hits">
    {board.zones.filter(item => rendered(item.layer)).map((item, i) => <NetShape key={`zh:${item.id}:${i}`} board={board} visual={visual} net={item.net} onNetSelect={onNetSelect} onFocus={onFocus}><path d={[item.points, ...(item.holes ?? [])].map(loop => `M ${loop.map(point => `${point[0]} ${point[1]}`).join(" L ")} Z`).join(" ")} fill={selected(item.net) ? "#55e5d5" : "transparent"} fillOpacity={selected(item.net) ? .16 : 0} fillRule="evenodd" pointerEvents="fill" /></NetShape>)}
    {board.tracks.filter(item => rendered(item.layer)).map((item, i) => { const isSelected = selected(item.net); return <NetShape key={`th:${item.id}:${i}`} board={board} visual={visual} net={item.net} onNetSelect={onNetSelect} onFocus={onFocus}><g>{isSelected && <line x1={item.start[0]} y1={item.start[1]} x2={item.end[0]} y2={item.end[1]} stroke="#55e5d5" strokeWidth={Math.max(item.width, .28)} strokeLinecap="round" pointerEvents="none" />}<line x1={item.start[0]} y1={item.start[1]} x2={item.end[0]} y2={item.end[1]} stroke="transparent" strokeWidth={Math.max(item.width, .8)} strokeLinecap="round" pointerEvents="stroke" /></g></NetShape>; })}
    {showVias && board.vias.filter(item => item.layers.some(rendered)).map((item, i) => { const isSelected = selected(item.net); return <NetShape key={`vh:${item.id}:${i}`} board={board} visual={visual} net={item.net} onNetSelect={onNetSelect} onFocus={onFocus}><g>{isSelected && <circle cx={item.at[0]} cy={item.at[1]} r={item.size / 2} fill="#55e5d5" fillOpacity={.86} pointerEvents="none" />}<circle cx={item.at[0]} cy={item.at[1]} r={Math.max(item.size / 2, .5)} fill="transparent" pointerEvents="all" /></g></NetShape>; })}
    {board.pads.filter(item => item.layers.some(rendered)).map((item, i) => <NetShape key={`ph:${item.id}:${i}`} board={board} visual={visual} net={item.net} onNetSelect={onNetSelect} onFocus={onFocus}><rect x={item.at[0] - item.width / 2} y={item.at[1] - item.height / 2} width={item.width} height={item.height} rx={Math.min(item.width, item.height) * .16} fill={selected(item.net) ? "#55e5d5" : "transparent"} fillOpacity={selected(item.net) ? .76 : 0} transform={`rotate(${item.rotation} ${item.at[0]} ${item.at[1]})`} pointerEvents="all" /></NetShape>)}
  </g>;
});

export default function AssemblyLayoutViewport({ designs, boards, harnesses, selectedBoardId, linkedNets, visibleLayers, assemblyLayerVisibility = EMPTY_LAYER_RECORDS, assemblyLayerOpacity = EMPTY_LAYER_RECORDS, focusedLayerByBoard, onLayerFocus, layerOpacity, showVias, showNetNames = false, viewportBackground = "dark", showWorldGrid = true, selectionFilter = "all", onBoardSelect, onShowAllBoards, onComponentSelect, onNetSelect, onNetTune, onContextMenu, cameraCommand = "", snapTargets = [], selectedSnapTargetId = null, onSnapTarget }: AssemblyLayoutViewportProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<{ pointerId: number; x: number; y: number; view: AssemblyViewBox; panning: boolean } | null>(null);
  const suppressClick = useRef(false);
  const keyboardPointer=useRef<{clientX:number;clientY:number}|null>(null);
  const handledCameraCommand = useRef("");
  const lastFocus = useRef<FocusTarget | null>(null);
  const [localFocusedLayerByBoard, setLocalFocusedLayerByBoard] = useState<Record<string, string>>({});
  const netFocusActive = Object.values(linkedNets).some(nets => nets.length > 0);
  const netFocusStyle = netFocusActive ? { filter: "grayscale(1) brightness(.68)" } : undefined;
  const layerFocusByBoard = focusedLayerByBoard ?? localFocusedLayerByBoard;
  const [sourceAlignments, setSourceAlignments] = useState<Record<string, { board: ParsedBoard; offset: AssemblyDisplayOffset | null }>>({});
  const sourceOffsetsByDesign = useMemo(() => Object.fromEntries(Object.entries(sourceAlignments)
    .filter(([id, row]) => designs[id] === row.board).map(([id, row]) => [id, row.offset])), [sourceAlignments, designs]);
  useEffect(() => {
    let cancelled = false;
    void Promise.all(Object.entries(designs).map(async ([designId, board]) => {
      let alignment = sourceAlignmentCache.get(board);
      if (!alignment) {
        alignment = (async () => {
          const url = board.layoutLayerUrls?.["Edge.Cuts"];
          if (!url || !safeLayerImage(url)) return null;
          try {
            const response = await fetch(url);
            if (!response.ok) return null;
            return inferAssemblyLayoutBoardToSourceOffset(board, await response.text());
          } catch { return null; }
        })();
        sourceAlignmentCache.set(board, alignment);
      }
      return [designId, { board, offset: await alignment }] as const;
    })).then(entries => { if (!cancelled) setSourceAlignments(Object.fromEntries(entries)); });
    return () => { cancelled = true; };
  }, [designs]);
  const placements = useMemo(() => arrangeAssemblyBoards(boards, designs, 5, sourceOffsetsByDesign), [boards, designs, sourceOffsetsByDesign]);
  const offsets = useMemo(() => displayOffsetByBoard(placements), [placements]);
  const placementById = useMemo(() => Object.fromEntries(placements.map(item => [item.visual.id, item])), [placements]);
  const fit = useMemo(() => displayContentBounds(placements, harnesses), [placements, harnesses]);
  // Immutable source artwork and occurrence layers do not change while panning.
  // Keep their props stable so React reuses the full geometry/hit-target trees.
  const presentationById = useMemo(() => new Map(boards.flatMap(visual => {
    const board = designs[visual.designId];
    if (!board) return [];
    const savedLayers = assemblyLayerVisibility[visual.id] ?? visibleLayers;
    const boardOpacity = assemblyLayerOpacity[visual.id] ?? layerOpacity;
    const layerFocus = resolveAssemblyLayerFocus(board, layerFocusByBoard[visual.id]);
    const allLayerNames = new Set([...board.layerDefinitions.map(layer => layer.name), ...board.layers,
      ...board.drawings.map(item => item.layer), ...board.tracks.map(item => item.layer),
      ...board.zones.map(item => item.layer), ...Object.keys(board.layoutLayerUrls ?? {})]);
    const boardLayers = layerFocus === "All" ? savedLayers : Object.fromEntries([...allLayerNames].map(layer =>
      [layer, visible(layer, savedLayers) && (layerFocus === "Overview" ? board.layers.includes(layer) : layer === layerFocus)]));
    const sourceLayers = Object.entries(board.layoutLayerUrls ?? {}).filter(([, url]) => safeLayerImage(url));
    const sourceOffset = sourceOffsetsByDesign[visual.designId];
    const hasAlignedSource = sourceLayers.length > 0 && sourceOffset != null;
    const useFallback = !hasAlignedSource;
    const layers = hasAlignedSource ? sourceLayers.filter(([layer]) => assemblyLayerIsRendered(layer, boardLayers, boardOpacity)) : [];
    const sourceFrame = assemblyLayoutSourceFrame(board, sourceOffset ?? undefined);
    return [[visual.id, { layerFocus, boardLayers, hasAlignedSource, useFallback, layers, sourceFrame, boardOpacity }] as const];
  })), [boards, designs, assemblyLayerVisibility, assemblyLayerOpacity, visibleLayers, layerOpacity, layerFocusByBoard, sourceOffsetsByDesign]);
  const [view, setView] = useState(fit);
  const viewportRect = (): AssemblyViewportRect => {
    const rect = svgRef.current?.getBoundingClientRect();
    return { left: rect?.left ?? 0, top: rect?.top ?? 0, width: Math.max(rect?.width ?? 1, 1), height: Math.max(rect?.height ?? 1, 1) };
  };
  const frame = (bounds: AssemblyViewBox, margin = .12) => {
    const rect = viewportRect();
    return focusAssemblyViewBox(bounds, rect.width / rect.height, margin);
  };
  const focusSelection = () => {
    const remembered = lastFocus.current?.boardId === selectedBoardId ? lastFocus.current.bounds : null;
    const boardBounds = selectedBoardId ? placementById[selectedBoardId]?.bounds : null;
    if (remembered ?? boardBounds) setView(frame((remembered ?? boardBounds)!));
  };
  const rememberGraphic = useCallback((boardId: string, element: SVGGraphicsElement) => {
    const bounds = svgRef.current ? svgGraphicBounds(element, svgRef.current) : null;
    if (bounds) lastFocus.current = { boardId, bounds };
  }, []);
  useEffect(() => setView(frame(fit, .03)), [fit.x, fit.y, fit.width, fit.height]);
  const netTuneRef = useRef(onNetTune);
  netTuneRef.current = onNetTune;
  const tuneBoardsRef = useRef({ boards, designs });
  tuneBoardsRef.current = { boards, designs };
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (event: WheelEvent) => {
      if (event.shiftKey && event.target instanceof Element) {
        const netId = event.target.closest("[data-canonical-net-id]")?.getAttribute("data-canonical-net-id");
        const occurrenceId = event.target.closest("[data-board-id]")?.getAttribute("data-board-id");
        const visual = tuneBoardsRef.current.boards.find(row => row.id === occurrenceId);
        const design = visual && tuneBoardsRef.current.designs[visual.designId];
        const net = netId && design ? design.nets[netId] ?? visual?.netNamesById?.[netId] : undefined;
        if (net && netTuneRef.current?.({ net, occurrenceId: occurrenceId ?? undefined, deltaY: event.deltaY, altKey: event.altKey })) { event.preventDefault(); event.stopPropagation(); return; }
      }
      event.preventDefault();
      const rect = svg.getBoundingClientRect();
      const factor = event.deltaY < 0 ? .82 : 1.22;
      setView(current => zoomAssemblyViewBox(current, rect, event.clientX, event.clientY, factor));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);
  useEffect(() => {
    if (!cameraCommand || handledCameraCommand.current === cameraCommand) return;
    handledCameraCommand.current = cameraCommand;
    if (cameraCommand.startsWith("fit")) { setView(frame(fit, .03)); return; }
    if (cameraCommand.startsWith("focus-selection")) { focusSelection(); return; }
    if(cameraCommand.startsWith("center-cursor")){
      const svg=svgRef.current,pointer=keyboardPointer.current;if(svg&&pointer)setView(current=>{const point=assemblyClientPoint(current,svg.getBoundingClientRect(),pointer.clientX,pointer.clientY);return {...current,x:point[0]-current.width/2,y:point[1]-current.height/2};});return;
    }
    setView(current => {
      if (cameraCommand.startsWith("zoom-")) { const factor = cameraCommand.startsWith("zoom-in") ? .8 : 1.25; const svg=svgRef.current,pointer=keyboardPointer.current;if(cameraCommand.includes("-cursor")&&svg&&pointer)return zoomAssemblyViewBox(current,svg.getBoundingClientRect(),pointer.clientX,pointer.clientY,factor); return { x: current.x + current.width * (1 - factor) / 2, y: current.y + current.height * (1 - factor) / 2, width: current.width * factor, height: current.height * factor }; }
      const step=navigationPanFraction(cameraCommand);const dx = current.width * step, dy = current.height * step;
      return { ...current, x: current.x + (cameraCommand.startsWith("pan-left") ? -dx : cameraCommand.startsWith("pan-right") ? dx : 0), y: current.y + (cameraCommand.startsWith("pan-up") ? -dy : cameraCommand.startsWith("pan-down") ? dy : 0) };
    });
  }, [cameraCommand, fit]);
  const sorted = useMemo(() => [...boards].sort((a, b) => boardAssemblyZ(a) - boardAssemblyZ(b)), [boards]);
  const selected = sorted.find(board => board.id === selectedBoardId);
  const selectedDesign = selected ? designs[selected.designId] : null;
  const selectedLayerFocus = resolveAssemblyLayerFocus(selectedDesign, selected ? layerFocusByBoard[selected.id] : undefined);
  const drawOrder = selected ? [...sorted.filter(board => board.id !== selected.id), selected] : sorted;
  return <div className="assembly-layout-viewport" style={{ background: viewportBackgroundColor(viewportBackground) }} >
    <div className="assembly-layout-controls" role="toolbar" aria-label="Assembly layout controls"><select aria-label="Visible assembly board" value={selectedBoardId ?? ""} onChange={event => { if (!event.target.value) { lastFocus.current = null; onShowAllBoards?.(); setView(frame(fit, .03)); return; } const board = boards.find(item => item.id === event.target.value); if (board) { const bounds = placementById[board.id]?.bounds; lastFocus.current = bounds ? { boardId: board.id, bounds } : null; onBoardSelect(board); } }}><option value="">All boards</option>{boards.map(board => <option key={board.id} value={board.id}>{board.name} (Z {boardAssemblyZ(board).toFixed(2)} mm)</option>)}</select><select className="assembly-layout-layer-focus" aria-label="Focused board layer" disabled={!selected || !selectedDesign} value={selectedLayerFocus} onChange={event => { if (!selected) return; const layer = event.target.value; setLocalFocusedLayerByBoard(current => ({ ...current, [selected.id]: layer })); onLayerFocus?.(selected.id, layer); }}><option value="All">All layers</option><option value="Overview">Copper overview</option>{selectedDesign?.layers.map(layer => <option key={layer} value={layer}>{layer}</option>)}</select><button type="button" onClick={() => setView(frame(fit, .03))}>Fit</button><button type="button" disabled={!selectedBoardId} onClick={focusSelection}>Focus</button></div>
    <svg ref={svgRef} className="assembly-layout-drawing" aria-label="2D multi-board assembly" viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`} width="100%" height="100%" onClickCapture={event => { if (!suppressClick.current) return; suppressClick.current = false; event.preventDefault(); event.stopPropagation(); }} onDoubleClick={event => { event.preventDefault(); setView(frame(fit, .03)); }} onPointerDown={event => { if (event.button === 0 && event.isPrimary) drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, view, panning: false }; }} onPointerMove={event => { keyboardPointer.current={clientX:event.clientX,clientY:event.clientY};const current = drag.current; if (!current || current.pointerId !== event.pointerId) return; const dx = event.clientX - current.x, dy = event.clientY - current.y; if (!current.panning) { if (!assemblyPanStarted(dx, dy)) return; current.panning = true; event.currentTarget.setPointerCapture(event.pointerId); event.currentTarget.style.cursor = "grabbing"; } event.preventDefault(); setView(panAssemblyViewBox(current.view, event.currentTarget.getBoundingClientRect(), dx, dy)); }} onPointerUp={event => { const current = drag.current; if (current?.pointerId !== event.pointerId) return; if (current.panning) { suppressClick.current = true; window.setTimeout(() => { suppressClick.current = false; }, 0); } drag.current = null; event.currentTarget.style.cursor = ""; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }} onPointerCancel={event => { if (drag.current?.pointerId !== event.pointerId) return; drag.current = null; suppressClick.current = false; event.currentTarget.style.cursor = ""; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }} onPointerLeave={() => { keyboardPointer.current=null;if (drag.current && !drag.current.panning) drag.current = null; }} onLostPointerCapture={event => { if (drag.current?.pointerId === event.pointerId) drag.current = null; event.currentTarget.style.cursor = ""; }}>
      <defs><pattern id="assembly-world-grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M 10 0 L 0 0 0 10" fill="none" stroke={viewportBackground === "light" ? "#9aadb6" : "#344a54"} strokeWidth="0.15" /></pattern></defs>
      {showWorldGrid && <rect x={view.x} y={view.y} width={view.width} height={view.height} fill="url(#assembly-world-grid)" opacity={0.5} pointerEvents="none" />}
      {drawOrder.map(visual => { const board = designs[visual.designId]; const placement = placementById[visual.id]; const prepared = presentationById.get(visual.id); if (!board || !placement || !prepared) return null; const isSelected = visual.id === selectedBoardId; const { layerFocus, boardLayers, hasAlignedSource, useFallback, layers, sourceFrame, boardOpacity } = prepared; return <g key={visual.id} data-board-id={visual.id} onContextMenu={event => {
        event.preventDefault(); event.stopPropagation();
        const frame = event.currentTarget.querySelector<SVGGElement>("[data-layout-board-frame]");
        const matrix = frame?.getScreenCTM(); if (!matrix) return;
        const source = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
        const point: [number, number] = [source.x, source.y];
        const target = event.target as Element;
        const componentId = target.closest("[data-component-id]")?.getAttribute("data-component-id");
        const component = board.components.find(item => item.id === componentId);
        const netId = target.closest("[data-canonical-net-id]")?.getAttribute("data-canonical-net-id");
        let object: BoardObject | null = null;
        onBoardSelect(visual);
        if (component) {
          onComponentSelect?.(visual.id, component.id);
          object = { id: component.id, type: "component", name: component.ref, ref: component.ref, position: point, occurrenceId: visual.id };
        } else if (netId) {
          onNetSelect(visual.id, netId);
          const net = visual.netNamesById?.[netId] ?? netId;
          object = { id: `assembly-net:${visual.id}:${netId}`, type: "trace", name: net, net, position: point, occurrenceId: visual.id };
        }
        onContextMenu?.({clientX:event.clientX, clientY:event.clientY, object,
          thermalTarget:{pointMm:point, componentRef:component?.ref, occurrenceId:visual.id}});
      }} data-net-focus={netFocusActive ? "active" : undefined} data-layer-focus={layerFocus} transform={assemblyDisplaySvgMatrix(visual.transform, offsets[visual.id] ?? [0, 0])} opacity={selectedBoardId && !isSelected ? .42 : 1} onClick={() => { lastFocus.current = { boardId: visual.id, bounds: placement.bounds }; onBoardSelect(visual); }} style={{ cursor: "pointer" }}>
        <g data-layout-source-frame transform={`translate(${sourceFrame.sourceToBoardOffset[0]} ${sourceFrame.sourceToBoardOffset[1]})`}>
          {layers.map(([layer, url]) => <image key={layer} href={url} x={sourceFrame.sourceViewBox.x} y={sourceFrame.sourceViewBox.y} width={sourceFrame.sourceViewBox.width} height={sourceFrame.sourceViewBox.height} opacity={renderedLayerOpacity(layer, boardOpacity) * (netFocusActive ? .32 : 1)} style={netFocusStyle} preserveAspectRatio="none" pointerEvents="none" />)}
          <g data-layout-board-frame transform={`translate(${sourceFrame.boardToSourceOffset[0]} ${sourceFrame.boardToSourceOffset[1]})`}>
            <rect x={board.bounds.minX} y={board.bounds.minY} width={board.width} height={board.height} fill="transparent" pointerEvents="all" />
            {useFallback && <g opacity={netFocusActive ? .32 : 1} style={netFocusStyle}><BoardFallback board={board} visual={visual} visibleLayers={boardLayers} layerOpacity={boardOpacity} showVias={showVias} onNetSelect={onNetSelect} onFocus={rememberGraphic} netSelectable={selectionFilter !== "part"} /></g>}
            {selectionFilter !== "part" && <NetHitShapes board={board} visual={visual} linked={linkedNets[visual.id] ?? EMPTY_LINKED_NETS} visibleLayers={boardLayers} layerOpacity={boardOpacity} showVias={showVias} onNetSelect={onNetSelect} onFocus={rememberGraphic} />}
            {selectionFilter !== "net" && <ComponentShapes board={board} visual={visual} sourceLayers={hasAlignedSource} onBoardSelect={onBoardSelect} onComponentSelect={onComponentSelect} onFocus={rememberGraphic} />}
            {showNetNames && <g className="assembly-net-labels" pointerEvents="none" fill="#eaf5fa" stroke="#101820" strokeWidth={.16} paintOrder="stroke" textAnchor="middle" dominantBaseline="central">
              {assemblyNetLabels(board,visual,boardLayers,boardOpacity,view.width / Math.max(svgRef.current?.clientWidth ?? 800,1)).map(label => <text key={`${label.layer}:${label.kind}:${label.id}`} data-net-label={label.canonicalNetId} data-occurrence-id={visual.id} x={label.x} y={label.y} fontSize={label.fontSize} transform={`rotate(${label.angle} ${label.x} ${label.y})`}><title>{`${visual.name}: ${label.net} (${label.layer})`}</title>{label.net}</text>)}
            </g>}
            <rect x={board.bounds.minX} y={board.bounds.minY} width={board.width} height={board.height} fill="none" stroke={isSelected ? "#6ee7ff" : "#8295a5"} strokeWidth={isSelected ? .45 : .16} vectorEffect="non-scaling-stroke" pointerEvents="stroke" />
          </g>
        </g>
      </g>; })}
      {snapTargets.map(target => { const point = offsetAssemblyPoint(target.worldPointMm, offsets[target.occurrenceId]); return target.kind === "hole"
        ? <circle data-assembly-snap="hole" key={target.id} cx={point[0]} cy={point[1]} r={Math.max(view.width / 250, .6)} fill={target.id === selectedSnapTargetId ? "#ffd32a" : "#6ee7ff"} fillOpacity={.8} onClick={event => { event.stopPropagation(); onSnapTarget?.(target); }} style={{ cursor: "crosshair" }}><title>{target.occurrenceId}: {target.sourceId}</title></circle>
        : <line data-assembly-snap="edge" key={target.id} x1={point[0] - target.worldDirection[0] * target.lengthMm / 2} y1={point[1] - target.worldDirection[1] * target.lengthMm / 2} x2={point[0] + target.worldDirection[0] * target.lengthMm / 2} y2={point[1] + target.worldDirection[1] * target.lengthMm / 2} stroke={target.id === selectedSnapTargetId ? "#ffd32a" : "#6ee7ff"} strokeWidth={Math.max(view.width / 250, .6)} onClick={event => { event.stopPropagation(); onSnapTarget?.(target); }} style={{ cursor: "crosshair" }}><title>{target.occurrenceId}: {target.sourceId}</title></line>; })}
      {harnesses.map(harness => <polyline key={harness.id} data-harness-id={harness.id} points={harnessDisplayPoints(harness, offsets).map(point => `${point[0]},${point[1]}`).join(" ")} fill="none" stroke="#f2b84b" strokeWidth={Math.max(view.width / 700, .25)} strokeDasharray={harness.routedPolyline ? undefined : `${view.width / 120} ${view.width / 180}`} pointerEvents="none" />)}
    </svg>
  </div>;
}
