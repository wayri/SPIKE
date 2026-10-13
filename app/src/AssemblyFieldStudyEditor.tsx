// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import DataTable from "./DataTable";
import AssemblyThermalMeshSetup, { AssemblyAmbientBoundaries } from "./AssemblyThermalMeshSetup";
import AssemblyThermalVolumeViewer from "./AssemblyThermalVolumeViewer";
import AssemblyThermalContacts from "./AssemblyThermalContacts";
import AssemblyThermalBodyPower from "./AssemblyThermalBodyPower";
import AssemblyAirflowPanel from "./AssemblyAirflowPanel";
import VolumeElectrothermalEditor from "./VolumeElectrothermalEditor";
import AssemblyTransientControls, { defaultTransientSettings } from "./AssemblyTransientControls";
import type { AssemblyIr } from "./mcadAssembly";
import { openNativeTextFile, runLocalWorker, runNativeProjectWorker, saveNativeTextFile, subscribeWorkerProgress, cancelLocalWorker, type WorkerResponse } from "./workerBridge";
import { runSerializedAutomaticWorker } from "./automaticWorkerQueue";
import { assertFieldAssembly, fieldCanRun, fieldOwnerName, fieldStudyDirty, fieldTemperatureRows, type FieldObject, type FieldRecord, type FieldSnapshot } from "./assemblyFieldStudyPresentation";
import "./assemblyFieldStudyEditor.css";

const formatted = (value: unknown) => JSON.stringify(value, null, 2);
function workerValue(response: WorkerResponse): FieldObject {
  if (!response.ok || !response.result) throw new Error([response.error_code, response.error, response.error_detail?.detail].filter(Boolean).join(" · ") || "Assembly field worker returned no data.");
  return response.result;
}

/** Supplied physical volumes are admitted and solved by the resident worker. */
export default function AssemblyFieldStudyEditor({ assembly, projectPath, manifestDigest, disabled, onUpdated, onStatus, onDirtyChange, initialSolver = "internal", initialMesher = "gmsh" }: {
  initialSolver?: "internal" | "calculix"; initialMesher?: "internal" | "gmsh";
  assembly: AssemblyIr; projectPath: string | null; manifestDigest: string | null; disabled: boolean;
  onUpdated: () => Promise<void>; onStatus: (message: string) => void; onDirtyChange?: (dirty: boolean) => void;
}) {
  const [solver, setSolver] = useState(initialSolver);
  useEffect(() => { setSolver(initialSolver); }, [initialSolver]);
  const [runtime, setRuntime] = useState<FieldObject | null>(null);
  const [physical, setPhysical] = useState<FieldObject | null>(null);
  const [record, setRecord] = useState<FieldRecord | null>(null);
  const [handoff, setHandoff] = useState<FieldObject | null>(null);
  const [requestText, setRequestText] = useState("");
  const [problemText, setProblemText] = useState("");
  const [baseline, setBaseline] = useState<FieldSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [volumeCouplingDirty, setVolumeCouplingDirty] = useState(false);
  const [airflowDirty, setAirflowDirty] = useState(false);
  const [meshSetup, setMeshSetup] = useState<FieldObject | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const generation = useRef(0);
  const pendingHydration = useRef<{ key: string; read: Promise<{ read: FieldObject; prepared: FieldObject | null } | undefined> } | null>(null);
  const saved = useRef<{ record: FieldRecord | null; handoff: FieldObject | null }>({ record: null, handoff: null });
  const transientOperation = useRef<string | null>(null);
  const [liveFrame, setLiveFrame] = useState<FieldObject | null>(null);
  const appliedRequestText = useMemo(() => record ? formatted(record.request) : "", [record?.request]);
  const appliedProblemText = useMemo(() => record ? formatted(record.problem) : "", [record?.problem]);
  const dirty = fieldStudyDirty({ requestText, problemText, result: record?.result ?? null }, baseline)
    || formatted(record?.transient_settings ?? null) !== formatted(saved.current.record?.transient_settings ?? null);
  const unapplied = !record || requestText !== appliedRequestText || problemText !== appliedProblemText;
  const locked = disabled || busy || loading || volumeCouplingDirty || !physical;
  useEffect(() => { onDirtyChange?.(dirty || busy || volumeCouplingDirty || airflowDirty); }, [onDirtyChange, dirty, busy, volumeCouplingDirty, airflowDirty]);
  useEffect(() => { setMeshSetup(null); }, [projectPath, manifestDigest]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  useEffect(() => () => {
    generation.current++;
    if (transientOperation.current) void cancelLocalWorker(transientOperation.current);
  }, []);

  const accept = (value: FieldRecord, prepared: FieldObject) => {
    setRecord(value); setHandoff(prepared); setRequestText(formatted(value.request)); setProblemText(formatted(value.problem));
  };
  useEffect(() => {
    let active = true;
    const token = ++generation.current;
    setRecord(null); setHandoff(null); setPhysical(null); setBaseline(null); setError("");
    saved.current = { record: null, handoff: null };
    setRequestText(""); setProblemText(""); setLoading(false);
    if (!projectPath || !manifestDigest) return;
    setLoading(true);
    void (async () => {
      const key = `${projectPath}\u0000${manifestDigest}`;
      let pending = pendingHydration.current;
      if (!pending || pending.key !== key) {
        const entry = { key, read: Promise.resolve(undefined) as Promise<{ read: FieldObject; prepared: FieldObject | null } | undefined> };
        pendingHydration.current = entry;
        entry.read = runSerializedAutomaticWorker(async () => {
          const read = workerValue(await runNativeProjectWorker({ method: "read_assembly_field_study_in_project", params: {
            project_path: projectPath, expected_manifest_payload_sha256: manifestDigest,
          } }));
          const prepared = read.record
            ? workerValue(await runLocalWorker({ method: "prepare_assembly_field_handoff", params: { request: read.record.request } }))
            : null;
          return { read, prepared };
        }, () => pendingHydration.current === entry);
        pending = entry;
        void entry.read.then(
          () => { if (pendingHydration.current === entry) pendingHydration.current = null; },
          () => { if (pendingHydration.current === entry) pendingHydration.current = null; },
        );
      }
      const loaded = await pending.read;
      if (!loaded || !active || token !== generation.current) return;
      const { read, prepared } = loaded;
      setPhysical(read.assembly);
      if (read.record) {
        accept(read.record, prepared!);
        saved.current = { record: read.record, handoff: prepared! };
        setBaseline({ requestText: formatted(read.record.request), problemText: formatted(read.record.problem), result: read.record.result });
      } else {
        const request = formatted({ contract: "spike/assembly-field-handoff-request/v1", assembly: read.assembly, domain: "thermal", bodies: [], materials: [] });
        const problem = formatted({ contract: "spike/assembly-field-thermal-problem/v1", boundaries: [], heat_sources: [], contacts: [] });
        setRequestText(request); setProblemText(problem);
        setBaseline({ requestText: request, problemText: problem, result: null });
        if (read.state === "stale") setError(read.action);
      }
    })().catch(caught => { if (active && token === generation.current) setError(String(caught)); })
      .finally(() => { if (active && token === generation.current) setLoading(false); });
    return () => { active = false; generation.current++; };
  }, [projectPath, manifestDigest, reload]);

  const action = async (work: (token: number) => Promise<void>) => {
    if (locked) return;
    const token = generation.current;
    setBusy(true); setError("");
    try { await work(token); } catch (caught) { if (token === generation.current) { setError(String(caught)); onStatus(String(caught)); } }
    finally { setBusy(false); }
  };
  const admit = async (value: FieldRecord) => {
    assertFieldAssembly(value.request, physical);
    const admitted = workerValue(await runLocalWorker({ method: "import_assembly_field_study", params: { record: value } })) as FieldRecord;
    const prepared = workerValue(await runLocalWorker({ method: "prepare_assembly_field_handoff", params: { request: admitted.request } }));
    return { admitted, prepared };
  };
  const open = () => action(async token => {
    const file = await openNativeTextFile("result"); if (!file) return;
    if (new TextEncoder().encode(file.contents).length > 8 * 1024 * 1024) throw new Error("ASSEMBLY_FIELD_RESOURCE: study file exceeds 8 MiB.");
    const { admitted, prepared } = await admit(JSON.parse(file.contents));
    if (token !== generation.current) return;
    accept(admitted, prepared); onStatus("Assembly volume study loaded and bound to the current physical assembly. Save to retain it in this project.");
  });
  const apply = () => action(async token => {
    const request = JSON.parse(requestText), problem = JSON.parse(problemText);
    assertFieldAssembly(request, physical);
    const value = workerValue(await runLocalWorker({ method: "export_assembly_field_study", params: { request, problem, include_results: false } })) as FieldRecord;
    const { admitted, prepared } = await admit(value);
    if (token === generation.current) accept(admitted, prepared);
  });
  const acceptGenerated = async (result: FieldObject) => {
    const token = generation.current;
    assertFieldAssembly(result.request, physical);
    const problem = { contract: "spike/assembly-field-thermal-problem/v1", boundaries: [], heat_sources: [], contacts: [] };
    const value = workerValue(await runLocalWorker({ method: "export_assembly_field_study", params: { request: result.request, problem, include_results: false } })) as FieldRecord;
    const { admitted, prepared } = await admit(value);
    if (token !== generation.current) return;
    accept(admitted, prepared);
    onStatus("Thermal volumes generated from retained geometry. Assign heat sources, matched contacts and ambient boundaries, then save the setup.");
  };
  const run = () => action(async token => {
    if (!record || !fieldCanRun(record.request, handoff, unapplied)) return;
    setRecord({ ...record, result: null });
    setLiveFrame(null);
    if (record.transient_settings) {
      const id = `thermal-transient-${crypto.randomUUID()}`;
      transientOperation.current = id;
      let unlisten: (() => void) | undefined;
      try {
        unlisten = await subscribeWorkerProgress(progress => {
        if (progress.operationId === id && token === generation.current && transientOperation.current === id) setLiveFrame(progress.frame);
        });
        const result = workerValue(await runLocalWorker({ id, method: "run_assembly_field_transient", params: {
          request: record.request, problem: record.problem, transient_settings: record.transient_settings, solver,
        } }));
        if (token !== generation.current) return;
        const value = workerValue(await runLocalWorker({ method: "export_assembly_field_study", params: {
          request: record.request, problem: record.problem, transient_settings: record.transient_settings, result,
        } })) as FieldRecord;
        if (token !== generation.current) return;
        const completed = await admit(value);
        if (token !== generation.current) return;
        accept(completed.admitted, completed.prepared);
        onStatus("Experimental transient assembly thermal completed. Save with results to retain all solved frames.");
      } finally { unlisten?.(); transientOperation.current = null; setLiveFrame(null); }
      return;
    }
    const response = solver === "calculix"
      ? workerValue(await runLocalWorker({ method: "invoke_extension", params: { extension_id: "spike.calculix-suite", contribution_id: "calculix-thermal-run", context: { parameters: { request: record.request, problem: record.problem } } } }))
      : workerValue(await runLocalWorker({ method: "run_assembly_field_thermal", params: { request: record.request, problem: record.problem } }));
    const result = solver === "calculix" ? response.data?.result : response;
    if (!result) throw new Error("The selected thermal solver returned no admitted field result.");
    if (token !== generation.current) return;
    const value = workerValue(await runLocalWorker({ method: "export_assembly_field_study", params: { request: record.request, problem: record.problem, result } })) as FieldRecord;
    const completed = solver === "calculix" ? await admit(value) : { admitted: value, prepared: handoff! };
    if (token === generation.current) { accept(completed.admitted, completed.prepared); onStatus("Experimental steady assembly thermal field completed. Save with results to retain the output."); }
  });
  const save = (includeResults: boolean) => action(async token => {
    if (!record || unapplied) return;
    const value = workerValue(await runLocalWorker({ method: "export_assembly_field_study", params: {
      request: record.request, problem: record.problem, result: record.result, include_results: includeResults,
      ...(record.transient_settings ? { transient_settings: record.transient_settings } : {}),
    } })) as FieldRecord;
    const savedResponse = workerValue(await runNativeProjectWorker({ method: "save_assembly_field_study_in_project", params: {
      project_path: projectPath, expected_manifest_payload_sha256: manifestDigest, record: value,
    } }));
    if (token !== generation.current) return;
    accept(savedResponse.record, handoff!);
    // Keep a validated baseline so reset restores the admitted result too.
    saved.current = { record: savedResponse.record, handoff: handoff! };
    setBaseline({ requestText: formatted(savedResponse.record.request), problemText: formatted(savedResponse.record.problem), result: savedResponse.record.result });
    await onUpdated(); onStatus(`Assembly volume study saved ${includeResults ? "with results" : "as setup only"}.`);
  });
  const exportFile = (includeResults: boolean) => action(async () => {
    if (!record || unapplied) return;
    const value = workerValue(await runLocalWorker({ method: "export_assembly_field_study", params: {
      request: record.request, problem: record.problem, result: record.result, include_results: includeResults,
      ...(record.transient_settings ? { transient_settings: record.transient_settings } : {}),
    } }));
    await saveNativeTextFile(`assembly-${record.request.domain}-volume-study.json`, formatted(value), "result");
  });
  const editProblem = (change: (copy: FieldObject) => void) => {
    if (!record) return;
    generation.current++;
    const problem = structuredClone(record.problem); change(problem);
    setRecord({ ...record, problem, result: null }); setProblemText(formatted(problem)); setError("");
  };
  const reset = () => {
    if (!baseline) return;
    generation.current++; setRequestText(baseline.requestText); setProblemText(baseline.problemText); setError("");
    setRecord(saved.current.record); setHandoff(saved.current.handoff);
  };
  const rows = fieldTemperatureRows(unapplied ? null : record?.result ?? null, assembly);
  const field = record?.result?.field_result;
  return <section className="assembly-field-study" aria-label="Assembly volume field study">
    <h4>Assembly volume field study</h4>
    <p>Generate conforming tetrahedral volumes from retained boards and STEP structures, or open an existing volume study. Steady solid conduction and prescribed ambient radiation are experimental. EM and SI volumes and ports can be prepared; their field solvers are not available here.</p>
    <p>Generated meshes verify retained source artifacts. Imported mesh hashes remain caller declarations. Transient solid thermal supports explicit heat capacity and time-dependent loads. Airflow is unavailable. Unrepresented connector or harness links block execution.</p>
    {!projectPath && <p role="status">Save and open the SPIKE project before importing a field study.</p>}
    {loading && <p role="status">Checking the saved volume study…</p>}
    {error && <p role="alert">{error}</p>}
    {projectPath && manifestDigest && <AssemblyThermalMeshSetup key={`${projectPath}:${manifestDigest}`} projectPath={projectPath} manifestDigest={manifestDigest}
      assembly={assembly} onSetupReady={setMeshSetup} initialMesher={initialMesher} disabled={locked || dirty} onBusyChange={setBusy} onPrepared={acceptGenerated} onProjectUpdated={onUpdated} />}
    <AssemblyAirflowPanel projectPath={projectPath} manifestDigest={manifestDigest} meshSetup={meshSetup}
      disabled={disabled || busy || loading || volumeCouplingDirty} onUpdated={onUpdated} onDirtyChange={setAirflowDirty}/>
    <label>Thermal solver<select aria-label="Assembly thermal solver" disabled={locked} value={solver} onChange={event => { setSolver(event.target.value as "internal" | "calculix"); setRuntime(null); }}><option value="internal">SPIKE reference tetrahedral solver</option><option value="calculix">CalculiX · external solid thermal</option></select></label>
    {record && !unapplied && <><label>Thermal analysis mode<select disabled={locked} value={record.transient_settings ? "transient" : "steady"} onChange={e => {
      generation.current++; setLiveFrame(null);
      setRecord({ ...record, result: null, transient_settings: e.target.value === "transient" ? defaultTransientSettings(record.request.materials ?? []) : undefined });
    }}><option value="steady">Steady state</option><option value="transient">Transient solid thermal</option></select></label>
    {record.transient_settings && <AssemblyTransientControls settings={record.transient_settings} disabled={locked} onChange={settings => {
      generation.current++; setRecord({ ...record, transient_settings: settings, result: null });
    }} />}</>}
    {solver === "calculix" && <><p>CalculiX needs its separately installed runtime. The same admitted volumes, physical materials and explicit interfaces are used; no airflow is inferred.</p><button type="button" disabled={locked || !record || unapplied || !!record.transient_settings} title={record?.transient_settings ? "Steady case preview only; transient requirements are checked when running." : undefined} onClick={() => void action(async token => { const data = workerValue(await runLocalWorker({ method: "invoke_extension", params: { extension_id: "spike.calculix-suite", contribution_id: "calculix-thermal-prepare", context: { parameters: { request: record!.request, problem: record!.problem } } } })); if (token === generation.current) setRuntime(data.data); })}>Check CalculiX requirements and preview case</button>{runtime && <details open><summary>CalculiX case and runtime</summary><pre>{formatted(runtime)}</pre></details>}</>}
    <div className="assembly-field-actions">
      {error && <button type="button" disabled={disabled || busy || loading || dirty || !projectPath || !manifestDigest} onClick={() => setReload(value => value + 1)}>Reload saved study</button>}
      <button type="button" disabled={locked || dirty} onClick={() => void open()}>Open volume study</button>
      <button type="button" disabled={locked || !dirty} onClick={reset}>Reset drafts</button>
      <button type="button" disabled={locked || !requestText || !problemText} onClick={() => void apply()}>Validate and apply volumes</button>
      <button type="button" className="spike-control--primary" disabled={locked || !fieldCanRun(record?.request ?? null, handoff, unapplied)} onClick={() => void run()}>{record?.transient_settings ? "Run transient thermal" : "Run steady thermal"}</button>
      {busy && transientOperation.current && <button type="button" onClick={() => {
        const id = transientOperation.current!;
        generation.current++; transientOperation.current = null; setLiveFrame(null);
        void cancelLocalWorker(id);
        onStatus("Thermal run cancelled. In-progress frames and late completion are withheld.");
      }}>Cancel thermal run</button>}
    </div>
    {dirty && <p role="status">Unsaved volume setup or result changes. Save this study or reset its drafts before changing the assembly.</p>}
    {handoff && !unapplied && <>
      <p>{String(record?.request.domain).toUpperCase()} · {handoff.mesh?.counts?.cells ?? 0} volume cells · {handoff.mesh?.counts?.vertices ?? 0} vertices · {handoff.source_traceability?.length ?? 0} physical occurrences</p>
      {!!handoff.execution_issues?.length && <ul aria-label="Field execution blockers">{handoff.execution_issues.map((issue: FieldObject, i: number) => <li key={i}>{issue.code} · {issue.detail || `Retained ${issue.collection} have no field model.`}</li>)}</ul>}
    </>}
    {liveFrame && <p role="status">Live computed frame: {String(liveFrame.time_s)} s. This is an in-progress preview, not a completed saved result.</p>}
    {handoff && !unapplied && <AssemblyThermalVolumeViewer handoff={handoff} result={liveFrame ? {
      ...handoff, contract: "spike/assembly-field-transient-result/v1", model_status: "experimental", production_qualified: false,
      field_result: { ...liveFrame, status: "experimental", temperature_units: "K", production_qualified: false },
    } : record?.result ?? null} />}
    {record?.request.domain === "thermal" && !unapplied && <details><summary>Thermal boundary values</summary>
      {(record.problem.boundaries?.length ?? 0) > 100 && <p>Showing the first 100 triangle boundary values. The complete boundary table remains editable in the advanced definition.</p>}
      <fieldset disabled={locked}>{(record.problem.boundaries ?? []).slice(0, 100).map((boundary: FieldObject, index: number) => <div className="assembly-field-boundary" key={index}>
        <strong>{fieldOwnerName(assembly, boundary.face.occurrence_id)} · face {boundary.face.face_id} · {boundary.type}</strong>
        {Object.entries({ temperature_k: "Temperature (K)", heat_flux_w_m2: "Inward heat flux (W/m²)", heat_transfer_coefficient_w_m2k: "Convection coefficient (W/m²K)", ambient_temperature_k: "Ambient temperature (K)", emissivity: "Emissivity", radiation_temperature_k: "Radiating surroundings temperature (K)" }).filter(([key]) => key in boundary).map(([key, label]) => <label key={key}>{label}<input type="number" step="any" value={boundary[key] ?? ""} onChange={event => editProblem(copy => { copy.boundaries[index][key] = event.target.value === "" ? null : Number(event.target.value); })} /></label>)}
      </div>)}</fieldset><p>Sources and matched contact faces are retained in the advanced problem definition below. Unassigned exterior faces are adiabatic.</p>
    </details>}
    {record?.request.domain === "thermal" && !unapplied && <AssemblyThermalBodyPower request={record.request} problem={record.problem} handoff={handoff} disabled={locked}
      onBusyChange={setBusy} onApply={sources => editProblem(copy => { copy.heat_sources = sources; })} />}
    {record?.request.domain === "thermal" && !unapplied && <AssemblyAmbientBoundaries request={record.request} problem={record.problem} disabled={locked}
      onApply={boundaries => editProblem(copy => { copy.boundaries = [...(copy.boundaries ?? []), ...boundaries]; })} />}
    {record?.request.domain === "thermal" && !unapplied && <AssemblyThermalContacts request={record.request} problem={record.problem} disabled={locked}
      onApply={problem => editProblem(copy => { copy.contacts = problem.contacts; })} />}
    <details><summary>Advanced volume request and boundary setup</summary>
      <fieldset disabled={locked}><label>Volume request JSON<textarea rows={10} spellCheck={false} value={requestText} onChange={event => { generation.current++; setRequestText(event.target.value); setHandoff(null); }} /></label>
      <label>Field problem JSON<textarea rows={8} spellCheck={false} value={problemText} onChange={event => { generation.current++; setProblemText(event.target.value); setHandoff(null); }} /></label></fieldset>
    </details>
    {!!rows.length && <><h5>Experimental {record?.result?.mode === "transient" ? "transient final-frame" : "steady"} thermal result</h5><DataTable label="Physical occurrence temperatures"><thead><tr><th>Occurrence</th><th>Minimum (K)</th><th>Maximum (K)</th></tr></thead><tbody>{rows.map((row, index) => <tr key={index}><td>{row.name}</td><td>{row.minimum.toFixed(3)}</td><td>{row.maximum.toFixed(3)}</td></tr>)}</tbody></DataTable>
      <p>Heat balance residual: {field?.heat_balance?.imbalance_w ?? "unavailable"} W. Results retain experimental status; snapshot integrity checks do not establish physical qualification.</p>
      <details><summary>Conservation, convergence and provenance</summary><pre>{formatted({ heat_balance: field?.heat_balance, diagnostics: field?.diagnostics, resources: field?.resources, source_traceability: record?.result?.source_traceability, limitations: record?.result?.limitations })}</pre></details></>}
    <div className="assembly-field-actions">
      <button type="button" disabled={locked || unapplied} onClick={() => void save(false)}>Save setup</button>
      <button type="button" disabled={locked || unapplied || !record?.result} onClick={() => void save(true)}>Save with results</button>
      <button type="button" disabled={locked || unapplied} onClick={() => void exportFile(false)}>Export setup</button>
      <button type="button" disabled={locked || unapplied || !record?.result} onClick={() => void exportFile(true)}>Export with results</button>
    </div>
    <VolumeElectrothermalEditor assembly={assembly} fieldRequest={unapplied ? null : record?.request ?? null}
      fieldProblem={unapplied ? null : record?.problem ?? null} projectPath={projectPath} manifestDigest={manifestDigest}
      disabled={disabled || busy || loading || dirty} onUpdated={onUpdated} onStatus={onStatus} onDirtyChange={setVolumeCouplingDirty} />
  </section>;
}
