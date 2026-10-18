// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";
import InteractivePlot from "./InteractivePlot";
import { cancelLocalWorker, isDesktopShell, runLocalWorker, saveNativeTextFile } from "./workerBridge";
import "./buttonStandard.css";
import "./PdnNetworkPanel.css";

export function examplePdnRequest(reference = "GND"): Record<string, unknown> {
  const provenance = { kind: "supplied", source_id: "SPIKE original RC mathematical example" };
  return { contract: "spike/pdn-network-request/v1", reference, nodes: ["rail"],
    elements: [{ id: "SourceZ", type: "source_output_impedance", positive: "rail", negative: reference, resistance_ohm: .1, inductance_h: 0, provenance },
      { id: "Cnet", type: "net_ground_capacitance", node: "rail", capacitance_f: 1e-3, provenance }],
    ports: [{ id: "load", mode: "single", positive: "rail", negative: reference }],
    frequencies_hz: [10, 100, 1000, 10000, 100000, 1000000],
    load_transient: { port_id: "load", points: [{ time_s: 0, current_a: 0 }, { time_s: 1e-6, current_a: 1 }, { time_s: 1e-3, current_a: 1 }],
      output_times_s: Array.from({ length: 101 }, (_, i) => i * 1e-5), max_step_s: 1e-6 } };
}

type NetworkResult = { contract: string; model_status: string; port_ids: string[];
  ac: { frequency_hz: number; impedance_ohm: { real: number; imag: number }[][]; node_transfer_impedance_ohm: Record<string, { real: number; imag: number }[]> }[];
  load_transient: null | { load_port_id?: string; load_port_ids?: string[];
    points: { time_s: number; load_current_a?: number; load_current_a_by_port?: Record<string, number>;
      port_voltage_v: Record<string, number>; node_voltage_v: Record<string, number> }[]; energy_balance_error_j: number };
  diagnostics: { max_ac_relative_residual: number; limitations: string[] } };

export function validPdnNetworkResult(value: unknown): value is NetworkResult {
  if (!value || typeof value !== "object") return false;
  const result = value as NetworkResult;
  const finite = (v: unknown) => typeof v === "number" && Number.isFinite(v);
  if (result.contract !== "spike/pdn-network-result/v1" || result.model_status !== "approximate"
    || !Array.isArray(result.port_ids) || result.port_ids.length < 1 || result.port_ids.length > 16
    || result.port_ids.some(p => typeof p !== "string") || new Set(result.port_ids).size !== result.port_ids.length
    || !Array.isArray(result.ac) || result.ac.length < 1 || result.ac.length > 512
    || !result.diagnostics || !finite(result.diagnostics.max_ac_relative_residual)
    || !Array.isArray(result.diagnostics.limitations) || result.diagnostics.limitations.some(v => typeof v !== "string")) return false;
  const pair = (p: { real: number; imag: number }) => p && finite(p.real) && finite(p.imag);
  let previous = 0;
  const nodeKeys = result.ac[0]?.node_transfer_impedance_ohm ? Object.keys(result.ac[0].node_transfer_impedance_ohm) : [];
  if (nodeKeys.length < 1 || nodeKeys.length > 64) return false;
  for (const point of result.ac) {
    if (!point || typeof point !== "object" || !finite(point.frequency_hz) || point.frequency_hz <= previous || !Array.isArray(point.impedance_ohm)
      || point.impedance_ohm.length !== result.port_ids.length || point.impedance_ohm.some(row => !Array.isArray(row)
        || row.length !== result.port_ids.length || row.some(p => !pair(p))) || !point.node_transfer_impedance_ohm
      || typeof point.node_transfer_impedance_ohm !== "object" || Object.keys(point.node_transfer_impedance_ohm).length > 64
      || Object.keys(point.node_transfer_impedance_ohm).length !== nodeKeys.length || nodeKeys.some(node => !(node in point.node_transfer_impedance_ohm))
      || Object.values(point.node_transfer_impedance_ohm).some(row => !Array.isArray(row) || row.length !== result.port_ids.length || row.some(p => !pair(p)))) return false;
    previous = point.frequency_hz;
  }
  if (result.load_transient !== null) {
    const transient = result.load_transient;
    if (!transient || !Array.isArray(transient.points) || transient.points.length < 1 || transient.points.length > 2048) return false;
    const multiple = "load_port_ids" in transient;
    const loads = multiple ? transient.load_port_ids : [transient.load_port_id];
    if (!Array.isArray(loads) || loads.length < 1 || loads.length > 16
      || loads.some(id => typeof id !== "string" || !result.port_ids.includes(id))
      || new Set(loads).size !== loads.length || (multiple && "load_port_id" in transient)) return false;
    previous = -1;
    for (const point of transient.points) {
      if (!point || typeof point !== "object" || !finite(point.time_s) || point.time_s <= previous || !point.port_voltage_v || !point.node_voltage_v
        || result.port_ids.some(p => !finite(point.port_voltage_v[p])) || Object.keys(point.node_voltage_v).length > 64
        || Object.keys(point.node_voltage_v).length !== nodeKeys.length || nodeKeys.some(node => !(node in point.node_voltage_v))
        || Object.values(point.node_voltage_v).some(v => !finite(v))) return false;
      if (multiple) {
        if ("load_current_a" in point || !point.load_current_a_by_port
          || Object.keys(point.load_current_a_by_port).length !== loads.length
          || loads.some(id => !finite(point.load_current_a_by_port![id!]))) return false;
      } else if (!finite(point.load_current_a) || "load_current_a_by_port" in point) return false;
      previous = point.time_s;
    }
  }
  return true;
}

export default function PdnNetworkPanel({ initial, groundNets = [], availableNets = [], onSave, onClose }: {
  initial?: Record<string, unknown>; groundNets?: string[]; availableNets?: string[]; onSave: (request: Record<string, unknown>) => void; onClose: () => void;
}) {
  const [draft, setDraft] = useState(() => JSON.stringify(initial ?? examplePdnRequest(groundNets[0] ?? "GND"), null, 2));
  const [result, setResult] = useState<NetworkResult | null>(null);
  const [message, setMessage] = useState("Explicit supplied model; the example is not extracted from the current PCB.");
  const [busy, setBusy] = useState(false);
  const [excitationPort, setExcitationPort] = useState("");
  const operation = useRef<string | null>(null);
  const revision = useRef(0);
  const [legDraft, setLegDraft] = useState(() => JSON.stringify({ contract: "spike/series-capacitor-leg/v1", voltage_v: 12,
    capacitors: ["C1", "C2"].map(id => ({ id, capacitance_f: 10e-6, tolerance_fraction: .2, rated_voltage_v: 6.3,
      leakage_resistance_ohm: null, balancing_resistance_ohm: null })) }, null, 2));
  const [legReview, setLegReview] = useState<Record<string, unknown> | null>(null);
  function edit(text: string) { revision.current += 1; setDraft(text); setResult(null); }
  function parse(): Record<string, unknown> {
    if (new TextEncoder().encode(draft).length > 8 * 1024 * 1024) throw new Error("Control file exceeds 8 MiB.");
    const request = JSON.parse(draft);
    if (!request || typeof request !== "object" || request.contract !== "spike/pdn-network-request/v1") throw new Error("A PDN network request v1 is required.");
    return request;
  }
  async function run(saveOnly = false) {
    try {
      const request = parse(), version = revision.current;
      setBusy(true); setMessage("Admitting explicit topology and resource budgets…");
      const id = `pdn-${crypto.randomUUID()}`; operation.current = id;
      const response = await runLocalWorker({ id, method: saveOnly ? "validate_pdn_network" : "evaluate_pdn_network", params: { request } });
      if (operation.current !== id || version !== revision.current) return;
      if (!response.ok || !response.result) throw new Error(response.error_detail?.detail ?? response.error ?? "PDN operation failed.");
      if (saveOnly) { onSave(request); setMessage("AC setup saved to power tree; structural admission is not numerical qualification."); }
      else {
        const candidate = response.result;
        if (!validPdnNetworkResult(candidate)) throw new Error("Malformed or incompatible PDN result. Verify worker version; no curves were installed.");
        setResult(candidate); setMessage("Completed explicit lumped AC/load-spike solve. This does not qualify arbitrary PCB extraction.");
      }
    } catch (error) { setResult(null); setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); operation.current = null; }
  }
  async function stop() { const id = operation.current; operation.current = null; if (id) await cancelLocalWorker(id); }
  async function extractField(file: File) {
    const version = revision.current;
    try {
      if (file.size > 8*1024*1024) throw new Error("Field request exceeds 8 MiB.");
      setBusy(true);
      const fieldRequest = JSON.parse(await file.text());
      const id = `pdn-field-${crypto.randomUUID()}`; operation.current = id;
      const response = await runLocalWorker({ id, method: "extract_pdn_electrostatic", params: { request: fieldRequest } });
      if (operation.current !== id || revision.current !== version) return;
      if (!response.ok || !response.result) throw new Error(response.error_detail?.detail ?? response.error ?? "Field extraction failed.");
      const field = response.result, request = parse();
      const referenceElectrode = field.reference_electrode as { id: string; node: string };
      if (referenceElectrode.node !== request.reference) throw new Error("Field return differs from the selected PDN reference. Review and align explicit identities before attachment.");
      if (!Array.isArray(field.pdn_elements) || !Array.isArray(field.nodes)) throw new Error("Missing field-derived capacitor network.");
      const elements = field.pdn_elements as Record<string, unknown>[];
      if ((request.elements as Record<string, unknown>[]).some(e => elements.some(c => c.id === e.id))) throw new Error("Duplicate capacitor IDs: replace the earlier extraction explicitly before attaching.");
      request.nodes = Array.from(new Set([...(request.nodes as string[]), ...(field.nodes as string[])]));
      request.elements = [...(request.elements as Record<string, unknown>[]), ...elements];
      edit(JSON.stringify(request, null, 2)); setMessage("Attached field-derived ground and mutual capacitors. Finite insulating boundary and geometry-specific refinement limits remain; rerun the PDN.");
    } catch (error) { setMessage(String(error)); }
    finally { setBusy(false); operation.current = null; }
  }
  function referenceChange(next: string) {
    try {
      const request = parse(), previous = request.reference;
      if ((request.nodes as string[]).includes(next)) throw new Error("That reference is currently a conductor node. Review topology before changing its physical meaning.");
      function replace(value: unknown, key = ""): unknown {
        if (["positive", "negative", "node", "reference"].includes(key) && value === previous) return next;
        if (Array.isArray(value)) return value.map(v => ["positive_nodes", "negative_nodes"].includes(key) && v === previous ? next : replace(v));
        if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, replace(v, k)]));
        return value;
      }
      edit(JSON.stringify(replace(request), null, 2));
    } catch (error) { setMessage(String(error)); }
  }
  function seriesLeg() {
    try {
      const request = parse(), nodes = request.nodes as string[], elements = request.elements as Record<string, unknown>[];
      const middle = `series-mid-${elements.length}`; nodes.push(middle);
      const provenance = { kind: "supplied", source_id: "REQUIRES reviewed individual capacitor model" };
      elements.push({ id: `${middle}-C1`, type: "capacitor", positive: nodes[0], negative: middle, capacitance_f: 0, provenance },
        { id: `${middle}-C2`, type: "capacitor", positive: middle, negative: request.reference, capacitance_f: 0, provenance });
      edit(JSON.stringify(request, null, 2)); setMessage("Series intermediate node retained. Assign each C, ESR/ESL and leakage/balancing branches; voltage ratings do not add automatically.");
    } catch (error) { setMessage(String(error)); }
  }
  async function reviewLeg() {
    setBusy(true); setLegReview(null);
    try {
      if (legDraft.length > 65536) throw new Error("Rating input exceeds 64 KiB.");
      const response = await runLocalWorker({ method: "review_series_capacitor_leg", params: { request: JSON.parse(legDraft) } });
      if (!response.ok || !response.result) throw new Error(response.error_detail?.detail ?? response.error ?? "Sharing review failed.");
      setLegReview(response.result);
    } catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }
  function insert(type: string) {
    try {
      const request = parse(), elements = request.elements as Record<string, unknown>[], nodes = request.nodes as string[];
      const id = `model-${elements.length+1}`, provenance = { kind: "supplied", source_id: "REQUIRES reviewed part model" };
      let element: Record<string, unknown>;
      if (type === "net_ground_capacitance") element = { id, type, node: nodes[0], capacitance_f: 0, provenance };
      else if (type === "cm_choke") {
        for (const name of ["cm-in+", "cm-in-", "cm-out+", "cm-out-"]) if (!nodes.includes(name)) nodes.push(name);
        element = { id, type, winding_a: { positive: "cm-in+", negative: "cm-out+", inductance_h: 0, resistance_ohm: 0 },
          winding_b: { positive: "cm-in-", negative: "cm-out-", inductance_h: 0, resistance_ohm: 0 }, coupling_coefficient: 0,
          polarity: "a_positive_to_b_positive", provenance };
      } else element = { id, type, positive: nodes[0], negative: request.reference, inductance_h: 0, resistance_ohm: 0, provenance };
      elements.push(element); edit(JSON.stringify(request, null, 2)); setMessage("Template added. Supply measured/reviewed values and endpoints; zero placeholders are not runnable models.");
    } catch (error) { setMessage(String(error)); }
  }
  const impedance = result?.port_ids.map((port, i) => ({ x: result.ac.map(p => p.frequency_hz),
    y: result.ac.map(p => Math.hypot(p.impedance_ohm[i][i].real, p.impedance_ohm[i][i].imag)), type: "scatter", mode: "lines", name: port })) ?? [];
  const transient = result?.load_transient;
  const sourcePort = result?.port_ids.includes(excitationPort) ? excitationPort : result?.port_ids[0];
  const sourceColumn = result?.port_ids.indexOf(sourcePort ?? "") ?? 0;
  const nodeNames = result?.ac[0] ? Object.keys(result.ac[0].node_transfer_impedance_ohm) : [];
  return <section className="pdn-network-panel" aria-label="AC PDN and CM DM filter network">
    <header><h2>AC PDN / CM–DM filters</h2><button type="button" disabled={busy} onClick={onClose}>Close</button></header>
    <p>Define named nodes, explicit ground, source output impedance, R/L/C, capacitor ESR/ESL and coupled windings. Net names do not infer capacitance or return paths.</p>
    <label>Reference / ground node<select aria-label="PDN ground reference" disabled={busy} value={(() => { try { return String(JSON.parse(draft).reference); } catch { return ""; } })()} onChange={e => referenceChange(e.target.value)}>
      {Array.from(new Set([...groundNets, ...availableNets, (() => { try { return String(JSON.parse(draft).reference); } catch { return "GND"; } })()])).map(net => <option key={net}>{net}</option>)}</select></label>
    <p>Ground suggestions default from the board's ground-like net names; this selects a circuit reference only. Geometry extraction still requires reviewed copper/return coverage.</p>
    <div className="pdn-network-actions">
      <button type="button" disabled={busy} onClick={() => insert("net_ground_capacitance")}>Add net → ground C</button>
      <button type="button" disabled={busy} onClick={() => insert("dm_choke")}>Add DM choke</button>
      <button type="button" disabled={busy} onClick={() => insert("cm_choke")}>Add coupled CM choke</button>
      <button type="button" disabled={busy} onClick={seriesLeg}>Add series capacitor leg</button>
      <label>Import setup<input type="file" accept="application/json,.json" disabled={busy} onChange={async e => { const file = e.target.files?.[0]; if (file && file.size <= 8*1024*1024) edit(await file.text()); else setMessage("File exceeds the control budget."); e.target.value = ""; }} /></label>
      <label>Extract from retained dielectric mesh<input type="file" accept="application/json,.json" disabled={busy || !isDesktopShell()} onChange={e => { const file = e.target.files?.[0]; if (file) void extractField(file); e.target.value = ""; }} /></label>
    </div>
    <label>Network definition in SI units<textarea aria-label="PDN network definition" spellCheck={false} disabled={busy} value={draft} onChange={e => edit(e.target.value)} /></label>
    <div className="pdn-network-actions"><button type="button" disabled={busy || !isDesktopShell()} onClick={() => void run(true)}>Save AC setup to tree</button>
      <button type="button" className="spike-control--primary" disabled={busy || !isDesktopShell()} onClick={() => void run()}>Run AC + load spike</button>
      <button type="button" disabled={!busy} onClick={() => void stop()}>Stop</button>
      <button type="button" disabled={busy} onClick={() => void saveNativeTextFile("pdn-request.json", draft, "result")}>Export setup</button>
      <button type="button" disabled={!result || busy} onClick={() => void saveNativeTextFile("pdn-result.json", JSON.stringify(result, null, 2), "result")}>Export result</button></div>
    <p role="status">{message}</p>
    {!isDesktopShell() && <p>Browser preview supports authoring only; execute in the desktop worker or Python API.</p>}
    <details><summary>Series-capacitor voltage-sharing review</summary><p>Original two-capacitor example. Unknown leakage means DC voltage sharing is not established; balancing resistors require explicit models.</p>
      <textarea aria-label="Series capacitor rating parameters" disabled={busy} value={legDraft} onChange={e => { setLegDraft(e.target.value); setLegReview(null); }} />
      <button type="button" disabled={busy || !isDesktopShell()} onClick={() => void reviewLeg()}>Review sharing and ratings</button>
      {legReview && <pre>{JSON.stringify(legReview, null, 2)}</pre>}</details>
    {result && <><p>Model: {result.model_status}; AC residual {result.diagnostics.max_ac_relative_residual.toExponential(3)}.</p>
      <InteractivePlot title="PDN driving-point impedance" revision={String(revision.current)} data={impedance} layout={{ xaxis: { title: "Frequency (Hz)", type: "log" }, yaxis: { title: "|Z| (ohm)", type: "log" } }} />
      <label>AC current excitation port<select value={sourcePort} onChange={e => setExcitationPort(e.target.value)}>{result.port_ids.map(port => <option key={port}>{port}</option>)}</select></label>
      <InteractivePlot title="Named-net transfer impedance" revision={`${revision.current}-${sourceColumn}`} data={nodeNames.map(node => ({ x: result.ac.map(p => p.frequency_hz), y: result.ac.map(p => Math.hypot(p.node_transfer_impedance_ohm[node][sourceColumn].real, p.node_transfer_impedance_ohm[node][sourceColumn].imag)), name: node, type: "scatter", mode: "lines" }))} layout={{ xaxis: { title: "Frequency (Hz)", type: "log" }, yaxis: { title: "|Vnet / Iport| (ohm)", type: "log" } }} />
      {transient && <InteractivePlot title="Small-signal load-spike response" revision={String(revision.current)} data={result.port_ids.map(port => ({ x: transient.points.map(p => p.time_s), y: transient.points.map(p => p.port_voltage_v[port]), name: port, type: "scatter", mode: "lines" }))} layout={{ xaxis: { title: "Time (s)" }, yaxis: { title: "Rail voltage deviation (V)" } }} />}
      {transient && <InteractivePlot title="Named-net load-spike response" revision={String(revision.current)} data={Object.keys(transient.points[0].node_voltage_v).map(node => ({ x: transient.points.map(p => p.time_s), y: transient.points.map(p => p.node_voltage_v[node]), name: node, type: "scatter", mode: "lines" }))} layout={{ xaxis: { title: "Time (s)" }, yaxis: { title: "Net voltage deviation (V)" } }} />}
      <ul>{result.diagnostics.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul></>}
  </section>;
}
