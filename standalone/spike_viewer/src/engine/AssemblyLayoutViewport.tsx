// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState, type ReactElement } from "react";
import type { ParsedBoard } from "./boardTypes";
import type { VirtualBoardVisual, VirtualHarnessVisual } from "./harnessVisualization";
import { assemblyContentBounds, assemblySvgMatrix, boardAssemblyZ, canonicalNetId, harnessAssemblyPoints, type AssemblyViewBox } from "./assemblyLayout2d";
import { layerCssColor } from "./layerPalette";
import "./AssemblyLayoutViewport.css";
import type { AssemblySnapTarget } from "./assemblySnapTargets";

export interface AssemblyLayoutViewportProps {
  designs: Record<string, ParsedBoard>;
  boards: VirtualBoardVisual[];
  harnesses: VirtualHarnessVisual[];
  selectedBoardId: string | null;
  linkedNets: Record<string, string[]>;
  visibleLayers: Record<string, boolean>;
  assemblyLayerVisibility?: Record<string, Record<string, boolean>>;
  assemblyLayerOpacity?: Record<string, Record<string, number>>;
  layerOpacity: Record<string, number>;
  showVias: boolean;
  onBoardSelect: (board: VirtualBoardVisual) => void;
  onNetSelect: (boardId: string, canonicalNetId: string) => void;
  cameraCommand?: string;
  snapTargets?: AssemblySnapTarget[];
  selectedSnapTargetId?: string | null;
  onSnapTarget?: (target: AssemblySnapTarget) => void;
}

const safeLayerImage = (url: string) => /^(?:blob:|data:image\/svg\+xml(?:;base64)?,|https?:\/\/|asset:|\/demo\/models\/)/i.test(url);
const visible = (layer: string, layers: Record<string, boolean>) => layers[layer] !== false;

function NetShape({ board, visual, linked, net, onNetSelect, children }: { board: ParsedBoard; visual: VirtualBoardVisual; linked: string[]; net?: string; onNetSelect: AssemblyLayoutViewportProps["onNetSelect"]; children: ReactElement }) {
  const id = canonicalNetId(board, visual.netIdsByName, net);
  return <g data-canonical-net-id={id ?? undefined} onClick={id ? event => { event.stopPropagation(); onNetSelect(visual.id, id); } : undefined} style={{ cursor: id ? "pointer" : undefined, filter: id && linked.includes(id) ? "drop-shadow(0 0 1px #ffe25b)" : undefined }}>{children}</g>;
}

function BoardFallback({ board, visual, linked, visibleLayers, layerOpacity, showVias, onNetSelect }: { board: ParsedBoard; visual: VirtualBoardVisual; linked: string[] } & Pick<AssemblyLayoutViewportProps, "visibleLayers" | "layerOpacity" | "showVias" | "onNetSelect">) {
  const color = (layer: string) => layerCssColor(layer, Math.max(0, board.layers.indexOf(layer)));
  const opacity = (layer: string) => Math.max(0, Math.min(1, layerOpacity[layer] ?? 1));
  return <>
    {board.zones.filter(item => visible(item.layer, visibleLayers)).map((item, i) => <NetShape key={`z:${item.id}:${i}`} board={board} visual={visual} linked={linked} net={item.net} onNetSelect={onNetSelect}><path d={[item.points, ...(item.holes ?? [])].map(loop => `M ${loop.map(p => `${p[0]} ${p[1]}`).join(" L ")} Z`).join(" ")} fill={color(item.layer)} fillOpacity={opacity(item.layer) * .38} fillRule="evenodd" /></NetShape>)}
    {board.drawings.filter(item => visible(item.layer, visibleLayers)).map((item, i) => item.points.length > 1 && (item.filled ? <polygon key={`d:${item.id}:${i}`} points={item.points.map(p => p.join(",")).join(" ")} fill={color(item.layer)} opacity={opacity(item.layer)} /> : <polyline key={`d:${item.id}:${i}`} points={item.points.map(p => p.join(",")).join(" ")} fill="none" stroke={color(item.layer)} strokeWidth={Math.max(item.width, .08)} opacity={opacity(item.layer)} />))}
    {board.tracks.filter(item => visible(item.layer, visibleLayers)).map((item, i) => <NetShape key={`t:${item.id}:${i}`} board={board} visual={visual} linked={linked} net={item.net} onNetSelect={onNetSelect}><line x1={item.start[0]} y1={item.start[1]} x2={item.end[0]} y2={item.end[1]} stroke={color(item.layer)} strokeWidth={item.width} strokeLinecap="round" opacity={opacity(item.layer)} /></NetShape>)}
    {showVias && board.vias.filter(item => item.layers.some(layer => visible(layer, visibleLayers))).map((item, i) => <NetShape key={`v:${item.id}:${i}`} board={board} visual={visual} linked={linked} net={item.net} onNetSelect={onNetSelect}><circle cx={item.at[0]} cy={item.at[1]} r={item.size / 2} fill="#d9b45c" stroke="#fff1b8" strokeWidth={.08} /></NetShape>)}
    {board.pads.filter(item => item.layers.some(layer => visible(layer, visibleLayers))).map((item, i) => <NetShape key={`p:${item.id}:${i}`} board={board} visual={visual} linked={linked} net={item.net} onNetSelect={onNetSelect}><rect x={item.at[0] - item.width / 2} y={item.at[1] - item.height / 2} width={item.width} height={item.height} rx={Math.min(item.width, item.height) * .16} fill="#d8a944" transform={`rotate(${item.rotation} ${item.at[0]} ${item.at[1]})`} /></NetShape>)}
    {board.components.map((item, i) => <g key={`c:${item.id}:${i}`} transform={`translate(${item.at[0]} ${item.at[1]}) rotate(${item.rotation})`} pointerEvents="none"><rect x={-item.width / 2} y={-item.height / 2} width={item.width} height={item.height} fill="none" stroke="#e6e9ef" strokeWidth={.12} /><text fontSize={Math.max(.8, Math.min(item.width / 4, 1.8))} textAnchor="middle" dominantBaseline="central" fill="#f4f5f7">{item.ref}</text></g>)}
  </>;
}

export default function AssemblyLayoutViewport({ designs, boards, harnesses, selectedBoardId, linkedNets, visibleLayers, assemblyLayerVisibility = {}, assemblyLayerOpacity = {}, layerOpacity, showVias, onBoardSelect, onNetSelect, cameraCommand = "", snapTargets = [], selectedSnapTargetId = null, onSnapTarget }: AssemblyLayoutViewportProps) {
  const drag = useRef<{ x: number; y: number; view: AssemblyViewBox } | null>(null);
  const fit = useMemo(() => assemblyContentBounds(boards, designs, harnesses), [boards, designs, harnesses]);
  const [view, setView] = useState(fit);
  useEffect(() => setView(fit), [fit.x, fit.y, fit.width, fit.height]);
  useEffect(() => {
    if (!cameraCommand) return;
    if (cameraCommand.startsWith("fit")) { setView(fit); return; }
    setView(current => {
      if (cameraCommand.startsWith("zoom-")) { const factor = cameraCommand.startsWith("zoom-in") ? .8 : 1.25; return { x: current.x + current.width * (1 - factor) / 2, y: current.y + current.height * (1 - factor) / 2, width: current.width * factor, height: current.height * factor }; }
      const dx = current.width * .08, dy = current.height * .08;
      return { ...current, x: current.x + (cameraCommand.startsWith("pan-left") ? -dx : cameraCommand.startsWith("pan-right") ? dx : 0), y: current.y + (cameraCommand.startsWith("pan-up") ? -dy : cameraCommand.startsWith("pan-down") ? dy : 0) };
    });
  }, [cameraCommand, fit]);
  const sorted = useMemo(() => [...boards].sort((a, b) => boardAssemblyZ(a) - boardAssemblyZ(b)), [boards]);
  const selected = sorted.find(board => board.id === selectedBoardId);
  const drawOrder = selected ? [...sorted.filter(board => board.id !== selected.id), selected] : sorted;
  return <div className="assembly-layout-viewport" >
    <div className="assembly-layout-controls" role="toolbar" aria-label="Assembly layout controls"><select aria-label="Visible assembly board" value={selectedBoardId ?? ""} onChange={event => { const board = boards.find(item => item.id === event.target.value); if (board) onBoardSelect(board); }}><option value="">All boards</option>{boards.map(board => <option key={board.id} value={board.id}>{board.name} (Z {boardAssemblyZ(board).toFixed(2)} mm)</option>)}</select><button type="button" onClick={() => setView(fit)}>Fit</button></div>
    <svg className="assembly-layout-drawing" aria-label="2D multi-board assembly" viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`} width="100%" height="100%" onWheel={event => { event.preventDefault(); const rect = event.currentTarget.getBoundingClientRect(), px = (event.clientX - rect.left) / Math.max(rect.width, 1), py = (event.clientY - rect.top) / Math.max(rect.height, 1), factor = event.deltaY < 0 ? .82 : 1.22; setView(old => ({ x: old.x + old.width * px * (1 - factor), y: old.y + old.height * py * (1 - factor), width: old.width * factor, height: old.height * factor })); }} onPointerDown={event => { if (event.button === 0 && !(event.target instanceof Element && event.target.closest("[data-assembly-snap]"))) { event.currentTarget.setPointerCapture(event.pointerId); drag.current = { x: event.clientX, y: event.clientY, view }; } }} onPointerMove={event => { if (!drag.current) return; const rect = event.currentTarget.getBoundingClientRect(); setView({ ...drag.current.view, x: drag.current.view.x - (event.clientX - drag.current.x) * drag.current.view.width / Math.max(rect.width, 1), y: drag.current.view.y - (event.clientY - drag.current.y) * drag.current.view.height / Math.max(rect.height, 1) }); }} onPointerUp={event => { drag.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}>
      {drawOrder.map(visual => { const board = designs[visual.designId]; const boardLayers = assemblyLayerVisibility[visual.id] ?? visibleLayers; const boardOpacity = assemblyLayerOpacity[visual.id] ?? layerOpacity; if (!board) return null; const isSelected = visual.id === selectedBoardId; const layers = Object.entries(board.layoutLayerUrls ?? {}).filter(([layer, url]) => visible(layer, boardLayers) && safeLayerImage(url)); const box = board.layoutViewBox ?? [board.bounds.minX, board.bounds.minY, board.width, board.height]; return <g key={visual.id} data-board-id={visual.id} transform={assemblySvgMatrix(visual.transform)} opacity={selectedBoardId && !isSelected ? .42 : 1} onClick={() => onBoardSelect(visual)} style={{ cursor: "pointer" }}>
        <rect x={board.bounds.minX} y={board.bounds.minY} width={board.width} height={board.height} fill="transparent" pointerEvents="all" />
        {layers.length ? layers.map(([layer, url]) => <image key={layer} href={url} x={box[0]} y={box[1]} width={box[2]} height={box[3]} opacity={boardOpacity[layer] ?? 1} preserveAspectRatio="none" pointerEvents="none" />) : <BoardFallback board={board} visual={visual} linked={linkedNets[visual.id] ?? []} visibleLayers={boardLayers} layerOpacity={boardOpacity} showVias={showVias} onNetSelect={onNetSelect} />}
        {layers.length ? board.tracks.filter(track => visible(track.layer, boardLayers)).map((track, i) => { const id = canonicalNetId(board, visual.netIdsByName, track.net); const isLinked = id && (linkedNets[visual.id] ?? []).includes(id); return id ? <line key={`pick:${track.id}:${i}`} x1={track.start[0]} y1={track.start[1]} x2={track.end[0]} y2={track.end[1]} stroke={isLinked ? "#ffe25b" : "transparent"} strokeWidth={Math.max(track.width, .8)} opacity={isLinked ? .9 : 1} onClick={event => { event.stopPropagation(); onNetSelect(visual.id, id); }} style={{ cursor: "pointer" }} /> : null; }) : null}
        <rect x={board.bounds.minX} y={board.bounds.minY} width={board.width} height={board.height} fill="none" stroke={isSelected ? "#6ee7ff" : "#8295a5"} strokeWidth={isSelected ? .45 : .16} vectorEffect="non-scaling-stroke" pointerEvents="stroke" />
      </g>; })}
      {snapTargets.map(target => target.kind === "hole"
        ? <circle data-assembly-snap="hole" key={target.id} cx={target.worldPointMm[0]} cy={target.worldPointMm[1]} r={Math.max(view.width / 250, .6)} fill={target.id === selectedSnapTargetId ? "#ffd32a" : "#6ee7ff"} fillOpacity={.8} onClick={event => { event.stopPropagation(); onSnapTarget?.(target); }} style={{ cursor: "crosshair" }}><title>{target.occurrenceId}: {target.sourceId}</title></circle>
        : <line data-assembly-snap="edge" key={target.id} x1={target.worldPointMm[0] - target.worldDirection[0] * target.lengthMm / 2} y1={target.worldPointMm[1] - target.worldDirection[1] * target.lengthMm / 2} x2={target.worldPointMm[0] + target.worldDirection[0] * target.lengthMm / 2} y2={target.worldPointMm[1] + target.worldDirection[1] * target.lengthMm / 2} stroke={target.id === selectedSnapTargetId ? "#ffd32a" : "#6ee7ff"} strokeWidth={Math.max(view.width / 250, .6)} onClick={event => { event.stopPropagation(); onSnapTarget?.(target); }} style={{ cursor: "crosshair" }}><title>{target.occurrenceId}: {target.sourceId}</title></line>)}
      {harnesses.map(harness => <polyline key={harness.id} data-harness-id={harness.id} points={harnessAssemblyPoints(harness).map(point => `${point[0]},${point[1]}`).join(" ")} fill="none" stroke="#f2b84b" strokeWidth={Math.max(view.width / 700, .25)} strokeDasharray={harness.routedPolyline ? undefined : `${view.width / 120} ${view.width / 180}`} pointerEvents="none" />)}
    </svg>
  </div>;
}
