// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
import { useEffect, useMemo, useRef, useState } from "react";
import ThermalHistoryPopup from "./ThermalHistoryPopup";
import { solidNodeThermalHistory, type ThermalProbeHistoryResult } from "./thermalProbeHistory";
import PlotlyChart from "./PlotlyChart";
import DataTable from "./DataTable";
import { thermalFrames } from "./thermalTransientPresentation";
import { prepareThermalVolumeGeometry, thermalVolumeField, thermalVolumeSurface, renderThermalVolumePlot, type ThermalMeshView } from "./assemblyThermalVolumePlot";
import SavedFramePlaybackControls from "./SavedFramePlaybackControls";
import { captureGifFrames, captureWebM, type AnimationExportRequest } from "./animationExport";
import { buildAnimationExportPlan, gifDelayCentiseconds, throwIfCancelled } from "./transientPlayback";
import { capturePlotlySurface, waitForPlotlyRender } from "./plotAnimationCapture";
import { encodeGif } from "./gifExport";
import "./buttonStandard.css";
import "./AssemblyThermalVolumeViewer.css";

export default function AssemblyThermalVolumeViewer({ handoff, result }: { handoff: any; result: any | null }) {
  const [selectedNode, setSelectedNode] = useState<{ occurrence: string; index: number } | null>(null);
  const [history, setHistory] = useState<ThermalProbeHistoryResult | null>(null);
  useEffect(() => { setSelectedNode(null); setHistory(null); }, [handoff?.handoff_digest, result?.result_digest]);
  const openNodeHistory = () => {
    if (!selectedNode) return;
    const trace = solidNodeThermalHistory(result, handoff, selectedNode.occurrence, selectedNode.index);
    setHistory({ label: `${selectedNode.occurrence} node ${selectedNode.index}`, traces: trace ? [trace] : [],
      unavailableReason: trace ? undefined : "This mesh node has no retained transient temperature history." });
  };
  const plotRoot = useRef<HTMLDivElement>(null);
  const [occurrence, setOccurrence] = useState("");
  const [unit, setUnit] = useState<"K" | "C">("C");
  const [mode, setMode] = useState<"temperature" | "geometry">("temperature");
  const [edges, setEdges] = useState<ThermalMeshView>("none");
  const [frameIndex, setFrameIndex] = useState(0), [playing, setPlaying] = useState(false), [speed, setSpeed] = useState(1);
  const [exportNotice, setExportNotice] = useState("");
  const frames = useMemo(() => thermalFrames(result), [result]);
  const frameTimes = useMemo(() => frames.map(frame => frame.time_s), [frames]);
  useEffect(() => { setFrameIndex(0); setPlaying(false); }, [result?.result_digest]);
  const activeFrame = frames[Math.min(frameIndex, frames.length - 1)];
  const displayed = useMemo(() => activeFrame ? { ...result, field_result: { ...result.field_result, node_temperatures_k: activeFrame.node_temperatures_k } } : result, [result, activeFrame]);
  useEffect(() => { setOccurrence(""); setEdges("none"); }, [handoff?.handoff_digest]);
  const geometry = useMemo(() => prepareThermalVolumeGeometry(handoff), [handoff]);
  const historyRange = useMemo(() => {
    if (!frames.length) return null;
    let minimum = Infinity, maximum = -Infinity;
    for (const frame of frames) for (const value of frame.node_temperatures_k) {
      minimum = Math.min(minimum, value); maximum = Math.max(maximum, value);
    }
    return Number.isFinite(minimum) && Number.isFinite(maximum) ? { minimum, maximum } : null;
  }, [frames]);
  const field = useMemo(() => {
    const current = thermalVolumeField(geometry, displayed);
    return current.hasTemperature && historyRange ? { ...current, colorMinimum: historyRange.minimum, colorMaximum: historyRange.maximum > historyRange.minimum ? historyRange.maximum : historyRange.minimum + 1 } : current;
  }, [geometry, displayed, historyRange]);
  const surface = useMemo(() => thermalVolumeSurface(geometry, occurrence, edges), [geometry, occurrence, edges]);
  const plot = useMemo(() => renderThermalVolumePlot(geometry, field, surface, unit, mode), [geometry, field, surface, unit, mode]);
  const layout = useMemo(() => ({ height: 480, margin: { l: 0, r: 30, t: 16, b: 0 },
    scene: { uirevision: handoff?.handoff_digest, aspectmode: "data", xaxis: { title: "X (mm)" }, yaxis: { title: "Y (mm)" }, zaxis: { title: "Z (mm)" } } }), [handoff?.handoff_digest]);
  const temperature = (value: number) => (unit === "K" ? value : value - 273.15).toFixed(3);
  const unitLabel = unit === "K" ? "K" : "deg C";
  const exportAnimation = async (request: AnimationExportRequest, signal: AbortSignal) => {
    const plan = buildAnimationExportPlan(frameTimes, request.playbackSpeed, { maximumFrames: 160 });
    const originalFrame = frameIndex, originalPlaying = playing;
    let presentedFrame = frameIndex;
    setPlaying(false); setExportNotice("");
    const presentFrame = async (nextFrame: number) => {
      throwIfCancelled(signal);
      if (nextFrame === presentedFrame) return;
      const rendered = waitForPlotlyRender(plotRoot.current, signal);
      presentedFrame = nextFrame;
      setFrameIndex(nextFrame);
      await rendered;
    };
    const width = 800, height = 500;
    const options = { plan, width, height, presentFrame, signal,
      captureFrame: () => capturePlotlySurface(plotRoot.current, width, height, signal) };
    try {
      const blob = request.format === "webm" ? await captureWebM(options)
        : encodeGif(await captureGifFrames(options), gifDelayCentiseconds(plan));
      throwIfCancelled(signal);
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = `assembly-thermal-volume.${request.format}`; anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setExportNotice(`Exported ${plan.frames.length} saved thermal frames as ${request.format.toUpperCase()} at ${request.playbackSpeed}x simulated time.`);
    } finally {
      setFrameIndex(originalFrame); setPlaying(originalPlaying);
    }
  };
  if (!handoff) return <p>Prepare the volume handoff to preview the retained 3D mesh.</p>;
  return <section aria-label="Assembly thermal volume" className="assembly-thermal-volume">
    {frames.length > 1 && <SavedFramePlaybackControls timesS={frameTimes} frameIndex={frameIndex} playing={playing} playbackSpeed={speed}
      onFrame={setFrameIndex} onPlaying={setPlaying} onPlaybackSpeed={setSpeed} onExport={exportAnimation} exportLabel="thermal volume" />}
    {exportNotice && <p role="status">{exportNotice}</p>}
    <div className="assembly-thermal-volume__controls">
      <label>Occurrence
        <select aria-label="Thermal volume occurrence" value={occurrence} onChange={e => setOccurrence(e.target.value)}>
          <option value="">All occurrences</option>
          {plot.occurrences.map(id => <option key={id} value={id}>{id}</option>)}
        </select>
      </label>
      <label>Display
        <select aria-label="Thermal volume display" value={mode} onChange={e => setMode(e.target.value as typeof mode)}>
          <option value="temperature" disabled={!field.hasTemperature}>Temperature</option><option value="geometry">Geometry</option>
        </select>
      </label>
      <label>Temperature units
        <select aria-label="Thermal volume temperature units" value={unit} onChange={e => setUnit(e.target.value as "K" | "C")}>
          <option value="C">deg C</option><option value="K">K</option>
        </select>
      </label>
      <label>Mesh inspection
        <select aria-label="Thermal volume mesh inspection" value={edges} onChange={e => setEdges(e.target.value as ThermalMeshView)}>
          <option value="none">Exterior surface</option><option value="surface">Surface mesh edges</option>
          <option value="volume" disabled={!geometry.interiorAvailable}>Interior tetrahedra and nodes</option>
        </select>
      </label>
    </div>
    {plot.error ? <p role="status">{plot.error}</p> : <>
      <p>{plot.showTemperature ? "Experimental nodal temperatures; surface colors interpolate between retained nodes." : field.hasTemperature ? "Geometry view. Switch Display to Temperature for the retained solution." : "Geometry preview only. Run the admitted thermal study to display temperatures."} {plot.triangles} surface triangles. Coordinates in mm.</p>
      {field.hasTemperature && <p className="assembly-thermal-volume__scale">Common temperature scale: <strong>{temperature(field.colorMinimum)} to {temperature(field.colorMaximum)} {unitLabel}</strong> across all occurrences and volume nodes{frames.length ? ", fixed across all saved frames" : ""}. Filtering an occurrence preserves this scale.</p>}
      {surface.interior && <p>Interior inspection: transparent exterior, actual tetrahedral edges and retained node samples. Hover a node for its occurrence, index and temperature.</p>}
      {!geometry.interiorAvailable && <p>Interior inspection is available for retained tetrahedral meshes with complete occurrence ranges and at most 5,000 cells.</p>}
      {plot.notice && <p role="status">{plot.notice}</p>}
      <p>Click a retained mesh node to select it, then right-click the plot and choose Plot temperature vs time.
        {selectedNode && <> Selected: {selectedNode.occurrence}, node {selectedNode.index}.</>}</p>
      {history && <ThermalHistoryPopup history={history} onClose={() => setHistory(null)} />}
      <div ref={plotRoot}><PlotlyChart onPointClick={point => {
        const value = point.customdata;
        if (Array.isArray(value) && typeof value[0] === "string" && Number.isInteger(value[1]))
          setSelectedNode({ occurrence: value[0], index: value[1] });
      }} contextActions={[{ label: "Plot temperature vs time", onSelect: openNodeHistory, disabled: !selectedNode }]} data={plot.traces} title="Assembly thermal volume" revision={`${handoff.handoff_digest}:${result?.result_digest ?? "mesh"}:${activeFrame?.time_s ?? "final"}:${occurrence}:${unit}:${mode}:${edges}`} layout={layout} /></div>
      {field.hasTemperature && <DataTable label={`Occurrence temperature extremes (${unitLabel})`} pageSize={25}>
        <thead><tr><th>Occurrence</th><th>Sample scope</th><th>Nodes</th><th>Minimum ({unitLabel})</th><th>Maximum ({unitLabel})</th></tr></thead>
        <tbody>{field.stats.map(row => <tr key={row.occurrence}><td className="assembly-thermal-volume__identity">{row.occurrence}</td>
          <td>{geometry.volumeOwnership ? "Volume nodes" : "Surface nodes"}</td><td>{row.count}</td><td>{temperature(row.minimum)}</td><td>{temperature(row.maximum)}</td></tr>)}</tbody>
      </DataTable>}
    </>}
  </section>;
}
