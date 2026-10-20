// SPDX-License-Identifier: Apache-2.0
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import BoardViewport from "../src/BoardViewport";
import MainFieldControls from "../src/MainFieldControls";
import { useMainFieldViewport } from "../src/mainFieldViewport";
import { parseKicadBoard } from "../src/boardParser";
import { Focus, Orbit, Hand } from "../src/icons";
import curves from "../../examples/field_visualization/illustrative-curves.json";
import volume from "../../examples/field_visualization/illustrative-volume.json";
import "../src/styles.css";
import "../src/buttonStandard.css";
const noop = () => {}, layers = { "F.Cu": true, "B.Cu": true, "F.Mask": true }, opacity = {};
// Authored board for source-frame presentation checks, not an engineering case.
const board = parseKicadBoard(`(kicad_pcb (version 20240108) (generator pcbnew)
 (general (thickness 0.2)) (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
 (gr_rect (start -1 -1) (end 7 3) (stroke (width 0.05) (type default)) (fill none) (layer "Edge.Cuts")))`);
board.stackup = [{ name: "Synthetic thin core", type: "core", thickness: .2, material: "FR4" }];
function Preview() {
  const [open, setOpen] = useState(false), [camera, setCamera] = useState("fit:0"), [nav, setNav] = useState<"orbit" | "pan">("orbit"), [status, setStatus] = useState("");
  const field = useMainFieldViewport("fixture", () => setOpen(true), setStatus);
  useEffect(() => { field.present(curves); setOpen(false); }, []);
  return <main style={{ height:"100vh", display:"grid", gridTemplateRows:"40px 32px minmax(0,1fr)", overflow:"hidden" }}>
    <header style={{padding:"8px 12px",display:"flex",gap:12,alignItems:"center",fontSize:12}}><strong>SPIKE · Main viewport</strong><small>Synthetic rendering fixture · no solver output</small></header>
    <nav aria-label="Viewport tools" style={{display:"flex",alignItems:"center",gap:4,padding:"0 8px",borderBottom:"1px solid var(--spike-table-border)"}}>
      <button aria-label="Orbit" onClick={()=>setNav("orbit")}><Orbit size={14}/></button><button aria-label="Pan" onClick={()=>setNav("pan")}><Hand size={14}/></button><button aria-label="Fit scene" onClick={()=>setCamera(`fit:${Date.now()}`)}><Focus size={14}/></button>
      <MainFieldControls view={field.view} open={open} onOpen={setOpen} onPresent={field.present} onOptions={field.options} onVisible={field.visible} onClear={field.clear}/>
      <button onClick={()=>field.present(curves)}>Curves fixture</button><button onClick={()=>field.present(volume)}>Volume history fixture</button><small role="status">{status}</small>
    </nav>
    <div style={{position:"relative",minHeight:0}}><BoardViewport board={board} viewMode="3D" visibleLayers={layers} layerOpacity={opacity} layerSeparation={0} showVias showModels={false} showSmdModels={false} showThtModels={false} navigationMode={nav} navigationInertia cameraCommand={camera} selectionFilter="all" selectedId={null} onSelect={noop} onCamera={noop} fieldVolume={field.view?.visible ? field.view : null} onFieldError={setStatus}/></div>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview/>);
