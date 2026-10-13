// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { availableEMQuantities, emResultFrequencies, emViewportPayload, type EMViewportRecord, type EMViewportSettings, type EMViewportData } from "./emViewportResults";
import { downloadEMergeText, exportEMergeNetwork } from "./emergeSampleExport";
import { reviewEMergeNetwork } from "./emergeNetworkReview";
import { admitOpenEMSFarfield, openEMSFarfieldCut } from "./openEMSFarfield";
import { admitOpenEMSNetworkSamples, exportOpenEMSNetworkTouchstone } from "./openEMSNetworkSamples";
import PlotlyChart from "./PlotlyChart";
import { minimizeTool, removeMinimizedTool } from "./minimizedTools";
import "./EMViewportResultManager.css";

type Props = {
  records: EMViewportRecord[]; activeRecordId: string; settings: EMViewportSettings; data: EMViewportData | null;
  onSelectRecord: (id: string) => void; onSettingsChange: (settings: EMViewportSettings) => void; onClose: () => void;
};
const recordOf = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const payloadOf = emViewportPayload;

export default function EMViewportResultManager({ records, activeRecordId, settings, data, onSelectRecord, onSettingsChange, onClose }: Props) {
  const [minimized, setMinimized] = useState(false), [error, setError] = useState("");
  const shelfId = "em-viewport-results";
  useEffect(() => () => removeMinimizedTool(shelfId), []);
  const minimize = () => {
    if (minimizeTool({ id: shelfId, label: "EM result manager", restore: () => setMinimized(false), close: onClose })) setMinimized(true);
  };
  const active = records.find(record => record.id === activeRecordId) ?? records[0];
  const quantities = active ? availableEMQuantities(active) : [];
  const frequencies = active ? emResultFrequencies(active) : [];
  const update = (patch: Partial<EMViewportSettings>) => onSettingsChange({ ...settings, ...patch });
  const sample = data && data.values.length ? Math.max(0, Math.min(settings.selectedSample, data.values.length - 1)) : 0;
  const nodeEligible = settings.projection === "magnitude" && !/interference|poynting|delta|change/i.test(settings.quantity);
  const scalarQuantity = ["pattern_delta", "interference"].includes(settings.quantity);
  const exportSamples = () => {
    if (!data) return;
    const rows = ["frequency_hz,sample_index,x_mm,y_mm,z_mm,display_value,unit", ...data.values.map((value, index) => [data.frequencyHz, data.nativeSampleIndices?.[index] ?? index, ...data.positionsMm[index], value, JSON.stringify(data.unit)].join(","))];
    downloadEMergeText("em-viewport-samples.csv", rows.join("\n") + "\n");
  };
  if (minimized) return null;
  return <aside className="em-viewport-manager" aria-label="EM viewport result manager" onPointerDown={event => event.stopPropagation()} onWheel={event => event.stopPropagation()}>
    <header><strong>EM RESULT MANAGER</strong><span className="em-manager-heading-actions"><button aria-label="Minimize EM result manager" title="Minimize to the bottom tool shelf" onClick={minimize}>−</button><button aria-label="Close EM result manager" onClick={onClose}>×</button></span></header>
    <div className="em-manager-body">
      {!active ? <p className="em-manager-empty">Run a supported EM extension to add solved results to this viewport.</p> : <>
        <div className="em-manager-controls">
          <label className="em-manager-wide">Result<select aria-label="EM viewport result" value={active.id} onChange={event => onSelectRecord(event.target.value)}>{records.map(record => <option key={record.id} value={record.id}>{record.label}</option>)}</select></label>
          <label>Frequency<select aria-label="EM viewport frequency" value={Math.min(settings.frequencyIndex, Math.max(0, frequencies.length - 1))} disabled={!frequencies.length} onChange={event => update({ frequencyIndex: Number(event.target.value), selectedSample: 0 })}>{frequencies.map((frequency, index) => <option key={frequency} value={index}>{frequency.toPrecision(6)} Hz</option>)}</select></label>
          <label>Quantity<select aria-label="EM viewport quantity" value={settings.quantity} onChange={event => update({ quantity: event.target.value, selectedSample: 0 })}>{quantities.map(quantity => <option key={quantity.id} value={quantity.id}>{quantity.label}</option>)}</select></label>
          <label>Component<select aria-label="EM viewport component" disabled={scalarQuantity} value={settings.component} onChange={event => update({ component: event.target.value as EMViewportSettings["component"] })}><option value="norm" disabled={settings.projection !== "magnitude"}>Vector norm</option>{["x", "y", "z"].map(component => <option key={component} value={component}>{component.toUpperCase()}</option>)}</select></label>
          <label>Projection<select aria-label="EM viewport projection" disabled={scalarQuantity} value={settings.projection} onChange={event => update({ projection: event.target.value as EMViewportSettings["projection"], ...(event.target.value !== "magnitude" && settings.component === "norm" ? { component: "x" as const } : {}) })}><option value="magnitude">Magnitude</option><option value="real">Real</option><option value="imaginary">Imaginary</option><option value="phase">Phase</option><option value="instantaneous">Instantaneous phasor</option></select></label>
          <label>Style<select aria-label="EM viewport style" value={settings.style} onChange={event => update({ style: event.target.value as EMViewportSettings["style"] })}><option value="surface">Surface</option><option value="samples">Samples</option><option value="vectors">Vectors</option><option value="contours">Contours</option></select></label>
          <label>Opacity<input aria-label="EM viewport opacity" type="range" min="0.05" max="1" step="0.05" value={settings.opacity} onChange={event => update({ opacity: Number(event.target.value) })} /></label>
          <label>Phasor phase (deg)<input aria-label="EM viewport phasor phase" type="number" min="-360" max="360" step="5" disabled={settings.projection !== "instantaneous"} value={settings.phaseDeg} onChange={event => { const value = Number(event.target.value); if (Number.isFinite(value) && Math.abs(value) <= 360) update({ phaseDeg: value }); }} /></label>
          <label>Pattern display radius (mm)<input aria-label="EM viewport pattern radius" type="number" min="1" max="10000" value={settings.displayRadiusMm} onChange={event => { const value = Number(event.target.value); if (Number.isFinite(value) && value >= 1 && value <= 10000) update({ displayRadiusMm: value }); }} /></label>
        </div>
        <div className="em-manager-checks"><label><input type="checkbox" checked={settings.visible} onChange={event => update({ visible: event.target.checked })} />Show overlay</label><label><input type="checkbox" checked={settings.showStructure} onChange={event => update({ showStructure: event.target.checked })} />Show structure</label><label><input type="checkbox" disabled={!nodeEligible} checked={nodeEligible && settings.nodes} onChange={event => update({ nodes: event.target.checked })} />Low amplitude</label><label><input type="checkbox" disabled={!nodeEligible} checked={nodeEligible && settings.antinodes} onChange={event => update({ antinodes: event.target.checked })} />High amplitude</label></div>
        <label className="em-manager-controls">Node / antinode threshold (% of peak)<input aria-label="EM viewport amplitude threshold" type="range" min="1" max="25" step="1" disabled={!nodeEligible} value={settings.thresholdPct} onChange={event => update({ thresholdPct: Number(event.target.value) })} /></label>
        <small className="em-manager-warning">{String(payloadOf(active.result).model_status ?? "unvalidated")} · Low/high amplitude samples are candidate nodes/antinodes, not certified standing-wave locations. Pattern radius is a display scale, not spatial field extent.</small>
        {data ? <>
          <small>{data.label} · {data.frequencyHz.toPrecision(6)} Hz · {data.values.length} actual samples · {data.unit}</small>
          <div className="em-manager-controls"><label className="em-manager-wide">Linked viewport probe<input aria-label="EM viewport sample probe" type="number" min="0" max={Math.max(0, data.values.length - 1)} step="1" value={sample} onChange={event => { const value = Number(event.target.value); if (Number.isInteger(value) && value >= 0 && value < data.values.length) update({ selectedSample: value }); }} /></label></div>
          {data.positionsMm[sample] && <small role="status">Sample {sample}{data.nativeSampleIndices ? ` (native ${data.nativeSampleIndices[sample]})` : ""}: ({data.positionsMm[sample].map(value => value.toPrecision(6)).join(", ")}) mm · {typeof data.values[sample] === "number" ? data.values[sample]!.toPrecision(6) : "invalid / unavailable"} {data.unit}</small>}
          <LinkedSampleGraph values={data.values} selected={sample} label={`${data.label} (${data.unit})`} onSelect={index => update({ selectedSample: index })} />
          {data.notices.map((notice, index) => <small key={index} className="em-manager-warning">{notice}</small>)}
        </> : <small className="em-manager-warning">This result has no admitted samples for the current quantity/frequency. Choose an available quantity; missing fields are not synthesized.</small>}
        <EMResultGraphs key={active.id} result={active.result} frequencyIndex={settings.frequencyIndex} onFrequencyChange={index => update({ frequencyIndex: index, selectedSample: 0 })} />
        <div className="extension-actions"><button className="secondary-btn" disabled={!data} onClick={exportSamples}>Export displayed samples</button><button className="secondary-btn" onClick={() => { try { downloadEMergeText("em-analysis.json", JSON.stringify(payloadOf(active.result), null, 2)); setError(""); } catch { setError("Result export failed."); } }}>Export result JSON</button></div>{error && <small role="alert">{error}</small>}
      </>}
    </div>
  </aside>;
}

function LinkedSampleGraph({ values, selected, label, onSelect }: { values: Array<number | null>; selected: number; label: string; onSelect: (index: number) => void }) {
  const data: Record<string, unknown>[] = [{ type: "scatter", mode: "lines", name: label,
    x: values.map((_, index) => index), y: values, connectgaps: false, line: { color: "#71d2e9", width: 1.5 },
    hovertemplate: "Sample %{x}<br>%{y:.6g}<extra></extra>" }];
  const selectedValue = values[selected];
  const layout: Record<string, unknown> = { margin: { t: 18, r: 16, b: 48, l: 58 }, showlegend: false,
    xaxis: { title: "Actual sample index" }, yaxis: { title: label },
    ...(typeof selectedValue === "number" ? { shapes: [{ type: "line", x0: selected, x1: selected, y0: 0, y1: 1, xref: "x", yref: "paper", line: { color: "#ffbd69", width: 1, dash: "dot" } }] } : {}) };
  return <section className="em-manager-graph" onKeyDownCapture={event => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); event.stopPropagation(); onSelect(Math.max(0, Math.min(values.length - 1, selected + (event.key === "ArrowRight" ? 1 : -1)))); } }}><b>{label}</b><div className="em-linked-plot"><PlotlyChart title={`Linked EM sample graph: ${label}`} data={data} layout={layout} revision={`em-samples:${label}:${values.length}`} onPointClick={(point: { pointNumber: number; curveNumber: number }) => { if (point.curveNumber === 0) onSelect(point.pointNumber); }} /></div><small>Click or use arrow keys to move the viewport probe. Invalid solver samples leave gaps.</small></section>;
}

function EMResultGraphs({ result, frequencyIndex, onFrequencyChange }: { result: Record<string, unknown>; frequencyIndex: number; onFrequencyChange: (index: number) => void }) {
  const payload = payloadOf(result), fields = recordOf(payload.fields), radiation = recordOf(fields.radiation), comparison = recordOf(fields.comparison);
  const [receive, setReceive] = useState(0), [excited, setExcited] = useState(0), [networkProjection, setNetworkProjection] = useState("magnitude");
  const [enabled, setEnabled] = useState<Record<string, boolean>>({ bare: true, installed: true, radiation: true });
  const review = reviewEMergeNetwork({ data: { analysis_result: payload } });
  const network = recordOf(recordOf(payload.networks).s_parameters);
  const openemsNetwork = ["completed", "completed_with_warnings"].includes(String(payload.status)) ? admitOpenEMSNetworkSamples(network) : null;
  const openemsField = admitOpenEMSFarfield(fields.openems_far_field);
  const viewportFrequencies = emResultFrequencies({ id: "graph", label: "graph", result });
  const activeFrequencyHz = viewportFrequencies[frequencyIndex];
  const openemsCut = openemsField ? openEMSFarfieldCut(openemsField, openemsField.frequencies.indexOf(activeFrequencyHz)) : null;
  const ports = Array.isArray(network.ports) ? network.ports as string[] : [];
  const matrices = openemsNetwork?.values ?? (Array.isArray(network.values) ? network.values as number[][][][] : []);
  const frequencies = Array.isArray(network.frequencies_hz) ? network.frequencies_hz as number[] : [];
  const radiationCuts = Array.isArray(radiation.cuts) ? radiation.cuts : [];
  const cut = recordOf(radiationCuts.find(item => recordOf(item).frequency_hz === activeFrequencyHz));
  const angularTraces: GraphTrace[] = [];
  if (openemsCut) angularTraces.push({ id: "openems", label: "OpenEMS |E| (peak V/m)", x: openemsCut.thetaDeg, y: openemsCut.magnitudeVm, color: "#70d4e8" });
  if (Array.isArray(cut.angles_deg) && Array.isArray(cut.relative_amplitude_db) && cut.angles_deg.length === cut.relative_amplitude_db.length) angularTraces.push({ id: "radiation", label: "Radiation", x: cut.angles_deg as number[], y: cut.relative_amplitude_db as number[], color: "#70d4e8" });
  if (comparison.frequency_hz === activeFrequencyHz && Array.isArray(comparison.theta_deg) && Array.isArray(comparison.phi_deg)) for (const [id, key, color] of [["bare", "bare_relative_db", "#70d4e8"], ["installed", "structure_relative_db", "#eabc71"]]) {
    const values = comparison[key];
    if (Array.isArray(values) && values.length === comparison.theta_deg.length * comparison.phi_deg.length) angularTraces.push({ id, label: id === "bare" ? "Bare" : "Installed", x: comparison.theta_deg as number[], y: (comparison.theta_deg as number[]).map((_, index) => values[index * (comparison.phi_deg as number[]).length] as number), color });
  }
  const traces = angularTraces.filter(trace => trace.x.every(Number.isFinite) && trace.y.every(value => typeof value === "number" && Number.isFinite(value)));
  const networkValues = review.issue === null || openemsNetwork ? frequencies.map((frequency, index) => { const pair = matrices[index]?.[Math.min(receive, ports.length - 1)]?.[Math.min(excited, ports.length - 1)]; if (!pair) return { x: frequency, y: null }; return { x: frequency, y: networkProjection === "phase" ? (pair[0] === 0 && pair[1] === 0 ? null : Math.atan2(pair[1], pair[0]) * 180 / Math.PI) : 20 * Math.log10(Math.max(Math.hypot(...pair), 1e-15)) }; }) : [];
  return <>
    {traces.length > 0 && <section className="em-manager-graph"><b>Linked radiation cuts · {openemsCut ? `phi = ${openemsCut.phiDeg}°, peak V/m at ${openemsField!.radiusM} m · 1 W incident · not validated` : Array.isArray(comparison.theta_deg) ? "phi = 0°, common bare reference" : `phi = ${String(cut.phi_deg ?? 0)}°`}</b><div className="em-manager-traces">{traces.map(trace => <label key={trace.id}><input type="checkbox" checked={enabled[trace.id] !== false} onChange={event => setEnabled({ ...enabled, [trace.id]: event.target.checked })} />{trace.label}</label>)}</div><MultiTraceGraph traces={traces.filter(trace => enabled[trace.id] !== false)} xLabel="Theta (deg)" yLabel={openemsCut ? "Peak field (V/m)" : "Relative field (dB)"} /></section>}
    {networkValues.length > 0 && <section className="em-manager-graph"><b>S-parameter sweep</b><div className="em-manager-controls"><label>Receive<select aria-label="EM graph receive port" value={receive} onChange={event => setReceive(Number(event.target.value))}>{ports.map((port, index) => <option key={port} value={index}>{port}</option>)}</select></label><label>Excited<select aria-label="EM graph excited port" value={excited} onChange={event => setExcited(Number(event.target.value))}>{ports.map((port, index) => <option key={port} value={index}>{port}</option>)}</select></label><label>Network display<select aria-label="EM graph network display" value={networkProjection} onChange={event => setNetworkProjection(event.target.value)}><option value="magnitude">Magnitude (dB)</option><option value="phase">Phase (deg)</option></select></label></div><MultiTraceGraph traces={[{ id: "network", label: "S", x: networkValues.map(point => point.x), y: networkValues.map(point => point.y), color: "#70d4e8" }]} xLabel="Frequency (Hz)" yLabel={networkProjection === "phase" ? "Phase (deg)" : "Magnitude (dB)"} onSelect={index => { const viewportIndex = viewportFrequencies.indexOf(frequencies[index]); if (viewportIndex >= 0) onFrequencyChange(viewportIndex); }} selectedIndex={frequencies.indexOf(activeFrequencyHz)} /><button className="secondary-btn" disabled={Boolean(openemsNetwork?.missingColumns.length)} title={openemsNetwork?.missingColumns.length ? "Uncomputed excitation columns cannot be exported as Touchstone." : "Export actual complete matrix"} onClick={() => { const output = openemsNetwork ? exportOpenEMSNetworkTouchstone(openemsNetwork) : exportEMergeNetwork({ data: { analysis_result: payload } }, "touchstone"); downloadEMergeText(output.name, output.text); }}>Export Touchstone</button>{openemsNetwork?.missingColumns.length ? <small>Uncomputed excitation columns: {openemsNetwork.missingColumns.join(", ")}. Graph gaps preserve unavailable data; Touchstone export requires the complete matrix.</small> : null}</section>}
  </>;
}
type GraphTrace = { id: string; label: string; x: number[]; y: Array<number | null>; color: string };
function MultiTraceGraph({ traces, xLabel, yLabel, onSelect, selectedIndex = 0 }: { traces: GraphTrace[]; xLabel: string; yLabel: string; onSelect?: (index: number) => void; selectedIndex?: number }) {
  if (!traces.length) return <small>No graph traces selected.</small>;
  const data: Record<string, unknown>[] = traces.map(trace => ({ type: "scatter", mode: "lines", name: trace.label,
    x: trace.x, y: trace.y, connectgaps: false, line: { color: trace.color, width: 1.5 }, hovertemplate: "%{x:.6g}, %{y:.6g}<extra></extra>" }));
  const selectedX = traces[0].x[selectedIndex];
  const layout: Record<string, unknown> = { margin: { t: 18, r: 16, b: 48, l: 58 }, xaxis: { title: xLabel }, yaxis: { title: yLabel },
    showlegend: traces.length > 1, ...(onSelect && selectedX !== undefined ? { shapes: [{ type: "line", x0: selectedX, x1: selectedX, y0: 0, y1: 1, xref: "x", yref: "paper", line: { color: "#ffbd69", width: 1, dash: "dot" } }] } : {}) };
  return <div onKeyDownCapture={event => { if (onSelect && (event.key === "ArrowLeft" || event.key === "ArrowRight")) { event.preventDefault(); event.stopPropagation(); onSelect(Math.max(0, Math.min(traces[0].x.length - 1, selectedIndex + (event.key === "ArrowRight" ? 1 : -1)))); } }}><div className="em-linked-plot"><PlotlyChart title={`${yLabel} versus ${xLabel}`} data={data} layout={layout} revision={`em-traces:${xLabel}:${yLabel}:${traces.map(trace => `${trace.id}:${trace.x.length}`).join("|")}`} onPointClick={onSelect ? (point: { pointNumber: number; curveNumber: number }) => { if (point.curveNumber === 0) onSelect(point.pointNumber); } : undefined} /></div><small>{yLabel}; straight segments connect solved samples.{onSelect ? " Click a frequency or use arrow keys to update the viewport." : ""}</small></div>;
}
