import { useState } from "react";
import DataTable from "./DataTable";
import type { AssemblyIr, AssemblyDesigns } from "./mcadAssembly";
import { runLocalWorker, saveNativeTextFile } from "./workerBridge";

type Plan = { harnesses: Array<Record<string, unknown>>; connector_mappings: Array<Record<string, unknown>>; connectors: Record<string, unknown>; diagnostics: Array<{ message: string }>; wire_list: Array<Record<string, unknown>>; total_wire_length_mm: number };
type Props = { assembly: AssemblyIr; designs: AssemblyDesigns | null; onApply: (plan: Plan) => void; onStatus: (text: string) => void };

export default function HarnessAutoPlanner({ assembly, designs, onApply, onStatus }: Props) {
  const [slack, setSlack] = useState(10);
  const [allowance, setAllowance] = useState(10);
  const [gauge, setGauge] = useState(24);
  const [clearance, setClearance] = useState(2);
  const [endpointA, setEndpointA] = useState("");
  const [endpointB, setEndpointB] = useState("");
  const [keepouts, setKeepouts] = useState("[]");
  const [waypoints, setWaypoints] = useState("[]");
  const [pinMap, setPinMap] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [fingerprint, setFingerprint] = useState("");
  const [busy, setBusy] = useState(false);
  const state = JSON.stringify({ assembly, designs, slack, allowance, gauge, clearance, endpointA, endpointB, keepouts, waypoints, pinMap });
  const stale = fingerprint !== state;
  const generate = async (discover = false) => {
    setBusy(true);
    try {
      if (!discover && Boolean(endpointA) !== Boolean(endpointB)) throw new Error("Choose both connector endpoints, or leave both automatic.");
      const pairs = discover ? [] : endpointA && endpointB ? [{ endpoint_a: endpointA, endpoint_b: endpointB, waypoints_mm: JSON.parse(waypoints), ...(pinMap.trim() ? { pin_map: JSON.parse(pinMap) } : {}) }] : undefined;
      const response = await runLocalWorker({ method: "plan_assembly_harnesses", params: { request: {
        assembly, designs: Object.fromEntries((designs?.designs ?? []).map(d => [d.design_id, d])), pairs,
        slack_percent: slack, termination_allowance_mm: allowance, gauge_awg: gauge, clearance_mm: clearance, keepouts: JSON.parse(keepouts),
      } } });
      if (!response.ok || !response.result) throw new Error(response.error || "Harness planner returned no result.");
      setPlan(response.result as unknown as Plan); setFingerprint(state);
      onStatus(discover ? "Connector candidates discovered. Review pin identities before generating harnesses." : "Harness proposal ready for review. Add it to the draft, then save the assembly.");
    } catch (error) { setPlan(null); onStatus(String(error)); }
    finally { setBusy(false); }
  };
  const exportCsv = async () => {
    if (!plan) return;
    const columns = ["harness_id", "from", "from_pin", "to", "to_pin", "cut_length_mm", "gauge_awg"];
    // Quoting alone does not prevent spreadsheet formula evaluation.
    const quote = (v: unknown) => { const text = String(v ?? ""); return `"${(/^[=+@\-\t\r]/.test(text) ? "'" + text : text).replace(/"/g, '""')}"`; };
    try {
      const path = await saveNativeTextFile("harness-wire-list.csv", [columns.join(","), ...plan.wire_list.map(row => columns.map(c => quote(row[c])).join(","))].join("\r\n"), "report");
      if (path) onStatus(`Wire list saved to ${path}`);
    } catch (error) { onStatus(String(error)); }
  };
  return <section className="mcad-semantics-editor">
    <h4>Auto-harness</h4>
    <p>Discover J, P and CN connector references from retained boards. Explicit connector mappings override discovered positions and pins. Automatic matching uses exact net names and skips ambiguous or occupied pins.</p>
    <button className="secondary-btn" disabled={busy} onClick={() => void generate(true)}>Discover connectors</button>
    <div className="field-row">
      <label>From connector<select value={endpointA} onChange={e => setEndpointA(e.target.value)}><option value="">Automatic</option>{Object.keys(plan?.connectors ?? {}).map(key => <option key={key}>{key}</option>)}</select></label>
      <label>To connector<select value={endpointB} onChange={e => setEndpointB(e.target.value)}><option value="">Automatic</option>{Object.keys(plan?.connectors ?? {}).map(key => <option key={key}>{key}</option>)}</select></label>
    </div>
    <div className="field-row">
      <label>Slack (%)<input type="number" min="0" max="100" value={slack} onChange={e => setSlack(Number(e.target.value))} /></label>
      <label>Allowance per end (mm)<input type="number" min="0" value={allowance} onChange={e => setAllowance(Number(e.target.value))} /></label>
      <label>Wire gauge (AWG)<input type="number" min="0" max="40" value={gauge} onChange={e => setGauge(Number(e.target.value))} /></label>
      <label>Keepout clearance (mm)<input type="number" min="0" value={clearance} onChange={e => setClearance(Number(e.target.value))} /></label>
    </div>
    <details><summary>Pin overrides, waypoints and cable keepouts</summary>
      <label>Explicit pin map for selected pair (optional)<textarea placeholder={'{"1":"2","2":"1"}'} value={pinMap} onChange={e => setPinMap(e.target.value)} /></label>
      <label>Waypoints in assembly XYZ mm<textarea value={waypoints} onChange={e => setWaypoints(e.target.value)} /></label>
      <label>Forbidden volumes in assembly mm<textarea value={keepouts} onChange={e => setKeepouts(e.target.value)} /></label>
      <small>Keepout format: {`[{"min_mm":[10,10,0],"max_mm":[20,20,30]}]`}. Declare solid obstacles; an enclosure's entire outer box also includes its usable interior.</small>
    </details>
    <button className="secondary-btn" disabled={busy || assembly.boards.length < 2} onClick={() => void generate()}>{busy ? "Planning…" : "Generate harness proposal"}</button>
    {plan && <div aria-live="polite">
      <p>{plan.harnesses.length} harnesses · {plan.wire_list.length} conductors · {(plan.total_wire_length_mm / 1000).toFixed(3)} m total cut length{stale ? " · Inputs changed; regenerate proposal" : ""}</p>
      <DataTable label="Planned harness routes" className="data-table"><thead><tr><th>From</th><th>To</th><th>Pins</th><th>Cut length</th></tr></thead><tbody>{plan.harnesses.map(h => <tr key={String(h.id)}><td>{String(h.endpoint_a)}</td><td>{String(h.endpoint_b)}</td><td>{JSON.stringify(h.pin_map)}</td><td>{Number(h.length_mm).toFixed(1)} mm</td></tr>)}</tbody></DataTable>
      {plan.diagnostics.map((d, i) => <p key={i}>{d.message}</p>)}
      <p>Routes avoid the declared boxes. Bend radius, physical fit, connector compatibility and electrical ratings require review.</p>
      <button className="run-btn" disabled={busy || stale || !plan.harnesses.length} onClick={() => { onApply(plan); setPlan(null); }}>Add proposal to assembly draft</button>
      <button className="secondary-btn" disabled={stale || !plan.wire_list.length} onClick={() => void exportCsv()}>Export wire list CSV</button>
    </div>}
  </section>;
}
