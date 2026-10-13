// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import PlotlyChart from "./PlotlyChart";
import { numericExtent, numericMaximum } from "./numericRange";
import { isDesktopShell, runLocalWorker } from "./workerBridge";
import "./buttonStandard.css";
import "./MagneticMachineWorkbench.css";

export type MagneticMachineRequest = {
  contract: "spike/magnetic-machine-study/v1";
  model: "pm_rotor" | "solenoid";
  geometry: Record<string, unknown>;
  mesh_edge_m: number;
  stack_depth_m: number;
  relative_permeability: number;
  remanence_t: number;
  current_density_a_m2: number;
  position: number;
  motion?: {
    duration_s: number;
    time_step_s: number;
    mass_or_inertia: number;
    damping: number;
    external_load: number;
    initial_velocity: number;
  };
  transient?: Record<string, unknown>;
};

type MagneticField = {
  nodes_m: Array<[number, number]>;
  triangles: Array<[number, number, number]>;
  element_b_t: Array<[number, number]>;
  element_h_a_per_m: Array<[number, number]>;
  potential_a_wb_per_m: number[];
};

type CoupledHistoryFrame = {
  time_s: number;
  potential_a_wb_per_m: number[];
  temperature_k: number[];
  element_b_t?: Array<[number, number]>;
  element_joule_loss_w?: number[];
  joule_loss_w?: number;
  max_temperature_k?: number;
};

type MagneticThermalResult = {
  contract: "spike/planar-magnetic-thermal-result/v1";
  model_status: "experimental";
  history: CoupledHistoryFrame[];
  final_thermal_result: { temperature_k: number[]; element_mean_temperature_k?: number[] };
  limitations?: string[];
};

export type MagneticMachineResult = {
  contract: "spike/magnetic-machine-study-result/v1";
  model_status: "experimental";
  model?: MagneticMachineRequest["model"];
  request_sha256?: string;
  production_qualified?: boolean;
  summary_state?: "initial_position" | "final_stationary_transient";
  field_position?: number;
  field_time_s?: number;
  steady_reference_summary?: {
    max_b_t: number;
    magnetic_energy_j: number;
    force_x_n: number;
    force_y_n: number;
    torque_n_m: number;
  };
  stress_contour_m?: Array<[number, number]>;
  final_stress?: { force_x_n: number; force_y_n: number; torque_n_m: number };
  coupled?: MagneticThermalResult;
  field: MagneticField;
  summary: {
    max_b_t: number;
    magnetic_energy_j: number;
    force_x_n: number;
    force_y_n: number;
    torque_n_m: number;
  };
  histories?: {
    time_s: number[];
    position: number[];
    velocity: number[];
    force_n_or_torque_nm: number[];
  };
  limitations?: string[];
};

export type MagneticMachineStudy = { request: MagneticMachineRequest; result: MagneticMachineResult | null };

const defaultMotion = () => ({
  duration_s: 0.01,
  time_step_s: 0.001,
  mass_or_inertia: 0.001,
  damping: 0.001,
  external_load: 0,
  initial_velocity: 0,
});

export function defaultMagneticMachineRequest(model: MagneticMachineRequest["model"] = "pm_rotor"): MagneticMachineRequest {
  return {
    contract: "spike/magnetic-machine-study/v1",
    model,
    geometry: {},
    mesh_edge_m: 0.002,
    stack_depth_m: 0.02,
    relative_permeability: 1000,
    remanence_t: model === "pm_rotor" ? 1 : 0,
    current_density_a_m2: 1e6,
    position: 0,
  };
}

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const vector2 = (value: unknown): value is [number, number] => Array.isArray(value) && value.length === 2 && value.every(finite);
const triangle = (value: unknown): value is [number, number, number] => Array.isArray(value) && value.length === 3
  && value.every(item => Number.isInteger(item) && item >= 0);

function parseRequest(text: string): MagneticMachineRequest {
  const raw: unknown = JSON.parse(text);
  if (!raw || typeof raw !== "object") throw new Error("The request must be a JSON object.");
  const request = raw as MagneticMachineRequest;
  if (request.contract !== "spike/magnetic-machine-study/v1") throw new Error("Request contract must be spike/magnetic-machine-study/v1.");
  if (request.model !== "pm_rotor" && request.model !== "solenoid") throw new Error("Model must be pm_rotor or solenoid.");
  if (!request.geometry || typeof request.geometry !== "object" || Array.isArray(request.geometry)) throw new Error("geometry must be a JSON object.");
  for (const key of ["mesh_edge_m", "stack_depth_m", "relative_permeability", "remanence_t", "current_density_a_m2", "position"] as const) {
    if (!finite(request[key])) throw new Error(`${key} must be a finite number.`);
  }
  if (request.mesh_edge_m <= 0 || request.stack_depth_m <= 0 || request.relative_permeability <= 0) throw new Error("Mesh edge, stack depth, and relative permeability must be positive.");
  if (request.motion) {
    for (const key of ["duration_s", "time_step_s", "mass_or_inertia", "damping", "external_load", "initial_velocity"] as const) {
      if (!finite(request.motion[key])) throw new Error(`motion.${key} must be a finite number.`);
    }
    if (request.motion.duration_s <= 0 || request.motion.time_step_s <= 0 || request.motion.mass_or_inertia <= 0 || request.motion.damping < 0) {
      throw new Error("Motion duration, time step, and mass or inertia must be positive; damping cannot be negative.");
    }
  }
  if (request.transient != null && (!request.transient || typeof request.transient !== "object" || Array.isArray(request.transient))) {
    throw new Error("transient must be a JSON object.");
  }
  if (request.motion && request.transient) throw new Error("Motion and transient magnetic-thermal solving cannot be enabled together.");
  return request;
}

function validCoupled(raw: unknown, nodeCount: number, elementCount: number): raw is MagneticThermalResult {
  if (!raw || typeof raw !== "object") return false;
  const coupled = raw as MagneticThermalResult;
  if (coupled.contract !== "spike/planar-magnetic-thermal-result/v1" || coupled.model_status !== "experimental"
    || !Array.isArray(coupled.history) || coupled.history.length < 1 || coupled.history.length > 1001
    || !coupled.final_thermal_result || !Array.isArray(coupled.final_thermal_result.temperature_k)
    || coupled.final_thermal_result.temperature_k.length !== nodeCount
    || !coupled.final_thermal_result.temperature_k.every(finite)) return false;
  return coupled.history.every((frame, index) => finite(frame.time_s) && (index === 0 || frame.time_s > coupled.history[index - 1].time_s)
    && Array.isArray(frame.potential_a_wb_per_m) && frame.potential_a_wb_per_m.length === nodeCount && frame.potential_a_wb_per_m.every(finite)
    && Array.isArray(frame.temperature_k) && frame.temperature_k.length === nodeCount && frame.temperature_k.every(finite)
    && (frame.element_b_t == null || (frame.element_b_t.length === elementCount && frame.element_b_t.every(vector2)))
    && (frame.element_joule_loss_w == null || (frame.element_joule_loss_w.length === elementCount && frame.element_joule_loss_w.every(finite)))
    && (frame.joule_loss_w == null || finite(frame.joule_loss_w))
    && (frame.max_temperature_k == null || finite(frame.max_temperature_k)));
}

export function validMagneticMachineResult(raw: unknown, model: MagneticMachineRequest["model"]): raw is MagneticMachineResult {
  if (!raw || typeof raw !== "object") return false;
  const result = raw as MagneticMachineResult;
  if (result.contract !== "spike/magnetic-machine-study-result/v1" || result.model_status !== "experimental"
    || (result.model != null && result.model !== model) || !result.field || !result.summary) return false;
  const field = result.field;
  if (!Array.isArray(field.nodes_m) || field.nodes_m.length < 3 || !field.nodes_m.every(vector2) || !Array.isArray(field.triangles)
    || field.triangles.length < 1
    || !field.triangles.every(triangle) || !Array.isArray(field.element_b_t) || !field.element_b_t.every(vector2)
    || !Array.isArray(field.element_h_a_per_m) || !field.element_h_a_per_m.every(vector2)
    || !Array.isArray(field.potential_a_wb_per_m) || !field.potential_a_wb_per_m.every(finite)
    || field.element_b_t.length !== field.triangles.length || field.element_h_a_per_m.length !== field.triangles.length
    || field.potential_a_wb_per_m.length !== field.nodes_m.length
    || field.triangles.some(face => face.some(index => index >= field.nodes_m.length))) return false;
  if (result.stress_contour_m != null && (!Array.isArray(result.stress_contour_m) || result.stress_contour_m.length < 4
    || !result.stress_contour_m.every(vector2))) return false;
  if (result.final_stress != null && (![result.final_stress.force_x_n, result.final_stress.force_y_n, result.final_stress.torque_n_m].every(finite))) return false;
  if (result.field_time_s != null && !finite(result.field_time_s)) return false;
  if (result.summary_state != null && result.summary_state !== "initial_position" && result.summary_state !== "final_stationary_transient") return false;
  if (result.steady_reference_summary != null && ![result.steady_reference_summary.max_b_t, result.steady_reference_summary.magnetic_energy_j,
    result.steady_reference_summary.force_x_n, result.steady_reference_summary.force_y_n, result.steady_reference_summary.torque_n_m].every(finite)) return false;
  if (result.coupled != null && !validCoupled(result.coupled, field.nodes_m.length, field.triangles.length)) return false;
  if (result.summary_state === "final_stationary_transient" && (!result.coupled || !finite(result.field_time_s) || !result.steady_reference_summary)) return false;
  if (![result.summary.max_b_t, result.summary.magnetic_energy_j, result.summary.force_x_n,
    result.summary.force_y_n, result.summary.torque_n_m].every(finite)) return false;
  const histories = result.histories;
  if (!histories) return true;
  const count = histories.time_s?.length;
  return Number.isInteger(count) && count >= 2 && count <= 20001
    && [histories.time_s, histories.position, histories.velocity, histories.force_n_or_torque_nm]
      .every(series => Array.isArray(series) && series.length === count && series.every(finite))
    && histories.time_s.every((time, index) => index === 0 || time > histories.time_s[index - 1]);
}

function magnitude(vector: [number, number]): number { return Math.hypot(vector[0], vector[1]); }

function returnedJouleLoss(frame: CoupledHistoryFrame): number | null {
  if (finite(frame.joule_loss_w)) return frame.joule_loss_w;
  if (!frame.element_joule_loss_w) return null;
  let total = 0;
  for (const watts of frame.element_joule_loss_w) total += watts;
  return Number.isFinite(total) ? total : null;
}

type FieldQuantity = "b" | "h" | "a" | "temperature" | "joule";

export function magneticMachineFieldTraces(result: MagneticMachineResult, quantity: FieldQuantity) {
  const field = result.field;
  const outlinesX: Array<number | null> = [], outlinesY: Array<number | null> = [];
  const centroids = field.triangles.map(face => {
    const points = face.map(index => field.nodes_m[index]);
    [...points, points[0]].forEach(point => { outlinesX.push(point[0]); outlinesY.push(point[1]); });
    outlinesX.push(null); outlinesY.push(null);
    return [points.reduce((sum, point) => sum + point[0], 0) / 3, points.reduce((sum, point) => sum + point[1], 0) / 3] as [number, number];
  });
  const finalFrame = result.coupled?.history[result.coupled.history.length - 1];
  const vectors = quantity === "h" ? field.element_h_a_per_m : quantity === "b" ? field.element_b_t : [];
  const values = quantity === "a" ? field.potential_a_wb_per_m
    : quantity === "temperature" ? result.coupled?.final_thermal_result.temperature_k ?? []
      : quantity === "joule" ? finalFrame?.element_joule_loss_w ?? [] : vectors.map(magnitude);
  const nodal = quantity === "a" || quantity === "temperature";
  const locations = nodal ? field.nodes_m : centroids;
  const labels = quantity === "a" ? "A (Wb/m)" : quantity === "b" ? "|B| (T)" : quantity === "h" ? "|H| (A/m)"
    : quantity === "temperature" ? "Temperature (K)" : "Element Joule loss (W)";
  const traces: Record<string, unknown>[] = [{
    type: "scattergl", mode: "lines", x: outlinesX, y: outlinesY, name: "Mesh triangles",
    line: { color: "rgba(145, 155, 175, 0.35)", width: 1 }, hoverinfo: "skip", showlegend: false,
  }, {
    type: "scattergl", mode: "markers", x: locations.map(point => point[0]), y: locations.map(point => point[1]),
    name: labels, marker: { color: values, colorscale: "Viridis", showscale: true, colorbar: { title: { text: labels } }, size: nodal ? 6 : 8 },
    customdata: values, hovertemplate: `x=%{x:.6g} m<br>y=%{y:.6g} m<br>${labels}=%{customdata:.6g}<extra></extra>`,
  }];
  if ((quantity === "b" || quantity === "h") && vectors.length) {
    const xExtent = numericExtent(field.nodes_m.map(point => point[0]));
    const yExtent = numericExtent(field.nodes_m.map(point => point[1]));
    const span = Math.max(xExtent.maximum - xExtent.minimum, yExtent.maximum - yExtent.minimum, Number.EPSILON);
    const maximum = Math.max(numericMaximum(vectors.map(magnitude)), Number.EPSILON);
    const vectorX: Array<number | null> = [], vectorY: Array<number | null> = [];
    const stride = Math.max(1, Math.ceil(vectors.length / 2000));
    let shown = 0;
    centroids.forEach((point, index) => {
      if (index % stride !== 0) return;
      shown += 1;
      vectorX.push(point[0], point[0] + vectors[index][0] * span * 0.035 / maximum, null);
      vectorY.push(point[1], point[1] + vectors[index][1] * span * 0.035 / maximum, null);
    });
    traces.push({ type: "scattergl", mode: "lines", x: vectorX, y: vectorY,
      name: `${quantity.toUpperCase()} direction (${shown} of ${vectors.length} elements; uniform stride)`,
      line: { color: "rgba(245, 245, 245, 0.78)", width: 1 }, hoverinfo: "skip" });
  }
  if (result.stress_contour_m?.length) {
    traces.push({ type: "scattergl", mode: "lines", x: result.stress_contour_m.map(point => point[0]), y: result.stress_contour_m.map(point => point[1]),
      name: "Returned stress contour", line: { color: "#f0a04b", width: 2 }, hovertemplate: "Stress contour<br>x=%{x:.6g} m<br>y=%{y:.6g} m<extra></extra>" });
    const contourX = numericExtent(result.stress_contour_m.map(point => point[0])), contourY = numericExtent(result.stress_contour_m.map(point => point[1]));
    const center = [(contourX.minimum + contourX.maximum) / 2, (contourY.minimum + contourY.maximum) / 2];
    const displayedStress = result.final_stress ?? result.summary;
    const force = [displayedStress.force_x_n, displayedStress.force_y_n];
    const forceMagnitude = Math.hypot(force[0], force[1]);
    if (forceMagnitude > 0) {
      const xExtent = numericExtent(field.nodes_m.map(point => point[0])), yExtent = numericExtent(field.nodes_m.map(point => point[1]));
      const arrowLength = Math.max(xExtent.maximum - xExtent.minimum, yExtent.maximum - yExtent.minimum) * 0.08;
      traces.push({ type: "scattergl", mode: "lines+markers", x: [center[0], center[0] + force[0] * arrowLength / forceMagnitude],
        y: [center[1], center[1] + force[1] * arrowLength / forceMagnitude], name: `${result.final_stress ? "Final " : "Initial "}force direction (normalized display arrow)`,
        customdata: [[force[0], force[1], forceMagnitude], [force[0], force[1], forceMagnitude]], marker: { size: [3, 8] },
        line: { color: "#ff6d5a", width: 3 }, hovertemplate: "Fx=%{customdata[0]:.6g} N<br>Fy=%{customdata[1]:.6g} N<br>|F|=%{customdata[2]:.6g} N<extra>Normalized direction display</extra>" });
    }
    const torque = displayedStress.torque_n_m;
    if (torque !== 0) {
      const xExtent = numericExtent(field.nodes_m.map(point => point[0])), yExtent = numericExtent(field.nodes_m.map(point => point[1]));
      const radius = Math.max(xExtent.maximum - xExtent.minimum, yExtent.maximum - yExtent.minimum) * 0.06;
      const direction = Math.sign(torque), torqueX: number[] = [], torqueY: number[] = [], torqueData: number[] = [];
      for (let index = 0; index <= 56; index += 1) {
        const angle = direction * index * Math.PI * 1.75 / 56;
        torqueX.push(radius * Math.cos(angle)); torqueY.push(radius * Math.sin(angle)); torqueData.push(torque);
      }
      traces.push({ type: "scattergl", mode: "lines+markers", x: torqueX, y: torqueY,
        name: `${result.final_stress ? "Final " : "Initial "}torque direction (normalized display circle)`, customdata: torqueData,
        marker: { size: torqueData.map((_, index) => index === torqueData.length - 1 ? 8 : 0) }, line: { color: "#c87cff", width: 3 },
        hovertemplate: "Torque=%{customdata:.6g} N·m<extra>Normalized direction display about origin</extra>" });
    }
  }
  return traces;
}

export function MagneticMachineWorkbench({ study, onStudy, busy }: {
  study?: MagneticMachineStudy;
  onStudy: (value: MagneticMachineStudy) => void;
  busy: boolean;
}) {
  const value = study ?? { request: defaultMagneticMachineRequest(), result: null };
  const [requestText, setRequestText] = useState(() => JSON.stringify(value.request, null, 2));
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [quantity, setQuantity] = useState<FieldQuantity>("b");
  const alive = useRef(true);
  const editRevision = useRef(0);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { setRequestText(JSON.stringify(value.request, null, 2)); }, [value.request]);
  const requestDirty = requestText !== JSON.stringify(value.request, null, 2);
  const result = !requestDirty && validMagneticMachineResult(value.result, value.request.model) ? value.result : null;
  const blocked = busy || working;
  let transientAuthored = false;
  let motionAuthored = false;
  try {
    const authored = JSON.parse(requestText) as { transient?: unknown; motion?: unknown };
    transientAuthored = Boolean(authored?.transient);
    motionAuthored = Boolean(authored?.motion);
  } catch { /* incomplete JSON */ }
  const editText = (text: string) => {
    editRevision.current += 1;
    setRequestText(text); setError("");
  };
  const commitText = () => {
    try { const request = parseRequest(requestText); onStudy({ request, result: null }); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  };
  const updateRequest = (patch: Partial<MagneticMachineRequest>) => {
    setError("");
    onStudy({ request: { ...value.request, ...patch }, result: null });
  };
  const updateNumber = (key: "mesh_edge_m" | "stack_depth_m" | "relative_permeability" | "remanence_t" | "current_density_a_m2" | "position", raw: string) => {
    if (raw === "") return;
    const number = Number(raw);
    if (Number.isFinite(number)) updateRequest({ [key]: number });
  };
  const setMotion = (enabled: boolean) => {
    try {
      const request = parseRequest(requestText);
      const next = { ...request, ...(enabled ? { motion: request.motion ?? defaultMotion() } : {}) };
      if (!enabled) delete next.motion;
      onStudy({ request: next, result: null });
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  };
  const run = async () => {
    let request: MagneticMachineRequest;
    try { request = parseRequest(requestText); } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); return; }
    onStudy({ request, result: null });
    setWorking(true); setError(""); const revision = editRevision.current;
    try {
      const response = await runLocalWorker({ method: "run_magnetic_machine", params: { request } });
      if (!alive.current || editRevision.current !== revision) return;
      if (!response.ok) throw new Error(response.error ?? "Magnetic machine study failed.");
      if (!validMagneticMachineResult(response.result, request.model)) throw new Error("Worker returned an incompatible magnetic machine study result.");
      onStudy({ request, result: response.result });
    } catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { if (alive.current) setWorking(false); }
  };
  const traces = useMemo(() => result ? magneticMachineFieldTraces(result, quantity) : [], [result, quantity]);
  const motion = result?.histories;
  const coupled = result?.coupled;
  const lossHistory = coupled?.history.map(frame => ({ time: frame.time_s, watts: returnedJouleLoss(frame) })).filter((row): row is { time: number; watts: number } => row.watts != null) ?? [];
  const rotating = value.request.model === "pm_rotor";
  useEffect(() => {
    if (!coupled && (quantity === "temperature" || quantity === "joule")) setQuantity("b");
  }, [coupled, quantity]);
  return <section className="magnetic-machine" aria-label="Planar magnetic field study">
    <h4>Planar magnetic field study</h4>
    <div className="magnetic-machine-limit" role="note"><strong>Experimental model limits.</strong> This generated planar 2D finite-element study does not import native 3D CAD or establish mesh-converged or hardware accuracy. JSON-authored transient studies support fixed-mesh stationary-conductor eddy loss and sequential thermal conductivity feedback only; moving-conductor eddy effects, hysteresis, temperature-dependent magnetic laws, and 3D end effects remain unsupported.</div>
    <fieldset className="magnetic-machine-setup" disabled={blocked}><legend>Geometry and excitation</legend>
      <div className="magnetic-machine-fields">
        <label>Model<select value={value.request.model} onChange={event => onStudy({ request: defaultMagneticMachineRequest(event.target.value as MagneticMachineRequest["model"]), result: null })}>
          <option value="pm_rotor">Permanent-magnet rotor</option><option value="solenoid">Solenoid</option>
        </select></label>
        <label>Mesh edge (m)<input type="number" min="0" step="any" value={value.request.mesh_edge_m} onChange={event => updateNumber("mesh_edge_m", event.target.value)} /></label>
        <label>Stack depth (m)<input type="number" min="0" step="any" value={value.request.stack_depth_m} onChange={event => updateNumber("stack_depth_m", event.target.value)} /></label>
        <label>Current density (A/m²)<input type="number" step="any" value={value.request.current_density_a_m2} onChange={event => updateNumber("current_density_a_m2", event.target.value)} /></label>
        <label>{value.request.model === "pm_rotor" ? "Rotor angle (rad)" : "Plunger translation (m)"}<input type="number" step="any" value={value.request.position} onChange={event => updateNumber("position", event.target.value)} /></label>
        <label>Relative permeability<input type="number" min="0" step="any" value={value.request.relative_permeability} onChange={event => updateNumber("relative_permeability", event.target.value)} /></label>
        <label>Remanence (T)<input type="number" step="any" value={value.request.remanence_t} onChange={event => updateNumber("remanence_t", event.target.value)} /></label>
      </div>
    </fieldset>
    <details className="magnetic-machine-advanced"><summary>Advanced request JSON</summary>
      <label className="magnetic-machine-json">Study request JSON
        <textarea rows={16} spellCheck={false} value={requestText} disabled={blocked} onChange={event => editText(event.target.value)} onBlur={commitText} aria-describedby="magnetic-machine-json-help" />
      </label>
      <p id="magnetic-machine-json-help">Geometry is passed directly to the selected machine mesh builder. Position is rotor angle in radians for <code>pm_rotor</code> and translation in metres for <code>solenoid</code>. Transient parameters are authored directly in this JSON.</p>
    </details>
    <label className="magnetic-machine-motion" title={transientAuthored ? "Motion and fixed-mesh magnetic-thermal transient solving cannot run together." : undefined}><input type="checkbox" checked={Boolean(value.request.motion)} disabled={blocked || transientAuthored} onChange={event => setMotion(event.target.checked)} /> Integrate one-degree-of-freedom motion</label>
    {transientAuthored && <p role="status">Fixed-mesh transient study authored. Motion is disabled because the backend does not solve moving-conductor eddy effects.</p>}
    {transientAuthored && motionAuthored && <p role="alert">Remove either <code>motion</code> or <code>transient</code>; the backend rejects this unsupported combination.</p>}
    <div className="magnetic-machine-actions">
      <button type="button" className="spike-control--primary" disabled={blocked || !isDesktopShell() || (transientAuthored && motionAuthored)} onClick={() => void run()}>Run planar field study</button>
    </div>
    {!isDesktopShell() && <p role="status">Run requires the desktop worker; browser previews support request editing and retained result inspection.</p>}
    {working && <p role="status">Meshing and solving in the worker…</p>}
    {error && <p role="alert">{error} Review the JSON request and retry.</p>}
    {!result && <p>No current planar field result. Editing a valid request clears the previous result.</p>}
    {result && <>
      <h5>Field result · experimental</h5>
      <div className="magnetic-machine-summary" aria-label="Magnetic field summary">
        <span><strong>Maximum |B|</strong>{result.summary.max_b_t.toPrecision(7)} T</span>
        <span><strong>Magnetic constitutive potential</strong>{result.summary.magnetic_energy_j.toPrecision(7)} J</span>
        <span><strong>Force X</strong>{result.summary.force_x_n.toPrecision(7)} N</span>
        <span><strong>Force Y</strong>{result.summary.force_y_n.toPrecision(7)} N</span>
        <span><strong>Torque</strong>{result.summary.torque_n_m.toPrecision(7)} N·m</span>
      </div>
      <small>Magnetic constitutive potential uses the solver's w(B=0)=0 reference. It may be negative for the ideal permanent-magnet law and is not a total stored-energy claim.</small>
      {result.summary_state === "initial_position" && <p className="magnetic-machine-state-note">Summary force, torque, energy, and maximum flux density are from the initial position. The field plot is from {coupled ? "the final stationary transient state" : "the final motion position"}{finite(result.field_position) ? ` (${result.field_position.toPrecision(7)} ${rotating ? "rad" : "m"})` : ""}.</p>}
      {result.summary_state === "final_stationary_transient" && <p className="magnetic-machine-state-note">Summary values and the displayed magnetic field are from the final stationary transient state{finite(result.field_time_s) ? ` at ${result.field_time_s.toPrecision(7)} s` : ""}. The steady magnetostatic solve is retained separately as reference data.</p>}
      <label className="magnetic-machine-quantity">Displayed returned quantity<select value={quantity} onChange={event => setQuantity(event.target.value as FieldQuantity)}>
        <option value="b">Element B vector and magnitude</option><option value="h">Element H vector and magnitude</option><option value="a">Nodal magnetic vector potential A</option>
        {coupled && <option value="temperature">Final nodal temperature</option>}{coupled?.history.some(frame => frame.element_joule_loss_w) && <option value="joule">Final element Joule loss</option>}
      </select></label>
      <PlotlyChart title="Returned planar finite-element field" revision={`${result.request_sha256 ?? "field"}-${quantity}`}
        data={traces} layout={{ xaxis: { title: { text: "X (m)" } }, yaxis: { title: { text: "Y (m)" }, scaleanchor: "x", scaleratio: 1 }, margin: { l: 75, r: 30, b: 65, t: 30 }, hovermode: "closest" }} />
      {(quantity === "b" || quantity === "h" || quantity === "joule") && <small>Element markers include every returned scalar sample at triangle centroids. Vector direction lines use one shared display scale and a uniformly strided subset capped at 2,000 elements, as labeled in the legend. The force line is a normalized direction indicator whose tooltip reports the returned force in newtons. No spatial interpolation is applied.</small>}
      {(quantity === "a" || quantity === "temperature") && <small>Markers contain returned nodal values at their original mesh coordinates. No spatial interpolation is applied.</small>}
      {motion && <div className="magnetic-machine-history">
        <PlotlyChart title={rotating ? "Rotor motion" : "Solenoid motion"} revision={`${result.request_sha256 ?? "motion"}-state`}
          data={[
            { type: "scatter", mode: "lines", name: rotating ? "Angle" : "Translation", x: motion.time_s, y: motion.position },
            { type: "scatter", mode: "lines", name: rotating ? "Angular velocity" : "Velocity", x: motion.time_s, y: motion.velocity, yaxis: "y2" },
          ]} layout={{ xaxis: { title: { text: "Time (s)" } }, yaxis: { title: { text: rotating ? "Angle (rad)" : "Translation (m)" } },
            yaxis2: { title: { text: rotating ? "Angular velocity (rad/s)" : "Velocity (m/s)" }, overlaying: "y", side: "right" }, margin: { l: 75, r: 75, b: 65, t: 30 } }} />
        <PlotlyChart title={rotating ? "Electromagnetic torque history" : "Electromagnetic force history"} revision={`${result.request_sha256 ?? "motion"}-load`}
          data={[{ type: "scatter", mode: "lines", name: rotating ? "Torque" : "Force", x: motion.time_s, y: motion.force_n_or_torque_nm }]}
          layout={{ xaxis: { title: { text: "Time (s)" } }, yaxis: { title: { text: rotating ? "Torque (N·m)" : "Force (N)" } }, margin: { l: 75, r: 30, b: 65, t: 30 } }} />
      </div>}
      {coupled && <div className="magnetic-machine-coupled">
        <h5>Stationary eddy-current and thermal history</h5>
        <PlotlyChart title="Maximum returned nodal temperature" revision={`${result.request_sha256 ?? "thermal"}-temperature`}
          data={[{ type: "scatter", mode: "lines+markers", name: "Maximum nodal temperature", x: coupled.history.map(frame => frame.time_s), y: coupled.history.map(frame => frame.max_temperature_k ?? numericMaximum(frame.temperature_k)) }]}
          layout={{ xaxis: { title: { text: "Time (s)" } }, yaxis: { title: { text: "Maximum temperature (K)" } }, margin: { l: 75, r: 30, b: 65, t: 30 } }} />
        {lossHistory.length > 0 && <PlotlyChart title="Stationary-conductor Joule loss" revision={`${result.request_sha256 ?? "thermal"}-loss`}
          data={[{ type: "scatter", mode: "lines+markers", name: "Joule loss", x: lossHistory.map(row => row.time), y: lossHistory.map(row => row.watts) }]}
          layout={{ xaxis: { title: { text: "Time (s)" } }, yaxis: { title: { text: "Joule loss (W)" } }, margin: { l: 75, r: 30, b: 65, t: 30 } }} />}
      </div>}
      {result.limitations?.length ? <div className="magnetic-machine-limit"><strong>Solver-reported limitations</strong><ul>{result.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul></div> : null}
      {result.request_sha256 && <small>Request SHA-256: {result.request_sha256}</small>}
    </>}
  </section>;
}
