import { solverReadinessLabel } from "./solverReadinessLabel";
import { Activity, Box, CheckCircle2, Cpu, FileCode2, Gauge, Play, RefreshCw, Save, ShieldAlert, Trash2, X, Zap } from "lucide-react";
import { useMemo, useState } from "react";

export type ExternalEngineCatalogEntry = {
  id: string;
  name: string;
  role: string;
  license: string;
  homepage: string;
  executable: string;
  version: string;
  state: string;
  interface: string;
  capabilities: string[];
  candidate_capabilities?: string[];
  actions: string[];
  reason: string;
  adapter_version: string;
  result_contract?: string;
  trust?: string;
  model_status?: string;
  runtime_validation?: {
    status?: string;
    validation_scope?: string;
    maximum_relative_error?: number;
    [key: string]: unknown;
  };
  runtime_backend?: {
    linear_solver?: string;
    mumps_registered?: boolean;
    circuit_coupling_validated?: boolean;
    [key: string]: unknown;
  };
  qualification?: {
    status?: string;
    runtime_available?: boolean;
    runtime_signature_verified?: boolean;
    mumps_registered?: boolean;
    summary?: { required?: number; passed?: number; failed?: number; blocked?: number };
    fixtures?: Array<{ id: string; physics: string; status: string; reason: string }>;
    reason?: string;
  };
};

export type AccelerationCatalogEntry = {
  id: string;
  name: string;
  kind: string;
  state: string;
  version: string;
  provider: string;
  capabilities: string[];
  reason: string;
  license: string;
};

export type ExternalCaseState = {
  status: string;
  caseDir: string;
  canRun: boolean;
  errors: string[];
  warnings: string[];
};

export type SolverManagerCatalog = {
  contract: string;
  selection_policy: string;
  installation: { managed_downloads: boolean; reason: string; register_local_paths: boolean; remove_behavior: string };
  registrations: Record<string, { path: string; managed: boolean }>;
  tuning_profiles: Array<{ target_id: string; application_state?: string; note?: string; parameters: Array<{ key: string; type: "enum" | "integer" | "number" | "boolean"; value: string | number | boolean; values?: string[]; minimum?: number; maximum?: number }> }>;
  workloads: Array<{ id: string; name: string; domain: string; status: string; required: string[]; recommended: { id: string; name: string; state: string; model_status: string; reason: string } | null; candidates: Array<{ id: string; name: string; state: string; eligible: boolean; missing: string[]; reason: string }> }>;
  emi_pipeline: { state: string; stages: Array<{ id: string; state: string; detail: string }> };
};

type Props = {
  engines: ExternalEngineCatalogEntry[];
  accelerators: AccelerationCatalogEntry[];
  manager: SolverManagerCatalog;
  solverSelections: Record<string, string>;
  selectedNets: string[];
  designAvailable: boolean;
  caseState: ExternalCaseState | null;
  busy: boolean;
  onClose: () => void;
  onRefresh: () => void;
  onPrepare: (engineId: string) => void;
  onRun: (engineId: string, setupOnly: boolean) => void;
  onRegister: (engineId: string, path: string) => void;
  onUnregister: (engineId: string) => void;
  onTune: (targetId: string, values: Record<string, string | number | boolean>) => void;
  onSelectSolver: (workloadId: string, solverId: string) => void;
};

const readableState = (state: string) => state.replace(/_/g, " ");
const available = (state: string) => ["available", "experimental", "reference_validated"].includes(state);
type ReadinessTone = "ready" | "review" | "gated";
type Readiness = { label: string; value: string; detail: string; tone: ReadinessTone };

const engineReadiness = (engine: ExternalEngineCatalogEntry): Readiness[] => {
  const runtimeStatus = String(engine.runtime_validation?.status ?? "");
  const runtimeVerified = runtimeStatus === "passed" || engine.state.startsWith("runtime_verified");
  const adapterRunnable = engine.actions.includes("run") && engine.capabilities.length > 0;
  const adapterPending = engine.state.includes("adapter_pending") || engine.state.includes("configured_source");
  const workflowRunnable = adapterRunnable && available(engine.state);
  const rawModelStatus = engine.model_status ?? "unsupported";
  const modelStatus = readableState(rawModelStatus);
  const qualification = engine.qualification;
  const qualificationStatus = String(qualification?.status ?? rawModelStatus);

  return [
    {
      label: "Runtime",
      value: runtimeVerified ? "verified" : engine.executable ? "detected" : "not detected",
      detail: runtimeVerified ? "Integrity fixture passed" : engine.executable ? "No integrity evidence" : "No local runtime discovered",
      tone: runtimeVerified ? "ready" : engine.executable ? "review" : "gated",
    },
    {
      label: "Adapter",
      value: adapterRunnable ? "runnable" : adapterPending ? "pending" : "not enabled",
      detail: adapterRunnable ? "Case and result contract installed" : adapterPending ? "PCB translation or result import incomplete" : "No bounded adapter is installed",
      tone: adapterRunnable ? "ready" : adapterPending ? "review" : "gated",
    },
    {
      label: "Validation",
      value: readableState(qualificationStatus || modelStatus),
      detail: qualification?.reason ?? (["validated", "reference_validated"].includes(rawModelStatus)
        ? "Declared workflow validation evidence is available"
        : "A runtime self-test does not validate an engineering workflow"),
      tone: qualificationStatus === "validated" || ["validated", "reference_validated"].includes(rawModelStatus) ? "ready" : qualificationStatus === "failed" || rawModelStatus === "unsupported" ? "gated" : "review",
    },
    {
      label: "Workflow",
      value: workflowRunnable ? "enabled" : "gated",
      detail: workflowRunnable ? "Available through the declared adapter" : "No solver workflow is enabled from runtime evidence alone",
      tone: workflowRunnable ? "ready" : "gated",
    },
  ];
};

export default function ExternalEngineCenter({
  engines,
  accelerators,
  manager,
  solverSelections,
  selectedNets,
  designAvailable,
  caseState,
  busy,
  onClose,
  onRefresh,
  onPrepare,
  onRun,
  onRegister,
  onUnregister,
  onTune,
  onSelectSolver,
}: Props) {
  const [section, setSection] = useState<"engines" | "acceleration" | "manager">("engines");
  const [selectedId, setSelectedId] = useState("external.openems");
  const [registrationPath, setRegistrationPath] = useState("");
  const [workloadId, setWorkloadId] = useState("dc_pi");
  const [candidateDrafts, setCandidateDrafts] = useState<Record<string, string>>({});
  const [tuningDrafts, setTuningDrafts] = useState<Record<string, Record<string, string | number | boolean>>>({});
  const selected = useMemo(
    () => engines.find(engine => engine.id === selectedId) ?? engines[0],
    [engines, selectedId],
  );
  const selectedReady = Boolean(selected && available(selected.state));
  const openems = selected?.id === "external.openems";
  const registration = selected ? manager.registrations[selected.id] : undefined;
  const workload = manager.workloads.find(item => item.id === workloadId) ?? manager.workloads[0];
  const selectedCandidateId = (workload ? candidateDrafts[workload.id] || solverSelections[workload.id] : "") || workload?.recommended?.id || workload?.candidates[0]?.id || "";
  const readiness = selected ? engineReadiness(selected) : [];
  const workloadRows = manager.workloads.flatMap(item => item.candidates.map(candidate => ({ workload: item, candidate })));
  const tuneValue = (target: string, key: string, fallback: string | number | boolean) => tuningDrafts[target]?.[key] ?? fallback;
  const setTuneValue = (target: string, key: string, value: string | number | boolean) => setTuningDrafts(current => ({ ...current, [target]: { ...(current[target] ?? {}), [key]: value } }));
  const saveTuning = (target: string) => {
    const profile = manager.tuning_profiles.find(item => item.target_id === target);
    if (!profile) return;
    const values = Object.fromEntries(profile.parameters.map(parameter => {
      const raw = tuneValue(target, parameter.key, parameter.value);
      return [parameter.key, parameter.type === "integer" ? Number.parseInt(String(raw), 10) : parameter.type === "number" ? Number(raw) : raw];
    }));
    onTune(target, values);
  };

  return <div className="modal-shade external-engine-shade">
    <section className="floating-panel external-engine-center" role="dialog" aria-modal="true" aria-label="External engines and acceleration">
      <header className="floating-heading"><div><b>EXTERNAL ENGINES</b><small>Offline adapters, solver readiness, and acceleration backends</small></div><button onClick={onClose} title="Close"><X size={15} /></button></header>
      <div className="engine-tabs" role="tablist">
        <button className={section === "engines" ? "selected" : ""} onClick={() => setSection("engines")}><Box size={14} /> Engines</button>
        <button className={section === "acceleration" ? "selected" : ""} onClick={() => setSection("acceleration")}><Cpu size={14} /> Acceleration</button>
        <button className={section === "manager" ? "selected" : ""} onClick={() => setSection("manager")}><Gauge size={14} /> Solver manager</button>
        <button className="engine-refresh" onClick={onRefresh} disabled={busy}><RefreshCw size={13} /> Detect</button>
      </div>

      {section === "engines" ? <div className="engine-layout">
        <nav className="engine-list" aria-label="External engines">{engines.map(engine => <button key={engine.id} className={selected?.id === engine.id ? "selected" : ""} onClick={() => setSelectedId(engine.id)}>
          <span className={`engine-dot ${available(engine.state) ? "ready" : "gated"}`} />
          <span><b>{engine.name}</b><small>{readableState(engine.state)}</small></span>
        </button>)}</nav>
        <article className="engine-detail">{selected ? <>
          <div className="engine-title"><span><b>{selected.name}</b><small>{selected.id} / adapter {selected.adapter_version}</small></span><i className={selectedReady ? "ready" : "gated"}>{readiness.find(item => item.label === "Workflow")?.value ?? readableState(selected.state)}</i></div>
          <p>{selected.role}</p>
          <div className="engine-readiness" aria-label="Engine readiness">
            {readiness.map(item => <article key={item.label} className={item.tone}><span>{item.label}</span><b>{item.value}</b><small>{item.detail}</small></article>)}
          </div>
          <dl><dt>Interface</dt><dd>{readableState(selected.interface)}</dd><dt>Version</dt><dd>{selected.version || "not detected"}</dd><dt>Location</dt><dd title={selected.executable}>{selected.executable || "not detected"}</dd><dt>License</dt><dd>{selected.license}</dd><dt>Trust</dt><dd>{readableState(selected.trust || "discovery only")}</dd><dt>Result contract</dt><dd>{selected.result_contract || "adapter gated"}</dd></dl>
          {(selected.runtime_validation || selected.runtime_backend) && <div className="engine-runtime-details">
            <label className="engine-label">RUNTIME EVIDENCE</label>
            {selected.runtime_validation && <div><b>Fixture</b><span>{String(selected.runtime_validation.status ?? "not run")}</span><small>{String(selected.runtime_validation.validation_scope ?? "No declared validation scope")}{selected.runtime_validation.maximum_relative_error !== undefined ? ` / max relative error ${selected.runtime_validation.maximum_relative_error}` : ""}</small></div>}
            {selected.runtime_backend && <div><b>Backend</b><span>{readableState(String(selected.runtime_backend.linear_solver ?? "not declared"))}</span><small>MUMPS {selected.runtime_backend.mumps_registered ? "registered" : "not registered"}; circuit coupling {selected.runtime_backend.circuit_coupling_validated ? "validated" : "gated"}</small></div>}
          </div>}
          {selected.qualification && <div className="engine-runtime-details">
            <label className="engine-label">PCB WORKFLOW QUALIFICATION</label>
            <div><b>Release gate</b><span>{readableState(selected.qualification.status ?? "blocked")}</span><small>{selected.qualification.summary?.passed ?? 0} of {selected.qualification.summary?.required ?? 0} required fixtures passed</small></div>
            <div><b>Trust and sparse backend</b><span>{selected.qualification.runtime_signature_verified ? "signed runtime" : "signature required"}</span><small>PETSc/MUMPS {selected.qualification.mumps_registered ? "registered and probed" : "not registered"}</small></div>
            {selected.qualification.fixtures?.map(fixture => <div key={fixture.id}><b>{readableState(fixture.physics)}</b><span>{readableState(fixture.status)}</span><small title={fixture.reason}>{fixture.id}</small></div>)}
          </div>}
          <label className="engine-label">CAPABILITIES</label><div className="engine-capabilities">{selected.capabilities.map(capability => <span key={capability}>{readableState(capability)}</span>)}</div>
          {!!selected.candidate_capabilities?.length && <><label className="engine-label">UPSTREAM CANDIDATES - NOT ENABLED</label><div className="engine-capabilities candidate">{selected.candidate_capabilities.map(capability => <span key={capability}>{readableState(capability)}</span>)}</div></>}
          {selected.reason && <div className="engine-notice"><ShieldAlert size={14} /><span>{selected.reason}</span></div>}
          {selected.actions.includes("register") && <div className="engine-registration"><label className="engine-label">LOCAL REGISTRATION</label>{registration ? <div className="registered-path"><span title={registration.path}>{registration.path}</span><button onClick={() => onUnregister(selected.id)} disabled={busy} title="Forget registration without deleting files"><Trash2 size={13} /> Forget</button></div> : <div className="register-path"><input value={registrationPath} onChange={event => setRegistrationPath(event.target.value)} placeholder="Absolute adapter, library, or source path" /><button onClick={() => onRegister(selected.id, registrationPath)} disabled={busy || !registrationPath.trim()}><Save size={13} /> Register</button></div>}<small>Registration never installs, executes, or deletes the selected software.</small></div>}
          {openems && <div className="openems-workflow">
            <label className="engine-label">CURRENT HANDOFF</label>
            <div className="engine-handoff"><span>Design</span><b>{designAvailable ? "loaded" : "required"}</b><span>Nets</span><b title={selectedNets.join(", ")}>{selectedNets.length ? selectedNets.join(", ") : "select a net"}</b><span>Ports</span><b>explicit ports required to solve</b></div>
            {caseState && <div className={`engine-case ${caseState.canRun ? "ready" : "review"}`}><FileCode2 size={15} /><span><b>{readableState(caseState.status)}</b><small title={caseState.caseDir}>{caseState.caseDir || "No case directory"}</small>{caseState.errors.map(error => <em key={error}>{error}</em>)}{caseState.warnings.slice(0, 2).map(warning => <em key={warning}>{warning}</em>)}</span></div>}
          </div>}
        </> : <div className="extension-empty">No external engines are catalogued.</div>}</article>
      </div> : section === "acceleration" ? <div className="accelerator-layout">
        <div className="accelerator-summary"><Zap size={18} /><span><b>Deterministic acceleration policy</b><small>Numba accelerates approved kernels; PETSc/MUMPS and SuperLU solve sparse systems. Physics and validity status do not change.</small></span></div>
        <div className="accelerator-grid">{accelerators.map(backend => <article key={backend.id}>
          <header><Cpu size={15} /><span><b>{backend.name}</b><small>{readableState(backend.kind)} / {backend.version || (available(backend.state) ? "detected" : "not detected")}</small></span><i className={available(backend.state) ? "ready" : "gated"}>{readableState(backend.state)}</i></header>
          <p>{backend.reason || `${backend.provider} is ready for policy-controlled execution.`}</p>
          <div>{backend.capabilities.map(capability => <span key={capability}>{readableState(capability)}</span>)}</div>
        </article>)}</div>
      </div> : <div className="solver-manager-layout">
        <section className="manager-workloads">
          <div className="manager-policy"><Gauge size={17} /><span><b>Best available, never silent fallback</b><small>{readableState(manager.selection_policy)}. Approximate and experimental engines retain their validity labels.</small></span></div>
          <label className="engine-label" htmlFor="solver-workload">WORKLOAD</label>
          <select id="solver-workload" value={workload?.id ?? ""} onChange={event => setWorkloadId(event.target.value)}>{manager.workloads.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          {workload && <div className="engine-registration"><label className="engine-label" htmlFor="solver-candidate">EXPLICIT SOLVER PLUGIN</label><div className="register-path"><select id="solver-candidate" value={selectedCandidateId} onChange={event => setCandidateDrafts(current => ({ ...current, [workload.id]: event.target.value }))}>{workload.candidates.map(candidate => <option key={candidate.id} value={candidate.id}>{candidate.name} · {solverReadinessLabel(candidate)}</option>)}</select><button disabled={busy || !selectedCandidateId} onClick={() => onSelectSolver(workload.id, selectedCandidateId)}><Save size={13} /> Select</button></div><small>{solverSelections[workload.id] ? `Project selection: ${solverSelections[workload.id]}.` : "No project selection is stored for this workload."} Selection never substitutes another solver and does not bypass route-specific geometry or validation gates.</small></div>}
          {workload && <div className={`manager-recommendation ${workload.recommended ? "ready" : "gated"}`}><header><span><b>{workload.recommended?.name ?? "No runnable solver"}</b><small>{readableState(workload.status)} / {workload.domain.toUpperCase()}</small></span><i>{workload.recommended ? readableState(workload.recommended.model_status) : "capability gap"}</i></header><p>{workload.recommended?.reason ?? `Required: ${workload.required.map(readableState).join(", ")}`}</p></div>}
          <label className="engine-label">SELECTED WORKLOAD CANDIDATES</label>
          <div className="manager-candidates">{workload?.candidates.map(candidate => <article key={candidate.id}><span className={`engine-dot ${candidate.eligible ? "ready" : "gated"}`} /><span><b>{candidate.name}</b><small>{readableState(candidate.state)}</small><em>{candidate.reason}</em>{candidate.missing.length > 0 && <small>Missing workflow capabilities: {candidate.missing.map(readableState).join(", ")}</small>}</span></article>)}</div>
          <label className="engine-label">WORKLOAD READINESS MATRIX</label>
          <div className="manager-matrix-wrap"><table className="manager-matrix"><thead><tr><th>Workload</th><th>Candidate</th><th>State</th><th>Gate</th></tr></thead><tbody>{workloadRows.map(({ workload: matrixWorkload, candidate }) => <tr key={`${matrixWorkload.id}:${candidate.id}`}>
            <td><b>{matrixWorkload.name}</b><small>{matrixWorkload.required.map(readableState).join(", ") || "No declared requirements"}</small></td>
            <td>{candidate.name}</td>
            <td><i className={candidate.eligible ? "ready" : "gated"}>{solverReadinessLabel(candidate)}</i></td>
            <td title={candidate.reason}>{candidate.missing.length ? candidate.missing.map(readableState).join(", ") : candidate.reason}</td>
          </tr>)}</tbody></table></div>
          <label className="engine-label">EMI PIPELINE</label>
          <div className="emi-pipeline">{manager.emi_pipeline.stages.map(stage => <article key={stage.id}><b>{readableState(stage.id)}</b><i>{readableState(stage.state)}</i><small>{stage.detail}</small></article>)}</div>
        </section>
        <section className="manager-tuning">
          <div className="engine-notice"><ShieldAlert size={14} /><span>{manager.installation.reason}</span></div>
          <label className="engine-label">ALLOWLISTED TUNING</label>
          {manager.tuning_profiles.map(profile => <article className="tuning-profile" key={profile.target_id}><header><span><b>{readableState(profile.target_id)}</b><small>{readableState(profile.application_state ?? "unknown")}</small></span><button onClick={() => saveTuning(profile.target_id)} disabled={busy}><Save size={12} /> Save</button></header>{profile.note && <p>{profile.note}</p>}{profile.parameters.map(parameter => <label key={parameter.key}><span>{readableState(parameter.key)}<small>{parameter.minimum !== undefined ? `${parameter.minimum} - ${parameter.maximum}` : parameter.type}</small></span>{parameter.type === "enum" ? <select value={String(tuneValue(profile.target_id, parameter.key, parameter.value))} onChange={event => setTuneValue(profile.target_id, parameter.key, event.target.value)}>{parameter.values?.map(value => <option key={value}>{value}</option>)}</select> : parameter.type === "boolean" ? <input type="checkbox" checked={Boolean(tuneValue(profile.target_id, parameter.key, parameter.value))} onChange={event => setTuneValue(profile.target_id, parameter.key, event.target.checked)} /> : <input type="number" min={parameter.minimum} max={parameter.maximum} value={String(tuneValue(profile.target_id, parameter.key, parameter.value))} onChange={event => setTuneValue(profile.target_id, parameter.key, event.target.value)} />}</label>)}</article>)}
        </section>
      </div>}

      <footer className="engine-footer"><span><CheckCircle2 size={13} /> No engine is downloaded or executed without an explicit action.</span>{section === "engines" && openems && <div>
        <button className="secondary-btn" onClick={() => onPrepare(selected?.id ?? "external.openems")} disabled={busy || !designAvailable || !selectedNets.length}><FileCode2 size={13} /> Prepare case</button>
        <button className="secondary-btn" onClick={() => onRun(selected?.id ?? "external.openems", true)} disabled={busy || !selectedReady || !caseState?.caseDir}><Activity size={13} /> Build setup</button>
        <button className="run-btn" onClick={() => onRun(selected?.id ?? "external.openems", false)} disabled={busy || !selectedReady || !caseState?.canRun}><Play size={13} /> {busy ? "Working..." : "Run"}</button>
      </div>}</footer>
    </section>
  </div>;
}
