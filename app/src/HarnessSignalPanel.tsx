// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import PlotlyChart from "./PlotlyChart";
import { runLocalWorker, cancelLocalWorker, cancelLocalWorkerCleanup } from "./workerBridge";
import { HARNESS_SI_FIELDS, HARNESS_SI_KEY, harnessSignalRequest, validHarnessSiResult } from "./harnessSignalModel";
import "./HarnessSignalPanel.css";

export default function HarnessSignalPanel({ value, onChange }: { value: Record<string, any>; onChange: (value: Record<string, any>) => void }) {
  const setup = value.extensions?.[HARNESS_SI_KEY] ?? { selection: {}, model_input: {}, source: "" };
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [em, setEm] = useState<any>(null);
  const operation = useRef<string | null>(null);
  const identity = JSON.stringify(value), current = useRef(identity); current.current = identity;
  useEffect(() => () => { if (operation.current) void cancelLocalWorkerCleanup(operation.current); operation.current = null; }, []);
  const persist = (next: any) => onChange({ ...value, extensions: { ...(value.extensions ?? {}), [HARNESS_SI_KEY]: next } });
  const wires = Array.isArray(value.wires) ? value.wires : [];
  const pairs = (Array.isArray(value.pairs) ? value.pairs : []).filter((pair: any) => pair.kind === "differential");
  let request: any = null;
  try { request = harnessSignalRequest(value, setup); } catch { /* Incomplete forms remain editable. */ }
  const result = request && validHarnessSiResult(setup.latest_result, request) ? setup.latest_result : null;
  const stale = Boolean(setup.latest_result && !result);
  const run = async (method: "run_harness_si" | "prepare_harness_em") => {
    if (busy) return;
    const id = crypto.randomUUID(); operation.current = id; setBusy(true); setError("");
    const submitted = identity;
    try {
      const harness = structuredClone(value); if (harness.extensions) delete harness.extensions[HARNESS_SI_KEY];
      const input = method === "run_harness_si" ? harnessSignalRequest(value, setup)
        : { contract: "spike/harness-em-request/v1", harness, wire_ids: wires.map((wire: any) => wire.id) };
      const response = await runLocalWorker({ id, method, params: { request: input } });
      if (operation.current !== id || current.current !== submitted) return;
      if (!response.ok || !response.result) throw new Error(response.error ?? "Harness worker returned no result.");
      if (method === "run_harness_si") {
        if (!validHarnessSiResult(response.result, input)) throw new Error("The SI result does not match the submitted harness/model.");
        persist({ ...setup, latest_result: response.result });
      } else {
        if (response.result.contract !== "spike/harness-em-handoff/v1" || response.result.status !== "unsupported") throw new Error("Unsupported EM readiness response.");
        setEm({ result: response.result, identity: submitted });
      }
    } catch (reason) { if (operation.current === id) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (operation.current === id) { operation.current = null; setBusy(false); } }
  };
  const series = (output: number, input: number) => result.frequency_hz.map((_: number, index: number) =>
    20 * Math.log10(Math.max(1e-15, Math.hypot(result.s_real[index][output][input], result.s_imag[index][output][input]))));
  return <section className="harness-signal-panel" aria-label="Harness SI and EM"><h4>Harness SI and EM</h4>
    <p>SI solves a uniform two-conductor line from supplied loop or differential-mode RLGC. Pair labels and twist pitch do not extract impedance, common mode or crosstalk. EM readiness lists the missing field-solver requirements.</p>
    <div className="harness-signal-fields"><label>Channel<select value={setup.selection?.pair_id ? `pair:${setup.selection.pair_id}` : "single"} onChange={event => persist({ ...setup, selection: event.target.value === "single" ? {} : { pair_id: event.target.value.slice(5) } })}>
      <option value="single">Explicit signal and return</option>{pairs.map((pair: any) => <option key={pair.id} value={`pair:${pair.id}`}>Differential · {pair.id}</option>)}
    </select></label>
    {!setup.selection?.pair_id && ["signal_wire_id", "return_wire_id"].map(key => <label key={key}>{key === "signal_wire_id" ? "Signal conductor" : "Return conductor"}<select value={setup.selection?.[key] ?? ""} onChange={event => persist({ ...setup, selection: { ...setup.selection, [key]: event.target.value } })}>
      <option value="">Select conductor…</option>{wires.map((wire: any) => <option key={wire.id} value={wire.id}>{wire.id} · {wire.role ?? "unspecified"}</option>)}
    </select></label>)}
    {Object.entries(HARNESS_SI_FIELDS).map(([key, label]) => <label key={key}>{label}<input type="number" min="0" step="any" value={setup.model_input?.[key] ?? ""} onChange={event => persist({ ...setup, model_input: { ...setup.model_input, [key]: event.target.value } })} /></label>)}
    <label className="harness-signal-source">Model source / conditions<input value={setup.source ?? ""} onChange={event => persist({ ...setup, source: event.target.value })} /></label></div>
    <div className="harness-signal-actions"><button className="run-btn" disabled={busy || !wires.length} onClick={() => void run("run_harness_si")}>Run harness SI</button>
      <button className="secondary-btn" disabled={busy || !wires.length} onClick={() => void run("prepare_harness_em")}>Check EM requirements</button>{busy && <><span role="status">Worker running…</span><button className="secondary-btn" onClick={() => {
        const id = operation.current; operation.current = null; setBusy(false); if (id) void cancelLocalWorker(id); setError("Operation stopped; late output will be discarded.");
      }}>Stop</button></>}</div>
    {error && <p role="alert">{error}</p>}{stale && <p role="status">Saved SI result is stale. Recalculate for the current harness and model.</p>}
    {result && <><p>{result.mode} · {result.wire_ids?.join(" / ")} · {result.frequency_hz.length} samples · experimental supplied model</p>
      <PlotlyChart revision={result.request_digest} data={[{ x: result.frequency_hz, y: series(1, 0), name: "S21 transmission", type: "scatter" }, { x: result.frequency_hz, y: series(0, 0), name: "S11 reflection", type: "scatter" }]} layout={{ height: 290, xaxis: { title: { text: "Frequency (Hz)" } }, yaxis: { title: { text: "Magnitude (dB)" } }, margin: { l: 58, r: 15, t: 20, b: 50 } }} />
      <p>Saved with the project. This two-port result excludes board copper, nonlinear devices and coupling to other conductors.</p></>}
    {em && em.identity === identity && <div className="harness-em-readiness"><strong>Harness EM field solve unavailable</strong>{em.result.issues?.map((issue: any, index: number) => <p key={index}><code>{issue.code}</code> · {issue.message}</p>)}</div>}
  </section>;
}
