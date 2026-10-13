// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import PlotlyChart from "./PlotlyChart";
import { MagneticMachineWorkbench, type MagneticMachineStudy } from "./MagneticMachineWorkbench";
import { isDesktopShell, runLocalWorker } from "./workerBridge";
import "./buttonStandard.css";
import "./EmMachineWorkbench.css";

type Request = Record<string, number | string> & { model: string };
type Result = { contract: string; model: string; model_status: string; request_sha256: string; summary: Record<string, number>;
  histories?: Record<string, number[]>; energy?: Record<string, number>; limitations: string[]; actual_time_step_s?: number };
export type EmMachineStudy = { request: Request; result: Result | null; fieldStudy?: MagneticMachineStudy };
const common = { resistance_ohm: 1, inductance_h: .01, coupling_constant: .1, inertia_kg_m2: .001,
  damping_n_m_s_per_rad: .001, shaft_torque_n_m: 0, initial_current_a: 0, initial_speed_rad_s: 0,
  initial_angle_rad: 0, duration_s: 1, time_step_s: .001 };
export function defaultMachineRequest(model = "pm_dc_motor"): Request {
  return model === "electromagnet" ? { model, turns: 200, current_a: 1, resistance_ohm: 2, core_length_m: .1,
    core_area_m2: .0001, core_relative_permeability: 1000, gap_length_m: .001, gap_area_m2: .0001 }
    : model === "pm_dc_generator" ? { model, ...common, shaft_torque_n_m: .2, load_resistance_ohm: 10 }
      : { model, ...common, voltage_v: 12 };
}
const labels: Record<string, string> = {
  resistance_ohm: "Winding resistance (Ω)", inductance_h: "Winding inductance (H)",
  coupling_constant: "Reciprocal K (N·m/A = V·s/rad)", inertia_kg_m2: "Rotor inertia (kg·m²)",
  damping_n_m_s_per_rad: "Viscous damping (N·m·s/rad)", shaft_torque_n_m: "External shaft torque (N·m)",
  initial_current_a: "Initial current into machine (A)", initial_speed_rad_s: "Initial angular speed (rad/s)",
  initial_angle_rad: "Initial angle (rad)", duration_s: "Duration (s)", time_step_s: "Requested time step (s)",
  voltage_v: "Applied voltage (V)", load_resistance_ohm: "External load resistance (Ω)",
  turns: "Winding turns", current_a: "DC winding current (A)", core_length_m: "Core path length (m)",
  core_area_m2: "Core section area (m²)", core_relative_permeability: "Linear relative permeability",
  gap_length_m: "Single air gap (m)", gap_area_m2: "Air-gap area (m²)",
};
const resultLabels: Record<string, string> = {
 time_s: "Time (s)", current_a: "Current into machine (A)", speed_rad_s: "Angular speed (rad/s)",
 angle_rad: "Rotor angle (rad)", torque_n_m: "Electromagnetic torque (N·m)", back_emf_v: "Back EMF (V)",
 terminal_voltage_v: "Terminal voltage (V)", terminal_power_w: "Electrical power into machine (W)", shaft_power_w: "External shaft power (W)",
 reluctance_a_turn_per_wb: "Reluctance (A·turn/Wb)", flux_wb: "Flux (Wb)", flux_linkage_wb_turn: "Flux linkage (Wb·turn)",
 inductance_h: "Inductance (H)", core_flux_density_t: "Core flux density (T)", gap_flux_density_t: "Air-gap flux density (T)",
 gap_closing_force_n: "Gap-closing force (N)", stored_energy_j: "Stored energy (J)", coenergy_j: "Coenergy (J)", copper_loss_w: "Copper loss (W)",
};
function validResult(raw: unknown, model: string): raw is Result {
  if (!raw || typeof raw !== "object") return false;
  const r = raw as Result;
  if (r.contract !== "spike/em-machine-result/v1" || r.model !== model || r.model_status !== "experimental"
    || !/^[a-f0-9]{64}$/.test(r.request_sha256) || !r.summary || !Object.values(r.summary).every(Number.isFinite)
    || !Array.isArray(r.limitations) || !r.limitations.every(v => typeof v === "string")) return false;
  if (model === "electromagnet") return Number.isFinite(r.summary.gap_closing_force_n);
  const h = r.histories, t = h?.time_s;
  return Boolean(t && t.length >= 2 && t.length <= 20001 && t.every(Number.isFinite)
    && t.every((v, i) => i === 0 || v > t[i - 1]) && r.energy && Object.values(r.energy).every(Number.isFinite)
    && ["current_a", "speed_rad_s", "torque_n_m", "terminal_power_w", "shaft_power_w"].every(k =>
      h?.[k]?.length === t.length && h[k].every(Number.isFinite)));
}
function exportStudy(study: EmMachineStudy) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(study, null, 2)], { type: "application/json" }));
  const link = document.createElement("a"); link.href = url; link.download = study.request.model + "-study.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function EmMachineWorkbench({ study, onStudy, busy }: {
  study?: EmMachineStudy; onStudy: (value: EmMachineStudy) => void; busy: boolean;
}) {
  const value = study ?? { request: defaultMachineRequest(), result: null };
  const [working, setWorking] = useState(false), [error, setError] = useState("");
  const current = useRef(value), alive = useRef(true);
  current.current = value;
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const request = value.request, result = validResult(value.result, request.model) ? value.result : null;
  const blocked = busy || working;
  const patch = (key: string, n: number) => { setError(""); onStudy({ ...value, request: { ...request, [key]: n }, result: null }); };
  const run = async () => {
    setWorking(true); setError(""); const key = JSON.stringify(request);
    try {
      const response = await runLocalWorker({ method: "run_em_machine", params: { request } });
      if (!alive.current || JSON.stringify(current.current.request) !== key) return;
      if (!response.ok) throw new Error(response.error ?? "Machine solve failed.");
      if (!validResult(response.result, request.model)) throw new Error("Worker returned an incompatible machine result.");
      onStudy({ ...current.current, request, result: response.result });
    } catch (cause) { if (alive.current) setError(String(cause instanceof Error ? cause.message : cause)); }
    finally { if (alive.current) setWorking(false); }
  };
  const h = result?.histories;
  return <section className="em-machine" aria-label="Machines and electromagnets">
    <h3>Machines and electromagnets</h3>
    <MagneticMachineWorkbench study={value.fieldStudy} busy={blocked}
      onStudy={fieldStudy => onStudy({ ...current.current, fieldStudy })} />
    <details><summary>Parameter reference models</summary>
    <p>Experimental reduced models. Run reciprocal shaft/electrical dynamics or a single-gap magnetic circuit. These models do not mesh imported CAD or solve spatial fields.</p>
    <fieldset disabled={blocked}><legend>Model and SI parameters</legend>
      <label>Model<select value={request.model} onChange={e => { setError(""); onStudy({ ...value, request: defaultMachineRequest(e.target.value), result: null }); }}>
        <option value="pm_dc_motor">Permanent-magnet DC motor</option><option value="pm_dc_generator">PM DC generator / resistive load</option><option value="electromagnet">Linear single-gap electromagnet</option>
      </select></label>
      <div className="em-machine-fields">{Object.entries(request).filter(([key]) => key !== "model" && key !== "provenance").map(([key, number]) =>
        <label key={key}>{labels[key] ?? key}<input type="number" step="any" value={Number.isFinite(number) ? number : ""} onChange={e => patch(key, e.target.value === "" ? NaN : Number(e.target.value))} /></label>)}</div>
    </fieldset>
    <p>Positive shaft torque drives the rotor. Current enters the machine; negative terminal power indicates generation. K links torque and back EMF in reciprocal SI units. Generator mode connects a passive resistive load. Electromagnet force is in the gap-closing direction at fixed current.</p>
    <div className="em-machine-actions"><button type="button" className="spike-control--primary" disabled={blocked || !isDesktopShell()} onClick={() => void run()}>Run machine model</button>
      <button type="button" disabled={blocked} onClick={() => exportStudy(value)}>Export setup / result JSON</button></div>
    {!isDesktopShell() && <p role="status">Run requires the desktop worker; browser previews support setup and result inspection.</p>}
    {working && <p role="status">Solving in the worker…</p>}{error && <p role="alert">{error} Review the inputs and retry.</p>}
    {!result && <p>No current result. Parameter changes clear the previous result.</p>}
    {result && <><h4>Saved result · experimental</h4><table><tbody>{Object.entries(result.summary).map(([name, n]) =>
      <tr key={name}><th scope="row">{resultLabels[name] ?? name.replace(/_/g, " ")}</th><td>{n.toPrecision(7)}</td></tr>)}</tbody></table>
      {h && <>{[["current_a", "Current (A)"], ["speed_rad_s", "Angular speed (rad/s)"], ["torque_n_m", "Electromagnetic torque (N·m)"]].map(([quantity, unit]) =>
        <PlotlyChart key={quantity} title={unit} revision={result.request_sha256 + quantity}
          data={[{ type: "scatter", mode: "lines", name: unit, x: h.time_s, y: h[quantity], hovertemplate: "%{x:.6g} s<br>%{y:.6g} " + unit + "<extra></extra>" }]}
          layout={{ xaxis: { title: { text: "Time (s)" } }, yaxis: { title: { text: unit } }, margin: { l: 75, r: 20, b: 65, t: 25 } }} />)}
        <PlotlyChart title="Signed power conversion" revision={result.request_sha256 + "power"}
          data={[["terminal_power_w", "Electrical into machine"], ["shaft_power_w", "External shaft into machine"]].map(([key, name]) =>
            ({ type: "scatter", mode: "lines", name, x: h.time_s, y: h[key], hovertemplate: "%{x:.6g} s<br>%{y:.6g} W<extra>" + name + "</extra>" }))}
          layout={{ xaxis: { title: { text: "Time (s)" } }, yaxis: { title: { text: "Power (W)" } }, margin: { l: 75, r: 20, b: 85, t: 25 } }} />
      </>}
      {result.energy && <details open><summary>Energy ledger (J; relative residual dimensionless)</summary><table><tbody>{Object.entries(result.energy).map(([name, n]) =>
        <tr key={name}><th scope="row">{name.replace(/_/g, " ")}</th><td>{n.toPrecision(7)}</td></tr>)}</tbody></table></details>}
      <details open><summary>Validity limits</summary><ul>{result.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul></details>
      <small>Request SHA-256: {result.request_sha256}. Setup and result are retained with the project EM setup.</small>
    </>}
    </details>
  </section>;
}
