// SPDX-License-Identifier: Apache-2.0
// Visual acceptance harness using saved solver samples; never runs a solver.
import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import BoardViewport from "../src/BoardViewport";
import MainFieldControls from "../src/MainFieldControls";
import ViewportPlaybackBar from "../src/ViewportPlaybackBar";
import { useViewportPlayback } from "../src/useViewportPlayback";
import { useMainFieldViewport } from "../src/mainFieldViewport";
import { parseKicadBoard } from "../src/boardParser";
import boardText from "../../examples/esp32/source/iot-esp-eth-ind.kicad_pcb?raw";
import coupled from "../../artifacts/unified-transient-20261026/cfd/coupled-flow-solid.field.json";
import "../src/styles.css";
import "../src/buttonStandard.css";
const board = parseKicadBoard(boardText), noop = () => {};
const layers = { "F.Cu": true, "B.Cu": true, "F.Mask": true }, opacity = {};
function Review() {
  const [open, setOpen] = useState(false), [camera, setCamera] = useState("fit:0");
  const [flow, setFlow] = useState(false), [status, setStatus] = useState("");
  const field = useMainFieldViewport("coupled-native-samples", () => {}, setStatus);
  useEffect(() => { field.present(coupled); }, []);
  const sources = useMemo(() => field.view ? [{ id: field.view.data.id, label: "CHT: fluid + solid temperature", revision: field.view.data,
    times: field.view.data.frames.map(f => f.timeS), flow: true, onActivate: () => field.visible(true),
    onFrame: (frame: number) => field.options({ frame }), onFlow: setFlow }] : [], [field.view?.data]);
  const playback = useViewportPlayback(sources, "coupled-native-samples");
  return <main style={{ height: "100vh", display: "flex", flexDirection: "column", background: "var(--spike-table-surface)", color: "var(--spike-table-text)" }}>
    <header style={{ padding: 10, display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
      <strong>SPIKE · Coupled thermal / flow review</strong><small>Saved native solver output · declared component cuboids · 0.004–0.020 s</small>
      <button onClick={() => setCamera(`fit:${Date.now()}`)}>Fit scene</button>
      <MainFieldControls view={field.view} open={open} onOpen={setOpen} onPresent={field.present} onOptions={field.options} onVisible={field.visible} onClear={field.clear} managedPlayback />
    </header>
    <ViewportPlaybackBar playback={playback}/><small role="status">{status}</small>
    <div style={{ position: "relative", minHeight: 0, flex: 1 }}><BoardViewport board={board} viewMode="3D" visibleLayers={layers} layerOpacity={opacity} layerSeparation={0} showVias showModels={false} showSmdModels={false} showThtModels={false} showWorldGrid={false} showAxes={false} showOriginAxes={false} navigationMode="orbit" navigationInertia cameraCommand={camera} selectionFilter="all" selectedId={null} onSelect={noop} onCamera={noop} fieldVolume={field.view?.visible ? field.view : null} fieldFlowPlaying={flow} onFieldError={setStatus}/></div>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Review/>);
