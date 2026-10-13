// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { runLocalWorker } from "./workerBridge";
import "./SmpsConverterPanel.css";

export type SmpsComponentOption = { occurrenceId: string; reference: string; label?: string };
export type SmpsBinding = { occurrence_id: string; component_ref: string };
export type SmpsSwitchGroup = {
  role: "on" | "off";
  devices: SmpsBinding[];
  series_count: number;
  parallel_count: number;
  rds_on_ohm: number;
  rise_time_s: number;
  fall_time_s: number;
  gate_charge_c: number;
  gate_drive_v: number;
  voltage_rating_v: number;
  current_rating_a: number;
};
export type SmpsConverterRequest = {
  contract: "spike/smps-converter-request/v1";
  block_id: string;
  topology: "synchronous_buck" | "synchronous_boost" | "inverting_buck_boost";
  input_voltage_v: number;
  output_voltage_v: number;
  output_current_a: number;
  switching_frequency_hz: number;
  switches: [SmpsSwitchGroup, SmpsSwitchGroup];
  inductor: SmpsBinding & { inductance_h: number; dcr_ohm: number; current_rating_a: number };
};
export type SmpsLossRow = SmpsBinding & {
  role: "on" | "off" | "inductor";
  conduction_power_w: number;
  switching_power_w: number;
  total_power_w: number;
};
export type SmpsConverterResult = {
  contract: "spike/smps-converter-result/v1";
  block_id: string;
  topology: SmpsConverterRequest["topology"];
  request_snapshot: SmpsConverterRequest;
  model_status: "approximate";
  temporal_scope: "steady_average_only";
  duty_cycle: number;
  input_current_a: number;
  input_power_w: number;
  output_power_w: number;
  total_loss_w: number;
  efficiency: number;
  inductor_average_current_a: number;
  inductor_rms_current_a: number;
  inductor_peak_current_a: number;
  inductor_minimum_current_a: number;
  inductor_ripple_current_a: number;
  losses: SmpsLossRow[];
  auxiliary_loss_w: number;
  auxiliary_loss_location: "unassigned_gate_drive";
  solver: {
    iterations: number;
    duty_bracket_width: number;
    periodic_current_residual_a: number;
    energy_balance_residual_w: number;
  };
  limitations: string[];
};

type SwitchDraft = {
  role: "on" | "off";
  seriesCount: string;
  parallelCount: string;
  devices: SmpsBinding[];
  rdsOnOhm: string;
  riseTimeS: string;
  fallTimeS: string;
  gateChargeC: string;
  gateDriveV: string;
  voltageRatingV: string;
  currentRatingA: string;
};
export type SmpsConverterDraft = {
  blockId: string;
  topology: SmpsConverterRequest["topology"];
  inputVoltageV: string;
  outputVoltageV: string;
  outputCurrentA: string;
  switchingFrequencyHz: string;
  switches: [SwitchDraft, SwitchDraft];
  inductor: SmpsBinding & { inductanceH: string; dcrOhm: string; currentRatingA: string };
};
export type SmpsConverterPanelProps = {
  workerAvailable: boolean;
  components: SmpsComponentOption[];
  initialRequest?: SmpsConverterRequest | null;
  initialResult?: unknown;
  onResult?: (request: SmpsConverterRequest, result: SmpsConverterResult) => void;
  onStatus?: (message: string) => void;
};

const emptyBinding = (): SmpsBinding => ({ occurrence_id: "", component_ref: "" });
const emptySwitch = (role: "on" | "off"): SwitchDraft => ({
  role, seriesCount: "1", parallelCount: "1", devices: [emptyBinding()], rdsOnOhm: "",
  riseTimeS: "", fallTimeS: "", gateChargeC: "", gateDriveV: "", voltageRatingV: "", currentRatingA: "",
});
export const createEmptySmpsDraft = (): SmpsConverterDraft => ({
  blockId: "converter-1", topology: "synchronous_buck", inputVoltageV: "", outputVoltageV: "",
  outputCurrentA: "", switchingFrequencyHz: "", switches: [emptySwitch("on"), emptySwitch("off")],
  inductor: { ...emptyBinding(), inductanceH: "", dcrOhm: "", currentRatingA: "" },
});

const textNumber = (value: number) => Number.isFinite(value) ? String(value) : "";
function draftFromRequest(request?: SmpsConverterRequest | null): SmpsConverterDraft {
  if (!request) return createEmptySmpsDraft();
  const group = (role: "on" | "off"): SwitchDraft => {
    const source = request.switches.find(item => item.role === role);
    if (!source) return emptySwitch(role);
    return { role, seriesCount: textNumber(source.series_count), parallelCount: textNumber(source.parallel_count),
      devices: source.devices.map(item => ({ ...item })), rdsOnOhm: textNumber(source.rds_on_ohm),
      riseTimeS: textNumber(source.rise_time_s), fallTimeS: textNumber(source.fall_time_s),
      gateChargeC: textNumber(source.gate_charge_c), gateDriveV: textNumber(source.gate_drive_v),
      voltageRatingV: textNumber(source.voltage_rating_v), currentRatingA: textNumber(source.current_rating_a) };
  };
  return {
    blockId: request.block_id, topology: request.topology, inputVoltageV: textNumber(request.input_voltage_v),
    outputVoltageV: textNumber(request.output_voltage_v), outputCurrentA: textNumber(request.output_current_a),
    switchingFrequencyHz: textNumber(request.switching_frequency_hz), switches: [group("on"), group("off")],
    inductor: { occurrence_id: request.inductor.occurrence_id, component_ref: request.inductor.component_ref,
      inductanceH: textNumber(request.inductor.inductance_h), dcrOhm: textNumber(request.inductor.dcr_ohm),
      currentRatingA: textNumber(request.inductor.current_rating_a) },
  };
}

export function createSyntheticSmpsDraft(components: SmpsComponentOption[] = []): SmpsConverterDraft {
  const draft = createEmptySmpsDraft();
  draft.blockId = "synthetic-buck-example";
  draft.inputVoltageV = "12"; draft.outputVoltageV = "5"; draft.outputCurrentA = "2";
  draft.switchingFrequencyHz = "500000";
  draft.switches = (["on", "off"] as const).map((role, index) => ({
    ...emptySwitch(role), devices: components.length ? [emptyBinding()] : [{ occurrence_id: "synthetic-demo", component_ref: `Q${index + 1}` }],
    rdsOnOhm: index === 0 ? "0.015" : "0.01", riseTimeS: "1e-8", fallTimeS: "1e-8",
    gateChargeC: "2e-8", gateDriveV: "5", voltageRatingV: "30", currentRatingA: "20",
  })) as [SwitchDraft, SwitchDraft];
  draft.inductor = { ...(components.length ? emptyBinding() : { occurrence_id: "synthetic-demo", component_ref: "L1" }),
    inductanceH: "1e-5", dcrOhm: "0.02", currentRatingA: "4" };
  return draft;
}

const identity = (binding: SmpsBinding) => JSON.stringify([binding.occurrence_id, binding.component_ref]);
const optionBinding = (option: SmpsComponentOption): SmpsBinding => ({ occurrence_id: option.occurrenceId, component_ref: option.reference });
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const numberFrom = (value: string, label: string, positive = false) => {
  if (!value.trim()) throw new Error(`${label} is required.`);
  const parsed = Number(value);
  if (!finite(parsed) || (positive ? parsed <= 0 : parsed < 0)) throw new Error(`${label} must be a finite ${positive ? "positive" : "nonnegative"} value.`);
  return parsed;
};
const signedNumberFrom = (value: string, label: string) => {
  if (!value.trim()) throw new Error(`${label} is required.`);
  const parsed = Number(value);
  if (!finite(parsed)) throw new Error(`${label} must be finite.`);
  return parsed;
};
const countFrom = (value: string, label: string) => {
  const parsed = numberFrom(value, label, true);
  if (!Number.isInteger(parsed) || parsed > 64) throw new Error(`${label} must be an integer from 1 to 64.`);
  return parsed;
};
const requireBinding = (binding: SmpsBinding, label: string, available: Set<string> | null) => {
  if (!binding.occurrence_id.trim() || !binding.component_ref.trim()) throw new Error(`${label} requires an occurrence and component reference.`);
  if (available && !available.has(identity(binding))) throw new Error(`${label} must select a component from the loaded board.`);
  return { occurrence_id: binding.occurrence_id.trim(), component_ref: binding.component_ref.trim() };
};

export function buildSmpsConverterRequest(draft: SmpsConverterDraft, components: SmpsComponentOption[] = []): SmpsConverterRequest {
  if (!draft.blockId.trim()) throw new Error("Block ID is required.");
  const available = components.length ? new Set(components.map(item => identity(optionBinding(item)))) : null;
  const inputVoltage = numberFrom(draft.inputVoltageV, "Input voltage", true);
  const outputVoltage = signedNumberFrom(draft.outputVoltageV, "Output voltage");
  const outputCurrent = numberFrom(draft.outputCurrentA, "Output current", true);
  const frequency = numberFrom(draft.switchingFrequencyHz, "Switching frequency", true);
  if (outputVoltage === 0) throw new Error("Output voltage must be nonzero.");
  if (draft.topology === "synchronous_buck" && !(outputVoltage > 0 && outputVoltage < inputVoltage)) throw new Error("Synchronous buck requires 0 < Vout < Vin.");
  if (draft.topology === "synchronous_boost" && !(outputVoltage > inputVoltage)) throw new Error("Synchronous boost requires Vout > Vin.");
  if (draft.topology === "inverting_buck_boost" && outputVoltage >= 0) throw new Error("Inverting buck-boost requires a negative output voltage.");
  const seen = new Set<string>();
  const switches = draft.switches.map(source => {
    const series = countFrom(source.seriesCount, `${source.role} series count`);
    const parallel = countFrom(source.parallelCount, `${source.role} parallel count`);
    const count = series * parallel;
    if (count > 64 || source.devices.length !== count) throw new Error(`${source.role} device slots must equal series count x parallel count, at most 64.`);
    const devices = source.devices.map((item, index) => {
      const binding = requireBinding(item, `${source.role} device ${index + 1}`, available);
      const key = identity(binding);
      if (seen.has(key)) throw new Error(`${binding.component_ref} in ${binding.occurrence_id} is reused across converter roles.`);
      seen.add(key); return binding;
    });
    const rise = numberFrom(source.riseTimeS, `${source.role} rise time`);
    const fall = numberFrom(source.fallTimeS, `${source.role} fall time`);
    if ((rise + fall) * frequency > 0.1) throw new Error(`${source.role} rise plus fall time must be at most 10% of a switching period.`);
    return { role: source.role, devices, series_count: series, parallel_count: parallel,
      rds_on_ohm: numberFrom(source.rdsOnOhm, `${source.role} Rds(on)`), rise_time_s: rise, fall_time_s: fall,
      gate_charge_c: numberFrom(source.gateChargeC, `${source.role} gate charge`), gate_drive_v: numberFrom(source.gateDriveV, `${source.role} gate drive voltage`),
      voltage_rating_v: numberFrom(source.voltageRatingV, `${source.role} voltage rating`, true),
      current_rating_a: numberFrom(source.currentRatingA, `${source.role} current rating`, true) };
  }) as [SmpsSwitchGroup, SmpsSwitchGroup];
  const inductorBinding = requireBinding(draft.inductor, "Inductor", available);
  if (seen.has(identity(inductorBinding))) throw new Error(`${inductorBinding.component_ref} in ${inductorBinding.occurrence_id} is reused as both a switch and inductor.`);
  return { contract: "spike/smps-converter-request/v1", block_id: draft.blockId.trim(), topology: draft.topology,
    input_voltage_v: inputVoltage, output_voltage_v: outputVoltage, output_current_a: outputCurrent,
    switching_frequency_hz: frequency, switches, inductor: { ...inductorBinding,
      inductance_h: numberFrom(draft.inductor.inductanceH, "Inductance", true),
      dcr_ohm: numberFrom(draft.inductor.dcrOhm, "Inductor DCR"),
      current_rating_a: numberFrom(draft.inductor.currentRatingA, "Inductor current rating", true) } };
}

const near = (a: number, b: number) => Math.abs(a - b) <= 1e-8 * Math.max(1, Math.abs(a), Math.abs(b));
const canonicalJson = (value: unknown) => {
  const ancestors = new Set<object>();
  let visited = 0;
  const visit = (item: unknown, depth: number): string => {
    if (++visited > 2048 || depth > 32) throw new Error("JSON value exceeds the comparison envelope.");
    if (item === null) return "null";
    if (typeof item === "string" || typeof item === "boolean") return JSON.stringify(item);
    if (typeof item === "number") {
      if (!Number.isFinite(item)) throw new Error("JSON numbers must be finite.");
      return JSON.stringify(item);
    }
    if (typeof item !== "object") throw new Error("Value is not JSON-compatible.");
    if (ancestors.has(item)) throw new Error("JSON value is cyclic.");
    ancestors.add(item);
    let output: string;
    if (Array.isArray(item)) output = `[${item.map(entry => visit(entry, depth + 1)).join(",")}]`;
    else {
      const record = item as Record<string, unknown>;
      output = `{${Object.keys(record).sort().map(key => `${JSON.stringify(key)}:${visit(record[key], depth + 1)}`).join(",")}}`;
    }
    ancestors.delete(item);
    return output;
  };
  return visit(value, 0);
};
const canonicallyEqual = (left: unknown, right: unknown) => {
  try { return canonicalJson(left) === canonicalJson(right); }
  catch { return false; }
};
export function validSmpsConverterResult(raw: unknown, request?: SmpsConverterRequest | null): raw is SmpsConverterResult {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return false;
  const result = raw as SmpsConverterResult;
  const scalars = [result.duty_cycle, result.input_current_a, result.input_power_w, result.output_power_w, result.total_loss_w,
    result.efficiency, result.inductor_average_current_a, result.inductor_rms_current_a, result.inductor_peak_current_a,
    result.inductor_minimum_current_a, result.inductor_ripple_current_a, result.auxiliary_loss_w];
  if (result.contract !== "spike/smps-converter-result/v1" || !["synchronous_buck", "synchronous_boost", "inverting_buck_boost"].includes(result.topology)
    || !result.request_snapshot || typeof result.request_snapshot !== "object" || Array.isArray(result.request_snapshot)
    || result.request_snapshot.contract !== "spike/smps-converter-request/v1"
    || result.request_snapshot.block_id !== result.block_id || result.request_snapshot.topology !== result.topology
    || result.model_status !== "approximate"
    || result.temporal_scope !== "steady_average_only" || result.auxiliary_loss_location !== "unassigned_gate_drive"
    || !scalars.every(finite) || result.duty_cycle <= 0 || result.duty_cycle >= 1 || result.efficiency <= 0 || result.efficiency > 1
    || result.input_current_a <= 0 || result.input_power_w <= 0 || result.output_power_w <= 0
    || result.total_loss_w < 0 || result.auxiliary_loss_w < 0 || result.inductor_minimum_current_a <= 0
    || result.inductor_average_current_a <= 0 || result.inductor_rms_current_a <= 0
    || result.inductor_peak_current_a < result.inductor_minimum_current_a || result.inductor_ripple_current_a < 0
    || !Array.isArray(result.losses) || !result.solver || !Number.isInteger(result.solver.iterations) || result.solver.iterations < 1
    || ![result.solver.duty_bracket_width, result.solver.periodic_current_residual_a, result.solver.energy_balance_residual_w].every(finite)
    || result.solver.duty_bracket_width < 0
    || !Array.isArray(result.limitations) || !result.limitations.every(item => typeof item === "string" && item.length > 0)) return false;
  if (!result.losses.every(row => row && ["on", "off", "inductor"].includes(row.role)
    && typeof row.occurrence_id === "string" && row.occurrence_id.length > 0 && typeof row.component_ref === "string" && row.component_ref.length > 0
    && [row.conduction_power_w, row.switching_power_w, row.total_power_w].every(value => finite(value) && value >= 0)
    && near(row.total_power_w, row.conduction_power_w + row.switching_power_w))
    || new Set(result.losses.map(identity)).size !== result.losses.length) return false;
  if (!near(result.efficiency, result.output_power_w / result.input_power_w)
    || !near(result.input_power_w - result.output_power_w - result.total_loss_w, result.solver.energy_balance_residual_w)
    || !near(result.total_loss_w, result.losses.reduce((sum, row) => sum + row.total_power_w, 0) + result.auxiliary_loss_w)) return false;
  if (!request) return true;
  if (!canonicallyEqual(result.request_snapshot, request)) return false;
  const expected = new Map<string, string>();
  for (const group of request.switches) for (const item of group.devices) expected.set(identity(item), group.role);
  expected.set(identity(request.inductor), "inductor");
  return result.losses.length === expected.size && result.losses.every(row => expected.get(identity(row)) === row.role);
}

const resizeBindings = (items: SmpsBinding[], count: number) => Array.from({ length: count }, (_, index) => items[index] ?? emptyBinding());
const format = (value: number, digits = 5) => value.toLocaleString(undefined, { maximumSignificantDigits: digits });
const topologyName = (value: SmpsConverterRequest["topology"]) => ({
  synchronous_buck: "Synchronous buck", synchronous_boost: "Synchronous boost", inverting_buck_boost: "Inverting buck-boost",
})[value];

function BindingControl({ binding, label, components, selected, disabled, onChange }: {
  binding: SmpsBinding; label: string; components: SmpsComponentOption[]; selected: Set<string>; disabled: boolean; onChange: (value: SmpsBinding) => void;
}) {
  if (!components.length) return <div className="smps-binding smps-binding--manual">
    <label><span>{label} occurrence</span><input aria-label={`${label} occurrence`} value={binding.occurrence_id} disabled={disabled} onChange={event => onChange({ ...binding, occurrence_id: event.target.value })} /></label>
    <label><span>{label} reference</span><input aria-label={`${label} reference`} value={binding.component_ref} disabled={disabled} onChange={event => onChange({ ...binding, component_ref: event.target.value })} /></label>
  </div>;
  const own = identity(binding);
  return <label className="smps-binding"><span>{label}</span><select aria-label={label} value={own === identity(emptyBinding()) ? "" : own} disabled={disabled} onChange={event => {
    const option = components.find(item => identity(optionBinding(item)) === event.target.value);
    onChange(option ? optionBinding(option) : emptyBinding());
  }}><option value="">Select loaded-board component…</option>{components.map(option => {
    const value = identity(optionBinding(option));
    return <option key={value} value={value} disabled={value !== own && selected.has(value)}>{option.reference}{option.label ? ` — ${option.label}` : ""} · {option.occurrenceId}</option>;
  })}</select></label>;
}

const numericFields: Array<{ key: keyof Omit<SwitchDraft, "role" | "devices" | "seriesCount" | "parallelCount">; label: string; unit: string; positive?: boolean }> = [
  { key: "rdsOnOhm", label: "Per-device Rds(on)", unit: "ohm" }, { key: "riseTimeS", label: "Rise time", unit: "s" },
  { key: "fallTimeS", label: "Fall time", unit: "s" }, { key: "gateChargeC", label: "Gate charge", unit: "C" },
  { key: "gateDriveV", label: "Gate drive", unit: "V" }, { key: "voltageRatingV", label: "Voltage rating", unit: "V", positive: true },
  { key: "currentRatingA", label: "Current rating", unit: "A", positive: true },
];

function ResultView({ request, result }: { request: SmpsConverterRequest; result: SmpsConverterResult }) {
  const blocking = request.topology === "synchronous_buck" ? request.input_voltage_v
    : request.topology === "synchronous_boost" ? Math.abs(request.output_voltage_v)
      : request.input_voltage_v + Math.abs(request.output_voltage_v);
  const balanceLimit = 1e-8 * Math.max(result.input_power_w, result.output_power_w, 1e-12);
  return <div className="smps-results">
    <div className="smps-result-heading"><div><strong>APPROXIMATE · STEADY AVERAGE ONLY</strong><span>{topologyName(result.topology)}</span></div><span>CCM admitted</span></div>
    <div className="smps-balance" aria-label="Converter power balance"><span>Input <b>{format(result.input_power_w)} W</b></span><i>=</i><span>Output <b>{format(result.output_power_w)} W</b></span><i>+</i><span>Loss <b>{format(result.total_loss_w)} W</b></span><small>Residual {format(result.solver.energy_balance_residual_w)} W · tolerance {format(balanceLimit)} W</small></div>
    <dl className="smps-metrics">
      <div><dt>Efficiency</dt><dd>{format(result.efficiency * 100)}%</dd></div><div><dt>Duty cycle</dt><dd>{format(result.duty_cycle * 100)}%</dd></div>
      <div><dt>Input current</dt><dd>{format(result.input_current_a)} A</dd></div><div><dt>Inductor ripple</dt><dd>{format(result.inductor_ripple_current_a)} A pk-pk</dd></div>
      <div><dt>Inductor minimum</dt><dd>{format(result.inductor_minimum_current_a)} A</dd></div><div><dt>Inductor peak</dt><dd>{format(result.inductor_peak_current_a)} A</dd></div>
      <div><dt>Inductor average</dt><dd>{format(result.inductor_average_current_a)} A</dd></div><div><dt>Inductor RMS</dt><dd>{format(result.inductor_rms_current_a)} A</dd></div>
    </dl>
    <section className="smps-result-section"><h5>Supplied rating checks</h5><div className="smps-table-wrap"><table><thead><tr><th>Role</th><th>Per-device voltage</th><th>Rating</th><th>Per-device peak current</th><th>Rating</th></tr></thead><tbody>
      {request.switches.map(group => <tr key={group.role}><td>{group.role}</td><td>{format(blocking / group.series_count)} V</td><td>{format(group.voltage_rating_v)} V</td><td>{format(result.inductor_peak_current_a / group.parallel_count)} A</td><td>{format(group.current_rating_a)} A</td></tr>)}
      <tr><td>inductor</td><td colSpan={2}>n/a</td><td>{format(result.inductor_peak_current_a)} A</td><td>{format(request.inductor.current_rating_a)} A</td></tr>
    </tbody></table></div></section>
    <section className="smps-result-section"><h5>Component loss ledger</h5><div className="smps-table-wrap"><table><thead><tr><th>Occurrence</th><th>Reference</th><th>Role</th><th>Conduction</th><th>Switching</th><th>Total</th></tr></thead><tbody>{result.losses.map(row => <tr key={`${row.occurrence_id}:${row.component_ref}`}><td title={row.occurrence_id}>{row.occurrence_id}</td><td>{row.component_ref}</td><td>{row.role}</td><td>{format(row.conduction_power_w)} W</td><td>{format(row.switching_power_w)} W</td><td>{format(row.total_power_w)} W</td></tr>)}</tbody></table></div>
      <p className="smps-gate-note"><strong>Unassigned gate-drive heat:</strong> {format(result.auxiliary_loss_w)} W. It is included in total loss and is not deposited on a selected component.</p>
    </section>
    <p className="smps-scope-note">No switching waveform, control-loop stability, transient response, or hardware qualification is claimed by this result.</p>
    <details><summary>Model limits and solver evidence</summary><p>{result.solver.iterations} root iterations · duty bracket {format(result.solver.duty_bracket_width)} · periodic residual {format(result.solver.periodic_current_residual_a)} A</p><ul>{result.limitations.map(item => <li key={item}>{item}</li>)}</ul></details>
  </div>;
}

export default function SmpsConverterPanel({ workerAvailable, components, initialRequest, initialResult, onResult, onStatus }: SmpsConverterPanelProps) {
  const [draft, setDraft] = useState<SmpsConverterDraft>(() => draftFromRequest(initialRequest));
  const admittedInitial = validSmpsConverterResult(initialResult, initialRequest);
  const [result, setResult] = useState<SmpsConverterResult | null>(() => admittedInitial ? initialResult : null);
  const [resultRequest, setResultRequest] = useState<SmpsConverterRequest | null>(() => admittedInitial ? initialRequest ?? null : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const runSequence = useRef(0);
  useEffect(() => () => { runSequence.current += 1; }, []);
  const patchDraft = <K extends keyof SmpsConverterDraft>(key: K, value: SmpsConverterDraft[K]) => setDraft(current => ({ ...current, [key]: value }));
  const patchSwitch = (index: number, patch: Partial<SwitchDraft>) => setDraft(current => {
    const switches = current.switches.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) as [SwitchDraft, SwitchDraft];
    return { ...current, switches };
  });
  const selected = new Set([...draft.switches.flatMap(group => group.devices), draft.inductor].filter(item => item.occurrence_id && item.component_ref).map(identity));
  const run = async () => {
    const sequence = ++runSequence.current;
    let request: SmpsConverterRequest;
    try { request = buildSmpsConverterRequest(draft, components); }
    catch (caught) { const message = caught instanceof Error ? caught.message : String(caught); setError(message); onStatus?.(`Converter input error: ${message}`); return; }
    setBusy(true); setError(""); onStatus?.("Running approximate steady CCM converter estimate…");
    try {
      const id = globalThis.crypto?.randomUUID?.() ?? `smps-converter-${Date.now()}-${sequence}`;
      const response = await runLocalWorker({ id, method: "run_smps_converter", params: { request } });
      if (runSequence.current !== sequence) return;
      if (!response.ok || !response.result) throw new Error(response.error ?? "Converter worker returned no result.");
      if (!validSmpsConverterResult(response.result, request)) throw new Error("Converter worker returned a malformed or unsupported result.");
      setResult(response.result); setResultRequest(request); onResult?.(request, response.result);
      onStatus?.("Steady CCM converter estimate completed.");
    } catch (caught) {
      if (runSequence.current !== sequence) return;
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message); onStatus?.(`Converter estimate failed: ${message}`);
    } finally { if (runSequence.current === sequence) setBusy(false); }
  };
  let currentRequest: SmpsConverterRequest | null = null;
  try { currentRequest = buildSmpsConverterRequest(draft, components); } catch { /* Run reports actionable validation. */ }
  const stale = Boolean(result && resultRequest && JSON.stringify(resultRequest) !== JSON.stringify(currentRequest));
  return <section className="smps-panel" aria-labelledby="smps-panel-heading">
    <header><div><p className="smps-eyebrow">Power integrity · converter block</p><h4 id="smps-panel-heading">MOSFET and inductor loss estimate</h4></div><span className="smps-badge">Approximate CCM</span></header>
    <p className="smps-intro">Declare one synchronous topology, every physical switch slot, and one inductor. Values remain caller supplied; SPIKE does not look up or infer device properties from a board reference.</p>
    <div className="smps-toolbar"><button type="button" className="spike-control--compact" disabled={busy} onClick={() => { setDraft(createSyntheticSmpsDraft(components)); setError(""); }}>Fill labeled synthetic example</button><span>{components.length ? `${components.length} loaded-board component choices. Synthetic values do not select or characterize them.` : "No board components loaded. Manual occurrence and reference fields are enabled."}</span></div>
    <fieldset disabled={busy}><legend>Operating point</legend><div className="smps-operating-grid">
      <label><span>Block ID</span><input aria-label="Converter block ID" value={draft.blockId} onChange={event => patchDraft("blockId", event.target.value)} /></label>
      <label><span>Topology</span><select aria-label="Converter topology" value={draft.topology} onChange={event => patchDraft("topology", event.target.value as SmpsConverterRequest["topology"])}><option value="synchronous_buck">Synchronous buck</option><option value="synchronous_boost">Synchronous boost</option><option value="inverting_buck_boost">Inverting buck-boost</option></select></label>
      {[{ key: "inputVoltageV", label: "Input voltage", unit: "V" }, { key: "outputVoltageV", label: "Output voltage", unit: "V" }, { key: "outputCurrentA", label: "Output current magnitude", unit: "A" }, { key: "switchingFrequencyHz", label: "Switching frequency", unit: "Hz" }].map(field => <label key={field.key}><span>{field.label}<small>{field.unit}</small></span><input aria-label={`${field.label} (${field.unit})`} type="number" step="any" value={draft[field.key as keyof Pick<SmpsConverterDraft, "inputVoltageV" | "outputVoltageV" | "outputCurrentA" | "switchingFrequencyHz">]} onChange={event => patchDraft(field.key as keyof SmpsConverterDraft, event.target.value as never)} /></label>)}
    </div></fieldset>
    <div className="smps-switch-grid">{draft.switches.map((group, groupIndex) => {
      const title = group.role === "on" ? "On-interval switch group" : "Off-interval switch group";
      return <fieldset key={group.role} disabled={busy}><legend>{title}</legend><p>Identical devices: {group.parallelCount || "?"} parallel string(s), {group.seriesCount || "?"} in series per string.</p><div className="smps-count-grid">
        {([{ key: "seriesCount", label: "Series devices" }, { key: "parallelCount", label: "Parallel strings" }] as const).map(field => <label key={field.key}><span>{field.label}</span><input aria-label={`${title} ${field.label}`} type="number" min="1" max="64" step="1" value={group[field.key]} onChange={event => {
          const nextValue = event.target.value; const other = field.key === "seriesCount" ? group.parallelCount : group.seriesCount;
          const count = Number(nextValue) * Number(other); patchSwitch(groupIndex, { [field.key]: nextValue, devices: Number.isInteger(count) && count >= 1 && count <= 64 ? resizeBindings(group.devices, count) : group.devices });
        }} /></label>)}
      </div><div className="smps-device-list">{group.devices.map((binding, deviceIndex) => <BindingControl key={deviceIndex} binding={binding} label={`${group.role} device ${deviceIndex + 1}`} components={components} selected={selected} disabled={busy} onChange={value => patchSwitch(groupIndex, { devices: group.devices.map((item, index) => index === deviceIndex ? value : item) })} />)}</div>
      <div className="smps-property-grid">{numericFields.map(field => <label key={field.key}><span>{field.label}<small>{field.unit}</small></span><input aria-label={`${group.role} ${field.label} (${field.unit})`} type="number" step="any" min={field.positive ? "0" : undefined} value={group[field.key]} onChange={event => patchSwitch(groupIndex, { [field.key]: event.target.value })} /></label>)}</div></fieldset>;
    })}</div>
    <fieldset disabled={busy}><legend>Inductor</legend><BindingControl binding={draft.inductor} label="Inductor component" components={components} selected={selected} disabled={busy} onChange={value => patchDraft("inductor", { ...draft.inductor, ...value })} /><div className="smps-property-grid">
      {[{ key: "inductanceH", label: "Inductance", unit: "H" }, { key: "dcrOhm", label: "DCR", unit: "ohm" }, { key: "currentRatingA", label: "Current rating", unit: "A" }].map(field => <label key={field.key}><span>{field.label}<small>{field.unit}</small></span><input aria-label={`Inductor ${field.label} (${field.unit})`} type="number" step="any" min="0" value={draft.inductor[field.key as keyof Pick<typeof draft.inductor, "inductanceH" | "dcrOhm" | "currentRatingA">]} onChange={event => patchDraft("inductor", { ...draft.inductor, [field.key]: event.target.value })} /></label>)}
    </div></fieldset>
    <p className="smps-boundary-note">Enter operating-temperature Rds(on) and DCR, per-device transition and gate values, and supplied ratings. Zero explicitly idealizes an admitted loss term; blank means unauthored and blocks a run.</p>
    <div className="smps-actions"><button type="button" className="spike-control--primary" disabled={!workerAvailable || busy} onClick={() => void run()}>{busy ? "Running converter estimate…" : "Run converter estimate"}</button><span aria-live="polite">{!workerAvailable ? "Local solver worker unavailable." : busy ? "Solver request in progress." : "Ready for a local approximate run."}</span></div>
    {error && <p className="smps-error" role="alert">{error} {result ? "The last valid result remains visible." : "Review the authored inputs and run again."}</p>}
    {stale && <p className="smps-stale" role="status">Inputs differ from the solved setup. Results below show the previous solver request.</p>}
    {result && resultRequest ? <ResultView request={resultRequest} result={result} /> : <div className="smps-empty">Author all component bindings and device values, then run the worker. No loss values are estimated in the browser.</div>}
  </section>;
}
