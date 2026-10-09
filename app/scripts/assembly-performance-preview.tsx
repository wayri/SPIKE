// SPDX-License-Identifier: Apache-2.0
import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import BoardViewport, { type ModelLoadStatus, type RenderTelemetry } from "../src/BoardViewport";
import { parseDesignSourceOffThread } from "../src/boardImport";
import type { ParsedBoard } from "../src/boardParser";
import { buildVirtualHarnessVisualization, type VirtualBoardVisual, type VirtualHarnessVisual } from "../src/harnessVisualization";
import { DEFAULT_ASSEMBLY_SECTION, type AssemblySection } from "../src/mcadAssembly";
import AssemblyIconToolbar, { type AssemblyToolbarAction } from "../src/AssemblyIconToolbar";
import AssemblyViewportHelp from "../src/AssemblyViewportHelp";
import { Box, CircleHelp, Focus, Layers3, Maximize2, PanelRight, Play, ScanLine, View, ZoomIn } from "../src/icons";
import ToolRestoreShelf from "../src/ToolRestoreShelf";
import "../src/styles.css";
import "../src/buttonStandard.css";
import "./assembly-performance-preview.css";

const noop = () => {}, empty = {}, noModels = [];
const root = "../.tmp/assembly-performance/";
function Preview() {
  const [board, setBoard] = useState<ParsedBoard | null>(null), [message, setMessage] = useState("Loading retained Sailor Hat source and KiCad models…");
  const [telemetry, setTelemetry] = useState<RenderTelemetry | null>(null), [status, setStatus] = useState<ModelLoadStatus | null>(null);
  const [x, setX] = useState(95), [angle, setAngle] = useState(0), [hidden, setHidden] = useState(false), [innerHidden, setInnerHidden] = useState(false);
  const [selected, setSelected] = useState<string | null>("B"), [camera, setCamera] = useState("fit:0"), [running, setRunning] = useState(false);
  const [qualityHost, setQualityHost] = useState<HTMLSpanElement | null>(null);
  const [motionFrames, setMotionFrames] = useState(0);
  const [sectionMode, setSectionMode] = useState("off"), [exploded, setExploded] = useState(false);
  const [sidePanel, setSidePanel] = useState<"inspector" | "help" | null>("inspector");
  const explodeOffsets = useMemo(() => exploded ? { A: 0, B: 25 } : {}, [exploded]);
  const section = useMemo((): AssemblySection => ({ ...DEFAULT_ASSEMBLY_SECTION, enabled: sectionMode !== "off", mode: sectionMode === "box" ? "box" : "plane", axis: "x", offsetMm: 0, minXMm: -40, maxXMm: 45, minYMm: -40, maxYMm: 40, minZMm: -10, maxZMm: 40 }), [sectionMode]);
  const [harnessShown, setHarnessShown] = useState(() => new URLSearchParams(location.search).has("harness")), [wireSelection, setWireSelection] = useState<VirtualHarnessVisual | null>(null);
  useEffect(() => { let disposed = false;
    void (async () => {
      try {
        const response = await fetch(root + "source.json"); if (!response.ok) throw new Error("Capture the retained fixture before opening this page.");
        const parsed = await parseDesignSourceOffThread("retained.spike-design.json", await response.text(), "spike-normalized");
        if (disposed) return;
        setBoard({ ...parsed, boardModelUrl: new URL(root + "board.glb", location.href).href,
          componentModelUrl: new URL(root + "components.glb", location.href).href, boardModelIncludesCopper: true });
        setMessage(`${parsed.components.length} components · ${parsed.layers.filter(layer => layer.endsWith('.Cu')).length} copper layers per board · two occurrences of the retained SH-RPi design`);
      } catch (cause) { if (!disposed) setMessage(String(cause)); }
    })(); return () => { disposed = true; };
  }, []);
  useEffect(() => { if (!running) return; let frame = 0, token = 0;
    const tick = () => { frame++; setX(95 + Math.sin(frame / 15) * 20); setAngle(frame / 4); setMotionFrames(frame);
      if (frame < 240) token = requestAnimationFrame(tick); else setRunning(false); };
    token = requestAnimationFrame(tick); return () => cancelAnimationFrame(token);
  }, [running]);
  const layers = useMemo(() => Object.fromEntries((board?.layers ?? []).map(name => [name,
    name.endsWith('.Cu') || name.endsWith('.Mask') || name.endsWith('.SilkS') || name === 'Edge.Cuts'])), [board]);
  const sources = useMemo(() => board ? { retained: board } : {}, [board]);
  const visibility = useMemo(() => ({ B: !hidden }), [hidden]);
  const boardLayers = useMemo(() => innerHidden ? { B: { ...layers, "In1.Cu": false, "In2.Cu": false } } : empty, [innerHidden, layers]);
  const boards = useMemo((): VirtualBoardVisual[] => {
    if (!board) return [];
    const cx = (board.bounds.minX + board.bounds.maxX) / 2, cy = (board.bounds.minY + board.bounds.maxY) / 2;
    const occurrence = (id: string, offset: number, rotation: number): VirtualBoardVisual => {
      const c = Math.cos(rotation * Math.PI / 180), s = Math.sin(rotation * Math.PI / 180);
      return { id, name: `Sailor Hat · ${id}`, designId: "retained", active: id === "A", widthMm: board.width, heightMm: board.height,
        thicknessMm: 1.6, localCenterMm: [cx, cy, 0], netIdsByName: Object.fromEntries(Object.entries(board.nets).map(([key, name]) => [name, `${id}:${key}`])),
        transform: [c, -s, 0, offset - c * cx + s * cy, s, c, 0, -s * cx - c * cy, 0, 0, 1, 0, 0, 0, 0, 1] };
    }; return [occurrence("A", 0, 0), occurrence("B", x, angle)];
  }, [board, x, angle]);
  const harnesses = useMemo(() => {
    if (!board || boards.length !== 2 || !harnessShown) return [];
    const cx = (board.bounds.minX + board.bounds.maxX) / 2, cy = (board.bounds.minY + board.bounds.maxY) / 2;
    return buildVirtualHarnessVisualization({ contract: "spike/assembly-ir/v1", assembly_id: "preview", name: "Synthetic wiring visual fixture", parts: [],
      boards: boards.map(item => ({ id: item.id, design_id: item.designId, frame: { frame_id: `${item.id}-frame`, units: "mm", handedness: "right", transform: item.transform } })),
      connector_mappings: boards.map(item => ({ id: `${item.id}-visual`, data: { board_id: item.id, connector_id: "VISUAL_J", position_mm: [cx,cy,2] } })),
      harnesses: [{ id: "visual-loom", name: "Synthetic power + differential loom", endpoint_a: "A::VISUAL_J", endpoint_b: "B::VISUAL_J", length_mm: Math.abs(x) + 75,
        pin_map: {"1":"1","2":"2","3":"3","4":"4","5":"5","6":"6"}, extensions: {
          "spike.harness-routing": { route_mm: [[0,0,2],[0,-30,8],[x,-30,8],[x,0,2]] },
          "spike.harness-conductors": {contract:"spike/assembly-harness-conductors/v1", wires:["power","return","signal","signal","other","shield"].map((role,index)=>({id:`W${index+1}`,from_pin:String(index+1),to_pin:String(index+1),role})),
            pairs:[{id:"data",kind:"differential",wire_ids:["W3","W4"],twisted:true,twist_pitch_mm:12}] }
        } }] }).visuals;
  }, [board, boards, harnessShown, x]);
  const cameraActions: AssemblyToolbarAction[] = [
    { id: "fit", label: "Fit assembly", text: "Fit", icon: Maximize2, onClick: () => setCamera(`fit:${Date.now()}`) },
    { id: "top", label: "Top view", text: "Top", icon: View, onClick: () => setCamera(`view-top:${Date.now()}`) },
    { id: "isometric", label: "Isometric view", text: "Iso", icon: Box, onClick: () => setCamera(`view-isometric:${Date.now()}`) },
    { id: "focus", label: "Focus board", text: "Focus", icon: Focus, disabled: !selected, onClick: () => setCamera(`focus-selection:${Date.now()}`) },
    { id: "zoom", label: "Zoom in", text: "Zoom", icon: ZoomIn, onClick: () => setCamera(`zoom-in:${Date.now()}`) },
  ];
  const togglePanel = (panel: "inspector" | "help") => setSidePanel(current => current === panel ? null : panel);
  return <main className="assembly-preview-shell">
    <header className="assembly-preview-header">
      <strong className="assembly-preview-title">Real assembly rendering verification</strong>
      <AssemblyIconToolbar actions={cameraActions} label="Assembly camera tools" />
    </header>
    <p className="assembly-preview-status" title={message}>{message} · selected {selected ?? "none"} · motion frames {motionFrames} · harness {wireSelection?.selectedConductorId ?? "none"} · wiring is synthetic visual evidence, not a qualified pinout</p>
    <div className={`assembly-preview-workspace${sidePanel ? " has-side-panel" : ""}`}>
      <nav className="assembly-preview-rail" aria-label="Assembly preview panels">
        <button type="button" className="spike-control--compact spike-control--icon" title="Placement and display inspector" aria-label="Placement and display inspector" aria-controls="assembly-preview-side-panel" aria-pressed={sidePanel === "inspector"} onClick={() => togglePanel("inspector")}><PanelRight size={18} aria-hidden="true"/><span>Inspect</span></button>
        <button type="button" className="spike-control--compact spike-control--icon" title="Assembly viewport help" aria-label="Assembly viewport help" aria-controls="assembly-preview-side-panel" aria-pressed={sidePanel === "help"} onClick={() => togglePanel("help")}><CircleHelp size={18} aria-hidden="true"/><span>Help</span></button>
      </nav>
      <div className="board-canvas is-3d assembly-preview-canvas">
      {board && <BoardViewport board={board} viewMode="3D" visibleLayers={layers} layerOpacity={empty} layerSeparation={0} qualityTarget={qualityHost}
        showVias showModels showSmdModels showThtModels showNetNames navigationMode="orbit" navigationInertia cameraCommand={camera}
        assemblyModels={noModels} virtualBoards={boards} assemblyBoardDesigns={sources} assemblyBoardVisibility={visibility}
        assemblyLayerVisibility={boardLayers} assemblySection={section} assemblyExplodeOffsets={explodeOffsets}
        virtualHarnesses={harnesses} selectedHarnessId={wireSelection?.id} selectedHarnessConductorId={wireSelection?.selectedConductorId} onHarnessSelect={setWireSelection}
        selectedBoardInstanceId={selected} onBoardInstanceSelect={visual => setSelected(visual.id)}
        selectionFilter="all" selectedId={null} onSelect={noop} onCamera={noop} onModelStatus={setStatus} onTelemetry={setTelemetry} />}
      </div>
      {sidePanel && <aside id="assembly-preview-side-panel" className="assembly-preview-side-panel">
        {sidePanel === "help" ? <div className="assembly-preview-help"><AssemblyViewportHelp/><a className="assembly-preview-editor-link" href="fixtures/harness-editor.html">Open wiring editor</a></div> : <>
          <div className="assembly-preview-panel-heading"><PanelRight size={17} aria-hidden="true"/><h2>Assembly inspector</h2></div>
          <section className="assembly-preview-control-group" aria-labelledby="preview-placement-heading">
            <h3 id="preview-placement-heading">Placement</h3>
            <label>X mm <input type="number" value={x.toFixed(2)} onChange={event => setX(Number(event.target.value))} /></label>
            <label>RZ deg <input type="number" value={angle.toFixed(2)} onChange={event => setAngle(Number(event.target.value))} /></label>
            <button className="spike-control--primary" disabled={running || !board} onClick={() => setRunning(true)}><Play size={16} aria-hidden="true"/>Exercise 240 placements</button>
          </section>
          <section className="assembly-preview-control-group" aria-labelledby="preview-visibility-heading">
            <h3 id="preview-visibility-heading"><Layers3 size={15} aria-hidden="true"/>Visibility</h3>
            <label><input type="checkbox" checked={hidden} onChange={event => setHidden(event.target.checked)} />Hide board B</label>
            <label><input type="checkbox" checked={innerHidden} onChange={event => setInnerHidden(event.target.checked)} />Hide inner copper on B</label>
            <label><input type="checkbox" checked={harnessShown} onChange={event=>setHarnessShown(event.target.checked)} />Synthetic mixed harness</label>
            <label><input type="checkbox" checked={exploded} onChange={event=>setExploded(event.target.checked)} />Explode B 25 mm</label>
          </section>
          <section className="assembly-preview-control-group" aria-labelledby="preview-section-heading">
            <h3 id="preview-section-heading"><ScanLine size={15} aria-hidden="true"/>Section</h3>
            <label>Section<select value={sectionMode} onChange={event=>setSectionMode(event.target.value)}><option value="off">Off</option><option value="angle">X plane</option><option value="box">Box</option></select></label>
            <div className="assembly-preview-button-grid">
              <button onClick={()=>setSectionMode("angle")}>X cut plane</button>
              <button onClick={()=>setSectionMode("box")}>Cut box</button>
              <button onClick={()=>setSectionMode("off")}>Clear cuts</button>
            </div>
          </section>
          <a className="assembly-preview-editor-link" href="fixtures/harness-editor.html">Wiring editor</a>
        </>}
      </aside>}
    </div>
    <footer className="bottom-dock assembly-preview-footer"><div className="dock-tabs"><ToolRestoreShelf /><span ref={setQualityHost} className="viewport-quality-host" /></div></footer>
    <output className="assembly-preview-telemetry">Board {status?.board} · parts {status?.components} · {status?.error || "No model-load errors"}
      {telemetry && ` · ${telemetry.geometries} geometries · ${telemetry.textures} textures · ${telemetry.drawCalls} draws · ${telemetry.triangles.toLocaleString()} triangles · ${telemetry.fps.toFixed(1)} FPS · ${telemetry.frameTimeMs.toFixed(1)} ms/render`}</output>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
