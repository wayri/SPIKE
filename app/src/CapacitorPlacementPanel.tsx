// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import PlotlyChart from "./PlotlyChart";
import { runLocalWorker } from "./workerBridge";
import "./buttonStandard.css";
import "./CapacitorPlacementPanel.css";

type Capacitor = { capacitance_f: number; esr_ohm: number; esl_h: number; voltage_rating_v: number; ripple_current_rating_a_rms: number };
type Candidate = { id: string; port_id: string; occurrence_id: string; x_mm: number; y_mm: number; capacitor: Capacitor };
export type CapacitorPlacementRequest = {
  contract: "spike/capacitor-placement-request/v1"; board_occurrence_id: string;
  reference_return: { occurrence_id: string; net: string }; frequencies_hz: number[];
  ports: { id: string; occurrence_id: string }[]; z_ohm: [number, number][][][];
  loads: { port_id: string; current_a_rms: number }[]; candidates: Candidate[];
  dc_voltage_v: number; target_impedance_ohm: number; frequency_band_hz: [number, number];
  provenance: { source_id: string; conditions: string };
};
type Sample = { frequency_hz: number; status: "computed" | "ill_conditioned_shunt_resonance";
  load_impedance_ohm?: [number, number][]; load_impedance_magnitude_ohm?: number[];
  maximum_impedance_ohm?: number; maximum_target_ratio?: number };
type Summary = { samples: Sample[]; worst_target_ratio: number | null; peak_impedance_ohm: number | null;
  peak_frequency_hz: number | null; meets_sampled_target: boolean };
type CandidateResult = Candidate & Summary & { status: "computed" | "incomplete"; eligible: boolean; issues: string[];
  color_metric: number | null; improvement_fraction: number | null; maximum_capacitor_current_a_rms: number | null;
  required_voltage_rating_v: number | null; maximum_capacitor_esr_loss_w: number | null };
export type CapacitorPlacementResult = {
  contract: "spike/capacitor-placement-result/v1"; model_status: "approximate"; status: "completed";
  board_occurrence_id: string; reference_return: CapacitorPlacementRequest["reference_return"];
  frequency_band_hz: [number, number]; target_impedance_ohm: number; load_port_ids: string[];
  baseline: Summary; candidates: CandidateResult[]; ranked_candidate_ids: string[];
  best_candidate_id: string | null; recommended_candidate_id: string | null;
  provenance: CapacitorPlacementRequest["provenance"]; limitations: string[];
  request_snapshot: CapacitorPlacementRequest;
};
export type CapacitorPlacementPanelProps = {
  workerAvailable: boolean;
  initialRequest?: CapacitorPlacementRequest | null;
  initialResult?: unknown;
  onResult?: (request: CapacitorPlacementRequest, result: CapacitorPlacementResult) => void;
  onStatus?: (message: string) => void;
};
const MAX_TEXT = 24 * 1024 * 1024;
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const nonnegative = (v: unknown): v is number => finite(v) && v >= 0;
const text = (v: unknown): v is string => typeof v === "string" && v.length > 0 && v.length <= 256 && v.trim() === v;
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const numbers = (v: unknown): v is number[] => Array.isArray(v) && v.every(finite);
const texts = (v: unknown): v is string[] => Array.isArray(v) && v.every(item => typeof item === "string");
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
export function sameCapacitorPlacementRequest(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b)
    && a.length === b.length && a.every((value, i) => sameCapacitorPlacementRequest(value, b[i]));
  if (!record(a) || !record(b)) return false;
  const keys = Object.keys(a).sort(), otherKeys = Object.keys(b).sort();
  return same(keys, otherKeys) && keys.every(key => sameCapacitorPlacementRequest(a[key], b[key]));
}
const format = (v: number | null | undefined) => finite(v) ? v.toPrecision(4) : "Not available";

export function parseCapacitorPlacementRequest(source: string): CapacitorPlacementRequest {
  if (!source.trim()) throw new Error("Paste a sampled-network JSON request or load the labeled synthetic example.");
  if (source.length > MAX_TEXT) throw new Error("Request exceeds the 24 MiB text budget.");
  const raw: unknown = JSON.parse(source);
  if (!record(raw) || raw.contract !== "spike/capacitor-placement-request/v1" || !text(raw.board_occurrence_id)) throw new Error("Expected a capacitor-placement request with a board occurrence.");
  const r = raw as unknown as CapacitorPlacementRequest;
  if (!record(r.reference_return) || r.reference_return.occurrence_id !== r.board_occurrence_id || !text(r.reference_return.net)) throw new Error("Declare a return net on the same board occurrence.");
  if (!numbers(r.frequencies_hz) || r.frequencies_hz.length < 2 || r.frequencies_hz.length > 1024
    || r.frequencies_hz.some((f, i) => f <= 0 || (i > 0 && f <= r.frequencies_hz[i - 1]))) throw new Error("Supply 2-1024 positive increasing frequencies in Hz.");
  if (!Array.isArray(r.ports) || !r.ports.length || r.ports.length > 32
    || r.ports.some(p => !record(p) || !text(p.id) || p.occurrence_id !== r.board_occurrence_id)) throw new Error("Declare 1-32 same-board ports.");
  const ids = new Set(r.ports.map(p => p.id));
  if (ids.size !== r.ports.length) throw new Error("Port IDs must be unique.");
  const count = r.ports.length;
  if (r.frequencies_hz.length * count * count > 262144 || !Array.isArray(r.z_ohm) || r.z_ohm.length !== r.frequencies_hz.length
    || r.z_ohm.some(matrix => !Array.isArray(matrix) || matrix.length !== count || matrix.some(row => !Array.isArray(row) || row.length !== count
      || row.some(pair => !numbers(pair) || pair.length !== 2)))) throw new Error("Z must be bounded [frequency][row][column][real, imaginary] samples in ohms.");
  if (!Array.isArray(r.loads) || !r.loads.length || r.loads.length > 32 || r.loads.some(l => !record(l) || !ids.has(l.port_id) || !finite(l.current_a_rms))
    || new Set(r.loads.map(l => l.port_id)).size !== r.loads.length) throw new Error("Supply distinct declared load ports and finite RMS ripple currents.");
  if (!Array.isArray(r.candidates) || !r.candidates.length || r.candidates.length > 256
    || r.candidates.length * r.loads.length * r.frequencies_hz.length > 131072) throw new Error("Candidate/frequency/load response budget exceeded or candidates missing.");
  const capFields = ["capacitance_f", "esr_ohm", "esl_h", "voltage_rating_v", "ripple_current_rating_a_rms"] as const;
  if (r.candidates.some(c => !record(c) || !text(c.id) || !ids.has(c.port_id) || c.occurrence_id !== r.board_occurrence_id
    || !finite(c.x_mm) || !finite(c.y_mm) || !record(c.capacitor) || capFields.some(key => !finite(c.capacitor[key])))
    || new Set(r.candidates.map(c => c.id)).size !== r.candidates.length) throw new Error("Candidates require unique IDs, same-board port bindings, XY coordinates and explicit capacitor values/ratings.");
  if (!finite(r.dc_voltage_v) || !finite(r.target_impedance_ohm) || r.target_impedance_ohm <= 0 || !numbers(r.frequency_band_hz) || r.frequency_band_hz.length !== 2
    || !record(r.provenance) || !text(r.provenance.source_id) || !text(r.provenance.conditions)) throw new Error("Provide DC voltage, positive target impedance, band edges and source conditions.");
  return r; // Physical admission and strict field checking remain authoritative in Python.
}

export function validCapacitorPlacementResult(raw: unknown, request: CapacitorPlacementRequest): raw is CapacitorPlacementResult {
  if (!record(raw)) return false;
  const r = raw as unknown as CapacitorPlacementResult;
  if (r.contract !== "spike/capacitor-placement-result/v1" || r.model_status !== "approximate" || r.status !== "completed"
    || !sameCapacitorPlacementRequest(r.request_snapshot, request)
    || r.board_occurrence_id !== request.board_occurrence_id || !sameCapacitorPlacementRequest(r.reference_return, request.reference_return)
    || !same(r.frequency_band_hz, request.frequency_band_hz) || r.target_impedance_ohm !== request.target_impedance_ohm
    || !same(r.load_port_ids, request.loads.map(l => l.port_id)) || !sameCapacitorPlacementRequest(r.provenance, request.provenance)
    || !texts(r.limitations) || !r.limitations.length || !Array.isArray(r.candidates) || r.candidates.length !== request.candidates.length) return false;
  const validSummary = (s: Summary, complete: boolean) => record(s) && Array.isArray(s.samples) && s.samples.length === request.frequencies_hz.length
    && typeof s.meets_sampled_target === "boolean" && [s.worst_target_ratio, s.peak_impedance_ohm, s.peak_frequency_hz].every(v => complete ? nonnegative(v) : v === null)
    && s.samples.every((p, i) => record(p) && p.frequency_hz === request.frequencies_hz[i] && (p.status === "ill_conditioned_shunt_resonance" ? !complete
      : p.status === "computed" && nonnegative(p.maximum_impedance_ohm) && nonnegative(p.maximum_target_ratio)
      && Array.isArray(p.load_impedance_ohm) && p.load_impedance_ohm.length === request.loads.length && p.load_impedance_ohm.every(pair => numbers(pair) && pair.length === 2)
      && Array.isArray(p.load_impedance_magnitude_ohm) && p.load_impedance_magnitude_ohm.length === request.loads.length && p.load_impedance_magnitude_ohm.every(nonnegative)));
  if (!validSummary(r.baseline, true)) return false;
  if (!r.candidates.every((c, i) => {
    const expected = request.candidates[i];
    return record(c) && c.id === expected.id && c.port_id === expected.port_id && c.occurrence_id === expected.occurrence_id
      && c.x_mm === expected.x_mm && c.y_mm === expected.y_mm && sameCapacitorPlacementRequest(c.capacitor, expected.capacitor)
      && (c.status === "computed" || c.status === "incomplete") && typeof c.eligible === "boolean" && texts(c.issues)
      && c.eligible === (c.status === "computed" && !c.issues.length) && validSummary(c, c.status === "computed")
      && (c.status === "computed" || c.samples.some(s => s.status !== "computed"))
      && c.color_metric === c.worst_target_ratio && (c.improvement_fraction === null || finite(c.improvement_fraction))
      && [c.maximum_capacitor_current_a_rms, c.required_voltage_rating_v, c.maximum_capacitor_esr_loss_w].every(v => c.status === "computed" ? nonnegative(v) : v === null);
  })) return false;
  const eligible = new Set(r.candidates.filter(c => c.eligible).map(c => c.id));
  const best = r.candidates.find(c => c.id === r.best_candidate_id);
  return texts(r.ranked_candidate_ids) && new Set(r.ranked_candidate_ids).size === r.ranked_candidate_ids.length
    && r.ranked_candidate_ids.length === eligible.size && r.ranked_candidate_ids.every(id => eligible.has(id))
    && r.best_candidate_id === (r.ranked_candidate_ids[0] ?? null)
    && (r.recommended_candidate_id === null || (r.recommended_candidate_id === r.best_candidate_id && eligible.has(r.recommended_candidate_id)
      && best?.worst_target_ratio !== null && best?.worst_target_ratio !== undefined && best.worst_target_ratio < r.baseline.worst_target_ratio!));
}

export function syntheticCapacitorPlacementRequest(): CapacitorPlacementRequest {
  // Original constant two-node resistor Z samples: 0.1 ohm to reference and
  // 0.05 ohm link. These are illustrative data, not extracted PCB impedances.
  const frequencies = [100, 300, 1000, 3000, 10000, 30000, 100000];
  const occurrence = "synthetic-two-node-example";
  return { contract: "spike/capacitor-placement-request/v1", board_occurrence_id: occurrence,
    reference_return: { occurrence_id: occurrence, net: "synthetic-return" }, frequencies_hz: frequencies,
    ports: ["upstream", "load"].map(id => ({ id, occurrence_id: occurrence })),
    z_ohm: frequencies.map(() => [[[0.1, 0], [0.1, 0]], [[0.1, 0], [0.15, 0]]]),
    loads: [{ port_id: "load", current_a_rms: 1 }],
    candidates: ["upstream", "load"].map((port_id, i) => ({ id: `example-${i + 1}`, port_id, occurrence_id: occurrence, x_mm: i * 10, y_mm: i * 5,
      capacitor: { capacitance_f: 0.001, esr_ohm: 0.01, esl_h: 1e-9, voltage_rating_v: 25, ripple_current_rating_a_rms: 10 } })),
    dc_voltage_v: 5, target_impedance_ohm: 0.1, frequency_band_hz: [100, 100000],
    provenance: { source_id: "synthetic-series-resistor-example", conditions: "Original illustrative 0.1 ohm source and 0.05 ohm link. No PCB extraction or measured device data." } };
}

export function CapacitorPlacementResults({ result, selectedId, onSelect }: { result: CapacitorPlacementResult; selectedId: string; onSelect: (id: string) => void }) {
  const selected = result.candidates.find(c => c.id === selectedId) ?? result.candidates[0];
  const frequencies = result.baseline.samples.map(s => s.frequency_hz);
  const traces = [{ type: "scatter", mode: "lines+markers", name: "Baseline maximum across loads", x: frequencies,
    y: result.baseline.samples.map(s => s.maximum_impedance_ohm! > 0 ? s.maximum_impedance_ohm : null), connectgaps: false },
  { type: "scatter", mode: "lines+markers", name: `Selected: ${selected.id}`, x: frequencies,
    y: selected.samples.map(s => s.status === "computed" && s.maximum_impedance_ohm! > 0 ? s.maximum_impedance_ohm : null), connectgaps: false },
  { type: "scatter", mode: "lines", name: "Target impedance", x: frequencies, y: frequencies.map(() => result.target_impedance_ohm), line: { dash: "dash" } }];
  const groups = [result.candidates.filter(c => c.eligible), result.candidates.filter(c => !c.eligible)];
  const mapTraces: Record<string, unknown>[] = groups.map((group, index) => ({ type: "scatter", mode: "markers", name: index ? "Excluded" : "Eligible candidates",
    x: group.map(c => c.x_mm), y: group.map(c => c.y_mm), customdata: group.map(c => c.id), text: group.map(c => c.id),
    marker: index ? { size: 13, symbol: "x", color: "#8c8c8c" } : { size: 15, color: group.map(c => c.color_metric),
      colorscale: [[0, "#2a9d8f"], [0.5, "#f4d35e"], [1, "#e76f51"]], showscale: true, colorbar: { title: "Worst |Z| / target", thickness: 12 } },
    hovertemplate: "%{text}<br>X %{x} mm; Y %{y} mm<extra></extra>" }));
  mapTraces.push({ type: "scatter", mode: "markers", name: "Selected candidate", x: [selected.x_mm], y: [selected.y_mm],
    customdata: [selected.id], marker: { size: 22, symbol: "circle-open", color: "#4986c7", line: { width: 3 } },
    hovertemplate: "Selected candidate<extra></extra>" });
  return <div className="cap-placement-results">
    <p className="cap-placement-notice"><b>Approximate sampled-network comparison.</b> Best eligible supplied candidate: {result.best_candidate_id ?? "none"}.
      {result.recommended_candidate_id ? ` Improving candidate: ${result.recommended_candidate_id}.` : " No eligible candidate improves the baseline."}</p>
    <div className="cap-placement-plots">
      <figure><figcaption>Impedance magnitude versus frequency</figcaption><PlotlyChart title="Capacitor placement impedance sweep" data={traces}
        revision={`cap-curve:${selected.id}:${JSON.stringify(traces.map(t => t.y))}`} layout={{ margin: { l: 72, r: 15, t: 15, b: 70 }, legend: { orientation: "h" },
          xaxis: { title: "Frequency (Hz)", type: "log" }, yaxis: { title: "Maximum load |Z| (ohm)", type: "log" } }} />
        <small>Lines join supplied samples. Singular samples leave gaps; exact zero impedance is omitted on the log scale. No unsampled resonance search.</small></figure>
      <figure><figcaption>Candidate positions and impedance score</figcaption><PlotlyChart title="Capacitor candidate XY map" data={mapTraces}
        revision={`cap-map:${selected.id}:${JSON.stringify(result.candidates.map(c => [c.id, c.x_mm, c.y_mm, c.color_metric, c.eligible]))}`}
        onPointClick={point => { if (typeof point.customdata === "string" && result.candidates.some(c => c.id === point.customdata)) onSelect(point.customdata); }}
        layout={{ margin: { l: 52, r: 65, t: 15, b: 65 }, legend: { orientation: "h" }, xaxis: { title: "X (mm)" }, yaxis: { title: "Y (mm)", scaleanchor: "x" } }} />
        <small>Click a candidate or use its table button. Lower score is better; gray crosses are excluded. Coordinates label network ports; no continuous spatial field is inferred.</small></figure>
    </div>
    <div className="cap-placement-table"><table aria-label="Capacitor candidate ranking"><thead><tr><th>Candidate</th><th>Rank</th><th>Worst |Z| / target</th><th>Improvement</th><th>Admission</th></tr></thead>
      <tbody>{result.candidates.map(c => <tr key={c.id} aria-selected={c.id === selected.id}><td><button type="button" className="spike-control--compact" aria-pressed={c.id === selected.id} onClick={() => onSelect(c.id)}>{c.id}</button></td>
        <td>{c.eligible ? result.ranked_candidate_ids.indexOf(c.id) + 1 : "Excluded"}</td><td>{format(c.worst_target_ratio)}</td><td>{c.improvement_fraction === null ? "Not available" : `${format(c.improvement_fraction * 100)}%`}</td>
        <td>{c.issues.length ? c.issues.join(", ") : c.meets_sampled_target ? "Within sampled target" : "Eligible; target exceeded"}</td></tr>)}</tbody></table></div>
    <section aria-label="Selected capacitor diagnostics"><h4>Selected candidate: {selected.id}</h4>
      <p>Port {selected.port_id} on {selected.occurrence_id}; ({format(selected.x_mm)}, {format(selected.y_mm)}) mm.</p>
      <p>Peak sampled impedance {format(selected.peak_impedance_ohm)} ohm at {format(selected.peak_frequency_hz)} Hz.
        Required voltage rating {format(selected.required_voltage_rating_v)} V; supplied {format(selected.capacitor.voltage_rating_v)} V.
        Maximum capacitor ripple {format(selected.maximum_capacitor_current_a_rms)} A RMS; supplied rating {format(selected.capacitor.ripple_current_rating_a_rms)} A RMS.
        Maximum independent-scenario ESR loss {format(selected.maximum_capacitor_esr_loss_w)} W.</p>
      {selected.issues.length > 0 && <p role="status">Excluded from ranking: {selected.issues.join(", ")}</p>}</section>
    <details><summary>Computed frequency samples</summary><div className="cap-placement-table"><table aria-label="Capacitor frequency values"><thead><tr><th>Hz</th><th>Baseline maximum (ohm)</th><th>Selected maximum (ohm)</th><th>Status</th></tr></thead>
      <tbody>{selected.samples.map((s, i) => <tr key={s.frequency_hz}><td>{format(s.frequency_hz)}</td><td>{format(result.baseline.samples[i].maximum_impedance_ohm)}</td><td>{format(s.maximum_impedance_ohm)}</td><td>{s.status}</td></tr>)}</tbody></table></div></details>
    <details><summary>Source, return and model limits</summary><p>Source: {result.provenance.source_id}. {result.provenance.conditions}</p>
      <p>Reference return: {result.reference_return.net} on {result.reference_return.occurrence_id}. Scoring band: {result.frequency_band_hz.map(format).join(" to ")} Hz.</p>
      <ul>{result.limitations.map((limit, i) => <li key={i}>{limit}</li>)}</ul></details>
  </div>;
}

export default function CapacitorPlacementPanel({ workerAvailable, initialRequest, initialResult, onResult, onStatus }: CapacitorPlacementPanelProps) {
  const [initial] = useState(() => {
    let source = "";
    let request: CapacitorPlacementRequest | null = null;
    let result: CapacitorPlacementResult | null = null;
    if (initialRequest) {
      try {
        const parsed = parseCapacitorPlacementRequest(JSON.stringify(initialRequest));
        request = parsed;
        source = JSON.stringify(parsed, null, 2);
        if (validCapacitorPlacementResult(initialResult, parsed)) result = initialResult;
      } catch { /* Invalid persisted input remains untrusted and is not displayed. */ }
    }
    return { source, request, result };
  });
  const [source, setSource] = useState(() => initial.source);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [solved, setSolved] = useState<{ source: string; request: CapacitorPlacementRequest; result: CapacitorPlacementResult } | null>(() =>
    initial.result && initial.request ? { source: initial.source, request: initial.request, result: initial.result } : null);
  const [selectedId, setSelectedId] = useState(() => initial.result?.best_candidate_id ?? initial.result?.candidates[0]?.id ?? "");
  const runId = useRef(0);
  const currentSource = useRef(source); currentSource.current = source;
  useEffect(() => () => { runId.current += 1; }, []);
  const edit = (value: string) => { currentSource.current = value; setSource(value); setError(""); runId.current += 1; setBusy(false); };
  const run = async () => {
    if (!workerAvailable || busy) return;
    const id = ++runId.current;
    const submittedSource = source;
    setError("");
    try {
      const request = parseCapacitorPlacementRequest(submittedSource);
      setBusy(true);
      const response = await runLocalWorker({ id: `capacitor-placement-${id}`, method: "evaluate_capacitor_placement", params: { request } });
      if (runId.current !== id || currentSource.current !== submittedSource) return;
      if (!response.ok) throw new Error(response.error || "Capacitor comparison failed.");
      if (!validCapacitorPlacementResult(response.result, request)) throw new Error("Worker result does not match the submitted network or result contract.");
      setSolved({ source: submittedSource, request, result: response.result });
      setSelectedId(response.result.best_candidate_id ?? response.result.candidates[0].id);
      onResult?.(request, response.result);
      onStatus?.("Capacitor candidate comparison completed; sampled-network limits apply.");
    } catch (reason) {
      if (runId.current === id) { const message = reason instanceof Error ? reason.message : String(reason); setError(message); onStatus?.(message); }
    } finally { if (runId.current === id) setBusy(false); }
  };
  const stale = solved && source !== solved.source;
  return <section className="cap-placement-panel" aria-label="Capacitor placement comparison">
    <h3>Capacitor placement comparison</h3><p>Paste an explicit sampled Z network with a declared return and candidate locations. SPIKE does not infer impedance from board coordinates.</p>
    <p>SI units; XY in mm. Load current is an independent single-tone RMS ripple amplitude, not the rail's DC current. Best means best eligible supplied candidate at supplied frequencies.</p>
    <label>Sampled-network request JSON<textarea aria-label="Capacitor placement request JSON" value={source} maxLength={MAX_TEXT} spellCheck={false}
      placeholder="Paste spike/capacitor-placement-request/v1 JSON" onChange={event => edit(event.target.value)} /></label>
    <div className="cap-placement-actions"><button type="button" className="spike-control--compact" onClick={() => edit(JSON.stringify(syntheticCapacitorPlacementRequest(), null, 2))}>Load synthetic example</button>
      <button type="button" className="spike-control--primary spike-control--compact" disabled={!workerAvailable || busy || !source.trim()} onClick={() => void run()}>{busy ? "Comparing candidates..." : "Compare candidates"}</button></div>
    <small>The synthetic example uses an original two-node resistor network. It contains no PCB extraction or measured capacitor data. Physical input validation runs in the local worker.</small>
    {!workerAvailable && <p role="status">Local solver worker unavailable. Input remains editable.</p>}
    {busy && <p role="status">Evaluating the submitted network...</p>}
    {error && <p role="alert">{error}{solved ? " The last completed result is retained below." : ""}</p>}
    {stale && <p className="cap-placement-notice" role="status">Inputs differ from the solved setup. The results below belong to the previous request.</p>}
    {solved && <CapacitorPlacementResults result={solved.result} selectedId={selectedId} onSelect={setSelectedId} />}
  </section>;
}
