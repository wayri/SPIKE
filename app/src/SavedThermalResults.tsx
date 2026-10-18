// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { X, Play, Pause } from "./icons";
import DataTable from "./DataTable";
import PlotlyChart from "./PlotlyChart";
import { numericExtent } from "./numericRange";
import { boardThermalAxisEdges } from "./boardThermalViewport";
import { thermalRecord, thermalResultEvidence, type SavedThermalEntry } from "./thermalSavedResultModel";
import { thermalOccurrenceMatchesDesign } from "./thermalAssemblyFrame";
import { usePanelPresentation } from "./panelPresentation";
import "./savedThermalResults.css";

type Section = "overview" | "plots" | "components" | "transient" | "inputs";
const number = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : null;
const format = (value: unknown) => number(value)?.toPrecision(6) ?? "Not recorded";
const vector = (value: unknown, length: number): value is number[] => Array.isArray(value) && value.length === length && value.every(item => number(item) !== null);

export default function SavedThermalResults({ entries, initialId, initialSection = "overview", occurrences = [], onShow, onClose, onSetup }:
  { entries: SavedThermalEntry[]; initialId?: string; initialSection?: Section;
    occurrences?: Array<{ id: string; name: string; designId: string; sourceNativeId?: string }>;
    onShow?: (entry: SavedThermalEntry, occurrenceId?: string) => void;
    onClose: () => void; onSetup: () => void }) {
  const { ownerDocument, ownerWindow } = usePanelPresentation();
  const [selectedId, setSelectedId] = useState(initialId ?? entries[0]?.id ?? "");
  const [section, setSection] = useState<Section>(initialSection);
  const [layer, setLayer] = useState(-1);
  const [frame, setFrame] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [occurrenceId, setOccurrenceId] = useState("");
  const entry = entries.find(item => item.id === selectedId) ?? entries[0];
  useEffect(() => { setSelectedId(initialId ?? entries[0]?.id ?? ""); setSection(initialSection); }, [initialId, initialSection]);
  useEffect(() => { setLayer(-1); setFrame(-1); setPlaying(false); setOccurrenceId(""); }, [entry?.id]);
  useEffect(() => {
    const doc = ownerDocument, view = ownerWindow; if (!doc || !view) return;
    const close = (event: KeyboardEvent) => { if (doc.querySelector(".saved-thermal-backdrop")?.closest("[hidden]")) return; if (event.key === "Escape") onClose(); };
    view.addEventListener("keydown", close);
    return () => view.removeEventListener("keydown", close);
  }, [ownerDocument, ownerWindow, onClose]);
  const frames = entry && Array.isArray(entry.result.transient) ? entry.result.transient.map(thermalRecord).filter(item => item && number(item.time_s) !== null) : [];
  useEffect(() => {
    const view = ownerWindow; if (!view || !playing || frames.length < 2) return;
    const timer = view.setInterval(() => setFrame(value => (value + 1) % frames.length), 400);
    return () => view.clearInterval(timer);
  }, [ownerWindow, playing, frames.length]);
  const evidence = entry ? thermalResultEvidence(entry) : null;
  const matchingOccurrences = occurrences.filter(item => thermalOccurrenceMatchesDesign(item, evidence?.designId));
  const selectedOccurrence = matchingOccurrences.find(item => item.id === occurrenceId)
    ?? (matchingOccurrences.length === 1 ? matchingOccurrences[0] : undefined);
  const summary = thermalRecord(entry?.result.summary);
  const grid = evidence?.grid;
  const layers = Array.isArray(entry?.result.layer_grids) ? entry.result.layer_grids.map(thermalRecord).filter(Boolean) : [];
  const selectedLayer = layers[layer];
  const selectedFrame = frames[frame];
  const frameLayers = selectedFrame?.layer_temperatures_c;
  const frameValues = Array.isArray(frameLayers) ? frameLayers[Math.max(0, layer)] : undefined;
  const values = selectedFrame ? frameValues : selectedLayer?.temperatures_c ?? grid?.temperatures_c;
  const validValues = grid && vector(values, grid.shape[0] * grid.shape[1]) ? values : null;
  const extent = numericExtent(validValues ?? [], 0, 1);
  // Keep one recorded range across playback; do not normalize each frame.
  const minimum = Math.min(extent.minimum, number(entry?.request?.ambient_temperature_c) ?? extent.minimum,
    number(summary?.minimum_board_temperature_c) ?? extent.minimum);
  const maximum = Math.max(extent.maximum, number(summary?.maximum_board_temperature_c) ?? extent.maximum,
    number(summary?.transient_peak_board_temperature_c) ?? extent.maximum);
  const components = Array.isArray(entry?.result.components) ? entry.result.components : Array.isArray(entry?.result.nodes) ? entry.result.nodes : [];
  const tableRows = components.map(thermalRecord).filter(Boolean);
  return <div className="modal-backdrop saved-thermal-backdrop" role="presentation"><section className="modal saved-thermal-results" role="dialog" aria-modal="true" aria-label="Saved thermal studies and results">
    <header><div><small>STORED ANALYSIS EVIDENCE</small><h2>Thermal studies and results</h2></div><button aria-label="Close saved thermal results" onClick={onClose}><X size={18} /></button></header>
    <div className="saved-thermal-layout"><aside aria-label="Saved thermal study browser">
      <label>Saved study<select aria-label="Saved thermal study" value={entry?.id ?? ""} onChange={event => setSelectedId(event.target.value)}>{entries.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      {([['overview', 'Run status and scope'], ['plots', 'Temperature and layers'], ['components', 'Component values'], ['transient', 'Transient animation'], ['inputs', 'Original saved inputs']] as const).map(([id, label]) => <button key={id} aria-current={section === id ? "page" : undefined} onClick={() => setSection(id)}>{label}</button>)}
      <button onClick={onSetup}>Edit thermal setup</button><small>Viewing saved data never runs a solver or replaces its inputs.</small>
    </aside><main tabIndex={-1}>
      {!entry || !evidence ? <p>No saved thermal result is available in this project. Use thermal setup to prepare an explicit study.</p> : <>
        <h3>{entry.name}</h3><p>{entry.source}{entry.capturedAt ? ` - captured ${entry.capturedAt}` : ""}</p>
        <div className="saved-thermal-status"><b>Saved board/result run: {evidence.status} - {evidence.modelStatus}</b><span>Solver: {evidence.solverId}</span><span>Owning design: {evidence.designId}</span><span>Object-network run status is separate from this saved board result.</span></div>
        {onShow && evidence.grid && <div className="saved-thermal-controls">
          {matchingOccurrences.length > 1 && <label>Display on occurrence<select aria-label="Saved thermal result occurrence" value={occurrenceId} onChange={event => setOccurrenceId(event.target.value)}><option value="">Choose the owning occurrence</option>{matchingOccurrences.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
          <button disabled={occurrences.length > 0 && !selectedOccurrence} onClick={() => onShow(entry, selectedOccurrence?.id)}>Show saved field in viewport</button>
          <small>One occurrence display of the retained single-board result; this does not solve coupled assembly cooling.</small>
        </div>}
        {entry.inputsChanged && <div role="alert" className="saved-thermal-warning">Current inputs differ. This is historical evidence displayed with its original recorded inputs.</div>}
        <details className="saved-thermal-warning" open={section === "overview"}><summary><b>{evidence.meshConverged ? "Review model scope and omissions" : "Review model omissions / mesh convergence not established"}</b>{evidence.warnings.find(message => message.includes("excluded from")) && <p>{evidence.warnings.find(message => message.includes("excluded from"))}</p>}</summary>{evidence.warnings.map(message => <p key={message}>{message}</p>)}</details>
        {section === "overview" && <dl>{[['Total power (W)', summary?.total_power_w], ['Peak board temperature (C)', summary?.maximum_board_temperature_c], ['Peak junction temperature (C)', summary?.maximum_junction_temperature_c], ['Linear relative residual', summary?.linear_relative_residual], ['Heat balance error (W)', summary?.energy_balance_error_w]].map(([label, value]) => <div key={String(label)}><dt>{String(label)}</dt><dd>{format(value)}</dd></div>)}</dl>}
        {(section === "plots" || section === "transient") && <>
          <div className="saved-thermal-controls"><label>Layer<select aria-label="Saved temperature layer" value={layer} onChange={event => setLayer(Number(event.target.value))}><option value={-1}>Top surface</option>{layers.map((item, index) => <option key={index} value={index}>{String(item?.name ?? `Layer ${index + 1}`)}</option>)}</select></label>
            {frames.length > 0 && <label>Frame<select aria-label="Saved thermal frame" value={frame} onChange={event => { setPlaying(false); setFrame(Number(event.target.value)); }}><option value={-1}>Saved steady state</option>{frames.map((item, index) => <option key={index} value={index}>{format(item?.time_s)} s</option>)}</select></label>}
            {section === "transient" && <button disabled={frames.length < 2} onClick={() => { if (frame < 0) setFrame(0); setPlaying(value => !value); }}>{playing ? <Pause size={14} /> : <Play size={14} />}{playing ? "Pause" : "Play saved frames"}</button>}
          </div>
          {validValues && grid ? <PlotlyChart title="Saved board temperature - source coordinates" revision={`${entry.id}:${layer}:${frame}`} data={[{ type: "heatmap", x: boardThermalAxisEdges(grid, 0), y: boardThermalAxisEdges(grid, 1), z: Array.from({ length: grid.shape[1] }, (_, row) => validValues.slice(row * grid.shape[0], (row + 1) * grid.shape[0])), zmin: minimum, zmax: maximum, colorscale: "Viridis", connectgaps: false, hovertemplate: "Source X %{x} mm<br>Source Y %{y} mm<br>%{z} C<extra></extra>", colorbar: { title: "C" } }]} layout={{ xaxis: { title: "Source X (mm)" }, yaxis: { title: "Source Y (mm)", autorange: "reversed", scaleanchor: "x" } }} /> : <p>No admitted temperature grid for this selection. Missing or malformed samples are not filled in.</p>}
          {section === "transient" && (frames.length ? <PlotlyChart title="Saved transient peak temperature" revision={`${entry.id}:history`} data={[{ type: "scatter", mode: "lines+markers", x: frames.map(item => item?.time_s), y: frames.map(item => item?.maximum_board_temperature_c), connectgaps: false }]} layout={{ xaxis: { title: "Time (s)" }, yaxis: { title: "Peak board temperature (C)" } }} /> : <p>No transient frames were saved. Viewing does not schedule a transient run.</p>)}
          {selectedFrame && <p>Saved frame {format(selectedFrame.time_s)} s. Board cells are transient samples; component values remain the saved steady-state estimates. Colors share the recorded range across playback.</p>}
        </>}
        {section === "components" && <DataTable label="Saved thermal component values"><thead><tr><th>Reference</th><th>Power W</th><th>Board C</th><th>Case C</th><th>Junction / object C</th></tr></thead><tbody>{tableRows.map((item, index) => <tr key={index}><td>{String(item?.component_ref ?? item?.id ?? index)}</td><td>{format(item?.power_w)}</td><td>{format(item?.board_temperature_c)}</td><td>{format(item?.case_temperature_c)}</td><td>{format(item?.junction_temperature_c ?? item?.temperature_c)}</td></tr>)}</tbody></DataTable>}
        {section === "inputs" && <><p>Retained input snapshot and result provenance; current setup is not applied to historical values.</p><pre>{JSON.stringify({ request: entry.request, provenance: entry.result.provenance }, null, 2)}</pre></>}
      </>}
    </main></div>
  </section></div>;
}
