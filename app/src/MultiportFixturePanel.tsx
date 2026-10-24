import { useGuidedRunAdapter } from "./useGuidedRunAdapter";
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { cancelLocalWorker, isDesktopShell, runLocalWorker } from "./workerBridge";
import { usePanelPresentation } from "./panelPresentation";
import { admitFixtureResult, MULTIPORT_INPUT_BYTES, parseFixtureRequest, type FixtureRequest, type FixtureResult } from "./multiportFixtureModel";
import "./buttonStandard.css";
import "./multiportFixture.css";

export default function MultiportFixturePanel({active:activeView=true,onReveal}:{active?:boolean;onReveal?:()=>void}={}) {
  const { ownerDocument } = usePanelPresentation();
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sample, setSample] = useState(0);
  const [capture, setCapture] = useState<{ source: FixtureRequest; result: FixtureResult } | null>(null);
  const generation = useRef(0);
  const active = useRef<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; generation.current++; const id = active.current; active.current = null; if (id) void cancelLocalWorker(id).catch(() => {}); }; }, []);
  const parsed = useMemo(() => { try { return { request: parseFixtureRequest(text), error: "" }; } catch (e) { return { request: null, error: text ? String(e instanceof Error ? e.message : e) : "Paste or import a complete request JSON." }; } }, [text]);
  function edit(value: string) { generation.current++; setText(value); setCapture(null); setError(""); }
  async function importFile(file?: File) {
    if (!file || busy) return;
    const token = ++generation.current;
    setCapture(null); setError("");
    try {
      if (file.size > MULTIPORT_INPUT_BYTES) throw new Error("Request exceeds the 8 MiB import limit.");
      const value = await file.text();
      if (!mounted.current || token !== generation.current) return;
      parseFixtureRequest(value); setText(value);
    } catch (e) { if (mounted.current && token === generation.current) { setText(""); setError(String(e instanceof Error ? e.message : e)); } }
  }
  const requestFixtureRun=useGuidedRunAdapter({
    id:"si-multiport",context:{key:"si-multiport-fixture",revision:JSON.stringify([text,busy,isDesktopShell(),activeView]),workspace:"HF / SI",title:"Multiport fixture removal"},
    check:async()=>({requirements:!activeView?[{id:"fixture-view",title:"Return to fixture setup",detail:"Reveal the fixture tool before checking or executing this request.",severity:"blocker",route:"request"}]:!isDesktopShell()||busy?[{id:"fixture-runtime",title:busy?"Wait for fixture processing":"Open SPIKE desktop",detail:busy?"Finish or cancel the current fixture operation.":"The local worker is required.",severity:"blocker",route:"request"}]:!parsed.request?[{id:"fixture-input",title:"Review the fixture request",detail:parsed.error,severity:"blocker",route:"request"}]:[],summary:"Source/fixture identity and numerical admission are checked again by the owning worker."}),
    fix:item=>{onReveal?.();setError(item.detail);ownerDocument?.querySelector<HTMLTextAreaElement>('textarea[aria-label="Multiport request JSON"]')?.focus();},
    run:async(_context,signal)=>{if(!signal.aborted)await run(true);},
    tutorSteps:[{id:"request",title:"Supply the request",detail:"Import reviewed DUT/fixture networks with explicit named port order and wave convention.",route:"request"},{id:"run",title:"Check and run",detail:"Resolve admission diagnostics and run the unchanged fixture removal service.",route:"request"},{id:"review",title:"Review and export",detail:"Inspect recovered samples and export the retained source/result capture; this is not measurement calibration qualification.",route:"request"}],
  });
  async function run(propagateFailure=false) {
    if (active.current || busy || !isDesktopShell()) return;
    let source: FixtureRequest;
    try { source = parseFixtureRequest(text); } catch { return; }
    const token = ++generation.current;
    const id = `multiport-fixture-${Date.now()}-${token}`;
    active.current = id; setBusy(true); setCapture(null); setError("");
    try {
      const response = await runLocalWorker({ id, method: "deembed_multiport", params: { request: JSON.parse(JSON.stringify(source)) } });
      if (!mounted.current || token !== generation.current || active.current !== id) return;
      if (!response.ok) {
        const detail = response.error_detail;
        const networkCode = detail?.context?.network_code;
        throw new Error([typeof networkCode === "string" ? networkCode : "", detail?.detail,
          response.error ?? "Fixture removal failed."].filter(Boolean).join(": "));
      }
      const result = admitFixtureResult(response.result, source);
      setSample(0); setCapture({ source: JSON.parse(JSON.stringify(source)), result });
    } catch (e) { if (mounted.current && token === generation.current) { setCapture(null); setError(String(e instanceof Error ? e.message : e)); } if(propagateFailure)throw e; }
    finally { if (mounted.current && active.current === id) { active.current = null; setBusy(false); } }
  }
  async function cancel() {
    const id = active.current;
    if (!id) return;
    generation.current++; active.current = null; setBusy(false); setCapture(null); setError("Fixture removal cancelled; no result retained.");
    try { await cancelLocalWorker(id); } catch { /* Late responses remain invalidated. */ }
  }
  function exportCapture() {
    if (!capture || !ownerDocument) return;
    const anchor = ownerDocument.createElement("a");
    const url = URL.createObjectURL(new Blob([JSON.stringify(capture, null, 2)], { type: "application/json" }));
    anchor.href = url; anchor.download = "multiport-fixture-capture.json"; anchor.click(); URL.revokeObjectURL(url);
  }
  return <section className="multiport-fixture" aria-label="Multiport fixture removal">
    <h3>Multiport fixture removal</h3>
    <p>Experimental supplied coupled 2N-port fixture algebra. Calibration, measurement uncertainty, causality and production qualification remain open. No geometry extraction or transient qualification.</p>
    <label>Complete request JSON (maximum 8 MiB)<textarea aria-label="Multiport request JSON" value={text} disabled={busy} onChange={e => edit(e.target.value)} spellCheck={false} /></label>
    <div className="multiport-fixture-actions"><label>Import request JSON <input aria-label="Import multiport request JSON" type="file" accept=".json,application/json" disabled={busy} onChange={e => { void importFile(e.target.files?.[0]); e.target.value = ""; }} /></label>
      <button type="button" className="spike-control--primary" disabled={busy || !parsed.request || !isDesktopShell()} onClick={requestFixtureRun}>Run fixture removal</button>
      <button type="button" disabled={!busy} onClick={() => void cancel()}>Cancel fixture removal</button>
      <button type="button" disabled={!capture || busy} onClick={exportCapture}>Export source and result</button></div>
    {!isDesktopShell() && <p>Execution requires the SPIKE desktop shell.</p>}
    {error ? <p role="alert">{error}</p> : parsed.error && <p role="status">{parsed.error}</p>}
    {busy && <p role="status">Removing supplied fixture…</p>}
    {parsed.request && <div className="multiport-fixture-summary"><p>Measured: {parsed.request.measured.id}; fixture: {parsed.request.fixture.id}</p><p>Ordered exterior set: {parsed.request.external_ports.join(", ")}</p><p>Ordered DUT set: {parsed.request.dut_ports.join(", ")}</p><p>These are independent ordered matrix index sets, not port-pairing claims.</p><p>{parsed.request.measured.frequencies_hz.length} samples; reference {parsed.request.measured.reference_impedance_ohm} ohm</p></div>}
    {capture && <div className="multiport-fixture-summary" aria-label="Retained fixture result"><h4>Experimental result retained</h4><p>{capture.result.derived_network.port_names.length} DUT ports; {capture.result.diagnostics.length} complete diagnostic samples</p><p>Input digest: {capture.result.input_digest}</p><ul>{capture.result.limitations.map((limitation, i) => <li key={i}>{limitation}</li>)}</ul>
      <label>Retained sample (zero-based)<input aria-label="Retained multiport sample" type="number" min={0} max={capture.result.diagnostics.length - 1} step={1} value={sample} onChange={e => { const i = Number(e.target.value); if (Number.isInteger(i) && i >= 0 && i < capture.result.diagnostics.length) setSample(i); }} /></label>
      <p>Frequency: {capture.result.derived_network.frequencies_hz[sample]} Hz. Matrix rows and columns both follow the ordered DUT set above. Entries retain real and imaginary components.</p>
      <details><summary>Selected DUT matrix and worker diagnostics</summary><pre>{JSON.stringify({ s_parameters: capture.result.derived_network.s_parameters[sample], diagnostics: capture.result.diagnostics[sample] }, null, 2)}</pre></details>
    </div>}
  </section>;
}
