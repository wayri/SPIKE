// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import InteractivePlot from "./InteractivePlot";
import { runLocalWorker } from "./workerBridge";
import { admitCavityResult, cavityHeatmap, type CavityRequest, type CavityResult } from "./nativeCfdPresentation";
import { showFieldInMainViewport } from "./mainFieldViewport";
import { nativeCavityFieldVolume } from "./fieldVolumeAdapters";
import "./buttonStandard.css";
import "./NativeCfdWorkbench.css";

type Props = { workerAvailable?: boolean; onStatus?: (message: string) => void };
const message = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);
export default function NativeCfdWorkbench({ workerAvailable = true, onStatus }: Props) {
  const [n, setN] = useState(16), [reynolds, setReynolds] = useState("100");
  const [runtime, setRuntime] = useState<"unchecked" | "checking" | "ready" | "missing">("unchecked");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [result, setResult] = useState<CavityResult | null>(null), [field, setField] = useState<"speed" | "pressure">("speed");
  const mounted = useRef(true), sequence = useRef(0);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; sequence.current++; }; }, []);
  const valid = Number.isFinite(Number(reynolds)) && reynolds.trim() !== "" && Number(reynolds) >= 1 && Number(reynolds) <= 400;
  const stale = Boolean(result && (result.settings.n !== n || result.settings.reynolds !== Number(reynolds)));
  const plot = useMemo(() => result?.fields ? cavityHeatmap(result, field) : [], [result, field]);
  const volume = useMemo(() => result ? nativeCavityFieldVolume(result) : null, [result]);
  const checkRuntime = async () => {
    setRuntime("checking"); setError("");
    try {
      const response = await runLocalWorker({ method: "cfd_capabilities", params: {} });
      if (!response.ok) throw new Error(response.error || "Worker runtime check failed.");
      const engines = response.result?.engines as Record<string, { available?: boolean }> | undefined;
      if (engines?.["spike.native_cavity"]?.available !== true) throw new Error("Native CFD runtime is missing. Install a worker package containing the native cavity kernel, then retry.");
      if (mounted.current) setRuntime("ready");
    } catch (reason) { if (mounted.current) { setRuntime("missing"); setError(message(reason)); } }
  };
  const run = async () => {
    if (!valid || busy || !workerAvailable || runtime !== "ready") return;
    const request: CavityRequest = { n, reynolds: Number(reynolds) }, token = ++sequence.current;
    setBusy(true); setError(""); setResult(null); onStatus?.("Running native cavity CFD...");
    try {
      const response = await runLocalWorker({ method: "run_native_cfd", params: { request } });
      if (!response.ok) throw new Error(response.error || "Native CFD execution failed.");
      const admitted = admitCavityResult(response.result, request);
      if (mounted.current && token === sequence.current) { setResult(admitted); onStatus?.(admitted.status === "converged" ? "Native cavity CFD converged." : "Native cavity CFD failed to converge."); }
    } catch (reason) { if (mounted.current && token === sequence.current) { setError(message(reason)); onStatus?.("Native CFD failed."); } }
    finally { if (mounted.current && token === sequence.current) setBusy(false); }
  };
  return <section className="native-cfd" aria-label="Native CFD cavity benchmark" aria-busy={busy}>
    <header><h2>Native CFD - cavity benchmark</h2><span className="native-cfd__badge">Experimental</span></header>
    <p>2D laminar square cavity with a moving top wall. Fixed 1 m cavity, 1 m/s lid and 1 kg/m3 density. No imported CAD, thermal coupling or turbulence.</p>
    <div className="native-cfd__controls">
      <label>Grid<select value={n} onChange={event => setN(Number(event.target.value))}>{[16, 32, 64].map(size => <option key={size} value={size}>{size} x {size}</option>)}</select></label>
      <label>Reynolds number<input type="number" min={1} max={400} step="any" value={reynolds} aria-invalid={!valid} onChange={event => setReynolds(event.target.value)} /></label>
      <button type="button" disabled={!workerAvailable || busy || runtime === "checking"} onClick={() => void checkRuntime()}>{runtime === "checking" ? "Checking..." : runtime === "ready" ? "Recheck runtime" : "Check / retry runtime"}</button>
      <button type="button" className="spike-control--primary" disabled={!workerAvailable || runtime !== "ready" || busy || !valid} onClick={() => void run()}>{busy ? "Running..." : "Run native CFD"}</button>
    </div>
    <div className="native-cfd__status" role="status" aria-live="polite">{!workerAvailable ? "Local worker unavailable." : busy ? "Solving in the native worker; results appear after convergence." : runtime === "ready" ? "Native runtime ready." : runtime === "checking" ? "Checking native runtime..." : "Check the native runtime before running."}{!valid && " Reynolds number must be between 1 and 400."}</div>
    {error && <p role="alert" className="native-cfd__error">{error}</p>}
    {stale && <p className="native-cfd__stale" role="status">Settings changed. Displayed result belongs to grid {result!.settings.n} and Re={result!.settings.reynolds}; run again for current settings.</p>}
    {result && <><div className="native-cfd__diagnostics"><strong>{result.status === "converged" ? "Converged" : "Failed to converge - no fields accepted"}</strong><span>{result.diagnostics.steps} steps</span><span>Max divergence: {result.diagnostics.divergence_linf.toExponential(3)} U/L</span><span>Steady rate: {result.diagnostics.steady_rate_linf.toExponential(3)} U^2/L</span></div>
      {result.fields && <><label className="native-cfd__field">Returned field<select value={field} onChange={event => setField(event.target.value as "speed" | "pressure")}><option value="speed">Velocity magnitude (m/s)</option><option value="pressure">Gauge pressure (Pa)</option></select></label><div className="native-cfd__plot"><InteractivePlot title={field === "speed" ? "Native cavity velocity magnitude" : "Native cavity gauge pressure"} data={plot} revision={`${result.settings.n}:${result.settings.reynolds}:${field}`} layout={{ xaxis: { title: { text: "x (m)" } }, yaxis: { title: { text: "y (m)" }, scaleanchor: "x", scaleratio: 1 }, margin: { l: 55, r: 45, t: 15, b: 45 } }} /></div></>}
    </>}
    {volume && <button type="button" onClick={() => showFieldInMainViewport(volume)}>Show fields in main viewport</button>}
    <small>Convergence is a solver stopping condition. This experimental benchmark is not production qualified; pressure has zero mean and no absolute-pressure interpretation.</small>
  </section>;
}
