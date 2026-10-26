// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { isDesktopShell, runLocalWorker } from "./workerBridge";
import { SiPlot } from "./SiWorkflowPlots";
import SolverSetupSteps from "./SolverSetupSteps";
import { usePanelPresentation } from "./panelPresentation";
import { coerceIbisDeploymentWorkspace, isIbisDeploymentRequest } from "./siDeploymentWorkspace";
import type { IbisDeploymentWorkspace } from "./siDeploymentWorkspace";
import "./buttonStandard.css";
import "./ibisBehavioral.css";

type Row = Record<string, unknown>;
const record = (value: unknown): Row => value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
const endpoint = () => ({ text: "", name: "model.ibs", model: "", component: "", pin: "", corner: "typ", capacitance_corner: "typ", package_corner: "typ" });
const initial = () => ({ contract: "spike/ibis-behavioral-request/v1", driver: endpoint(), receiver: endpoint(),
  stimulus: { initial_state: "low", transitions: [{ time_s: 1e-9, state: "high", waveform_indices: [0, 1] }] },
  interconnect: { kind: "lossless_tline", impedance_ohm: 50, delay_s: 1e-10 }, analysis: { time_step_s: 1e-11, stop_time_s: 5e-9 } });

export default function IbisBehavioralWorkbench({ workspace, onWorkspaceChange, stagedExample }: {
  workspace?: IbisDeploymentWorkspace | null; onWorkspaceChange?: (value: IbisDeploymentWorkspace) => void;
  stagedExample?: { token: number; requestText: string };
} = {}) {
  const { ownerDocument } = usePanelPresentation();
  const [saved] = useState(() => coerceIbisDeploymentWorkspace(workspace));
  const [request, setRequest] = useState<Row>(() => saved?.request ?? initial()), [step, setStep] = useState("models");
  const [compiled, setCompiled] = useState<Row | null>(null), [runtime, setRuntime] = useState<Row | null>(null);
  const [result, setResult] = useState<Row | null>(() => saved?.result ?? null), [error, setError] = useState("");
  const [resultRequest, setResultRequest] = useState<Row | null>(() => saved?.resultRequest ?? null);
  const [restored, setRestored] = useState(Boolean(saved?.result)), [executable, setExecutable] = useState("");
  const [busy, setBusy] = useState(false), [trusted, setTrusted] = useState(false), [draft, setDraft] = useState(saved?.draft ?? "");
  const [pendingExample, setPendingExample] = useState<string | null>(null);
  const lifetime = useRef(0), revision = useRef(0), notify = useRef(onWorkspaceChange);
  notify.current = onWorkspaceChange;
  const publication = useMemo(() => {
    const value = coerceIbisDeploymentWorkspace({ contract: "spike/ibis-deployment-workspace/v1", request, result, resultRequest, draft });
    return { value, signature: JSON.stringify(value) };
  }, [request, result, resultRequest, draft]);
  const lastPublished = useRef(publication.signature);
  useEffect(() => () => { lifetime.current++; }, []);
  useEffect(() => { if (stagedExample) setPendingExample(stagedExample.requestText); }, [stagedExample?.token]);
  useEffect(() => {
    if (!publication.value) setError("Workspace exceeds the 24 MiB save budget or has invalid input; reduce the draft before saving.");
    else if (lastPublished.current !== publication.signature) {
      lastPublished.current = publication.signature;
      notify.current?.(publication.value);
    }
  }, [publication]);
  const change = (value: Row) => { revision.current++; setRequest(value); setCompiled(null); setResult(null); setResultRequest(null); setRestored(false); setTrusted(false); setError(""); setBusy(false); };
  const worker = async (method: string, params: Row): Promise<Row> => {
    const response = await runLocalWorker({ method, params });
    if (!response.ok) throw new Error(response.error ?? `${method} failed`);
    return record(response.result);
  };
  const perform = async (action: () => Promise<void>) => {
    const valid = current();
    setBusy(true); setError(""); try { await action(); } catch (e) { if (valid()) setError(e instanceof Error ? e.message : String(e)); } finally { if (valid()) setBusy(false); }
  };
  const current = () => { const generation = lifetime.current, version = revision.current; return () => generation === lifetime.current && version === revision.current; };
  const load = (file: File | undefined) => { if (!file) return; const valid = current(); void perform(async () => {
    if (file.size > 17 * 1024 * 1024) throw new Error("Setup exceeds 17 MiB");
    const parsed = record(JSON.parse(await file.text()));
    if (!isIbisDeploymentRequest(parsed)) throw new Error("Expected a structurally valid IBIS behavioral setup, not a raw SPICE netlist");
    if (valid()) change(parsed);
  }); };
  const save = (name: string, value: unknown) => {
    if (!ownerDocument) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
    const link = ownerDocument.createElement("a"); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const editEndpoint = (key: "driver" | "receiver", field: string, value: string) => change({ ...request, [key]: { ...record(request[key]), [field]: value } });
  const models = (["driver", "receiver"] as const).map(key => <fieldset key={key}><legend>{key === "driver" ? "Driver" : "Input receiver / sink"}</legend>
    <label>IBIS file<input type="file" accept=".ibs,.ibis" onChange={event => {
      const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
      const valid = current(); void perform(async () => { if (file.size > 8 * 1024 * 1024) throw new Error("IBIS file exceeds 8 MiB"); const text = await file.text(); if (valid()) change({ ...request, [key]: { ...record(request[key]), text, name: file.name } }); });
    }} /></label>
    <span title={String(record(request[key]).name)}>{String(record(request[key]).name ?? "Choose a source file")}</span>
    {["model", "component", "pin"].map(field => <label key={field}>{field}<input value={String(record(request[key])[field] ?? "")} onChange={e => editEndpoint(key, field, e.target.value)} /></label>)}
    {["corner", "capacitance_corner", "package_corner"].map(field => <label key={field}>{field.replace(/_/g, " ")}<select value={String(record(request[key])[field] ?? "typ")} onChange={e => editEndpoint(key, field, e.target.value)}>{["typ", "min", "max"].map(value => <option key={value}>{value}</option>)}</select></label>)}
  </fieldset>);
  const diagnostics = Array.isArray(compiled?.diagnostics) ? compiled.diagnostics : [];
  const times = Array.isArray(result?.time_s) ? result.time_s as number[] : [];
  const probes = record(result?.probes);
  return <section className="ibis-behavioral" aria-label="Behavioral IBIS driver and receiver" aria-busy={busy}>
    <h3>Behavioral IBIS driver and receiver</h3>
    <p>Experimental classic single-ended I/V and waveform model. Compile first, then explicitly run a reviewed local ngspice executable. Unsupported models stop with diagnostics. This does not establish USB or Ethernet compliance.</p>
    {pendingExample !== null && <details open><summary>Review staged behavioral example</summary><p>The current setup is retained until you apply this example. Applying never compiles or runs it.</p>
      <label>Staged setup JSON<textarea rows={8} readOnly value={pendingExample} /></label>
      <button type="button" disabled={busy} onClick={() => { try { const value: unknown = JSON.parse(pendingExample); if (!isIbisDeploymentRequest(value)) throw new Error("Invalid behavioral example setup"); change(value); setDraft(pendingExample); setPendingExample(null); } catch (reason) { setError(String(reason)); } }}>Apply staged behavioral example</button>
      <button type="button" onClick={() => setPendingExample(null)}>Dismiss staged example</button></details>}
    <div className="ibis-actions"><label>Open setup<input disabled={busy} type="file" accept=".json" onChange={e => { load(e.target.files?.[0]); e.target.value = ""; }} /></label><button type="button" onClick={() => save("ibis-behavioral-setup.json", request)}>Save setup</button></div>
    <SolverSetupSteps label="Behavioral IBIS steps" current={step} onChange={setStep} steps={[
      { id: "models", label: "1. Driver and sink", description: "Choose source files, exact component/pin/model and independent corners." },
      { id: "stimulus", label: "2. Stimulus and channel", description: "Review switching fixtures, states, channel and time resolution." },
      { id: "run", label: "3. Compile and run", description: "Inspect diagnostics, admit the local runtime and inspect returned voltages." }]} />
    {!isDesktopShell() && <p role="status">Model compilation and execution require the SPIKE desktop worker.</p>}
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={busy} className="ibis-stage">
      {step === "models" && <div className="ibis-models">{models}</div>}
      {step === "stimulus" && <><p>Two calibrated resistive fixtures per switching edge are required. Fixture indices refer to the selected model's rising/falling waveform tables. Dynamic high-impedance transitions are unsupported.</p>
        <button type="button" onClick={() => setDraft(JSON.stringify(request, null, 2))}>Review complete setup JSON</button>
        <label>Structured setup (SI units)<textarea rows={16} value={draft} onChange={e => setDraft(e.target.value)} /></label>
        <button type="button" disabled={!draft.trim()} onClick={() => { try { const parsed: unknown = JSON.parse(draft); if (!isIbisDeploymentRequest(parsed)) throw new Error("Invalid setup structure"); change(parsed); } catch (e) { setError(String(e)); } }}>Apply reviewed setup</button></>}
      {step === "run" && <><div className="ibis-actions"><button type="button" disabled={!isDesktopShell()} onClick={() => { const valid = current(); void perform(async () => { const value = await worker("compile_ibis_behavioral", { request }); if (valid()) { setCompiled(value); setResult(null); } }); }}>Compile and check models</button>
        <label>Local ngspice executable (optional)<input value={executable} placeholder="Full path, or leave blank for local discovery" onChange={e => { revision.current++; setExecutable(e.target.value); setRuntime(null); setTrusted(false); setBusy(false); }} /></label>
        <button type="button" disabled={!isDesktopShell()} onClick={() => { const valid = current(); void perform(async () => { const value = await worker("inspect_ibis_behavioral_runtime", executable.trim() ? { executable: executable.trim() } : {}); if (valid()) { setRuntime(value); setTrusted(false); } }); }}>Inspect local ngspice</button></div>
        {compiled && <><p role="status">Compilation: {String(compiled.status)}</p><ul>{diagnostics.map((item, i) => <li key={i}>{String(record(item).message ?? JSON.stringify(item))}</li>)}</ul><details><summary>Generated circuit and provenance</summary><pre>{JSON.stringify(compiled, null, 2)}</pre></details></>}
        {runtime && <><p>Runtime: {String(runtime.status)}</p><code>{String(runtime.executable ?? "No local executable found")}</code><code>{String(runtime.executable_sha256 ?? "")}</code>
          <label><input type="checkbox" checked={trusted} disabled={runtime.status !== "available"} onChange={e => setTrusted(e.target.checked)} />I trust this local executable and want to run native code with the displayed identity.</label></>}
        <button type="button" className="spike-control--primary" disabled={!isDesktopShell() || compiled?.status !== "ready" || !trusted || runtime?.status !== "available"} onClick={() => { const valid = current(); void perform(async () => { const value = await worker("run_ibis_behavioral", { request, executable: runtime?.executable, executable_sha256: runtime?.executable_sha256, execution_requested: true }); if (valid()) { setResult(value); setResultRequest(request); setRestored(false); } }); }}>Run behavioral transient</button>
        <p>Runs are limited to 30 seconds and 512 MiB. Missing OS enforcement fails closed. Project saves retain setup and evidence; executable identity, trust and compile readiness require fresh review after reopening.</p>
        {restored && <p role="status">Restored saved evidence with a matching request snapshot. Source authenticity and the recorded request hash are unverified; this is not a fresh engine validation. Compile and inspect the runtime again before a new run.</p>}
        {result && <><p role="status">Transient: {String(result.status)}</p>{result.status === "completed" && <SiPlot title="IBIS endpoint voltages" xLabel="Time (s)" yLabel="Voltage (V)" curves={["driver_pad_v", "receiver_pad_v", "driver_die_v", "receiver_die_v"].map(name => ({ name, points: times.map((time, i) => ({ x: time, y: Number((probes[name] as number[] | undefined)?.[i]) })) }))} />}
          <button type="button" onClick={() => save("ibis-behavioral-result.json", { request, compiled, result })}>Save complete evidence</button><details><summary>Returned diagnostics and provenance</summary><pre>{JSON.stringify(result, null, 2)}</pre></details></>}
      </>}
    </fieldset>
  </section>;
}
