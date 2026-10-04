// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import { persistedEnginePython } from "./persistedEnginePython";
import DataTable from "./DataTable";
import { emergeRuntimePresentation } from "./emergeRuntimePresentation";
import PlotlyChart from "./PlotlyChart";
import { interpolateEMergePattern, type EMergeAngularPattern } from "./emergePatternInterpolation";
import "./EMergeExtension.css";
import "./EMergeGerberImport.css";
import { Layers3 } from "./icons";
import type { EMergeGerberSource } from "./emergeGerberSource";
import type { ParsedPad } from "./boardParser";
import { suggestEMergePadPairs } from "./emergeSetupSuggestions";
import { reviewEMergeNetwork } from "./emergeNetworkReview";
import { EMergeNearField } from "./EMergeNearField";
import { downloadEMergeText, exportEMergeNetwork } from "./emergeSampleExport";

export function EMergeCapabilityInventory({ rows }: { rows: unknown }) {
  if (!Array.isArray(rows)) return null;
  return <details className="extension-output"><summary>EMerge feature availability in SPIKE</summary><small>Upstream features are listed separately from the current adapter coverage. Integrated results remain unvalidated.</small><DataTable label="EMerge feature availability"><thead><tr><th>Feature</th><th>Adapter status</th><th>Scope</th></tr></thead><tbody>{rows.map((item, index) => { const feature = record(item); return <tr key={String(feature.id ?? index)}><td>{String(feature.name ?? feature.id)}</td><td>{feature.status === "implemented_unvalidated" ? "Integrated · unvalidated" : "Pending adapter"}</td><td>{String(feature.scope ?? "")}</td></tr>; })}</tbody></DataTable></details>;
}

export function EMergeRuntimeStatus({ value }: { value: Record<string, unknown> }) {
  const runtime = emergeRuntimePresentation(value);
  return <section className="extension-output" aria-label="EMerge runtime compatibility"><div className="extension-output-title"><b>{runtime.title}</b></div><small>{runtime.message}</small>
    {runtime.available && <small>Enabled adapter tools: {runtime.capabilities.join(", ") || "none"}</small>}
    {runtime.checks.length > 0 && <details><summary>Installed runtime API checks</summary><DataTable label="EMerge runtime API checks"><thead><tr><th>API family</th><th>Detected</th></tr></thead><tbody>{runtime.checks.map(check => <tr key={check.id}><td>{check.label}</td><td>{check.present ? "Yes" : "No"}</td></tr>)}</tbody></DataTable></details>}
  </section>;
}

export function EMergeScriptPreview({ data }: { data: Record<string, unknown> | null }) {
  const [error, setError] = useState("");
  if (typeof data?.script !== "string") return null;
  const script = data.script;
  return <section className="extension-output"><b>Generated simulation script</b><small>Read-only Python generated from the GUI setup. Changes to setup require a new preview. The solver regenerates this script from the current case.</small><small>Case SHA-256: {String(data.case_sha256 ?? "unavailable")}</small><div className="extension-actions"><button className="secondary-btn" onClick={() => void navigator.clipboard.writeText(script).then(() => setError("")).catch(() => setError("Clipboard unavailable; download the script instead."))}>Copy Python</button><button className="secondary-btn" onClick={() => downloadEMergeText("emerge-case.py", script)}>Download Python</button></div><textarea aria-label="Generated EMerge Python script" readOnly value={script} rows={18} style={{ width: "100%", fontFamily: "monospace", fontSize: 11 }} />{error && <p role="alert">{error}</p>}</section>;
}

export type EMergeSetup = {
  geometry_source?: "board" | "gerber";
  geometry_backend?: "emerge" | "emcad";
  reference_impedance_ohm?: string;
  include_dielectric_loss?: boolean;
  air_margin_mm?: string;
  radiation_theta_step_deg?: string;
  radiation_phi_step_deg?: string;
  radiation_cut_phi_deg?: string;
  parallel?: boolean;
  n_workers?: string;
  nearfield_enabled?: boolean;
  nearfield_z_mm?: string;
  nearfield_grid_points?: string;
  sparse_solver?: "auto" | "superlu";
  field_excited_port?: string;
  signal_net: string;
  return_net: string;
  signal_pad_id: string;
  return_pad_id: string;
  receive_signal_pad_id: string;
  receive_return_pad_id: string;
  frequency_start_hz: string;
  frequency_stop_hz: string;
  frequency_points: string;
  mesh_resolution_mm: string;
  python_executable: string;
  radome_enabled: boolean;
  radome_origin_x_mm: string;
  radome_origin_y_mm: string;
  radome_gap_mm: string;
  radome_width_mm: string;
  radome_depth_mm: string;
  radome_thickness_mm: string;
  radome_epsilon_r: string;
};

export const defaultEMergeSetup = (signalNet = ""): EMergeSetup => ({
  geometry_source: "board", geometry_backend: "emerge", sparse_solver: "auto", field_excited_port: "1",
  reference_impedance_ohm: "50", include_dielectric_loss: false, air_margin_mm: "",
  radiation_theta_step_deg: "15", radiation_phi_step_deg: "15", radiation_cut_phi_deg: "0",
  parallel: false, n_workers: "2", nearfield_enabled: false, nearfield_z_mm: "2", nearfield_grid_points: "11",
  signal_net: signalNet,
  return_net: "GND",
  signal_pad_id: "",
  return_pad_id: "",
  receive_signal_pad_id: "",
  receive_return_pad_id: "",
  frequency_start_hz: "100000000",
  frequency_stop_hz: "1000000000",
  frequency_points: "21",
  mesh_resolution_mm: "0.5",
  python_executable: persistedEnginePython(),
  radome_enabled: false,
  radome_origin_x_mm: "0", radome_origin_y_mm: "0", radome_gap_mm: "10",
  radome_width_mm: "50", radome_depth_mm: "40", radome_thickness_mm: "1.5", radome_epsilon_r: "2.1",
});

export function emergeParameters(setup: EMergeSetup, geometrySource: "board" | "gerber" = setup.geometry_source ?? "board"): Record<string, unknown> {
  if (!["board", "gerber"].includes(geometrySource)) throw new Error("Choose an imported board or native Gerber source.");
  if (setup.geometry_backend !== undefined && !["emerge", "emcad"].includes(setup.geometry_backend)) throw new Error("Choose a supported geometry preparation backend.");
  const number = (value: string, label: string, minimum: number) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < minimum) throw new Error(`${label} must be at least ${minimum}.`);
    return parsed;
  };
  const rangeNumber = (value: string, label: string, low: number, high: number) => {
    const parsed = number(value, label, low);
    if (parsed > high) throw new Error(`${label} must be at most ${high}.`);
    return parsed;
  };
  const start = rangeNumber(setup.frequency_start_hz, "Start frequency", 1e8, 1e11);
  const stop = rangeNumber(setup.frequency_stop_hz, "Stop frequency", 1e8, 1e11);
  if (stop <= start) throw new Error("Stop frequency must be greater than start frequency.");
  if (geometrySource === "board" && (!setup.signal_net.trim() || !setup.return_net.trim())) throw new Error("Signal and return nets are required.");
  if (geometrySource === "board" && (!setup.signal_pad_id.trim() || !setup.return_pad_id.trim())) throw new Error("Signal and return pad IDs are required.");
  const hasReceiveSignal = Boolean(setup.receive_signal_pad_id.trim());
  const hasReceiveReturn = Boolean(setup.receive_return_pad_id.trim());
  if (geometrySource === "board" && hasReceiveSignal !== hasReceiveReturn) throw new Error("Enter both receive port pad IDs, or leave both blank for a one-port solve.");
  const points = rangeNumber(setup.frequency_points, "Frequency points", 2, 64);
  if (!Number.isInteger(points)) throw new Error("Frequency points must be a whole number.");
  const parameters: Record<string, unknown> = {
    geometry_source: geometrySource,
    geometry_backend: geometrySource === "gerber" ? "emerge" : setup.geometry_backend ?? "emerge",
    signal_net: setup.signal_net.trim(), return_net: setup.return_net.trim(),
    signal_pad_id: setup.signal_pad_id.trim(), return_pad_id: setup.return_pad_id.trim(),
    frequency_start_hz: start, frequency_stop_hz: stop,
    frequency_points: points,
    mesh_resolution_mm: rangeNumber(setup.mesh_resolution_mm, "Mesh resolution", 0.05, 10),
  };
  parameters.reference_impedance_ohm = rangeNumber(setup.reference_impedance_ohm ?? "50", "Reference impedance", 1, 1000);
  parameters.include_dielectric_loss = setup.include_dielectric_loss ?? false;
  if (setup.air_margin_mm?.trim()) parameters.air_margin_mm = rangeNumber(setup.air_margin_mm, "Air margin", 5, 200);
  for (const key of ["radiation_theta_step_deg", "radiation_phi_step_deg"] as const) {
    const step = Number(setup[key] ?? "15");
    if (![5, 10, 15, 30].includes(step)) throw new Error("Radiation steps must be 5, 10, 15 or 30 degrees.");
    parameters[key] = step;
  }
  parameters.radiation_cut_phi_deg = rangeNumber(setup.radiation_cut_phi_deg ?? "0", "Radiation cut phi", 0, 360);
  if (!["auto", "superlu"].includes(setup.sparse_solver ?? "auto")) throw new Error("Choose a supported sparse solver.");
  parameters.sparse_solver = setup.sparse_solver ?? "auto";
  const excitation = Number(setup.field_excited_port ?? "1");
  if (![1, 2].includes(excitation) || (excitation === 2 && geometrySource === "board" && !hasReceiveSignal)) throw new Error("Field excitation requires an available port.");
  parameters.field_excited_port = excitation;
  parameters.parallel = setup.parallel ?? false;
  const workers = rangeNumber(setup.n_workers ?? "2", "Parallel workers", 1, 8);
  if (!Number.isInteger(workers)) throw new Error("Parallel workers must be a whole number.");
  parameters.n_workers = workers;
  parameters.nearfield_enabled = setup.nearfield_enabled ?? false;
  if (setup.nearfield_enabled) {
    const z = Number(setup.nearfield_z_mm ?? "2");
    if (!Number.isFinite(z) || Math.abs(z) > 200) throw new Error("Field plane Z must be within ±200 mm.");
    parameters.nearfield_z_mm = z;
    const grid = rangeNumber(setup.nearfield_grid_points ?? "11", "Field grid points", 3, 41);
    if (!Number.isInteger(grid)) throw new Error("Field grid points must be a whole number.");
    parameters.nearfield_grid_points = grid;
  }
  if (hasReceiveSignal && geometrySource === "board") {
    parameters.receive_signal_pad_id = setup.receive_signal_pad_id.trim();
    parameters.receive_return_pad_id = setup.receive_return_pad_id.trim();
  }
  if (setup.python_executable.trim()) parameters.python_executable = setup.python_executable.trim();
  if (setup.radome_enabled) {
    const position = (value: string, label: string) => {
      const parsed = Number(value);
      if (!Number.isFinite(parsed) || Math.abs(parsed) > 1000) throw new Error(`${label} must be within ±1000 mm.`);
      return parsed;
    };
    parameters.surrounding_geometry = {
      contract: "spike/emerge-surroundings/v1",
      objects: [{ kind: "dielectric_box", name: "Radome slab",
        origin_mm: [position(setup.radome_origin_x_mm, "Radome X"), position(setup.radome_origin_y_mm, "Radome Y"), rangeNumber(setup.radome_gap_mm, "Radome gap", 0.5, 199)],
        size_mm: [rangeNumber(setup.radome_width_mm, "Radome width", 0.1, 200), rangeNumber(setup.radome_depth_mm, "Radome depth", 0.1, 200), rangeNumber(setup.radome_thickness_mm, "Radome thickness", 0.1, 200)],
        epsilon_r: rangeNumber(setup.radome_epsilon_r, "Radome relative permittivity", 1.01, 30) }],
    };
  }
  return parameters;
}

export function EMergeSetupForm({ value, onChange, netOptions = [], padOptions = [], boardPads = [], copperLayerOrder = [], boardBounds, gerberSource, gerberRuntime, onOpenGerber }: { value: EMergeSetup; onChange: (value: EMergeSetup) => void; netOptions?: string[]; padOptions?: string[]; boardPads?: ParsedPad[]; copperLayerOrder?: string[]; boardBounds?: { minX: number; minY: number; maxX: number; maxY: number }; gerberSource?: EMergeGerberSource | null; gerberRuntime?: Record<string, unknown> | null; onOpenGerber?: (pythonExecutable: string) => void }) {
  const suggestions = useMemo(() => suggestEMergePadPairs(boardPads, value.signal_net.trim(), value.return_net.trim(), copperLayerOrder), [boardPads, copperLayerOrder, value.signal_net, value.return_net]);
  const applyPair = (index: number, receive: boolean) => {
    const pair = suggestions[index];
    if (pair) onChange({ ...value, ...(receive ? { receive_signal_pad_id: pair.signalId, receive_return_pad_id: pair.returnId } : { signal_pad_id: pair.signalId, return_pad_id: pair.returnId }) });
  };
  const update = (key: keyof EMergeSetup, next: string) => onChange({ ...value, [key]: next });
  const toggleRadome = (enabled: boolean) => onChange({ ...value, radome_enabled: enabled,
    ...(enabled && boardBounds ? { radome_origin_x_mm: String(boardBounds.minX - 5), radome_origin_y_mm: String(boardBounds.minY - 5),
      radome_width_mm: String(boardBounds.maxX - boardBounds.minX + 10), radome_depth_mm: String(boardBounds.maxY - boardBounds.minY + 10) } : {}) });
  return <div className="wizard-section">
    <label>EMERGE PORT SWEEP SETUP</label>
    {onOpenGerber && <button className="secondary-btn" onClick={() => onOpenGerber(value.python_executable)} title="Load original Gerber copper with EMerge's native loader; retain KiCad support"><Layers3 size={15}/>Native Gerber study</button>}
    {gerberSource && <section className="emerge-native-source" aria-label="Active native Gerber source"><b>Native Gerber source: {gerberSource.name}</b><small>Copper is loaded by EMerge's native tools during mesh preparation. Imported KiCad net and pad selectors do not define this study.</small><ul>{gerberSource.layers.map(layer => <li key={layer.name}>{layer.name}: {layer.file_name}</li>)}</ul><small>Declared port planes: {gerberSource.ports.map(port => `${port.id}: (${port.x_mm}, ${port.y_mm}) mm, ${port.width_mm} mm wide, ${port.signal_layer} / ${port.return_layer}`).join("; ")}. Inspect conductor contact in the mesh before solving.</small></section>}
    {gerberSource && gerberRuntime?.gerber_available !== true && <p role="status">{gerberRuntime?.gerber_available === false ? String(gerberRuntime.gerber_reason ?? "Native Gerber loading is unavailable. Install EMerge's gerber extra in the selected solver Python, then check the runtime again.") : "Check the EMerge runtime to confirm native Gerber loading before meshing or solving."}</p>}
    {Boolean(gerberSource?.drills?.length) && <p role="status">Excellon sources are retained. Native drill and via execution is pending, so this study is blocked before meshing or solving.</p>}
    <fieldset className="emerge-board-terminals" disabled={Boolean(gerberSource)} hidden={Boolean(gerberSource)}>
    <small>Choose aligned vertical signal/return pad pairs, with signal above return on adjacent explicit copper layers. Planar 2-16 layer boards require physical dielectric thickness and permittivity. Geometry and results remain approximate and unvalidated; preflight checks supported geometry.</small>
    <div className="sweep-grid"><label>Suggested excitation pair<select aria-label="Suggested excitation pair" value="" disabled={!suggestions.length} onChange={event => applyPair(Number(event.target.value), false)}><option value="">{suggestions.length ? "Choose a board pad pair" : "No exact-centre pair found"}</option>{suggestions.map((pair, index) => <option key={`${pair.signalId}-${pair.returnId}`} value={index}>{pair.signalId} ({pair.signalLayer}) / {pair.returnId} ({pair.returnLayer})</option>)}</select></label>
      <label>Suggested receive pair<select aria-label="Suggested receive pair" value="" disabled={!suggestions.length} onChange={event => applyPair(Number(event.target.value), true)}><option value="">Choose an optional second pair</option>{suggestions.map((pair, index) => <option disabled={pair.signalId === value.signal_pad_id && pair.returnId === value.return_pad_id} key={`${pair.signalId}-${pair.returnId}`} value={index}>{pair.signalId} / {pair.returnId}</option>)}</select></label></div>
    <small>Suggestions show up to 100 undrilled pairs with exactly matching centres on your selected nets and adjacent copper layers. Review the choice before running; manual IDs remain available for other aligned pads.</small>
    <div className="sweep-grid">
      <label>Signal net<input list="emerge-net-options" value={value.signal_net} onChange={event => update("signal_net", event.target.value)} /></label>
      <label>Return net<input list="emerge-net-options" value={value.return_net} onChange={event => update("return_net", event.target.value)} /></label>
      <label>Signal pad ID<input list="emerge-pad-options" value={value.signal_pad_id} onChange={event => update("signal_pad_id", event.target.value)} /></label>
      <label>Return pad ID<input list="emerge-pad-options" value={value.return_pad_id} onChange={event => update("return_pad_id", event.target.value)} /></label>
      <label>Receive signal pad ID (optional)<input list="emerge-pad-options" value={value.receive_signal_pad_id} onChange={event => update("receive_signal_pad_id", event.target.value)} /></label>
      <label>Receive return pad ID (optional)<input list="emerge-pad-options" value={value.receive_return_pad_id} onChange={event => update("receive_return_pad_id", event.target.value)} /></label>
    </div></fieldset><div className="sweep-grid">
      <label data-guide="emerge-frequency">Start frequency (Hz)<input type="number" min="100000000" max="100000000000" value={value.frequency_start_hz} onChange={event => update("frequency_start_hz", event.target.value)} /></label>
      <label>Stop frequency (Hz)<input type="number" min="100000000" max="100000000000" value={value.frequency_stop_hz} onChange={event => update("frequency_stop_hz", event.target.value)} /></label>
      <label>Frequency points<input type="number" min="2" max="64" step="1" value={value.frequency_points} onChange={event => update("frequency_points", event.target.value)} /></label>
      <label>Mesh resolution (mm)<input type="number" min="0.05" max="10" step="0.01" value={value.mesh_resolution_mm} onChange={event => update("mesh_resolution_mm", event.target.value)} /></label>
      <label>EMerge Python executable (optional)<input value={value.python_executable} placeholder="Use configured runtime" onChange={event => update("python_executable", event.target.value)} /></label>
      <label hidden={Boolean(gerberSource)}>Geometry preparation<select value={value.geometry_backend ?? "emerge"} onChange={event => onChange({ ...value, geometry_backend: event.target.value as "emerge" | "emcad" })}><option value="emerge">EMerge native geometry</option><option value="emcad">emcad copper union (requires installed emcad)</option></select></label>
    </div>
    <details><summary>Advanced solver and sampling controls</summary><div className="sweep-grid">
      <label>Reference impedance (ohm)<input type="number" min="1" max="1000" value={value.reference_impedance_ohm ?? "50"} onChange={event => update("reference_impedance_ohm", event.target.value)} /></label>
      <label>Air margin (mm, blank = automatic)<input type="number" min="5" max="200" value={value.air_margin_mm ?? ""} onChange={event => update("air_margin_mm", event.target.value)} /></label>
      {(["radiation_theta_step_deg", "radiation_phi_step_deg"] as const).map(key => <label key={key}>{key.includes("theta") ? "Theta" : "Phi"} radiation step (deg)<select value={value[key] ?? "15"} onChange={event => update(key, event.target.value)}>{[5, 10, 15, 30].map(step => <option key={step} value={step}>{step}</option>)}</select></label>)}
      <label>Far-field cut phi (deg)<input type="number" min="0" max="360" value={value.radiation_cut_phi_deg ?? "0"} onChange={event => update("radiation_cut_phi_deg", event.target.value)} /></label>
      <label>Sparse solver<select value={value.sparse_solver ?? "auto"} onChange={event => onChange({ ...value, sparse_solver: event.target.value as "auto" | "superlu" })}><option value="auto">Runtime default</option><option value="superlu">SuperLU</option></select></label>
      <label>Radiation / field excitation<select value={value.field_excited_port ?? "1"} onChange={event => update("field_excited_port", event.target.value)}><option value="1">P1</option><option value="2" disabled={gerberSource ? gerberSource.ports.length < 2 : !value.receive_signal_pad_id || !value.receive_return_pad_id}>P2</option></select></label>
      <label>Parallel workers<input type="number" min="1" max="8" disabled={!value.parallel} value={value.n_workers ?? "2"} onChange={event => update("n_workers", event.target.value)} /></label>
    </div><label><input type="checkbox" checked={value.include_dielectric_loss ?? false} onChange={event => onChange({ ...value, include_dielectric_loss: event.target.checked })} /> Include imported dielectric loss tangent</label><label><input type="checkbox" checked={value.parallel ?? false} onChange={event => onChange({ ...value, parallel: event.target.checked })} /> Parallel frequency solve</label><label><input type="checkbox" checked={value.nearfield_enabled ?? false} onChange={event => onChange({ ...value, nearfield_enabled: event.target.checked })} /> Capture complex E/H on XY field plane</label>
    {value.nearfield_enabled && <div className="sweep-grid"><label>Field plane Z above top copper (mm)<input type="number" min="-200" max="200" value={value.nearfield_z_mm ?? "2"} onChange={event => update("nearfield_z_mm", event.target.value)} /></label><label>Field grid points per axis<input type="number" min="3" max="41" value={value.nearfield_grid_points ?? "11"} onChange={event => update("nearfield_grid_points", event.target.value)} /></label></div>}
    <small>Loss, air boundaries, mesh and angular sampling need convergence review. Parallel solving depends on the selected EMerge runtime API. Invalid field points remain excluded.</small></details>
    <label data-guide="emerge-radome"><input type="checkbox" checked={value.radome_enabled} onChange={event => toggleRadome(event.target.checked)} /> Model dielectric cover in front of antenna</label>
    {value.radome_enabled && <><small>Top copper is z = 0; positive gap is above the board. The cover is an ideal dielectric box included in the FEM mesh. Start with a bare run, then compare its pattern with the cover run.</small><div className="sweep-grid">
      <label>Cover X origin (mm)<input type="number" value={value.radome_origin_x_mm} onChange={event => update("radome_origin_x_mm", event.target.value)} /></label>
      <label>Cover Y origin (mm)<input type="number" value={value.radome_origin_y_mm} onChange={event => update("radome_origin_y_mm", event.target.value)} /></label>
      <label>Gap above top copper (mm)<input type="number" min="0.5" value={value.radome_gap_mm} onChange={event => update("radome_gap_mm", event.target.value)} /></label>
      <label>Cover width X (mm)<input type="number" min="0.1" value={value.radome_width_mm} onChange={event => update("radome_width_mm", event.target.value)} /></label>
      <label>Cover depth Y (mm)<input type="number" min="0.1" value={value.radome_depth_mm} onChange={event => update("radome_depth_mm", event.target.value)} /></label>
      <label>Cover thickness (mm)<input type="number" min="0.1" value={value.radome_thickness_mm} onChange={event => update("radome_thickness_mm", event.target.value)} /></label>
      <label>Relative permittivity εr<input type="number" min="1.01" max="30" step="0.01" value={value.radome_epsilon_r} onChange={event => update("radome_epsilon_r", event.target.value)} /></label>
    </div></>}
    <datalist id="emerge-net-options">{netOptions.map(net => <option key={net} value={net} />)}</datalist>
    <datalist id="emerge-pad-options">{padOptions.map(pad => <option key={pad} value={pad} />)}</datalist>
  </div>;
}

type UnknownRecord = Record<string, unknown>;
const EMERGE_PATTERN_LAYOUT: Record<string, unknown> = {
  paper_bgcolor: "#101c23", plot_bgcolor: "#101c23", font: { color: "#cbdad5" },
  margin: { l: 0, r: 0, t: 10, b: 0 },
  scene: { aspectmode: "cube", xaxis: { title: "X" }, yaxis: { title: "Y" }, zaxis: { title: "Z" } },
};
const record = (value: unknown): UnknownRecord => value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
const number = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const complexMagnitudeDb = (value: unknown): number | null => {
  if (!Array.isArray(value) || value.length !== 2) return null;
  const real = number(value[0]); const imaginary = number(value[1]);
  if (real === null || imaginary === null) return null;
  return 20 * Math.log10(Math.max(Math.hypot(real, imaginary), 1e-30));
};
const complexPhaseDeg = (value: unknown): number | null => {
  if (!Array.isArray(value) || value.length !== 2) return null;
  const real = number(value[0]); const imaginary = number(value[1]);
  return real === null || imaginary === null ? null : Math.atan2(imaginary, real) * 180 / Math.PI;
};

function patternSurface(pattern: UnknownRecord): Record<string, unknown>[] {
  const theta = Array.isArray(pattern.theta_deg) ? pattern.theta_deg.map(number) : [];
  const phi = Array.isArray(pattern.phi_deg) ? pattern.phi_deg.map(number) : [];
  const db = Array.isArray(pattern.relative_amplitude_db) ? pattern.relative_amplitude_db.map(number) : [];
  if (theta.length < 3 || phi.length < 4 || db.length !== theta.length * phi.length
      || theta.some(value => value === null) || phi.some(value => value === null) || db.some(value => value === null)) return [];
  const x: number[][] = [], y: number[][] = [], z: number[][] = [], color: number[][] = [], directions: number[][][] = [];
  theta.forEach((thetaValue, row) => {
    const t = thetaValue! * Math.PI / 180;
    const xr: number[] = [], yr: number[] = [], zr: number[] = [], cr: number[] = [], dr: number[][] = [];
    phi.forEach((phiValue, column) => {
      const p = phiValue! * Math.PI / 180;
      const amplitudeDb = db[row * phi.length + column]!;
      const radius = Math.pow(10, Math.max(-60, amplitudeDb) / 20);
      xr.push(radius * Math.sin(t) * Math.cos(p));
      yr.push(radius * Math.sin(t) * Math.sin(p));
      zr.push(radius * Math.cos(t));
      cr.push(amplitudeDb);
      dr.push([thetaValue!, phiValue!]);
    });
    x.push(xr); y.push(yr); z.push(zr); color.push(cr); directions.push(dr);
  });
  return [{ type: "surface", x, y, z, surfacecolor: color, customdata: directions, cmin: -40, cmax: 0,
    colorscale: "Viridis", colorbar: { title: { text: "Relative dB" } },
    hovertemplate: "θ %{customdata[0]:.0f}° · φ %{customdata[1]:.0f}°<br>Relative amplitude %{surfacecolor:.1f} dB<extra></extra>" }];
}

function SampleLinePlot({ points, label, xUnit, yUnit, note }: {
  points: Array<[number, number]>; label: string; xUnit: string; yUnit: string; note: string;
}) {
  const [pinnedIndex, setPinnedIndex] = useState<number | null>(null);
  const sampleText = (index: number | null) => index !== null && points[index]
    ? `${points[index][0].toPrecision(7)} ${xUnit} · ${points[index][1].toPrecision(6)} ${yUnit}` : "";
  const pinned = pinnedIndex === null ? null : points[pinnedIndex];
  const layout: Record<string, unknown> = {
    margin: { t: 18, r: 20, b: 52, l: 64 }, hovermode: "closest", showlegend: false,
    xaxis: { title: xUnit }, yaxis: { title: yUnit },
    ...(pinned ? { shapes: [
      { type: "line", x0: pinned[0], x1: pinned[0], y0: 0, y1: 1, xref: "x", yref: "paper", line: { color: "#ffbd69", width: 1, dash: "dot" } },
      { type: "line", x0: 0, x1: 1, y0: pinned[1], y1: pinned[1], xref: "paper", yref: "y", line: { color: "#ffbd69", width: 1, dash: "dot" } },
    ] } : {}),
  };
  const data: Record<string, unknown>[] = [{ type: "scatter", mode: "lines", name: label,
    x: points.map(point => point[0]), y: points.map(point => point[1]), connectgaps: false,
    line: { color: "#70d4e8", width: 2 }, hovertemplate: `%{x:.7g} ${xUnit}<br>%{y:.6g} ${yUnit}<extra></extra>` }];
  return <>
    <div className="emerge-sample-plot"><PlotlyChart title={label} data={data} layout={layout}
      revision={`emerge-sample:${label}:${xUnit}:${yUnit}:${points.length}`}
      onPointClick={(point: { pointNumber: number }) => setPinnedIndex(point.pointNumber)} /></div>
    <small>{note}</small>
    {pinnedIndex !== null && <small role="status">Pinned sample {pinnedIndex}: {sampleText(pinnedIndex)}</small>}
  </>;
}

/** Displays only the angular and network arrays explicitly returned by EMerge. */
export function EMergeResultPlot({ result, frequencyIndex, onFrequencyIndexChange }: { result: Record<string, unknown> | null; frequencyIndex?: number; onFrequencyIndexChange?: (index: number) => void }) {
  const analysis = record(record(result).data).analysis_result;
  const payload = record(analysis);
  const fields = record(payload.fields); const networks = record(payload.networks);
  const radiation = record(fields.radiation); const sParameters = record(networks.s_parameters);
  const networkReview = reviewEMergeNetwork(result);
  const cuts = Array.isArray(radiation.cuts) ? radiation.cuts.map(record) : [];
  const patterns = Array.isArray(radiation.patterns_3d) ? radiation.patterns_3d as UnknownRecord[] : [];
  const frequencies = networkReview.issue === null && Array.isArray(sParameters.frequencies_hz) ? sParameters.frequencies_hz as number[] : [];
  const ports = Array.isArray(sParameters.ports) ? sParameters.ports.filter((item): item is string => typeof item === "string") : [];
  const [localCutIndex, setLocalCutIndex] = useState(0); const [receivePort, setReceivePort] = useState(0); const [excitedPort, setExcitedPort] = useState(0);
  const [interpolated, setInterpolated] = useState(true);
  const [exportError, setExportError] = useState("");
  const [networkSample, setNetworkSample] = useState(0);
  const exportNetwork = (format: "csv" | "touchstone") => {
    try { const output = exportEMergeNetwork(result, format); downloadEMergeText(output.name, output.text); setExportError(""); }
    catch (error) { setExportError(error instanceof Error ? error.message : "Network export failed."); }
  };
  const cutIndex = frequencyIndex ?? localCutIndex;
  const setCutIndex = onFrequencyIndexChange ?? setLocalCutIndex;
  const radiationPoints = useMemo(() => {
    const cut = cuts[Math.min(cutIndex, Math.max(0, cuts.length - 1))] ?? {};
    const angles = Array.isArray(cut.angles_deg) ? cut.angles_deg.map(number) : [];
    const db = Array.isArray(cut.relative_amplitude_db) ? cut.relative_amplitude_db.map(number) : [];
    return angles.flatMap((angle, index) => angle === null || db[index] === null ? [] : [[angle, db[index]!] as [number, number]]);
  }, [cuts, cutIndex]);
  const sParameterPoints = useMemo(() => {
    const matrices = Array.isArray(sParameters.values) ? sParameters.values : [];
    return frequencies.flatMap((frequency, index) => {
      const matrix = matrices[index];
      const row = Array.isArray(matrix) ? matrix[receivePort] : undefined;
      const db = complexMagnitudeDb(Array.isArray(row) ? row[excitedPort] : undefined);
      return db === null ? [] : [[frequency, db] as [number, number]];
    });
  }, [excitedPort, frequencies, receivePort, sParameters.values]);
  const sPhasePoints = useMemo(() => {
    const matrices = Array.isArray(sParameters.values) ? sParameters.values : [];
    return frequencies.flatMap((frequency, index) => {
      const matrix = matrices[index];
      const row = Array.isArray(matrix) ? matrix[receivePort] : undefined;
      const phase = complexPhaseDeg(Array.isArray(row) ? row[excitedPort] : undefined);
      return phase === null ? [] : [[frequency, phase] as [number, number]];
    });
  }, [excitedPort, frequencies, receivePort, sParameters.values]);
  const pattern = patterns[Math.min(cutIndex, Math.max(0, patterns.length - 1))];
  const displayPattern = useMemo(() => {
    if (!interpolated || !pattern) return record(pattern);
    try { return interpolateEMergePattern(pattern as EMergeAngularPattern, 5) as UnknownRecord; }
    catch { return record(pattern); }
  }, [interpolated, pattern]);
  const surface = useMemo(() => patternSurface(displayPattern), [displayPattern]);
  if (!cuts.length && !frequencies.length) return null;
  const status = String(payload.model_status ?? "unavailable");
  const summary = record(payload.summary);
  const provenance = record(payload.provenance);
  const geometryStatus = typeof summary.geometry_status === "string" ? summary.geometry_status : "Unavailable";
  const issues = Array.isArray(payload.issues) ? payload.issues.map(record) : [];
  return <div className="extension-output emerge-result-output">
    <label>EMERGE RESULT</label>
    <small>Model status: {status}. Curves and the 3D surface use solved EMerge samples. The 3D radius is relative field amplitude.</small>
    {networkReview.ports.length > 0 && <section><div className="extension-actions"><button className="secondary-btn" onClick={() => exportNetwork("csv")}>Export complex CSV</button><button className="secondary-btn" onClick={() => exportNetwork("touchstone")}>Export Touchstone</button></div><label>Probe solved network sample<select aria-label="Probe solved network frequency" value={Math.min(networkSample, frequencies.length - 1)} onChange={event => setNetworkSample(Number(event.target.value))}>{frequencies.map((frequency, index) => <option key={frequency} value={index}>{frequency} Hz</option>)}</select></label><DataTable label="EMerge network samples"><thead><tr><th>Term</th><th>Real</th><th>Imaginary</th><th>Magnitude</th><th>Phase (deg)</th></tr></thead><tbody>{ports.flatMap((receive, row) => ports.map((excited, column) => { const pair = (sParameters.values as number[][][][])[Math.min(networkSample, frequencies.length - 1)][row][column]; return <tr key={`${row}-${column}`}><td>{receive} ← {excited}</td><td>{pair[0].toPrecision(6)}</td><td>{pair[1].toPrecision(6)}</td><td>{Math.hypot(...pair).toPrecision(6)}</td><td>{(Math.atan2(pair[1], pair[0]) * 180 / Math.PI).toPrecision(6)}</td></tr>; }))}</tbody></DataTable>{exportError && <p role="alert">{exportError}</p>}</section>}
    <section><div className="extension-output-title"><b>Analysis information</b></div><DataTable label="EMerge analysis information"><tbody>
      <tr><th>Solver</th><td>{String(summary.engine ?? "EMerge")} {String(summary.engine_version ?? "")}</td></tr>
      <tr><th>Modeled nets</th><td>{Array.isArray(summary.modeled_nets) ? summary.modeled_nets.join(", ") : "Unavailable"}</td></tr>
      <tr><th>Sweep</th><td>{frequencies.length} solved frequencies · {ports.join(", ") || "no ports"}</td></tr>
      <tr><th>Geometry</th><td>{geometryStatus.replace(/_/g, " ")}</td></tr>
      <tr><th>Geometry preparation</th><td>{String(summary.geometry_backend ?? "emerge")}</td></tr>
      {Array.isArray(summary.copper_layers) && <tr><th>Copper stack</th><td>{summary.copper_layers.map(item => { const layer = record(item); return `${String(layer.name)}: ${String(layer.z_mm)} mm`; }).join(" / ")}</td></tr>}
      {Array.isArray(summary.surrounding_geometry) && summary.surrounding_geometry.length > 0 && <tr><th>Surroundings</th><td>{summary.surrounding_geometry.map((item: unknown) => { const box = record(item); return `${String(box.name ?? "Dielectric box")} (εr ${String(box.epsilon_r ?? "?")})`; }).join(", ")}</td></tr>}
      {number(provenance.air_margin_m) !== null && <tr><th>Air margin</th><td>{Number(provenance.air_margin_m) * 1000} mm</td></tr>}
      {patterns.length > 0 && <tr><th>3D angular grid</th><td>{Array.isArray(pattern.theta_deg) ? pattern.theta_deg.length : 0} theta × {Array.isArray(pattern.phi_deg) ? pattern.phi_deg.length : 0} phi samples per solved frequency</td></tr>}
    </tbody></DataTable>{issues.length > 0 && <ul>{issues.map((issue, index) => <li key={index}>{String(issue.message ?? issue.code ?? "Analysis warning")}</li>)}</ul>}</section>
    <EMergeNearField value={fields.nearfield} />
    {networkReview.ports.length > 0 && <section><b>Sampled matching review</b><DataTable label="EMerge matching review"><thead><tr><th>Port</th><th>Best match (Hz)</th><th>Return loss (dB)</th><th>VSWR</th></tr></thead><tbody>{networkReview.ports.map(port => <tr key={port.port}><td>{port.port}</td><td>{port.bestMatchHz.toPrecision(6)}</td><td>{port.returnLossDb?.toPrecision(5) ?? "unavailable"}</td><td>{port.vswr?.toPrecision(5) ?? "unavailable"}</td></tr>)}</tbody></DataTable><small>Extrema use solved samples only. Export the engineering report for sampled -10 dB spans and transmission extrema. Matching does not establish efficiency or model validation.</small></section>}
    {surface.length > 0 && <section><div className="extension-output-title"><b>3D far-field pattern</b><span>{String(pattern?.frequency_hz ?? "")} Hz</span><label>Surface<select aria-label="Radiation surface sampling" value={interpolated ? "interpolated" : "solved"} onChange={event => setInterpolated(event.target.value === "interpolated")}><option value="interpolated">Interpolated 5° display</option><option value="solved">Solved angular grid</option></select></label></div><PlotlyChart data={surface} layout={EMERGE_PATTERN_LAYOUT} revision={`emerge-pattern-${String(pattern?.frequency_hz)}-${interpolated}`} /><small>Drag to rotate · wheel to zoom. Interpolation is display-only between solved angular samples; probes on the solved grid remain the source data. Radius is relative field amplitude and color is peak-normalized dB.</small></section>}
    {cuts.length > 0 && <section><div className="extension-output-title"><b>Far-field relative amplitude</b><select aria-label="Radiation frequency" value={Math.min(cutIndex, cuts.length - 1)} onChange={event => setCutIndex(Number(event.target.value))}>{cuts.map((cut, index) => <option key={index} value={index}>{String(cut.frequency_hz ?? "frequency")} Hz</option>)}</select></div><SampleLinePlot key={`cut-${cutIndex}`} points={radiationPoints} label="Relative far-field amplitude versus angle" xUnit="degrees" yUnit="dB" note="Angle (degrees) · relative amplitude (dB, peak normalized to 0 dB)" /></section>}
    {frequencies.length > 0 && <section><div className="extension-output-title"><b>S-parameter magnitude</b><select aria-label="Receive port" value={receivePort} onChange={event => setReceivePort(Number(event.target.value))}>{ports.map((port, index) => <option key={port} value={index}>Receive {port}</option>)}</select><select aria-label="Excited port" value={excitedPort} onChange={event => setExcitedPort(Number(event.target.value))}>{ports.map((port, index) => <option key={port} value={index}>Excited {port}</option>)}</select></div><SampleLinePlot key={`s-mag-${receivePort}-${excitedPort}`} points={sParameterPoints} label="S-parameter magnitude versus frequency" xUnit="Hz" yUnit="dB" note={`Frequency (Hz) · magnitude (dB) · reference impedance ${String(sParameters.reference_impedance_ohm ?? "unknown")} ohm`} /></section>}
    {sPhasePoints.length > 0 && <section><div className="extension-output-title"><b>S-parameter phase</b><span>{ports[receivePort]} ← {ports[excitedPort]}</span></div><SampleLinePlot key={`s-phase-${receivePort}-${excitedPort}`} points={sPhasePoints} label="S-parameter phase versus frequency" xUnit="Hz" yUnit="degrees" note="Frequency (Hz) · wrapped phase (degrees)" /></section>}
  </div>;
}
