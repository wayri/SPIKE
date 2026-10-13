// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { numericExtent, numericMaximum } from "./numericRange";
import { runLocalWorker } from "./workerBridge";
import "./InternalAirflowPanel.css";

export type InternalAirflowRequest = {
  contract: "spike/internal-channel-airflow-request/v1";
  geometry: { length_m: number; gap_m: number; span_m: number };
  fluid: {
    density_kg_m3: number;
    specific_heat_j_kgk: number;
    thermal_conductivity_w_mk: number;
    dynamic_viscosity_pa_s: number;
  };
  operating: {
    mean_velocity_m_s: number;
    inlet_temperature_k: number;
    lower_wall_heat_flux_w_m2: number;
    upper_wall_heat_flux_w_m2: number;
  };
  mesh: { axial_cells: number; transverse_cells: number };
};

export type InternalAirflowResult = {
  request_snapshot: InternalAirflowRequest;
  contract: "spike/internal-channel-airflow-result/v1";
  status: "experimental";
  model_status: "experimental";
  production_qualified: false;
  flow_regime: "laminar_prescribed";
  turbulence_model: "none";
  request_digest: string;
  result_digest: string;
  units: "SI";
  field_location: "downstream_axial_station_by_transverse_cell";
  inlet_temperature_k: number;
  x_m: number[];
  y_m: number[];
  velocity_u_m_s: number[];
  temperature_k: number[][];
  bulk_temperature_k: number[];
  wall_temperature_k: { lower: number[]; upper: number[] };
  reynolds_hydraulic: number;
  peclet_length: number;
  mass_flow_kg_s: number;
  pressure_drop_pa: number;
  heat_balance: {
    wall_input_w: number;
    coolant_enthalpy_gain_w: number;
    imbalance_w: number;
    relative_imbalance: number;
    acceptance_tolerance_w: number;
  };
  diagnostics: {
    maximum_equation_residual_w: number;
    maximum_mass_imbalance_kg_s: number;
    omitted_viscous_heating_rise_k: number;
    mesh_convergence_verified: false;
    axial_scheme: "first_order_upwind";
    transverse_scheme: "centered_finite_volume";
  };
  resources: { axial_cells: number; transverse_cells: number; field_values: number; maximum_field_values: number };
  limitations: string[];
};

type Draft = {
  length_m: string;
  gap_m: string;
  width_m: string;
  mean_velocity_m_s: string;
  inlet_temperature_k: string;
  density_kg_m3: string;
  viscosity_pa_s: string;
  conductivity_w_mk: string;
  specific_heat_j_kgk: string;
  lower_wall_heat_flux_w_m2: string;
  upper_wall_heat_flux_w_m2: string;
  axial_cells: string;
  transverse_cells: string;
};

export type InternalAirflowPanelProps = {
  workerAvailable: boolean;
  initialRequest?: InternalAirflowRequest;
  initialResult?: unknown;
  onResult?: (request: InternalAirflowRequest, result: InternalAirflowResult) => void;
  onStatus?: (message: string) => void;
};

const DEFAULT_DRAFT: Draft = {
  length_m: "0.12",
  gap_m: "0.008",
  width_m: "0.04",
  mean_velocity_m_s: "0.35",
  inlet_temperature_k: "298.15",
  density_kg_m3: "1.184",
  viscosity_pa_s: "1.85e-5",
  conductivity_w_mk: "0.0262",
  specific_heat_j_kgk: "1007",
  lower_wall_heat_flux_w_m2: "500",
  upper_wall_heat_flux_w_m2: "0",
  axial_cells: "64",
  transverse_cells: "17",
};
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const positive = (value: unknown): value is number => finite(value) && value > 0;
const finiteArray = (value: unknown, length?: number) => Array.isArray(value)
  && (length === undefined || value.length === length) && value.every(finite);
const increasing = (values: number[]) => values.every((value, index) => index === 0 || value > values[index - 1]);
const draftValue = (value: number | undefined, fallback: string) => finite(value) ? String(value) : fallback;

function draftFromRequest(request?: InternalAirflowRequest): Draft {
  if (!request) return DEFAULT_DRAFT;
  return {
    length_m: draftValue(request.geometry?.length_m, DEFAULT_DRAFT.length_m),
    gap_m: draftValue(request.geometry?.gap_m, DEFAULT_DRAFT.gap_m),
    width_m: draftValue(request.geometry?.span_m, DEFAULT_DRAFT.width_m),
    mean_velocity_m_s: draftValue(request.operating?.mean_velocity_m_s, DEFAULT_DRAFT.mean_velocity_m_s),
    inlet_temperature_k: draftValue(request.operating?.inlet_temperature_k, DEFAULT_DRAFT.inlet_temperature_k),
    density_kg_m3: draftValue(request.fluid?.density_kg_m3, DEFAULT_DRAFT.density_kg_m3),
    viscosity_pa_s: draftValue(request.fluid?.dynamic_viscosity_pa_s, DEFAULT_DRAFT.viscosity_pa_s),
    conductivity_w_mk: draftValue(request.fluid?.thermal_conductivity_w_mk, DEFAULT_DRAFT.conductivity_w_mk),
    specific_heat_j_kgk: draftValue(request.fluid?.specific_heat_j_kgk, DEFAULT_DRAFT.specific_heat_j_kgk),
    lower_wall_heat_flux_w_m2: draftValue(request.operating?.lower_wall_heat_flux_w_m2, DEFAULT_DRAFT.lower_wall_heat_flux_w_m2),
    upper_wall_heat_flux_w_m2: draftValue(request.operating?.upper_wall_heat_flux_w_m2, DEFAULT_DRAFT.upper_wall_heat_flux_w_m2),
    axial_cells: draftValue(request.mesh?.axial_cells, DEFAULT_DRAFT.axial_cells),
    transverse_cells: draftValue(request.mesh?.transverse_cells, DEFAULT_DRAFT.transverse_cells),
  };
}

export function buildInternalAirflowRequest(draft: Draft): InternalAirflowRequest {
  const values = Object.fromEntries(Object.entries(draft).map(([key, value]) => [key, Number(value)])) as Record<keyof Draft, number>;
  const signed = new Set<keyof Draft>(["lower_wall_heat_flux_w_m2", "upper_wall_heat_flux_w_m2"]);
  for (const key of Object.keys(values) as Array<keyof Draft>) {
    if (!finite(values[key])) throw new Error(`Enter a finite value for ${key}.`);
    if (!signed.has(key) && values[key] <= 0) throw new Error(`${key} must be greater than zero.`);
  }
  if (!Number.isInteger(values.axial_cells) || values.axial_cells < 2 || values.axial_cells > 1000
    || !Number.isInteger(values.transverse_cells) || values.transverse_cells < 3 || values.transverse_cells > 200
    || values.axial_cells * values.transverse_cells > 100_000) throw new Error("Mesh budget: axial cells 2..1000, transverse cells 3..200, and at most 100,000 field values.");
  return {
    contract: "spike/internal-channel-airflow-request/v1",
    geometry: { length_m: values.length_m, gap_m: values.gap_m, span_m: values.width_m },
    fluid: {
      density_kg_m3: values.density_kg_m3,
      specific_heat_j_kgk: values.specific_heat_j_kgk,
      thermal_conductivity_w_mk: values.conductivity_w_mk,
      dynamic_viscosity_pa_s: values.viscosity_pa_s,
    },
    operating: {
      mean_velocity_m_s: values.mean_velocity_m_s,
      inlet_temperature_k: values.inlet_temperature_k,
      lower_wall_heat_flux_w_m2: values.lower_wall_heat_flux_w_m2,
      upper_wall_heat_flux_w_m2: values.upper_wall_heat_flux_w_m2,
    },
    mesh: { axial_cells: values.axial_cells, transverse_cells: values.transverse_cells },
  };
}

export function validInternalAirflowResult(raw: unknown, request?: InternalAirflowRequest): raw is InternalAirflowResult {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return false;
  const result = raw as InternalAirflowResult;
  if (result.contract !== "spike/internal-channel-airflow-result/v1" || result.status !== "experimental"
    || result.model_status !== "experimental" || result.production_qualified !== false
    || result.flow_regime !== "laminar_prescribed" || result.turbulence_model !== "none"
    || result.units !== "SI" || result.field_location !== "downstream_axial_station_by_transverse_cell"
    || !/^[0-9a-f]{64}$/.test(result.request_digest) || !/^[0-9a-f]{64}$/.test(result.result_digest)
    || !positive(result.inlet_temperature_k)) return false;
  const nx = Array.isArray(result.x_m) ? result.x_m.length : 0;
  const ny = Array.isArray(result.y_m) ? result.y_m.length : 0;
  if (nx < 2 || nx > 1000 || ny < 3 || ny > 200 || nx * ny > 100_000
    || !finiteArray(result.x_m, nx) || !finiteArray(result.y_m, ny)
    || !increasing(result.x_m) || !increasing(result.y_m) || result.x_m[0] <= 0 || result.y_m[0] <= 0
    || !finiteArray(result.velocity_u_m_s, ny) || result.velocity_u_m_s.some(value => value < 0)
    || !Array.isArray(result.temperature_k) || result.temperature_k.length !== nx
    || !result.temperature_k.every(row => finiteArray(row, ny) && row.every(positive))
    || !finiteArray(result.bulk_temperature_k, nx) || !result.bulk_temperature_k.every(positive)
    || !result.wall_temperature_k || !finiteArray(result.wall_temperature_k.lower, nx)
    || !finiteArray(result.wall_temperature_k.upper, nx)
    || !result.wall_temperature_k.lower.every(positive) || !result.wall_temperature_k.upper.every(positive)) return false;
  if (request) {
    const snapshot = result.request_snapshot;
    if (!snapshot || snapshot.contract !== request.contract) return false;
    const identity = (input: InternalAirflowRequest) => JSON.stringify([
      input.geometry?.length_m, input.geometry?.gap_m, input.geometry?.span_m,
      input.fluid?.density_kg_m3, input.fluid?.specific_heat_j_kgk,
      input.fluid?.thermal_conductivity_w_mk, input.fluid?.dynamic_viscosity_pa_s,
      input.operating?.mean_velocity_m_s, input.operating?.inlet_temperature_k,
      input.operating?.lower_wall_heat_flux_w_m2, input.operating?.upper_wall_heat_flux_w_m2,
      input.mesh?.axial_cells, input.mesh?.transverse_cells,
    ]);
    if (identity(snapshot) !== identity(request)) return false;
    const xTolerance = Math.max(1e-12, request.geometry.length_m * 1e-9);
    if (nx !== request.mesh.axial_cells || ny !== request.mesh.transverse_cells
      || Math.abs(result.x_m[nx - 1] - request.geometry.length_m) > xTolerance
      || result.y_m[ny - 1] >= request.geometry.gap_m
      || Math.abs(result.inlet_temperature_k - request.operating.inlet_temperature_k) > 1e-12) return false;
  }
  const scalarChecks = [result.reynolds_hydraulic, result.peclet_length, result.mass_flow_kg_s, result.pressure_drop_pa];
  if (!scalarChecks.every(value => finite(value) && value >= 0) || result.mass_flow_kg_s <= 0) return false;
  const heat = result.heat_balance;
  const diagnostics = result.diagnostics;
  if (!heat || ![heat.wall_input_w, heat.coolant_enthalpy_gain_w, heat.imbalance_w, heat.relative_imbalance, heat.acceptance_tolerance_w].every(finite)
    || heat.relative_imbalance < 0 || heat.acceptance_tolerance_w < 0 || !diagnostics
    || ![diagnostics.maximum_equation_residual_w, diagnostics.maximum_mass_imbalance_kg_s, diagnostics.omitted_viscous_heating_rise_k].every(value => finite(value) && value >= 0)
    || diagnostics.mesh_convergence_verified !== false || diagnostics.axial_scheme !== "first_order_upwind" || diagnostics.transverse_scheme !== "centered_finite_volume"
    || !result.resources || result.resources.axial_cells !== nx || result.resources.transverse_cells !== ny
    || result.resources.field_values !== nx * ny || result.resources.maximum_field_values !== 100_000
    || !Array.isArray(result.limitations) || !result.limitations.every(item => typeof item === "string" && item.length > 0)) return false;
  return true;
}

const format = (value: number, digits = 4) => value.toLocaleString(undefined, { maximumSignificantDigits: digits });
const sampleIndices = (length: number, maximum: number) => {
  if (length <= maximum) return Array.from({ length }, (_, index) => index);
  return Array.from(new Set(Array.from({ length: maximum }, (_, index) => Math.round(index * (length - 1) / (maximum - 1)))));
};
const temperatureColor = (value: number, minimum: number, maximum: number) => {
  const t = maximum > minimum ? Math.max(0, Math.min(1, (value - minimum) / (maximum - minimum))) : 0.5;
  const hue = 220 - 210 * t;
  return `hsl(${hue.toFixed(1)} 82% 55%)`;
};

function ResultView({ result, mode, onMode }: { result: InternalAirflowResult; mode: "temperature" | "velocity"; onMode: (mode: "temperature" | "velocity") => void }) {
  const temperatureExtent = numericExtent(result.temperature_k.flat());
  const minimumTemperature = temperatureExtent.minimum;
  const maximumTemperature = temperatureExtent.maximum;
  const maximumVelocity = numericMaximum(result.velocity_u_m_s);
  const xIndices = sampleIndices(result.x_m.length, mode === "temperature" ? 80 : 9);
  const yIndices = sampleIndices(result.y_m.length, mode === "temperature" ? 40 : 30);
  const xMaximum = result.x_m[result.x_m.length - 1];
  const yMinimum = result.y_m[0];
  const yMaximum = result.y_m[result.y_m.length - 1];
  const xPosition = (index: number) => 75 + 750 * result.x_m[index] / xMaximum;
  const yPosition = (index: number) => 225 - 150 * (result.y_m[index] - yMinimum) / Math.max(1e-12, yMaximum - yMinimum);
  const heatPasses = Math.abs(result.heat_balance.imbalance_w) <= result.heat_balance.acceptance_tolerance_w;
  return <div className="internal-airflow-results">
    <div className="internal-airflow-result-heading">
      <div><strong>EXPERIMENTAL</strong><span>Laminar prescribed flow · turbulence model: none</span></div>
      <div className="internal-airflow-view-toggle" role="group" aria-label="Airflow result view">
        <button type="button" className="spike-control--compact" aria-pressed={mode === "temperature"} onClick={() => onMode("temperature")}>Temperature</button>
        <button type="button" className="spike-control--compact" aria-pressed={mode === "velocity"} onClick={() => onMode("velocity")}>Velocity arrows</button>
      </div>
    </div>
    <figure className="internal-airflow-figure">
      <svg viewBox="0 0 900 285" role="img" aria-labelledby="internal-airflow-svg-title internal-airflow-svg-description">
        <title id="internal-airflow-svg-title">{`Internal channel ${mode === "temperature" ? "temperature field" : "velocity profile"}`}</title>
        <desc id="internal-airflow-svg-description">Visualization of solver-returned axial stations and transverse cells. The inlet at x equals zero is a boundary and is not a returned field station.</desc>
        <defs><marker id="internal-airflow-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" /></marker></defs>
        <rect className="internal-airflow-channel" x="70" y="58" width="770" height="184" rx="3" />
        <line className="internal-airflow-wall lower" x1="70" y1="242" x2="840" y2="242" />
        <line className="internal-airflow-wall" x1="70" y1="58" x2="840" y2="58" />
        <text className="internal-airflow-axis-label" x="455" y="273" textAnchor="middle">Axial position x (m)</text>
        <text className="internal-airflow-boundary-label" x="70" y="48">inlet x=0</text>
        {mode === "temperature" ? xIndices.flatMap((xi, sampledX) => yIndices.map((yi, sampledY) => {
          const xNext = xIndices[Math.min(sampledX + 1, xIndices.length - 1)];
          const yNext = yIndices[Math.min(sampledY + 1, yIndices.length - 1)];
          const width = Math.max(2, xPosition(xNext) - xPosition(xi) + (sampledX === xIndices.length - 1 ? 7 : 1));
          const height = Math.max(2, Math.abs(yPosition(yNext) - yPosition(yi)) + (sampledY === yIndices.length - 1 ? 5 : 1));
          return <rect key={`${xi}:${yi}`} x={xPosition(xi) - width / 2} y={yPosition(yi) - height / 2} width={width} height={height}
            fill={temperatureColor(result.temperature_k[xi][yi], minimumTemperature, maximumTemperature)} />;
        })) : xIndices.flatMap(xi => yIndices.map(yi => {
          const arrowLength = maximumVelocity > 0 ? 58 * result.velocity_u_m_s[yi] / maximumVelocity : 0;
          return <line key={`${xi}:${yi}`} className="internal-airflow-velocity-arrow" x1={xPosition(xi)} y1={yPosition(yi)} x2={xPosition(xi) + arrowLength} y2={yPosition(yi)} markerEnd="url(#internal-airflow-arrow)" />;
        }))}
      </svg>
      <figcaption>{mode === "temperature"
        ? <>Temperature (K): <span className="internal-airflow-swatch cool" /> {format(minimumTemperature, 6)} <span className="internal-airflow-gradient" /> <span className="internal-airflow-swatch hot" /> {format(maximumTemperature, 6)}</>
        : <>Axial velocity arrows from returned transverse cell averages · 0 to {format(maximumVelocity, 6)} m/s</>}</figcaption>
    </figure>
    <dl className="internal-airflow-metrics">
      <div><dt>Re<sub>Dh</sub></dt><dd>{format(result.reynolds_hydraulic, 6)}</dd></div>
      <div><dt>Pe<sub>L</sub></dt><dd>{format(result.peclet_length, 6)}</dd></div>
      <div><dt>Mass flow</dt><dd>{format(result.mass_flow_kg_s, 6)} kg/s</dd></div>
      <div><dt>Pressure drop</dt><dd>{format(result.pressure_drop_pa, 6)} Pa</dd></div>
      <div><dt>Wall input</dt><dd>{format(result.heat_balance.wall_input_w, 6)} W</dd></div>
      <div><dt>Coolant gain</dt><dd>{format(result.heat_balance.coolant_enthalpy_gain_w, 6)} W</dd></div>
      <div><dt>Heat imbalance</dt><dd>{format(result.heat_balance.imbalance_w, 6)} W · {heatPasses ? "within" : "outside"} {format(result.heat_balance.acceptance_tolerance_w, 4)} W tolerance</dd></div>
      <div><dt>Relative imbalance</dt><dd>{format(result.heat_balance.relative_imbalance, 6)}</dd></div>
      <div><dt>Max equation residual</dt><dd>{format(result.diagnostics.maximum_equation_residual_w, 6)} W</dd></div>
      <div><dt>Max mass imbalance</dt><dd>{format(result.diagnostics.maximum_mass_imbalance_kg_s, 6)} kg/s</dd></div>
      <div><dt>Mesh convergence</dt><dd>Not verified · {result.resources.axial_cells} × {result.resources.transverse_cells}</dd></div>
      <div><dt>Discretization</dt><dd>First order axial · centered transverse</dd></div>
    </dl>
    <details><summary>Solver limitations</summary><ul>{result.limitations.map(item => <li key={item}>{item}</li>)}</ul></details>
  </div>;
}

export default function InternalAirflowPanel({ workerAvailable, initialRequest, initialResult, onResult, onStatus }: InternalAirflowPanelProps) {
  const [draft, setDraft] = useState<Draft>(() => draftFromRequest(initialRequest));
  const [result, setResult] = useState<InternalAirflowResult | null>(() => validInternalAirflowResult(initialResult, initialRequest) ? initialResult : null);
  const [resultRequest, setResultRequest] = useState<InternalAirflowRequest | null>(() => validInternalAirflowResult(initialResult, initialRequest) ? initialRequest ?? null : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"temperature" | "velocity">("temperature");
  const runSequence = useRef(0);
  useEffect(() => () => { runSequence.current += 1; }, []);
  const patch = (key: keyof Draft, value: string) => setDraft(current => ({ ...current, [key]: value }));
  const run = async () => {
    const sequence = ++runSequence.current;
    let request: InternalAirflowRequest;
    try { request = buildInternalAirflowRequest(draft); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); return; }
    setBusy(true); setError("");
    onStatus?.("Running experimental internal channel airflow screening…");
    try {
      const id = globalThis.crypto?.randomUUID?.() ?? `internal-airflow-${Date.now()}-${sequence}`;
      const response = await runLocalWorker({ id, method: "run_internal_airflow", params: { request } });
      if (runSequence.current !== sequence) return;
      if (!response.ok || !response.result) throw new Error(response.error ?? "Internal airflow worker returned no result.");
      if (!validInternalAirflowResult(response.result, request)) throw new Error("Internal airflow worker returned a malformed or unsupported result.");
      setResult(response.result); setResultRequest(request); onResult?.(request, response.result);
      onStatus?.("Internal channel airflow screening completed.");
    } catch (caught) {
      if (runSequence.current !== sequence) return;
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message); onStatus?.(`Internal airflow screening failed: ${message}`);
    } finally {
      if (runSequence.current === sequence) setBusy(false);
    }
  };
  const controls: Array<{ key: keyof Draft; label: string; unit: string; min?: string; step?: string }> = [
    { key: "length_m", label: "Channel length", unit: "m", min: "0" },
    { key: "gap_m", label: "Channel gap", unit: "m", min: "0" },
    { key: "width_m", label: "Channel width", unit: "m", min: "0" },
    { key: "mean_velocity_m_s", label: "Mean velocity", unit: "m/s", min: "0" },
    { key: "inlet_temperature_k", label: "Inlet temperature", unit: "K", min: "0" },
    { key: "density_kg_m3", label: "Fluid density", unit: "kg/m³", min: "0" },
    { key: "viscosity_pa_s", label: "Dynamic viscosity", unit: "Pa·s", min: "0" },
    { key: "conductivity_w_mk", label: "Thermal conductivity", unit: "W/(m·K)", min: "0" },
    { key: "specific_heat_j_kgk", label: "Specific heat", unit: "J/(kg·K)", min: "0" },
    { key: "lower_wall_heat_flux_w_m2", label: "Lower wall heat flux", unit: "W/m²" },
    { key: "upper_wall_heat_flux_w_m2", label: "Upper wall heat flux", unit: "W/m²" },
    { key: "axial_cells", label: "Axial cells", unit: "count", min: "2", step: "1" },
    { key: "transverse_cells", label: "Transverse cells", unit: "count", min: "3", step: "1" },
  ];
  let currentRequest: InternalAirflowRequest | null = null;
  try { currentRequest = buildInternalAirflowRequest(draft); } catch { /* validation is reported when Run is selected */ }
  const stale = Boolean(result && resultRequest && JSON.stringify(resultRequest) !== JSON.stringify(currentRequest));
  return <section className="internal-airflow-panel" aria-labelledby="internal-airflow-heading">
    <header><div><p className="internal-airflow-eyebrow">Thermal environment</p><h4 id="internal-airflow-heading">Internal channel airflow</h4></div><span className="internal-airflow-badge">Experimental</span></header>
    <p className="internal-airflow-intro">Prescribed laminar flow and wall-heated fluid energy transport for a rectangular channel. This screen does not solve a solid domain, turbulence, flow separation, fans, or enclosure-scale CFD.</p>
    <div className="internal-airflow-controls">
      {controls.map(control => <label key={control.key}><span>{control.label}<small>{control.unit}</small></span><input aria-label={`${control.label} (${control.unit})`} type="number" step={control.step ?? "any"} min={control.min} value={draft[control.key]} disabled={busy} onChange={event => patch(control.key, event.target.value)} /></label>)}
    </div>
    <p className="internal-airflow-boundary-note">Both wall heat fluxes are signed: positive values heat the fluid and zero is adiabatic. Mesh admission is bounded to 2..1000 axial cells, 3..200 transverse cells, and 100,000 field values.</p>
    <div className="internal-airflow-actions"><button type="button" className="spike-control--primary" disabled={!workerAvailable || busy} onClick={() => void run()}>{busy ? "Running channel screen…" : "Run channel screen"}</button><span aria-live="polite">{!workerAvailable ? "Local solver worker unavailable." : busy ? "Solver request in progress." : "Ready for a local experimental run."}</span></div>
    {error && <p className="internal-airflow-error" role="alert">{error} {result ? "The last valid result remains visible." : "Review the inputs and run again."}</p>}
    {stale && <p className="internal-airflow-stale" role="status">Inputs differ from the solved setup. Results below show the previous solver request.</p>}
    {result ? <ResultView result={result} mode={mode} onMode={setMode} /> : <div className="internal-airflow-empty">Run the solver to view returned temperature stations or velocity arrows. No field is estimated in the browser.</div>}
  </section>;
}
