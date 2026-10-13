// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import type { AssemblyIr } from "./mcadAssembly";
import type { FieldObject } from "./assemblyFieldStudyPresentation";
import { assertFieldAssembly } from "./assemblyFieldStudyPresentation";
import AssemblyThermalVolumeViewer from "./AssemblyThermalVolumeViewer";
import DataTable from "./DataTable";
import { runLocalWorker, runNativeProjectWorker, type WorkerResponse } from "./workerBridge";
import { runSerializedAutomaticWorker } from "./automaticWorkerQueue";
import "./buttonStandard.css";
import "./assemblyFieldStudyEditor.css";

type RecordValue = { request: FieldObject; result: FieldObject | null };
const format = (value: unknown) => JSON.stringify(value, null, 2);
function value(response: WorkerResponse): FieldObject {
  if (!response.ok || !response.result) throw new Error([response.error_code, response.error, response.error_detail?.detail].filter(Boolean).join(" · ") || "Volume electrothermal worker returned no data.");
  return response.result;
}

/** Explicit reduced circuit loss bindings; all numerical admission stays in the worker. */
export default function VolumeElectrothermalEditor({ assembly, fieldRequest, fieldProblem, projectPath, manifestDigest,
  disabled, onUpdated, onStatus, onDirtyChange }: {
  assembly: AssemblyIr; fieldRequest: FieldObject | null; fieldProblem: FieldObject | null;
  projectPath: string | null; manifestDigest: string | null; disabled: boolean;
  onUpdated: () => Promise<void>; onStatus: (message: string) => void; onDirtyChange?: (dirty: boolean) => void;
}) {
  const [text, setText] = useState("");
  const [domain, setDomain] = useState<"pi" | "si">("pi");
  const [prepared, setPrepared] = useState<FieldObject | null>(null);
  const [preparedText, setPreparedText] = useState("");
  const [result, setResult] = useState<FieldObject | null>(null);
  const [handoff, setHandoff] = useState<FieldObject | null>(null);
  const [bindingHelp, setBindingHelp] = useState<FieldObject | null>(null);
  const [baseline, setBaseline] = useState<{ text: string; result: FieldObject | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);
  const generation = useRef(0);
  const saved = useRef<{ record: RecordValue; handoff: FieldObject | null } | null>(null);
  const pending = useRef<{ key: string; promise: Promise<FieldObject | undefined> } | null>(null);
  const dirty = baseline !== null && (text !== baseline.text || result !== baseline.result);
  const locked = disabled || busy || loading || !projectPath || !manifestDigest;
  const ready = !!prepared && text === preparedText;
  const retained = (assembly.extensions as FieldObject | undefined)?.["spike.multiboard-studies"]?.[domain]?.request;
  let editableDraft: FieldObject | null = null;
  try {
    const candidate = text.length <= 8 * 1024 * 1024 ? JSON.parse(text) : null;
    if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) editableDraft = candidate;
  } catch { /* Incomplete JSON remains editable; prepare provides its error. */ }
  useEffect(() => { onDirtyChange?.(dirty || busy); }, [dirty, busy, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);

  useEffect(() => {
    const token = ++generation.current;
    let active = true;
    setText(""); setResult(null); setHandoff(null); setPrepared(null); setPreparedText(""); setBindingHelp(null);
    setBaseline(null); setError(""); setMessage(""); setBusy(false); saved.current = null;
    if (!projectPath || !manifestDigest) { setLoading(false); return; }
    setLoading(true);
    const key = `${projectPath}\u0000${manifestDigest}\u0000${reload}`;
    if (!pending.current || pending.current.key !== key) {
      const entry = { key, promise: Promise.resolve(undefined) as Promise<FieldObject | undefined> };
      pending.current = entry;
      entry.promise = runSerializedAutomaticWorker(async () => {
        const read = value(await runNativeProjectWorker({ method: "read_volume_electrothermal_in_project", params: {
          project_path: projectPath, expected_manifest_payload_sha256: manifestDigest,
        } }));
        const currentResult = read.state === "current" ? read.record?.result : null;
        const preview = currentResult ? value(await runLocalWorker({ method: "prepare_assembly_field_handoff", params: { request: currentResult.thermal_geometry } })) : null;
        return { read, preview };
      }, () => pending.current === entry);
      void entry.promise.finally(() => { if (pending.current === entry) pending.current = null; }).catch(() => {});
    }
    void pending.current.promise.then(loaded => {
      if (!loaded || !active || token !== generation.current) return;
      const read = loaded.read;
      if (read.state === "current" && read.record) {
        const record = read.record as RecordValue;
        const serialized = format(record.request);
        setText(serialized); setResult(record.result); setHandoff(loaded.preview);
        saved.current = { record, handoff: loaded.preview };
        setBaseline({ text: serialized, result: record.result });
        setMessage(record.result ? "Saved electrothermal result verified against the current project." : "Saved electrothermal setup loaded. Prepare it before running.");
      } else {
        setBaseline({ text: "", result: null });
        if (read.state === "stale") setError(read.action || read.message || "Saved electrothermal study is stale. Review the current geometry and circuit before preparing a new study.");
        else setMessage("No saved volume electrothermal study. Start with the current volumes and a saved PI or SI circuit setup.");
      }
    }).catch(caught => { if (active && token === generation.current) { setError(String(caught)); setBaseline({ text: "", result: null }); } })
      .finally(() => { if (active && token === generation.current) setLoading(false); });
    return () => { active = false; generation.current++; };
  }, [projectPath, manifestDigest, reload]);

  const action = async (work: (token: number) => Promise<void>) => {
    if (locked) return;
    const token = generation.current;
    setBusy(true); setError("");
    try { await work(token); }
    catch (caught) { if (token === generation.current) { setError(String(caught)); onStatus(String(caught)); } }
    finally { if (token === generation.current) setBusy(false); }
  };
  const parse = () => {
    if (new TextEncoder().encode(text).length > 8 * 1024 * 1024) throw new Error("Volume electrothermal request exceeds 8 MiB.");
    const request = JSON.parse(text);
    if (!request || typeof request !== "object" || Array.isArray(request)) throw new Error("Volume electrothermal request must be a JSON object.");
    if (!fieldRequest) throw new Error("Prepare the current assembly volumes before preparing this coupled study.");
    assertFieldAssembly(request.geometry ?? {}, fieldRequest.assembly);
    return request as FieldObject;
  };
  const seed = () => {
    if (locked || !fieldRequest || !fieldProblem || !retained) return;
    generation.current++;
    const request = { contract: "spike/multiboard-volume-electrothermal-request/v1", geometry: fieldRequest,
      thermal_problem: fieldProblem, circuit: retained, loss_bindings: [], loss_accounting: "exhaustive_resistor_losses",
      thermal_engine: "internal", iteration: { initial_temperature_k: 300, max_iterations: 30, relaxation: 0.5,
        temperature_tolerance_k: 0.001, power_relative_tolerance: 0.0001 },
      ...(domain === "si" ? { ac_heating: { frequency_hz: null, phasor_convention: null } } : {}) };
    setText(format(request)); setResult(null); setHandoff(null); setPrepared(null); setPreparedText(""); setBindingHelp(null); setError("");
    setMessage("Draft copied. Add every compiled resistor loss mapping and its explicit temperature law; review the iteration settings. SI also needs one frequency and an RMS or peak convention.");
  };
  const chooseSolver = (engine: string) => {
    if (locked || !editableDraft || !["internal", "calculix"].includes(engine)) return;
    generation.current++;
    const changed: FieldObject = { ...editableDraft, thermal_engine: engine };
    if (engine === "internal") delete changed.thermal_engine_options;
    setText(format(changed)); setResult(null); setHandoff(null); setPrepared(null); setPreparedText(""); setBindingHelp(null); setError("");
    setMessage("Thermal solver changed. Prepare the coupled study again before running.");
  };
  const inspectIds = () => action(async token => {
    if (!fieldRequest) throw new Error("Prepare the current assembly volumes before inspecting binding IDs.");
    const circuit = text.trim() ? parse().circuit : retained;
    if (!circuit || typeof circuit !== "object" || Array.isArray(circuit)) throw new Error("Select a saved circuit or provide circuit in the coupled request JSON.");
    const answer = value(await runLocalWorker({ method: "describe_volume_electrothermal_bindings", params: { geometry: fieldRequest, circuit } }));
    if (token !== generation.current) return;
    if (!Array.isArray(answer.resistors) || answer.resistors.length > 20000 || !Array.isArray(answer.occurrences) ||
      answer.occurrences.length > 1000 || answer.occurrences.some((row: FieldObject) => !Array.isArray(row.cell_ids)) ||
      answer.occurrences.reduce((count: number, row: FieldObject) => count + row.cell_ids.length, 0) > 10000) {
      throw new Error("Binding ID inventory is malformed or exceeds the bounded table budget.");
    }
    setBindingHelp(answer); setMessage("Compiled resistor and retained volume IDs are available below. Inspection does not create loss mappings or run a solver.");
  });
  const prepare = () => action(async token => {
    const request = parse();
    const answer = value(await runLocalWorker({ method: "prepare_multiboard_volume_electrothermal", params: { request } }));
    if (token !== generation.current) return;
    setPrepared(answer); setPreparedText(text); setHandoff(answer.handoff ?? null); setResult(null);
    setMessage("Circuit, volume loss mappings and thermal setup admitted. Ready for an experimental steady coupled solve.");
  });
  const run = () => action(async token => {
    if (!ready) return;
    const request = parse();
    const computed = value(await runLocalWorker({ method: "run_multiboard_volume_electrothermal", params: { request } }));
    if (token !== generation.current) return;
    const admitted = value(await runLocalWorker({ method: "verify_multiboard_volume_electrothermal_result", params: { request, result: computed } }));
    if (token !== generation.current) return;
    const preview = value(await runLocalWorker({ method: "prepare_assembly_field_handoff", params: { request: admitted.thermal_geometry } }));
    if (token !== generation.current) return;
    setResult(admitted); setHandoff(preview);
    setMessage("Experimental coupled solve completed and verified. Save to retain its result in this project.");
  });
  const save = () => action(async token => {
    if (!ready && !result) return;
    const request = parse();
    const record = { request, result };
    value(await runNativeProjectWorker({ method: "save_volume_electrothermal_in_project", params: {
      project_path: projectPath, expected_manifest_payload_sha256: manifestDigest, record,
    } }));
    if (token !== generation.current) return;
    setBaseline({ text, result }); saved.current = { record, handoff };
    await onUpdated(); onStatus("Volume electrothermal study saved in the current project.");
  });
  const reset = () => {
    if (locked || !baseline) return;
    generation.current++;
    setText(baseline.text); setResult(saved.current?.record.result ?? null); setHandoff(saved.current?.handoff ?? null);
    setPrepared(null); setPreparedText(""); setBindingHelp(null); setError(""); setMessage("Draft restored to the last saved study.");
  };
  const rows = Array.isArray(result?.electrical?.losses) ? result.electrical.losses : [];
  const packageParts = (fieldRequest?.assembly?.parts ?? []).filter((part: FieldObject) => part.extensions?.["spike.thermal-component"]?.contract === "spike/thermal-component-provenance/v1");
  const editCircuit = (change: (circuit: FieldObject) => void) => {
    if (locked || !editableDraft?.circuit || typeof editableDraft.circuit !== "object") return;
    const changed = JSON.parse(text) as FieldObject;
    change(changed.circuit);
    generation.current++; setText(format(changed)); setPrepared(null); setPreparedText(""); setResult(null); setHandoff(null); setBindingHelp(null); setError("");
    setMessage("Circuit assembly or thermal-only package declaration changed. Review the circuit models and prepare again.");
  };
  return <section className="assembly-field-study" aria-label="PI SI volume electrothermal study">
    <h4>PI / SI circuit and volume thermal coupling</h4>
    <p>Couple the internal reduced circuit to admitted thermal volumes. Every resistor needs an explicit occurrence/cell heat distribution and temperature law. This is an experimental steady study; SI uses one sinusoidal frequency.</p>
    {!projectPath && <p role="status">Save and open the project to retain a coupled study.</p>}
    {loading && <p role="status">Checking the saved coupled study...</p>}
    {busy && <p role="status">Working on the coupled study...</p>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
    <div className="assembly-field-actions">
      <label>Saved circuit domain<select aria-label="Volume coupled circuit domain" disabled={locked} value={domain} onChange={event => { setDomain(event.target.value as "pi" | "si"); setBindingHelp(null); }}><option value="pi">PI - DC operating point</option><option value="si">SI - one AC frequency</option></select></label>
      <button type="button" disabled={locked || !fieldRequest || !fieldProblem || !retained} onClick={seed}>Copy current volumes and saved circuit</button>
      <button type="button" disabled={locked || !fieldRequest || (!text.trim() && !retained)} onClick={() => void inspectIds()}>Show resistor and volume IDs</button>
      <button type="button" disabled={locked || dirty} onClick={() => setReload(count => count + 1)}>Load saved coupled study</button>
      <button type="button" disabled={locked || !dirty} onClick={reset}>Reset coupled draft</button>
    </div>
    {!retained && <p>Save a {domain.toUpperCase()} circuit setup in the assembly study editor to enable copying it here. An explicit complete request can also be entered below.</p>}
    <label>Coupled thermal solver<select aria-label="Coupled thermal solver" disabled={locked || !editableDraft} value={editableDraft?.thermal_engine ?? "internal"} onChange={event => chooseSolver(event.target.value)}>
      {editableDraft?.thermal_engine && !["internal", "calculix"].includes(editableDraft.thermal_engine) && <option value={String(editableDraft.thermal_engine)}>Unsupported solver - choose a supported solver</option>}
      <option value="internal">Internal SPIKE thermal</option><option value="calculix">CalculiX external thermal</option>
    </select></label>
    <label>Coupled request JSON<textarea aria-label="Volume electrothermal request JSON" rows={14} spellCheck={false} disabled={locked} value={text} onChange={event => {
      generation.current++; setText(event.target.value); setResult(null); setHandoff(null); setPrepared(null); setPreparedText(""); setBindingHelp(null); setError(""); setMessage("Draft changed. Prepare it before running; previous temperatures are withheld.");
    }} /></label>
    {!!packageParts.length && <details><summary>Component package thermal volumes</summary>
      <p>Declare a promoted package thermal-only when its device loss is already modeled in the owning board circuit. Map that board resistor's heat to the package cells. Retained electrical bonds to the package prevent exclusion.</p>
      <button type="button" disabled={locked || !editableDraft?.circuit || !fieldRequest} onClick={() => editCircuit(circuit => { circuit.assembly = fieldRequest!.assembly; })}>Rebind circuit draft to reviewed current assembly</button>
      <fieldset disabled={locked || !editableDraft?.circuit}>{packageParts.slice(0, 100).map((part: FieldObject) => <label key={part.id}><span>
        <input type="checkbox" checked={!!editableDraft?.circuit?.thermal_only_part_ids?.includes(part.id)} onChange={event => editCircuit(circuit => {
          const ids = Array.isArray(circuit.thermal_only_part_ids) ? circuit.thermal_only_part_ids : [];
          circuit.thermal_only_part_ids = event.target.checked ? [...new Set([...ids, part.id])] : ids.filter((id: string) => id !== part.id);
        })} />{part.name || part.id} · {part.id} · thermal volume only
      </span></label>)}</fieldset>
      <p>Rebinding changes the draft's assembly identity. Review placement and all retained electrical links first. Remove any duplicate package part circuit model explicitly; no circuit elements are silently deleted.</p>
    </details>}
    {bindingHelp && <details open><summary>Resistor and volume IDs for loss mappings</summary>
      <p>These are read-only IDs from the current volume geometry and selected circuit. Search or page the tables to find the required entries. Every compiled resistor requires its own explicit mapping.</p>
      <DataTable label="Available compiled resistor IDs" pageSize={50}><thead><tr><th>Element ID</th><th>Reference resistance (ohm)</th></tr></thead><tbody>{bindingHelp.resistors.map((row: FieldObject) => <tr key={row.element_id}><td>{row.element_id}</td><td>{row.resistance_ohm}</td></tr>)}</tbody></DataTable>
      <DataTable label="Available occurrence and local cell IDs" pageSize={50}><thead><tr><th>Occurrence ID</th><th>Local cell ID</th></tr></thead><tbody>{bindingHelp.occurrences.flatMap((row: FieldObject) => row.cell_ids.map((cell: string) => <tr key={JSON.stringify([row.occurrence_id, cell])}><td>{row.occurrence_id}</td><td>{cell}</td></tr>))}</tbody></DataTable>
    </details>}
    <details><summary>Loss mapping and solver help</summary>
      <p>Use compiled resistor IDs, including link and bond resistors. Distribution weights must sum to one. Copy occurrence and local cell IDs from the admitted volumes. Specify each material law and its temperature range from reviewed data; no values are inferred.</p>
      <pre>{format({ element_id: "compiled-resistor-id", distribution: [{ occurrence_id: "occurrence-id", cell_id: "local-cell-id", weight: 1 }], temperature_law: { temperature_coefficient_per_k: "supply a number", reference_temperature_k: "supply K", temperature_range_k: ["minimum K", "maximum K"] } })}</pre>
      <p>Set thermal_engine to internal or calculix. CalculiX requires its separately installed runtime and accepts thermal_engine_options with timeout_seconds and threads. Thermal background heat_sources must be empty to avoid double counting. SI requires ac_heating.frequency_hz and phasor_convention rms or peak, matching a one-point AC circuit with no DC offset.</p>
    </details>
    <div className="assembly-field-actions">
      <button type="button" disabled={locked || !text.trim() || !fieldRequest} onClick={() => void prepare()}>Prepare coupled study</button>
      <button type="button" className="spike-control--primary" disabled={locked || !ready} onClick={() => void run()}>Run coupled electrothermal</button>
      <button type="button" disabled={locked || (!ready && !result)} onClick={() => void save()}>Save coupled study</button>
    </div>
    {dirty && <p role="status">Unsaved coupled setup or result. Save or reset before changing the assembly.</p>}
    {prepared && <details><summary>Admitted circuit and volume mappings</summary><pre>{format(prepared)}</pre></details>}
    {handoff && <AssemblyThermalVolumeViewer handoff={handoff} result={result?.thermal ?? null} />}
    {result && <>
      <h5>Experimental coupled result</h5>
      <p>Thermal engine: {String(result.thermal_engine)}. Thermal balance: {result.loss_balance?.thermal_imbalance_w == null ? "not reported" : `${result.loss_balance.thermal_imbalance_w} W`}.</p>
      <DataTable label="Mapped resistor thermal losses"><thead><tr><th>Compiled resistor</th><th>Average power (W)</th><th>Temperature (K)</th><th>Resistance (ohm)</th></tr></thead><tbody>{rows.map((row: FieldObject) => <tr key={row.element_id}><td>{row.element_id}</td><td>{row.average_power_w}</td><td>{row.temperature_k}</td><td>{row.resistance_ohm}</td></tr>)}</tbody></DataTable>
      <details><summary>Coupled convergence, loss balance and limitations</summary><pre>{format({ history: result.history, loss_balance: result.loss_balance, request_digest: result.request_digest, limitations: result.limitations })}</pre></details>
    </>}
  </section>;
}
