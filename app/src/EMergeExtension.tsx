// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import { numericExtent } from "./numericRange";
import PlotlyChart from "./PlotlyChart";
import { interpolateEMergePattern, type EMergeAngularPattern } from "./emergePatternInterpolation";
import "./EMergeExtension.css";

export type EMergeSetup = {
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
  python_executable: "",
  radome_enabled: false,
  radome_origin_x_mm: "0", radome_origin_y_mm: "0", radome_gap_mm: "10",
  radome_width_mm: "50", radome_depth_mm: "40", radome_thickness_mm: "1.5", radome_epsilon_r: "2.1",
});

export function emergeParameters(setup: EMergeSetup): Record<string, unknown> {
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
  if (!setup.signal_net.trim() || !setup.return_net.trim()) throw new Error("Signal and return nets are required.");
  if (!setup.signal_pad_id.trim() || !setup.return_pad_id.trim()) throw new Error("Signal and return pad IDs are required.");
  const hasReceiveSignal = Boolean(setup.receive_signal_pad_id.trim());
  const hasReceiveReturn = Boolean(setup.receive_return_pad_id.trim());
  if (hasReceiveSignal !== hasReceiveReturn) throw new Error("Enter both receive port pad IDs, or leave both blank for a one-port solve.");
  const points = rangeNumber(setup.frequency_points, "Frequency points", 2, 64);
  if (!Number.isInteger(points)) throw new Error("Frequency points must be a whole number.");
  const parameters: Record<string, unknown> = {
    signal_net: setup.signal_net.trim(), return_net: setup.return_net.trim(),
    signal_pad_id: setup.signal_pad_id.trim(), return_pad_id: setup.return_pad_id.trim(),
    frequency_start_hz: start, frequency_stop_hz: stop,
    frequency_points: points,
    mesh_resolution_mm: rangeNumber(setup.mesh_resolution_mm, "Mesh resolution", 0.05, 10),
  };
  if (hasReceiveSignal) {
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

export function EMergeSetupForm({ value, onChange, netOptions = [], padOptions = [], boardBounds }: { value: EMergeSetup; onChange: (value: EMergeSetup) => void; netOptions?: string[]; padOptions?: string[]; boardBounds?: { minX: number; minY: number; maxX: number; maxY: number } }) {
  const update = (key: keyof EMergeSetup, next: string) => onChange({ ...value, [key]: next });
  const toggleRadome = (enabled: boolean) => onChange({ ...value, radome_enabled: enabled,
    ...(enabled && boardBounds ? { radome_origin_x_mm: String(boardBounds.minX - 5), radome_origin_y_mm: String(boardBounds.minY - 5),
      radome_width_mm: String(boardBounds.maxX - boardBounds.minX + 10), radome_depth_mm: String(boardBounds.maxY - boardBounds.minY + 10) } : {}) });
  return <div className="wizard-section">
    <label>EMERGE PORT SWEEP SETUP</label>
    <small>Choose vertical signal/return pad pairs on opposite F.Cu and B.Cu layers with aligned centres. The initial adapter supports reviewed 2-layer planar surface-PEC boards only.</small>
    <div className="sweep-grid">
      <label>Signal net<input list="emerge-net-options" value={value.signal_net} onChange={event => update("signal_net", event.target.value)} /></label>
      <label>Return net<input list="emerge-net-options" value={value.return_net} onChange={event => update("return_net", event.target.value)} /></label>
      <label>Signal pad ID<input list="emerge-pad-options" value={value.signal_pad_id} onChange={event => update("signal_pad_id", event.target.value)} /></label>
      <label>Return pad ID<input list="emerge-pad-options" value={value.return_pad_id} onChange={event => update("return_pad_id", event.target.value)} /></label>
      <label>Receive signal pad ID (optional)<input list="emerge-pad-options" value={value.receive_signal_pad_id} onChange={event => update("receive_signal_pad_id", event.target.value)} /></label>
      <label>Receive return pad ID (optional)<input list="emerge-pad-options" value={value.receive_return_pad_id} onChange={event => update("receive_return_pad_id", event.target.value)} /></label>
      <label data-guide="emerge-frequency">Start frequency (Hz)<input type="number" min="100000000" max="100000000000" value={value.frequency_start_hz} onChange={event => update("frequency_start_hz", event.target.value)} /></label>
      <label>Stop frequency (Hz)<input type="number" min="100000000" max="100000000000" value={value.frequency_stop_hz} onChange={event => update("frequency_stop_hz", event.target.value)} /></label>
      <label>Frequency points<input type="number" min="2" max="64" step="1" value={value.frequency_points} onChange={event => update("frequency_points", event.target.value)} /></label>
      <label>Mesh resolution (mm)<input type="number" min="0.05" max="10" step="0.01" value={value.mesh_resolution_mm} onChange={event => update("mesh_resolution_mm", event.target.value)} /></label>
      <label>EMerge Python executable (optional)<input value={value.python_executable} placeholder="Use configured runtime" onChange={event => update("python_executable", event.target.value)} /></label>
    </div>
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

function plotPath(points: Array<[number, number]>, width = 420, height = 180) {
  const retained = points.length <= 2000 ? points : Array.from({ length: 2000 }, (_, index) => points[Math.round(index * (points.length - 1) / 1999)]);
  if (retained.length < 2) return "";
  const xs = retained.map(point => point[0]); const ys = retained.map(point => point[1]);
  const xRange = numericExtent(xs); const yRange = numericExtent(ys);
  const minX = xRange.minimum; const maxX = xRange.maximum;
  const minY = yRange.minimum; const maxY = yRange.maximum;
  const rangeX = maxX - minX || 1; const rangeY = maxY - minY || 1;
  return retained.map(([x, y], index) => `${index ? "L" : "M"}${((x - minX) / rangeX * width).toFixed(2)},${(height - (y - minY) / rangeY * height).toFixed(2)}`).join(" ");
}

function SampleLinePlot({ points, label, xUnit, yUnit, note }: {
  points: Array<[number, number]>; label: string; xUnit: string; yUnit: string; note: string;
}) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [pinnedIndex, setPinnedIndex] = useState<number | null>(null);
  const findNearest = (clientX: number, bounds: DOMRect) => {
    if (!points.length || bounds.width <= 0) return null;
    const extent = numericExtent(points.map(point => point[0]));
    const target = extent.minimum + Math.max(0, Math.min(1, (clientX - bounds.left) / bounds.width)) * (extent.maximum - extent.minimum);
    return points.reduce((best, point, index) => Math.abs(point[0] - target) < Math.abs(points[best][0] - target) ? index : best, 0);
  };
  const sampleText = (index: number | null) => index !== null && points[index]
    ? `${points[index][0].toPrecision(7)} ${xUnit} · ${points[index][1].toPrecision(6)} ${yUnit}` : "";
  return <>
    <svg viewBox="0 0 420 180" role="button" tabIndex={0} aria-label={`${label}. Move pointer to inspect samples; click or press Enter to pin.`}
      onMouseMove={event => setHoverIndex(findNearest(event.clientX, event.currentTarget.getBoundingClientRect()))}
      onMouseLeave={() => setHoverIndex(null)}
      onClick={event => setPinnedIndex(findNearest(event.clientX, event.currentTarget.getBoundingClientRect()))}
      onKeyDown={event => { if (event.key === "Enter" && points.length) setPinnedIndex(hoverIndex ?? 0); }}>
      <path d={plotPath(points)} fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
    <small>{note}</small>
    {(hoverIndex !== null || pinnedIndex !== null) && <small role="status">{hoverIndex !== null && `Sample: ${sampleText(hoverIndex)}`}{hoverIndex !== null && pinnedIndex !== null ? " · " : ""}{pinnedIndex !== null && `Pinned: ${sampleText(pinnedIndex)}`}</small>}
  </>;
}

/** Displays only the angular and network arrays explicitly returned by EMerge. */
export function EMergeResultPlot({ result, frequencyIndex, onFrequencyIndexChange }: { result: Record<string, unknown> | null; frequencyIndex?: number; onFrequencyIndexChange?: (index: number) => void }) {
  const analysis = record(record(result).data).analysis_result;
  const payload = record(analysis);
  const fields = record(payload.fields); const networks = record(payload.networks);
  const radiation = record(fields.radiation); const sParameters = record(networks.s_parameters);
  const cuts = Array.isArray(radiation.cuts) ? radiation.cuts.map(record) : [];
  const patterns = Array.isArray(radiation.patterns_3d) ? radiation.patterns_3d as UnknownRecord[] : [];
  const frequencies = Array.isArray(sParameters.frequencies_hz) ? sParameters.frequencies_hz.map(number).filter((item): item is number => item !== null) : [];
  const ports = Array.isArray(sParameters.ports) ? sParameters.ports.filter((item): item is string => typeof item === "string") : [];
  const [localCutIndex, setLocalCutIndex] = useState(0); const [receivePort, setReceivePort] = useState(0); const [excitedPort, setExcitedPort] = useState(0);
  const [interpolated, setInterpolated] = useState(true);
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
    <section><div className="extension-output-title"><b>Analysis information</b></div><table><tbody>
      <tr><th>Solver</th><td>{String(summary.engine ?? "EMerge")} {String(summary.engine_version ?? "")}</td></tr>
      <tr><th>Modeled nets</th><td>{Array.isArray(summary.modeled_nets) ? summary.modeled_nets.join(", ") : "Unavailable"}</td></tr>
      <tr><th>Sweep</th><td>{frequencies.length} solved frequencies · {ports.join(", ") || "no ports"}</td></tr>
      <tr><th>Geometry</th><td>{geometryStatus.replace(/_/g, " ")}</td></tr>
      {Array.isArray(summary.surrounding_geometry) && summary.surrounding_geometry.length > 0 && <tr><th>Surroundings</th><td>{summary.surrounding_geometry.map((item: unknown) => { const box = record(item); return `${String(box.name ?? "Dielectric box")} (εr ${String(box.epsilon_r ?? "?")})`; }).join(", ")}</td></tr>}
      {number(provenance.air_margin_m) !== null && <tr><th>Air margin</th><td>{Number(provenance.air_margin_m) * 1000} mm</td></tr>}
      {patterns.length > 0 && <tr><th>3D angular grid</th><td>{Array.isArray(pattern.theta_deg) ? pattern.theta_deg.length : 0} theta × {Array.isArray(pattern.phi_deg) ? pattern.phi_deg.length : 0} phi samples per solved frequency</td></tr>}
    </tbody></table>{issues.length > 0 && <ul>{issues.map((issue, index) => <li key={index}>{String(issue.message ?? issue.code ?? "Analysis warning")}</li>)}</ul>}</section>
    {surface.length > 0 && <section><div className="extension-output-title"><b>3D far-field pattern</b><span>{String(pattern?.frequency_hz ?? "")} Hz</span><label>Surface<select aria-label="Radiation surface sampling" value={interpolated ? "interpolated" : "solved"} onChange={event => setInterpolated(event.target.value === "interpolated")}><option value="interpolated">Interpolated 5° display</option><option value="solved">Solved angular grid</option></select></label></div><PlotlyChart data={surface} layout={EMERGE_PATTERN_LAYOUT} revision={`emerge-pattern-${String(pattern?.frequency_hz)}-${interpolated}`} /><small>Drag to rotate · wheel to zoom. Interpolation is display-only between solved angular samples; probes on the solved grid remain the source data. Radius is relative field amplitude and color is peak-normalized dB.</small></section>}
    {cuts.length > 0 && <section><div className="extension-output-title"><b>Far-field relative amplitude</b><select aria-label="Radiation frequency" value={Math.min(cutIndex, cuts.length - 1)} onChange={event => setCutIndex(Number(event.target.value))}>{cuts.map((cut, index) => <option key={index} value={index}>{String(cut.frequency_hz ?? "frequency")} Hz</option>)}</select></div><SampleLinePlot key={`cut-${cutIndex}`} points={radiationPoints} label="Relative far-field amplitude versus angle" xUnit="degrees" yUnit="dB" note="Angle (degrees) · relative amplitude (dB, peak normalized to 0 dB)" /></section>}
    {frequencies.length > 0 && <section><div className="extension-output-title"><b>S-parameter magnitude</b><select aria-label="Receive port" value={receivePort} onChange={event => setReceivePort(Number(event.target.value))}>{ports.map((port, index) => <option key={port} value={index}>Receive {port}</option>)}</select><select aria-label="Excited port" value={excitedPort} onChange={event => setExcitedPort(Number(event.target.value))}>{ports.map((port, index) => <option key={port} value={index}>Excited {port}</option>)}</select></div><SampleLinePlot key={`s-mag-${receivePort}-${excitedPort}`} points={sParameterPoints} label="S-parameter magnitude versus frequency" xUnit="Hz" yUnit="dB" note={`Frequency (Hz) · magnitude (dB) · reference impedance ${String(sParameters.reference_impedance_ohm ?? "unknown")} ohm`} /></section>}
    {sPhasePoints.length > 0 && <section><div className="extension-output-title"><b>S-parameter phase</b><span>{ports[receivePort]} ← {ports[excitedPort]}</span></div><SampleLinePlot key={`s-phase-${receivePort}-${excitedPort}`} points={sPhasePoints} label="S-parameter phase versus frequency" xUnit="Hz" yUnit="degrees" note="Frequency (Hz) · wrapped phase (degrees)" /></section>}
  </div>;
}
