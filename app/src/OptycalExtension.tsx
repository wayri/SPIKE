// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import DataTable from "./DataTable";
import PlotlyChart from "./PlotlyChart";
import { downloadEMergeText } from "./emergeSampleExport";
import { admitOptycalSource, optycalRecord, type OptycalSetup, type OptycalComparison as Comparison, admitOptycalComparison } from "./optycalStudy";
import "./EMergeExtension.css";
import { optycalReportHtml } from "./optycalReport";
export { admitOptycalComparison } from "./optycalStudy";

export function OptycalSetupForm({ value, onChange, sourceResult, onSelectStep, onSelectSource, busy = false }: {
  value: OptycalSetup; onChange: (value: OptycalSetup) => void; sourceResult: unknown;
  onSelectStep?: () => void; onSelectSource?: () => void; busy?: boolean;
}) {
  const source = admitOptycalSource(sourceResult);
  const update = (key: keyof OptycalSetup, text: string) => onChange({ ...value, [key]: text });
  return <section className="extension-output emerge-result-output" data-guide="optycal-setup">
    <b>EMerge antenna → Optycal structure study</b>
    <small>One-way far-zone source approximation with a perfectly conducting (PEC) structure. This study does not update antenna input matching or solve antenna–structure feedback. Results remain unvalidated.</small>
    <div className="extension-actions">{onSelectSource && <button className="secondary-btn" disabled={busy} onClick={onSelectSource}>Load EMerge result JSON</button>}{onSelectStep && <button className="secondary-btn" disabled={busy} onClick={onSelectStep}>Choose STEP structure</button>}</div>
    {source ? <small role="status">Source: {source.analysisId} · excited port {source.port} · {source.frequencies.length} solved frequencies. Port amplitude uses EMerge's coefficient convention; no absolute power calibration is claimed.</small> : <p role="alert">Run EMerge radiation in SPIKE or load a saved EMerge result containing complex 3D fields and excitation metadata.</p>}
    <div className="sweep-grid">
      <label>Structure STEP / STP path<input aria-label="Structure STEP path" disabled={busy} value={value.step_path} onChange={event => update("step_path", event.target.value)} placeholder="FreeCAD, KiCad or KiKaKuKa STEP assembly" /></label>
      <label>Solved source frequency<select aria-label="Optycal source frequency" disabled={busy || !source} value={value.frequency_hz || String(source?.frequencies[0] ?? "")} onChange={event => update("frequency_hz", event.target.value)}>{!source && <option value="">No usable radiation source</option>}{source?.frequencies.map(frequency => <option key={frequency} value={frequency}>{frequency} Hz</option>)}</select></label>
      <label>Structure material<select aria-label="Optycal structure material" value="pec" disabled><option value="pec">Perfect electric conductor (PEC)</option></select></label>
      <label>Structure mesh size (mm)<input type="number" min="0.1" max="1000" disabled={busy} value={value.mesh_size_mm} onChange={event => update("mesh_size_mm", event.target.value)} /></label>
      <label>Largest antenna physical extent (mm)<input type="number" min="0.001" max="10000" disabled={busy} value={value.antenna_aperture_mm} onChange={event => update("antenna_aperture_mm", event.target.value)} /></label>
      <label>Observation radius (m)<input type="number" min="0.01" max="100000" disabled={busy} value={value.observation_radius_m} onChange={event => update("observation_radius_m", event.target.value)} /></label>
      {(["theta_step_deg", "phi_step_deg"] as const).map(key => <label key={key}>{key === "theta_step_deg" ? "Theta" : "Phi"} angular step<select aria-label={`Optycal ${key}`} disabled={busy} value={value[key]} onChange={event => update(key, event.target.value)}>{[5, 10, 15, 30].map(step => <option key={step} value={step}>{step}°</option>)}</select></label>)}
      <label>Optycal Python executable (optional)<input disabled={busy} value={value.python_executable} onChange={event => update("python_executable", event.target.value)} placeholder="Use configured runtime" /></label>
    </div>
    <label><input type="checkbox" checked={value.source_phase_acknowledged} disabled={busy} onChange={event => onChange({ ...value, source_phase_acknowledged: event.target.checked })} />Treat EMerge samples as the far-field coefficient F with e⁺ʲωᵗ convention, E = F exp(−jkr) / r.</label><small>This explicit phase/origin assumption is required for the EMerge source handoff. Coherent amplitudes use arbitrary common units. The adapter checks source-to-structure far-zone clearance from the declared antenna extent; close enclosure studies require a full-wave model.</small>
    <details><summary>Antenna and structure placement</summary><small>Translations use millimetres. Rotation angles use degrees about X, Y and Z; the generated script records the transformation order. STEP material names are not electromagnetic assignments. Keep the source outside the structure and review coordinate units.</small>
      {(["antenna_translation_mm", "antenna_rotation_deg", "structure_translation_mm", "structure_rotation_deg"] as const).map(key => <div className="sweep-grid" key={key}>{value[key].map((text, index) => <label key={index}>{key.startsWith("antenna") ? "Antenna" : "Structure"} {key.endsWith("rotation_deg") ? "rotation" : "translation"} {"XYZ"[index]} ({key.endsWith("rotation_deg") ? "deg" : "mm"})<input type="number" disabled={busy} value={text} onChange={event => { const vector = [...value[key]] as [string, string, string]; vector[index] = event.target.value; onChange({ ...value, [key]: vector }); }} /></label>)}</div>)}
    </details>
    <small>Import the surroundings as STEP; the radiating antenna is the selected EMerge source. STEP antenna solids alone cannot define an excited antenna. Dielectric structures and fully coupled FEM are pending adapter support.</small>
  </section>;
}

export function OptycalScriptPreview({ data }: { data: Record<string, unknown> | null }) {
  const [error, setError] = useState("");
  if (typeof data?.script !== "string") return null;
  const script = data.script;
  return <section className="extension-output"><b>Generated Optycal Python</b><small>Read-only source generated from this GUI study. Changing settings requires a new preview. Script SHA-256: {String(data.script_sha256 ?? "unavailable")}</small><div className="extension-actions"><button className="secondary-btn" onClick={() => void navigator.clipboard.writeText(script).catch(() => setError("Clipboard unavailable; download the script instead."))}>Copy Python</button><button className="secondary-btn" onClick={() => downloadEMergeText("optycal-study.py", script)}>Download Python</button></div><textarea aria-label="Generated Optycal Python script" readOnly rows={16} value={script} style={{ width: "100%", fontFamily: "monospace", fontSize: 11 }} />{error && <p role="alert">{error}</p>}</section>;
}

export function OptycalResultPlot({ result }: { result: Record<string, unknown> | null }) {
  const data = optycalRecord(result?.data);
  const payload = optycalRecord(data.analysis_result);
  const comparison = optycalRecord(optycalRecord(payload.fields).comparison ?? data.comparison);
  const [metric, setMetric] = useState("delta_db");
  const [sample, setSample] = useState(0);
  const [reportError, setReportError] = useState("");
  const admitted = useMemo(() => admitOptycalComparison(comparison), [comparison]);
  if (!["completed", "completed_with_warnings"].includes(String(payload.status)) || !admitted) return null;
  const selected = Math.min(sample, admitted.theta.length * admitted.phi.length - 1);
  const values = admitted.series[metric] ?? admitted.series.delta_db;
  const signed = metric === "interference_cross_term" || metric === "delta_db";
  const span = values.reduce((maximum, value) => Math.max(maximum, Math.abs(value)), 1e-12);
  const traces = [{ ...(signed ? { zmin: -span, zmax: span } : {}), type: "heatmap", x: admitted.phi, y: admitted.theta, z: admitted.theta.map((_, row) => values.slice(row * admitted.phi.length, (row + 1) * admitted.phi.length)), colorscale: [[0, "#2166ac"], [0.5, "#f7f7f7"], [1, "#b2182b"]], colorbar: { title: metric === "interference_cross_term" ? "cross term" : "dB" } }];
  const report = (print: boolean) => {
    try {
      const html = optycalReportHtml(result);
      if (!print) downloadEMergeText("optycal-report.html", html);
      else {
        const preview = window.open("", "_blank");
        if (!preview) throw new Error("Report window unavailable; download the HTML report and use its Print / save PDF button.");
        preview.document.write(html); preview.document.close(); preview.focus(); preview.print();
      }
      setReportError("");
    } catch (error) { setReportError(error instanceof Error ? error.message : "Report generation failed."); }
  };
  return <section className="extension-output emerge-result-output">
    <b>Structure impact and coherent interference</b><small>Model status: {String(payload.model_status)}. Direct and scattered fields are summed coherently in the one-way approximation. Both patterns use the same bare-field peak reference, preserving relative structure-induced changes. Amplitudes are arbitrary coherent units.</small>
    <div className="extension-actions"><button className="secondary-btn" onClick={() => downloadEMergeText("optycal-analysis.json", JSON.stringify(payload, null, 2))}>Export full result JSON</button><button className="secondary-btn" onClick={() => downloadEMergeText("optycal-comparison.csv", comparisonCsv(admitted))}>Export comparison CSV</button><button className="secondary-btn" onClick={() => report(false)}>Download HTML report</button><button className="secondary-btn" onClick={() => report(true)}>Print / report</button></div>{reportError && <p role="alert">{reportError}</p>}
    <label>Interference display<select aria-label="Optycal interference display" value={metric} onChange={event => setMetric(event.target.value)}><option value="delta_db">Installed / bare amplitude change (dB)</option><option value="interference_cross_term">Coherent interference cross term / bare peak |E|²</option><option value="bare_relative_db">Bare relative amplitude (dB)</option><option value="structure_relative_db">Installed relative amplitude (dB)</option></select></label>
    <PlotlyChart data={traces} layout={{ paper_bgcolor: "#101c23", plot_bgcolor: "#101c23", font: { color: "#d9e5e7", size: 11 }, margin: { l: 60, r: 30, t: 20, b: 50 }, xaxis: { title: "Phi (deg)" }, yaxis: { title: "Theta (deg)" } }} revision={`optycal-${String(payload.analysis_id)}-${metric}`} />
    <label>Probe solved angular sample<input type="number" aria-label="Optycal angular probe index" min="0" max={values.length - 1} step="1" value={selected} onChange={event => { const index = Number(event.target.value); if (Number.isInteger(index) && index >= 0 && index < values.length) setSample(index); }} /></label>
    <small>θ {admitted.theta[Math.floor(selected / admitted.phi.length)]}° · φ {admitted.phi[selected % admitted.phi.length]}° · amplitude change {admitted.series.delta_db[selected].toPrecision(6)} dB · interference cross term {admitted.series.interference_cross_term[selected].toPrecision(6)}</small>
    <DataTable label="Optycal field components"><thead><tr><th>Field component</th><th>Real</th><th>Imaginary</th><th>Magnitude</th><th>Phase (deg)</th></tr></thead><tbody>{Object.entries(admitted.complex).flatMap(([name, vectors]) => vectors[selected].map((pair, axis) => <tr key={`${name}-${axis}`}><td>{name.replace("_e_xyz", "")} {"XYZ"[axis]}</td><td>{pair[0].toPrecision(6)}</td><td>{pair[1].toPrecision(6)}</td><td>{Math.hypot(...pair).toPrecision(6)}</td><td>{Math.hypot(...pair) === 0 ? "undefined at zero" : (Math.atan2(pair[1], pair[0]) * 180 / Math.PI).toPrecision(6)}</td></tr>))}</tbody></DataTable>
    <PlotlyChart data={patternSurfaces(admitted)} layout={{ paper_bgcolor: "#101c23", font: { color: "#d9e5e7", size: 11 }, margin: { l: 0, r: 0, t: 20, b: 10 }, scene: { aspectmode: "data", xaxis: { title: "x" }, yaxis: { title: "y" }, zaxis: { title: "z" } } }} revision={`optycal-sphere-${String(payload.analysis_id)}`} />
    <small>Drag to rotate the installed pattern. Radius uses field amplitude relative to the bare peak; color uses the same bare reference. This is an Optycal approximation, not a new EMerge full-wave solve.</small>
    <PlotlyChart data={comparisonCuts(admitted)} layout={{ paper_bgcolor: "#101c23", plot_bgcolor: "#101c23", font: { color: "#d9e5e7", size: 11 }, margin: { l: 60, r: 20, t: 20, b: 50 }, xaxis: { title: "Theta (deg), phi = 0°" }, yaxis: { title: "Amplitude / bare peak (dB)" } }} revision={`optycal-cut-${String(payload.analysis_id)}`} />
  </section>;
}

function comparisonCsv(value: Comparison): string {
  const complexHeaders = Object.keys(value.complex).flatMap(key => ["x", "y", "z"].flatMap(axis => [`${key}_${axis}_real`, `${key}_${axis}_imag`]));
  return [["theta_deg", "phi_deg", "bare_relative_db", "structure_relative_db", "delta_db", "interference_cross_term", ...complexHeaders].join(","), ...value.theta.flatMap((theta, row) => value.phi.map((phi, col) => { const index = row * value.phi.length + col; return [theta, phi, ...Object.values(value.series).map(array => array[index]), ...Object.values(value.complex).flatMap(array => array[index].flat())].join(","); }))].join("\n");
}
function patternSurfaces(value: Comparison): Record<string, unknown>[] {
  const coords = (axis: number) => value.theta.map((theta, row) => value.phi.map((phi, column) => {
    const t = theta * Math.PI / 180, p = phi * Math.PI / 180;
    const radius = 10 ** (value.series.structure_relative_db[row * value.phi.length + column] / 20);
    return radius * [Math.sin(t) * Math.cos(p), Math.sin(t) * Math.sin(p), Math.cos(t)][axis];
  }));
  return [{ type: "surface", x: coords(0), y: coords(1), z: coords(2), surfacecolor: value.theta.map((_, row) => value.series.structure_relative_db.slice(row * value.phi.length, (row + 1) * value.phi.length)), colorscale: "Viridis", colorbar: { title: "dB / bare peak" }, showscale: true }];
}
function comparisonCuts(value: Comparison): Record<string, unknown>[] {
  return ["bare_relative_db", "structure_relative_db"].map((key, index) => ({ type: "scatter", mode: "lines+markers", name: index === 0 ? "Bare" : "Installed", x: value.theta, y: value.theta.map((_, row) => value.series[key][row * value.phi.length]) }));
}
