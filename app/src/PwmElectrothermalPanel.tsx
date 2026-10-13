// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { numericExtent } from "./numericRange";
import SavedFramePlaybackControls from "./SavedFramePlaybackControls";
import {
  cancelLocalWorker,
  cancelLocalWorkerCleanup,
  runLocalWorker,
  saveNativeTextFile,
  subscribeWorkerProgress,
} from "./workerBridge";
import "./PwmElectrothermalPanel.css";

export const PWM_REQUEST_CONTRACT = "spike/pwm-electrothermal-request/v1" as const;
export const PWM_RESULT_CONTRACT = "spike/pwm-electrothermal-result/v1" as const;

export type PwmElectrothermalParameters = {
  input_voltage_v: number;
  target_voltage_v: number;
  inductance_h: number;
  capacitance_f: number;
  load_resistance_ohm: number;
  winding_resistance_ohm: number;
  temperature_coefficient_per_k: number;
  ambient_temperature_k: number;
  thermal_resistance_k_per_w: number;
  thermal_capacitance_j_per_k: number;
  switch_on_resistance_ohm: number;
  switch_off_resistance_ohm: number;
  switching_frequency_hz: number;
  maximum_step_s: number;
  cycles: number;
  controller_kp_per_v: number;
  controller_ki_per_v_s: number;
};

export type PwmElectrothermalRequest = {
  contract: typeof PWM_REQUEST_CONTRACT;
  parameters: PwmElectrothermalParameters;
};

type CycleEnergy = {
  source_j: number;
  switch_j: number;
  load_j: number;
  winding_j: number;
  ambient_j: number;
  be_numerical_dissipation_j: number;
};

export type PwmCycleWindow = {
  cycle: number;
  time_s: number;
  duty: number;
  output_voltage_v: number;
  inductor_current_a: number;
  winding_temperature_k: number;
  on_start_s: number;
  off_start_s: number;
  minimum_output_voltage_v: number;
  maximum_output_voltage_v: number;
  minimum_inductor_current_a: number;
  maximum_inductor_current_a: number;
  energy: CycleEnergy;
};

type PwmCheckpoint = {
  contract: "spike/pwm-electrothermal-checkpoint/v1";
  completed_cycles: number;
  configuration_sha256: string;
  library_sha256: string;
  state_sha256: string;
};

export type PwmElectrothermalResult = {
  contract: typeof PWM_RESULT_CONTRACT;
  status: "completed" | "cancelled";
  model_status: "experimental";
  checkpoint: PwmCheckpoint;
  restart: { method: "deterministic_replay"; verified: boolean; no_replay_speedup_claim: true };
  issue_codes: Array<"PWM_CANCELLED">;
  parameters: PwmElectrothermalParameters;
  windows: PwmCycleWindow[];
  energy: CycleEnergy & {
    electrical_stored_j: number;
    thermal_stored_j: number;
    electrical_balance_j: number;
    thermal_balance_j: number;
  };
  request_sha256: string;
  configuration_sha256: string;
  runtime: {
    engine: "native_spikes_persistent_mna";
    integration: "backward_euler";
    diagnostics: Record<string, number>;
    library_sha256: string;
  };
  quality: {
    maximum_step_electrical_balance_j: number;
    maximum_step_thermal_balance_j: number;
    maximum_element_power_balance_w: number;
  };
  limits: string[];
};

export type PwmElectrothermalAdmission = {
  contract: "spike/pwm-electrothermal-admission/v1";
  status: "accepted";
  parameters: PwmElectrothermalParameters;
  configuration_sha256: string;
  maximum_electrical_steps: number;
  model_status: "experimental";
};

export type PwmElectrothermalPanelProps = {
  workerAvailable: boolean;
  initialRequest?: PwmElectrothermalRequest;
  initialResult?: unknown;
  onResult?: (request: PwmElectrothermalRequest, result: PwmElectrothermalResult) => void;
  onStatus?: (message: string) => void;
};

type Draft = { [K in keyof PwmElectrothermalParameters]: string };
type ParameterKey = keyof PwmElectrothermalParameters;
type Field = { key: ParameterKey; label: string; unit: string; step?: string };

export const DEFAULT_PWM_ELECTROTHERMAL_PARAMETERS: PwmElectrothermalParameters = {
  input_voltage_v: 12,
  target_voltage_v: 5,
  inductance_h: 1e-4,
  capacitance_f: 1e-4,
  load_resistance_ohm: 5,
  winding_resistance_ohm: 0.2,
  temperature_coefficient_per_k: 0.02,
  ambient_temperature_k: 300,
  thermal_resistance_k_per_w: 10,
  thermal_capacitance_j_per_k: 0.01,
  switch_on_resistance_ohm: 0.02,
  switch_off_resistance_ohm: 1e6,
  switching_frequency_hz: 20000,
  maximum_step_s: 1e-6,
  cycles: 400,
  controller_kp_per_v: 0.04,
  controller_ki_per_v_s: 10,
};

const PARAMETER_KEYS = Object.keys(DEFAULT_PWM_ELECTROTHERMAL_PARAMETERS) as ParameterKey[];
const PARAMETER_RANGES: Record<ParameterKey, readonly [number, number]> = {
  input_voltage_v: [1, 100], target_voltage_v: [0.1, 99],
  inductance_h: [1e-6, 0.1], capacitance_f: [1e-7, 0.1],
  load_resistance_ohm: [0.1, 1000], winding_resistance_ohm: [1e-4, 10],
  temperature_coefficient_per_k: [0, 0.1], ambient_temperature_k: [250, 350],
  thermal_resistance_k_per_w: [0.01, 1000], thermal_capacitance_j_per_k: [1e-5, 100],
  switch_on_resistance_ohm: [1e-3, 10], switch_off_resistance_ohm: [1e3, 1e8],
  switching_frequency_hz: [100, 1e6], maximum_step_s: [1e-9, 1e-3],
  cycles: [1, 2000], controller_kp_per_v: [0, 10], controller_ki_per_v_s: [0, 1e5],
};
const SOURCE_FIELDS: Field[] = [
  { key: "input_voltage_v", label: "Input voltage", unit: "V" },
  { key: "target_voltage_v", label: "Target voltage", unit: "V" },
  { key: "switching_frequency_hz", label: "Switching frequency", unit: "Hz" },
  { key: "cycles", label: "PWM cycles", unit: "count", step: "1" },
  { key: "maximum_step_s", label: "Maximum electrical step", unit: "s" },
  { key: "controller_kp_per_v", label: "PI proportional gain", unit: "1/V" },
  { key: "controller_ki_per_v_s", label: "PI integral gain", unit: "1/(V·s)" },
];
const ELECTRICAL_FIELDS: Field[] = [
  { key: "inductance_h", label: "Inductance", unit: "H" },
  { key: "capacitance_f", label: "Capacitance", unit: "F" },
  { key: "load_resistance_ohm", label: "Load resistance", unit: "Ω" },
  { key: "winding_resistance_ohm", label: "Winding resistance", unit: "Ω" },
  { key: "switch_on_resistance_ohm", label: "Switch on resistance", unit: "Ω" },
  { key: "switch_off_resistance_ohm", label: "Switch off resistance", unit: "Ω" },
];
const THERMAL_FIELDS: Field[] = [
  { key: "temperature_coefficient_per_k", label: "Winding temperature coefficient", unit: "1/K" },
  { key: "ambient_temperature_k", label: "Ambient temperature", unit: "K" },
  { key: "thermal_resistance_k_per_w", label: "Winding thermal resistance", unit: "K/W" },
  { key: "thermal_capacitance_j_per_k", label: "Winding thermal capacitance", unit: "J/K" },
];
const HASH = /^[0-9a-f]{64}$/;
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const plainObject = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const exactKeys = (value: Record<string, unknown>, keys: readonly string[]) => {
  const actual = Object.keys(value).sort();
  return actual.length === keys.length && actual.every((key, index) => key === [...keys].sort()[index]);
};

function validateParameters(parameters: unknown): asserts parameters is PwmElectrothermalParameters {
  if (!plainObject(parameters) || !exactKeys(parameters, PARAMETER_KEYS)) throw new Error("PWM request must include exactly the supported parameters.");
  for (const key of PARAMETER_KEYS) {
    const value = parameters[key];
    const [minimum, maximum] = PARAMETER_RANGES[key];
    if (!finite(value)) throw new Error(`${key} must be finite.`);
    if (value < minimum || value > maximum) throw new Error(`${key} must be within ${minimum}..${maximum}.`);
  }
  const typed = parameters as unknown as PwmElectrothermalParameters;
  if (!Number.isInteger(typed.cycles)) throw new Error("cycles must be an integer.");
  if (typed.target_voltage_v >= typed.input_voltage_v) throw new Error("Buck target voltage must be below input voltage.");
  const period = 1 / typed.switching_frequency_hz;
  if (typed.maximum_step_s > period / 4) throw new Error("Maximum electrical step must be at most one quarter of the PWM period.");
  const budget = typed.cycles * (Math.ceil(period / typed.maximum_step_s) + 2);
  if (budget > 200_000) throw new Error("Electrical step budget exceeds 200,000 steps. Reduce cycles or increase the step size within the period limit.");
}

function parametersEqual(left: PwmElectrothermalParameters, right: PwmElectrothermalParameters): boolean {
  return PARAMETER_KEYS.every(key => left[key] === right[key]);
}

const draftFromParameters = (parameters: PwmElectrothermalParameters): Draft => Object.fromEntries(
  PARAMETER_KEYS.map(key => [key, String(parameters[key])]),
) as Draft;

export function buildPwmElectrothermalRequest(draft: Draft): PwmElectrothermalRequest {
  const parameters = Object.fromEntries(PARAMETER_KEYS.map(key => [key, Number(draft[key])])) as PwmElectrothermalParameters;
  validateParameters(parameters);
  return { contract: PWM_REQUEST_CONTRACT, parameters };
}

export function validPwmElectrothermalRequest(raw: unknown): raw is PwmElectrothermalRequest {
  if (!plainObject(raw) || !exactKeys(raw, ["contract", "parameters"]) || raw.contract !== PWM_REQUEST_CONTRACT) return false;
  try { validateParameters(raw.parameters); } catch { return false; }
  return true;
}

export function validPwmElectrothermalAdmission(raw: unknown, request: PwmElectrothermalRequest): raw is PwmElectrothermalAdmission {
  if (!plainObject(raw) || !exactKeys(raw, ["contract", "status", "parameters", "configuration_sha256", "maximum_electrical_steps", "model_status"])
    || raw.contract !== "spike/pwm-electrothermal-admission/v1" || raw.status !== "accepted"
    || raw.model_status !== "experimental" || typeof raw.configuration_sha256 !== "string" || !HASH.test(raw.configuration_sha256)
    || !Number.isInteger(raw.maximum_electrical_steps) || Number(raw.maximum_electrical_steps) < 1 || Number(raw.maximum_electrical_steps) > 200_000) return false;
  try { validateParameters(raw.parameters); } catch { return false; }
  return parametersEqual(raw.parameters, request.parameters);
}

function validEnergy(value: unknown, total = false): value is CycleEnergy {
  if (!plainObject(value)) return false;
  const keys = ["source_j", "switch_j", "load_j", "winding_j", "ambient_j", "be_numerical_dissipation_j"];
  const totalKeys = [...keys, "electrical_stored_j", "thermal_stored_j", "electrical_balance_j", "thermal_balance_j"];
  return exactKeys(value, total ? totalKeys : keys) && (total ? totalKeys : keys).every(key => finite(value[key]));
}

function validCheckpoint(value: unknown, completedCycles: number, configurationHash: string): value is PwmCheckpoint {
  return plainObject(value) && exactKeys(value, ["contract", "completed_cycles", "configuration_sha256", "library_sha256", "state_sha256"])
    && value.contract === "spike/pwm-electrothermal-checkpoint/v1" && value.completed_cycles === completedCycles
    && value.configuration_sha256 === configurationHash && typeof value.library_sha256 === "string" && HASH.test(value.library_sha256)
    && typeof value.state_sha256 === "string" && HASH.test(value.state_sha256);
}

export function validPwmElectrothermalResult(raw: unknown, request?: PwmElectrothermalRequest, configurationHash?: string): raw is PwmElectrothermalResult {
  if (!plainObject(raw) || !exactKeys(raw, ["contract", "status", "model_status", "checkpoint", "restart", "issue_codes", "parameters", "windows", "energy", "request_sha256", "configuration_sha256", "runtime", "quality", "limits"])
    || raw.contract !== PWM_RESULT_CONTRACT || !["completed", "cancelled"].includes(String(raw.status))
    || raw.model_status !== "experimental" || typeof raw.request_sha256 !== "string" || !HASH.test(raw.request_sha256)
    || typeof raw.configuration_sha256 !== "string" || !HASH.test(raw.configuration_sha256)) return false;
  try { validateParameters(raw.parameters); } catch { return false; }
  const parameters = raw.parameters;
  if (request && !parametersEqual(parameters, request.parameters)) return false;
  if (configurationHash && raw.configuration_sha256 !== configurationHash) return false;
  if (!Array.isArray(raw.windows) || raw.windows.length > parameters.cycles
    || (raw.status === "completed" && raw.windows.length !== parameters.cycles)) return false;
  let previousTime = -Infinity;
  for (let index = 0; index < raw.windows.length; index += 1) {
    const window = raw.windows[index];
    if (!plainObject(window) || !exactKeys(window, ["cycle", "time_s", "duty", "output_voltage_v", "inductor_current_a", "winding_temperature_k", "on_start_s", "off_start_s", "minimum_output_voltage_v", "maximum_output_voltage_v", "minimum_inductor_current_a", "maximum_inductor_current_a", "energy"])) return false;
    const scalars = [window.time_s, window.duty, window.output_voltage_v, window.inductor_current_a, window.winding_temperature_k,
      window.on_start_s, window.off_start_s, window.minimum_output_voltage_v, window.maximum_output_voltage_v,
      window.minimum_inductor_current_a, window.maximum_inductor_current_a];
    if (window.cycle !== index + 1 || !scalars.every(finite) || Number(window.time_s) <= previousTime
      || Number(window.duty) < 0.05 || Number(window.duty) > 0.95
      || Number(window.on_start_s) > Number(window.off_start_s) || Number(window.off_start_s) > Number(window.time_s)
      || Number(window.minimum_output_voltage_v) > Number(window.output_voltage_v) || Number(window.output_voltage_v) > Number(window.maximum_output_voltage_v)
      || Number(window.minimum_inductor_current_a) > Number(window.inductor_current_a) || Number(window.inductor_current_a) > Number(window.maximum_inductor_current_a)
      || Number(window.winding_temperature_k) < parameters.ambient_temperature_k - 1e-7 || !validEnergy(window.energy)) return false;
    previousTime = Number(window.time_s);
  }
  if (!validEnergy(raw.energy, true) || !validCheckpoint(raw.checkpoint, raw.windows.length, String(raw.configuration_sha256))) return false;
  if (!plainObject(raw.restart) || !exactKeys(raw.restart, ["method", "verified", "no_replay_speedup_claim"])
    || raw.restart.method !== "deterministic_replay" || typeof raw.restart.verified !== "boolean" || raw.restart.no_replay_speedup_claim !== true) return false;
  if (!Array.isArray(raw.issue_codes) || (raw.status === "completed" ? raw.issue_codes.length !== 0 : raw.issue_codes.length !== 1 || raw.issue_codes[0] !== "PWM_CANCELLED")) return false;
  const runtime = raw.runtime;
  if (!plainObject(runtime) || !exactKeys(runtime, ["engine", "integration", "diagnostics", "library_sha256"])
    || runtime.engine !== "native_spikes_persistent_mna" || runtime.integration !== "backward_euler"
    || typeof runtime.library_sha256 !== "string" || !HASH.test(runtime.library_sha256) || !plainObject(runtime.diagnostics)) return false;
  const diagnostics = runtime.diagnostics;
  if (!["completed_steps", "matrix_factorizations", "total_newton_iterations", "residual_inf_norm"].every(key => finite(diagnostics[key]))) return false;
  const quality = raw.quality;
  if (!plainObject(quality) || !exactKeys(quality, ["maximum_step_electrical_balance_j", "maximum_step_thermal_balance_j", "maximum_element_power_balance_w"])
    || !["maximum_step_electrical_balance_j", "maximum_step_thermal_balance_j", "maximum_element_power_balance_w"]
    .every(key => finite(quality[key]) && Number(quality[key]) >= 0)) return false;
  return Array.isArray(raw.limits) && raw.limits.length <= 8 && raw.limits.every(item => typeof item === "string" && item.length > 0 && item.length <= 256);
}

export function pwmElectrothermalPersistenceFingerprint(request?: PwmElectrothermalRequest, result?: PwmElectrothermalResult | null): string {
  if (!request) return "empty";
  const requestIdentity = PARAMETER_KEYS.map(key => request.parameters[key]).join("|");
  if (!result) return `request|${requestIdentity}`;
  return ["result", requestIdentity, result.status, result.request_sha256, result.configuration_sha256,
    result.runtime.library_sha256, result.checkpoint.completed_cycles, result.checkpoint.state_sha256].join("|");
}

const formatted = (value: unknown) => JSON.stringify(value, null, 2);
const format = (value: number, digits = 5) => value.toLocaleString(undefined, { maximumSignificantDigits: digits });
const range = (values: number[]) => {
  const { minimum, maximum } = numericExtent(values);
  const padding = maximum === minimum ? Math.max(Math.abs(maximum) * 0.05, 1e-9) : (maximum - minimum) * 0.08;
  return { minimum: minimum - padding, maximum: maximum + padding };
};

function TracePlot({ title, unit, windows, value, minimum, maximum, selected }: {
  title: string; unit: string; windows: PwmCycleWindow[]; value: (window: PwmCycleWindow) => number;
  minimum?: (window: PwmCycleWindow) => number; maximum?: (window: PwmCycleWindow) => number; selected: number;
}) {
  const values = windows.flatMap(window => [value(window), ...(minimum ? [minimum(window)] : []), ...(maximum ? [maximum(window)] : [])]);
  const extent = range(values);
  const x = (index: number) => 54 + index * 680 / Math.max(1, windows.length - 1);
  const y = (item: number) => 12 + (extent.maximum - item) * 104 / (extent.maximum - extent.minimum);
  const points = (selector: (window: PwmCycleWindow) => number) => windows.map((window, index) => `${x(index)},${y(selector(window))}`).join(" ");
  const selectedWindow = windows[selected];
  return <figure className="pwm-electrothermal-plot">
    <svg viewBox="0 0 760 145" role="img" aria-label={`${title} by completed PWM cycle`}>
      <title>{`${title} by completed PWM cycle`}</title>
      <line className="pwm-electrothermal-axis" x1="54" y1="116" x2="734" y2="116" />
      <line className="pwm-electrothermal-axis" x1="54" y1="12" x2="54" y2="116" />
      <text x="8" y="17">{format(extent.maximum, 4)}</text><text x="8" y="116">{format(extent.minimum, 4)}</text>
      <text x="54" y="136">1</text><text x="704" y="136">cycle {windows.length}</text>
      {minimum && maximum && <polygon className="pwm-electrothermal-band" points={`${points(minimum)} ${[...windows].reverse().map((window, reverseIndex) => `${x(windows.length - 1 - reverseIndex)},${y(maximum(window))}`).join(" ")}`} />}
      <polyline className="pwm-electrothermal-trace" points={points(value)} />
      {selectedWindow && <><line className="pwm-electrothermal-cursor" x1={x(selected)} y1="12" x2={x(selected)} y2="116" />
        <circle className="pwm-electrothermal-point" cx={x(selected)} cy={y(value(selectedWindow))} r="3.5" /></>}
    </svg>
    <figcaption><strong>{title}</strong><span>{selectedWindow ? `${format(value(selectedWindow), 6)} ${unit} at cycle ${selectedWindow.cycle}` : unit}</span></figcaption>
  </figure>;
}

function FieldGroup({ legend, fields, draft, disabled, patch }: { legend: string; fields: Field[]; draft: Draft; disabled: boolean; patch: (key: ParameterKey, value: string) => void }) {
  return <fieldset disabled={disabled}><legend>{legend}</legend><div className="pwm-electrothermal-fields">{fields.map(field =>
    <label key={field.key}><span>{field.label}<small>{field.unit}</small></span><input type="number" step={field.step ?? "any"}
      aria-label={`${field.label} (${field.unit})`} value={draft[field.key]} onChange={event => patch(field.key, event.target.value)} /></label>)}</div></fieldset>;
}

function ResultView({ result, selected, onSelected }: { result: PwmElectrothermalResult; selected: number; onSelected: (index: number) => void }) {
  const [playing, setPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const frameTimes = useMemo(() => result.windows.map(window => window.time_s), [result]);
  useEffect(() => { setPlaying(false); }, [result]);
  if (!result.windows.length) return <div className="pwm-electrothermal-empty">The cancelled run committed no complete PWM cycle, so there are no result frames to plot.</div>;
  const index = Math.max(0, Math.min(selected, result.windows.length - 1));
  const frame = result.windows[index];
  return <div className="pwm-electrothermal-results">
    <div className="pwm-electrothermal-result-heading"><div><strong>EXPERIMENTAL · {result.status.toUpperCase()}</strong><span>Native persistent MNA · backward Euler · one returned window per PWM cycle</span></div></div>
    {result.windows.length > 1 ? <SavedFramePlaybackControls timesS={frameTimes} frameIndex={index}
      playing={playing} playbackSpeed={playbackSpeed} onFrame={onSelected} onPlaying={setPlaying} onPlaybackSpeed={setPlaybackSpeed} />
      : <p className="pwm-electrothermal-single-frame">Single stored result frame · {format(frame.time_s, 7)} s</p>}
    <div className="pwm-electrothermal-plots">
      <TracePlot title="Output voltage" unit="V" windows={result.windows} value={item => item.output_voltage_v} minimum={item => item.minimum_output_voltage_v} maximum={item => item.maximum_output_voltage_v} selected={index} />
      <TracePlot title="Inductor current" unit="A" windows={result.windows} value={item => item.inductor_current_a} minimum={item => item.minimum_inductor_current_a} maximum={item => item.maximum_inductor_current_a} selected={index} />
      <TracePlot title="Winding temperature" unit="K" windows={result.windows} value={item => item.winding_temperature_k} selected={index} />
    </div>
    <dl className="pwm-electrothermal-metrics">
      <div><dt>Time</dt><dd>{format(frame.time_s, 7)} s</dd></div><div><dt>Duty</dt><dd>{format(frame.duty * 100, 5)}%</dd></div>
      <div><dt>Voltage range</dt><dd>{format(frame.minimum_output_voltage_v)} to {format(frame.maximum_output_voltage_v)} V</dd></div>
      <div><dt>Current range</dt><dd>{format(frame.minimum_inductor_current_a)} to {format(frame.maximum_inductor_current_a)} A</dd></div>
      <div><dt>Winding temperature</dt><dd>{format(frame.winding_temperature_k, 7)} K</dd></div>
      <div><dt>Winding heat this cycle</dt><dd>{format(frame.energy.winding_j, 6)} J</dd></div>
      <div><dt>External switch loss</dt><dd>{format(frame.energy.switch_j, 6)} J/cycle</dd></div>
      <div><dt>External load loss</dt><dd>{format(frame.energy.load_j, 6)} J/cycle</dd></div>
    </dl>
    <details><summary>Energy balance, quality, runtime and checkpoint</summary><pre>{formatted({ energy: result.energy, quality: result.quality, runtime: result.runtime, checkpoint: result.checkpoint, restart: result.restart })}</pre></details>
    <details open><summary>Model limits</summary><ul>{result.limits.map(limit => <li key={limit}>{limit}</li>)}</ul></details>
  </div>;
}

export default function PwmElectrothermalPanel({ workerAvailable, initialRequest, initialResult, onResult, onStatus }: PwmElectrothermalPanelProps) {
  const admittedInitialRequest = validPwmElectrothermalRequest(initialRequest) ? initialRequest : undefined;
  const initialAccepted = admittedInitialRequest && validPwmElectrothermalResult(initialResult, admittedInitialRequest) ? initialResult : null;
  const incomingFingerprint = pwmElectrothermalPersistenceFingerprint(admittedInitialRequest, initialAccepted);
  const initialParameters = admittedInitialRequest?.parameters ?? DEFAULT_PWM_ELECTROTHERMAL_PARAMETERS;
  const [draft, setDraft] = useState<Draft>(() => draftFromParameters(initialParameters));
  const [result, setResult] = useState<PwmElectrothermalResult | null>(initialAccepted);
  const [resultRequest, setResultRequest] = useState<PwmElectrothermalRequest | null>(initialAccepted ? admittedInitialRequest ?? null : null);
  const [admission, setAdmission] = useState<PwmElectrothermalAdmission | null>(null);
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<{ completed: number; total: number } | null>(null);
  const [selected, setSelected] = useState(Math.max(0, (initialAccepted?.windows.length ?? 1) - 1));
  const sequence = useRef(0);
  const operation = useRef<string | null>(null);
  const cancellationRequested = useRef(false);
  const currentPersistenceFingerprint = useRef(incomingFingerprint);
  useEffect(() => () => {
    sequence.current += 1;
    if (operation.current) void cancelLocalWorkerCleanup(operation.current);
  }, []);
  useEffect(() => {
    if (incomingFingerprint === currentPersistenceFingerprint.current) return;
    sequence.current += 1;
    const ownedOperation = operation.current;
    operation.current = null;
    if (ownedOperation) void cancelLocalWorkerCleanup(ownedOperation);
    cancellationRequested.current = false;
    currentPersistenceFingerprint.current = incomingFingerprint;
    setDraft(draftFromParameters(admittedInitialRequest?.parameters ?? DEFAULT_PWM_ELECTROTHERMAL_PARAMETERS));
    setResult(initialAccepted); setResultRequest(initialAccepted ? admittedInitialRequest ?? null : null);
    setAdmission(null); setBusy(false); setCancelling(false); setError(""); setProgress(null);
    setSelected(Math.max(0, (initialAccepted?.windows.length ?? 1) - 1));
  }, [incomingFingerprint]);
  const patch = (key: ParameterKey, value: string) => { setDraft(current => ({ ...current, [key]: value })); setAdmission(null); };
  const run = async () => {
    const token = ++sequence.current;
    let request: PwmElectrothermalRequest;
    try { request = buildPwmElectrothermalRequest(draft); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); return; }
    setBusy(true); setCancelling(false); setError(""); setProgress(null); cancellationRequested.current = false;
    onStatus?.("Validating the experimental PWM electrothermal request…");
    let unlisten: (() => void) | undefined;
    try {
      const preflight = await runLocalWorker({ method: "validate_pwm_electrothermal", params: { request } });
      if (sequence.current !== token) return;
      if (!preflight.ok || !validPwmElectrothermalAdmission(preflight.result, request)) throw new Error(preflight.error ?? "PWM preflight returned a malformed or unsupported admission result.");
      setAdmission(preflight.result);
      const id = `pwm-electrothermal-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${token}`}`;
      operation.current = id;
      unlisten = await subscribeWorkerProgress(event => {
        if (event.operationId !== id || event.method !== "run_pwm_electrothermal" || sequence.current !== token) return;
        const completed = event.frame.completed_cycles, total = event.frame.total_cycles;
        if (finite(completed) && finite(total) && Number.isInteger(completed) && Number.isInteger(total) && completed >= 0 && total > 0 && completed <= total) setProgress({ completed, total });
      });
      onStatus?.("Running the experimental native PWM electrothermal model…");
      const response = await runLocalWorker({ id, method: "run_pwm_electrothermal", params: { request } });
      if (sequence.current !== token) return;
      if (!response.ok || !response.result) {
        if (cancellationRequested.current) { onStatus?.("PWM electrothermal run cancelled."); return; }
        throw new Error(response.error ?? "PWM electrothermal worker returned no result.");
      }
      if (!validPwmElectrothermalResult(response.result, request, preflight.result.configuration_sha256)) throw new Error("PWM electrothermal worker returned a malformed or unsupported result.");
      currentPersistenceFingerprint.current = pwmElectrothermalPersistenceFingerprint(request, response.result);
      setResult(response.result); setResultRequest(request); setSelected(Math.max(0, response.result.windows.length - 1));
      onResult?.(request, response.result);
      onStatus?.(response.result.status === "cancelled" ? "PWM electrothermal run cancelled after its last complete cycle." : "PWM electrothermal run completed.");
    } catch (caught) {
      if (sequence.current !== token || cancellationRequested.current) return;
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message); onStatus?.(`PWM electrothermal run failed: ${message}`);
    } finally {
      unlisten?.();
      if (sequence.current === token) { operation.current = null; setBusy(false); setCancelling(false); }
    }
  };
  const cancel = async () => {
    const id = operation.current;
    if (!id || cancelling) return;
    const accepted = await cancelLocalWorker(id);
    if (operation.current !== id) return;
    if (accepted) {
      cancellationRequested.current = true; setCancelling(true);
      onStatus?.("PWM cancellation accepted; waiting for worker shutdown.");
    } else {
      setError("No active PWM worker operation accepted the cancellation request.");
    }
  };
  const exportRequest = async () => {
    try {
      const request = buildPwmElectrothermalRequest(draft);
      const path = await saveNativeTextFile("pwm-electrothermal-request.json", formatted(request), "result");
      onStatus?.(path ? `PWM request exported: ${path}` : "PWM request export cancelled.");
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
  };
  const exportResult = async () => {
    if (!result || !resultRequest) return;
    try {
      const document = { contract: "spike/pwm-electrothermal-export/v1", request: resultRequest, result };
      const path = await saveNativeTextFile("pwm-electrothermal-result.json", formatted(document), "result");
      onStatus?.(path ? `PWM result exported: ${path}` : "PWM result export cancelled.");
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
  };
  let currentRequest: PwmElectrothermalRequest | null = null;
  try { currentRequest = buildPwmElectrothermalRequest(draft); } catch { /* Run reports the exact validation problem. */ }
  const stale = Boolean(result && resultRequest && (!currentRequest || !parametersEqual(resultRequest.parameters, currentRequest.parameters)));
  const progressText = progress ? `${progress.completed} / ${progress.total} completed cycles (${Math.floor(100 * progress.completed / progress.total)}%)` : "Starting native switching run.";
  return <section className="pwm-electrothermal-panel" aria-labelledby="pwm-electrothermal-heading">
    <header><div><p className="pwm-electrothermal-eyebrow">PI and thermal shared analysis</p><h4 id="pwm-electrothermal-heading">PWM buck electrothermal</h4></div><span className="pwm-electrothermal-badge">Experimental</span></header>
    <p className="pwm-electrothermal-intro">Switching-level synchronous buck with finite R<sub>on</sub>/R<sub>off</sub> behavioral switches and persistent electrical state. Only winding Joule heat feeds the lumped thermal state; switch and load losses remain external.</p>
    <FieldGroup legend="Source and controller" fields={SOURCE_FIELDS} draft={draft} disabled={busy} patch={patch} />
    <FieldGroup legend="Electrical network" fields={ELECTRICAL_FIELDS} draft={draft} disabled={busy} patch={patch} />
    <FieldGroup legend="Winding thermal model" fields={THERMAL_FIELDS} draft={draft} disabled={busy} patch={patch} />
    <p className="pwm-electrothermal-boundary-note">Complementary gates are ideal and omit deadtime and gate charge. This model does not claim vendor transistor behavior, spatial or 3D thermal fields, EMI, measured correlation, controller stability, or hardware qualification.</p>
    <div className="pwm-electrothermal-actions">
      <button type="button" className="spike-control--primary" disabled={!workerAvailable || busy} onClick={() => void run()}>{busy ? "Running PWM model…" : "Validate and run"}</button>
      {busy && operation.current && <button type="button" disabled={cancelling} onClick={() => void cancel()}>{cancelling ? "Cancelling…" : "Cancel run"}</button>}
      <button type="button" disabled={busy || !currentRequest} onClick={() => void exportRequest()}>Export request</button>
      <button type="button" disabled={busy || !result || !resultRequest} onClick={() => void exportResult()}>Export request + result</button>
      <span aria-live="polite">{!workerAvailable ? "Local solver worker unavailable." : busy ? progressText : admission ? `Preflight accepted · at most ${admission.maximum_electrical_steps.toLocaleString()} electrical steps.` : "Ready for strict preflight and a local native run."}</span>
    </div>
    {error && <p className="pwm-electrothermal-error" role="alert">{error} {result ? "The last valid result remains visible." : "Review the inputs and run again."}</p>}
    {stale && <p className="pwm-electrothermal-stale" role="status">Inputs differ from the solved setup. Results below show the previous admitted request.</p>}
    {result ? <ResultView result={result} selected={selected} onSelected={setSelected} /> : <div className="pwm-electrothermal-empty">Run the native model to view returned voltage, current, winding temperature, cycle energy, and checkpoint evidence. The browser does not synthesize solver frames.</div>}
  </section>;
}
