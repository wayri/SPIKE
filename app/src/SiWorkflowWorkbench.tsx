import { useEffect, useState } from "react";
import { Download, Play, Plus, Trash2, Upload, X } from "lucide-react";
import { cancelLocalWorker, isDesktopShell, runLocalWorker } from "./workerBridge";
import catalogJson from "./siWorkflowCatalog.json";
import SiWorkflowPlots, { SiPlot } from "./SiWorkflowPlots";
import "./siWorkflow.css";

type RecordData = Record<string, unknown>;
const rec = (v: unknown): RecordData => v && typeof v === "object" && !Array.isArray(v) ? v as RecordData : {};
const records = (v: unknown): RecordData[] => Array.isArray(v) ? v.map(rec) : [];
const catalog = catalogJson as unknown as RecordData;
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const pretty = (v: unknown) => JSON.stringify(v, null, 2);
const message = (e: unknown) => e instanceof Error ? e.message : String(e);
const labels: Record<string, string> = {
  resistance_ohm: "Resistance (ohm)", capacitance_f: "Capacitance (F)", inductance_h: "Series inductance (H)",
  package_r_ohm: "Package R (ohm)", package_l_h: "Package L (H)", package_c_f: "Package C (F)",
  low_v: "Source low, open circuit (V)", high_v: "Source high, open circuit (V)", rise_time_s: "Rise 10–90% (s)", fall_time_s: "Fall 90–10% (s)",
  vil_v: "Maximum low threshold (V)", vih_v: "Minimum high threshold (V)", input_noise_rms_v: "Receiver noise RMS (V)",
  tolerance_fraction: "Tolerance (fraction, 0.01 = 1%)", tcr_ppm_per_c: "TCR (ppm/°C)", noise_index_db: "Excess noise index (dB)",
  dc_voltage_v: "DC voltage across part (V)", temperature_c: "Temperature (°C)", rated_voltage_v: "Rated voltage (V)",
  bias_factor: "C bias factor (1 = no derating)", temperature_factor: "Nominal C temperature factor", aging_percent_per_decade: "Aging (% per decade of hours)",
  age_hours: "Age since de-aging (hours)", esr_ohm: "ESR (ohm)", esl_h: "ESL (H)", leakage_ohm: "Leakage resistance (ohm)",
  length_m: "Channel length (m)", resistance_ohm_per_m: "R (ohm/m)", inductance_h_per_m: "Self L (H/m)", capacitance_f_per_m: "Maxwell self C (F/m)",
  inductive_coupling: "Mutual L / self L", capacitive_coupling: "−Mutual C / self C", loss_tangent: "Dielectric loss tangent",
  frequency_stop_hz: "Frequency stop (Hz)", frequency_points: "Frequency points", reference_impedance_ohm: "Reference impedance (ohm)",
  bit_rate_hz: "Bit rate (Hz)", bit_count: "PRBS bit count", delay_s: "Stimulus delay (s)", pattern_shift_bits: "PRBS7 shift (0–126 bits)",
};

function download(name: string, value: string, type = "application/json") {
  const url = URL.createObjectURL(new Blob([value], { type }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function Numeric({ name, value, onChange }: { name: string; value: unknown; onChange: (n: number) => void }) {
  const [text, setText] = useState(String(value ?? ""));
  const [editing, setEditing] = useState(false);
  return <label>{labels[name] ?? name.replace(/_/g, " ")}<input inputMode="decimal" value={editing ? text : String(value ?? "")}
    onFocus={() => { setText(String(value ?? "")); setEditing(true); }}
    onChange={e => { setText(e.target.value); const n = Number(e.target.value); const valid = !!e.target.value.trim() && Number.isFinite(n); e.target.setCustomValidity(valid ? "" : "Enter a finite number"); onChange(valid ? n : Number.NaN); }}
    onBlur={e => { if (e.target.checkValidity()) setEditing(false); else e.target.reportValidity(); }} /></label>;
}
function TableNumeric({ name, value, onChange }: { name: string; value: unknown; onChange: (n: number) => void }) {
  const [text, setText] = useState(String(value ?? ""));
  const [editing, setEditing] = useState(false);
  const label = labels[name] ?? name.replace(/_/g, " ");
  return <input aria-label={label} title={label} inputMode="decimal" value={editing ? text : String(value ?? "")}
    onFocus={() => { setText(String(value ?? "")); setEditing(true); }}
    onChange={e => { setText(e.target.value); const n = Number(e.target.value); const valid = !!e.target.value.trim() && Number.isFinite(n); e.target.setCustomValidity(valid ? "" : "Enter a finite number"); onChange(valid ? n : Number.NaN); }}
    onBlur={e => { if (e.target.checkValidity()) setEditing(false); else e.target.reportValidity(); }} />;
}
function NumericFields({ value, onChange, omit = [] }: { value: RecordData; onChange: (v: RecordData) => void; omit?: string[] }) {
  return <div className="si-fields">{Object.entries(value).filter(([key, v]) => typeof v === "number" && !omit.includes(key)).map(([key, v]) => <Numeric key={key} name={key} value={v} onChange={n => onChange({ ...value, [key]: n })} />)}</div>;
}

type Props = { design: RecordData | null; initialResult?: RecordData | null; initialStep?: "channel" | "endpoints"; intentToken?: number; onResult?: (r: RecordData) => void; onStatus: (s: string) => void };
export default function SiWorkflowWorkbench({ design, initialResult, initialStep = "channel", intentToken, onResult, onStatus }: Props) {
  const saved = initialResult?.contract === "spike/si-workflow-result/v1" ? initialResult : null;
  const [setup, setSetup] = useState<RecordData>(() => clone(saved?.request ? rec(saved.request) : rec(catalog.defaults)));
  const [result, setResult] = useState<RecordData | null>(saved);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [step, setStep] = useState<string>(initialStep), [jsonDraft, setJsonDraft] = useState("");
  useEffect(() => { if (intentToken) setStep(initialStep); }, [initialStep, intentToken]);
  const [ibis, setIbis] = useState<RecordData | null>(null), [ibisText, setIbisText] = useState("");
  const [ibisModel, setIbisModel] = useState(""), [ibisComponent, setIbisComponent] = useState(""), [ibisPin, setIbisPin] = useState("");
  const [ibisCorner, setIbisCorner] = useState("typ"), [ibisState, setIbisState] = useState("low");
  const [ibisVoltage, setIbisVoltage] = useState(0.9), [ibisTable, setIbisTable] = useState("pulldown");
  const [ibisTarget, setIbisTarget] = useState("sources:0");
  const [editValue, setEditValue] = useState("50"), [editKind, setEditKind] = useState("renormalize");
  const channel = rec(setup.channel), sources = records(setup.sources), receivers = records(setup.receivers), passives = records(setup.passives);
  const desktop = isDesktopShell();
  // A filename supplies only a UI hint; the worker validates the actual network.
  const portCount = channel.kind === "rlgc" ? (channel.coupled ? 4 : 2)
    : channel.kind === "touchstone" ? Number(String(channel.name).match(/\.s(\d+)p$/i)?.[1]) || null
    : channel.kind === "geometry" ? (rec(channel.request).victim_net ? 4 : 2) : null;
  const occupiedPorts = new Set([...sources, ...receivers].map(endpoint => Number(endpoint.port)));
  const freePort = Array.from({ length: portCount ?? 16 }, (_, i) => i).find(port => !occupiedPorts.has(port));
  const netRecords = records(design?.nets), layerRecords = records(design?.layers).filter(l => l.layer_type === "copper");
  const change = (key: string, value: unknown) => { setSetup(s => ({ ...s, [key]: value })); setError(""); };
  const updateEndpoint = (key: "sources" | "receivers", index: number, value: RecordData) => change(key, records(setup[key]).map((m, i) => i === index ? value : m));
  const updatePassive = (index: number, value: RecordData) => change("passives", passives.map((m, i) => i === index ? value : m));
  const run = async () => {
    setBusy(true); setRunning(true); setError("");
    try {
      const response = await runLocalWorker({ method: "run_si_workflow", params: { request: setup, design } });
      if (!response.ok || !response.result) throw new Error(response.error ?? "SI worker did not return a result.");
      setResult(response.result); onResult?.(response.result); setStep("results");
      onStatus(response.result.status === "partial"
        ? "Loaded SI study returned partial results; inspect the blocked stage and its recovery message."
        : "Loaded SI study completed; inspect time-domain status, model assumptions and threshold margins.");
    } catch (e) { setError(message(e)); } finally { setBusy(false); setRunning(false); }
  };
  const stop = async () => {
    onStatus("Cancelling the loaded SI study...");
    try {
      const accepted = await cancelLocalWorker();
      if (!accepted) onStatus("No cancellable SI worker operation was active; waiting for the current request to finish.");
    } catch (e) { setError(message(e)); }
  };
  const loadFile = async (file: File | undefined, kind: "setup" | "touchstone" | "ibis" | "cascade") => {
    if (!file) return;
    setError("");
    try {
      if (file.size > (kind === "ibis" ? 8_000_000 : 32_000_000)) throw new Error("Model file exceeds the import size limit.");
      const text = await file.text();
      if (kind === "setup") {
        const parsed = rec(JSON.parse(text)), request = parsed.contract === "spike/si-workflow-result/v1" ? rec(parsed.request) : parsed;
        if (request.contract !== "spike/si-workflow-request/v1") throw new Error("Expected a version 1 SI workflow setup or result.");
        setSetup({ ...clone(rec(catalog.defaults)), ...request });
        if (parsed.contract === "spike/si-workflow-result/v1") setResult(parsed);
      } else if (kind === "ibis") {
        setBusy(true);
        const response = await runLocalWorker({ method: "inspect_si_ibis", params: { text, name: file.name } });
        if (!response.ok || !response.result) throw new Error(response.error ?? "IBIS import failed.");
        setIbis(response.result); setIbisText(text); setIbisModel(Object.keys(rec(response.result.models))[0] ?? ""); setIbisComponent(""); setIbisPin("");
      } else {
        const item = { kind: "touchstone", name: file.name, text };
        if (kind === "cascade") change("edits", [...records(setup.edits), { kind: "cascade", channel: item }]);
        else change("channel", item);
      }
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  const useGeometry = () => {
    const prior = rec(channel.request), frequencies = rec(catalog.defaults).channel as RecordData;
    const count = Number(frequencies.frequency_points), stop = Number(frequencies.frequency_stop_hz);
    change("channel", { kind: "geometry", request: { contract: "spike/si-uniform-channel-request/v1", path_mode: "piecewise_planar",
      signal_net: String(netRecords.find(n => !/gnd|vss/i.test(String(n.name)))?.id ?? ""), reference_net: String(netRecords.find(n => /gnd|vss/i.test(String(n.name)))?.id ?? ""),
      reference_layer: String(layerRecords[1]?.id ?? ""), reference_impedance_ohm: 50,
      frequencies_hz: Array.from({ length: count }, (_, i) => i * stop / (count - 1)), coupled_separation_tolerance_mm: 0.001, coupled_skew_tolerance_mm: 0.001, ...prior } });
  };
  const endpointEditor = (key: "sources" | "receivers", values: RecordData[]) => {
    const numericKeys = Array.from(new Set(values.flatMap(value => Object.entries(value).filter(([field, item]) => field !== "port" && typeof item === "number").map(([field]) => field))));
    const kind = key === "sources" ? "source" : "receiver";
    return <>
    <div className="si-row"><h3>{key === "sources" ? "Sources and aggressors" : "Receivers"}</h3><button disabled={freePort === undefined} title={freePort === undefined ? "All channel ports already have an endpoint." : "Assign the next unused channel port"} onClick={() => { if (freePort !== undefined) change(key, [...values, { ...clone(rec(catalog[key === "sources" ? "source" : "receiver"])), port: freePort }]); }}><Plus size={14} /> Add {key === "sources" ? "source" : "receiver"}</button></div>
    <div className="si-endpoint-table-wrap"><table className="si-endpoint-table"><thead><tr><th scope="col">{key === "sources" ? "Endpoint" : "Receiver"}</th><th scope="col">Port</th>{numericKeys.map(field => <th scope="col" key={field}>{labels[field] ?? field.replace(/_/g, " ")}</th>)}<th scope="col">IBIS</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
      <tbody>{values.map((value, i) => <tr key={i}><th scope="row">{key === "sources" ? (i ? `Aggressor ${i}` : "Primary source") : `Receiver ${i + 1}`}</th>
        <td><input aria-label={`${kind} ${i + 1} port (1-based)`} type="number" min="1" value={Number(value.port) + 1} onChange={e => updateEndpoint(key, i, { ...value, port: Number(e.target.value) - 1 })} /></td>
        {numericKeys.map(field => <td key={field}><TableNumeric name={field} value={value[field]} onChange={n => updateEndpoint(key, i, { ...value, [field]: n })} /></td>)}
        <td>{value.ibis ? <span className="si-endpoint-ibis" title={`IBIS model ${String(rec(value.ibis).model)}, ${String(rec(value.ibis).corner)} corner`}>Bound <button onClick={() => { const next = { ...value }; delete next.ibis; updateEndpoint(key, i, next); }}>Detach</button></span> : "—"}</td>
        <td><button title={`Remove ${kind}`} aria-label={`Remove ${kind} ${i + 1}`} onClick={() => change(key, values.filter((_, j) => j !== i))}><Trash2 size={14} /></button></td></tr>)}</tbody></table></div>
    <p className="si-endpoint-hint">Port numbers are 1-based. Column headings identify each editable parameter. Bound IBIS values override matching editable parameters.</p>
  </>;
  };
  const model = rec(rec(ibis?.models)[ibisModel]), table = rec(model.tables)[ibisTable];
  const ibisRows = Array.isArray(table) ? table as (number | null)[][] : [];
  const stale = !!result && pretty(rec(result.request)) !== pretty(setup);
  return <div className="si-flow" aria-busy={busy}><div className="si-row si-toolbar">
    {running
      ? <button className="primary-btn" onClick={() => void stop()}><X size={15} />Stop SI study</button>
      : <button className="primary-btn" disabled={busy || !desktop} onClick={() => void run()}><Play size={15} />{busy ? "Inspecting IBIS..." : "Run loaded SI study"}</button>}
    <button onClick={() => download("si-study.json", pretty(setup))}><Download size={15} />Save setup</button>
    <label className="si-file"><Upload size={15} />Open setup / result<input disabled={busy} type="file" accept=".json" onChange={e => { void loadFile(e.target.files?.[0], "setup"); e.target.value = ""; }} /></label>
    <button disabled={busy} onClick={() => { setJsonDraft(pretty(setup)); setStep("json"); }}>Edit JSON</button>
  </div>
  <nav className="si-steps" aria-label="SI workflow stages">{[["channel", "1 · Channel"], ["endpoints", "2 · Sources / receivers"], ["passives", "3 · Passives"], ["ibis", "4 · IBIS"], ["edits", "5 · Network edits"], ["results", "6 · Results"]].map(([id, name]) => <button key={id} className={step === id ? "active" : ""} onClick={() => setStep(id)}>{name}</button>)}</nav>
  {error && <div className="sparam-error" role="alert">{error}</div>}
  {!desktop && <p className="si-note">Browser preview supports setup editing and saved results. Open the SPIKE desktop app to run studies or inspect IBIS files.</p>}
  <div className="si-note">Experimental linear SI. Defaults are editable assumptions. The exported Touchstone describes the channel after network edits; loaded source, receiver and passive responses are reported separately.</div>
  <fieldset disabled={busy} className="si-stage">
  {step === "channel" && <><h3>Channel and analysis conditions</h3><div className="si-row">
    <button onClick={() => change("channel", clone(rec(rec(catalog.defaults).channel)))}>Uniform RLGC line</button>
    <label className="si-file"><Upload size={15} />Import Touchstone<input type="file" accept=".s2p,.s3p,.s4p,.s6p,.s8p,.s12p,.s16p" onChange={e => { void loadFile(e.target.files?.[0], "touchstone"); e.target.value = ""; }} /></label>
    <button disabled={!design} onClick={useGeometry}>Extract active board path</button></div>
    {channel.kind === "rlgc" && <><label><input type="checkbox" checked={!!channel.coupled} onChange={e => { change("channel", { ...channel, coupled: e.target.checked }); change("receivers", [{ ...rec(catalog.receiver), port: e.target.checked ? 2 : 1 }]); }} /> Coupled pair (4 ports)</label>
      <p>4-port order: 1 aggressor near, 2 victim near, 3 aggressor far, 4 victim far. NEXT: source 1 → port 2. FEXT: source 1 → port 4. Two-port lines use 1 near, 2 far.</p>
      <NumericFields value={channel} onChange={v => change("channel", v)} /></>}
    {channel.kind === "touchstone" && <p>Imported: <b>{String(channel.name)}</b>. Assign endpoints to the file’s port order; use the reorder editor to change it. DC and uniform spacing are required for time-domain work.</p>}
    {(channel.kind === "network_graph" || channel.kind === "multiboard") && <p>Explicit {channel.kind === "network_graph" ? "N-port network graph" : "two-port multiboard chain"}: edit identities, model digests and reference planes in the JSON setup. Endpoint indices follow the resulting external port order. Interconnections do not extract cross-board electromagnetic fields.</p>}
    {channel.kind === "geometry" && <><p>Bounded planar paths: select the signal, explicit reference, and optional second conductor. Vias and unsupported discontinuities are rejected by extraction.</p><div className="si-fields">{["signal_net", "victim_net", "reference_net", "reference_layer"].map(key => <label key={key}>{key.replace(/_/g, " ")}<select value={String(rec(channel.request)[key] ?? "")} onChange={e => change("channel", { ...channel, request: { ...rec(channel.request), [key]: e.target.value } })}><option value="">Select / none</option>{(key === "reference_layer" ? layerRecords : netRecords).map(n => <option key={String(n.id)} value={String(n.id)}>{String(n.name)}</option>)}</select></label>)}</div><p>Frequency grid and extraction tolerances can be edited in the JSON setup.</p></>}
    <NumericFields value={setup} onChange={setSetup} /><label><input type="checkbox" checked={!!setup.run_time_domain} onChange={e => change("run_time_domain", e.target.checked)} /> Compute PRBS waveform, eye and channel TDR</label>
  </>}
  {step === "endpoints" && <><p>Port numbers below are 1-based. Each port has one endpoint; unassigned ports are terminated in their reference impedance. Additional sources act as deterministic aggressors. The eye is referenced to the first source.</p>{endpointEditor("sources", sources)}{endpointEditor("receivers", receivers)}</>}
  {step === "passives" && <><h3>Passive models and manufacturing assumptions</h3><p>Attach series parts between an endpoint and its channel port, or shunt parts from a channel port to reference. Capacitor grade specifies a temperature envelope. Bias, aging, ESR and ESL need part data; generic defaults do not imply a manufacturer guarantee.</p>
    <div className="si-row">{["resistor", "capacitor"].map(kind => <button key={kind} onClick={() => change("passives", [...passives, { id: `${kind}-${passives.length + 1}`, port: 0, connection: kind === "resistor" ? "series" : "shunt", model: clone(rec(catalog[kind])) }])}><Plus size={14} />Add {kind}</button>)}</div>
    {passives.map((item, i) => { const m = rec(item.model), kind = String(m.kind), grades = rec(catalog[kind === "resistor" ? "resistor_grades" : "capacitor_grades"]); return <fieldset key={i}><legend>{String(item.id)}</legend>
      <div className="si-fields"><label>Reference / name<input value={String(item.id)} onChange={e => updatePassive(i, { ...item, id: e.target.value })} /></label>
        <label>Port (1-based)<input type="number" min="1" value={Number(item.port) + 1} onChange={e => updatePassive(i, { ...item, port: Number(e.target.value) - 1 })} /></label>
        <label>Connection<select value={String(item.connection)} onChange={e => updatePassive(i, { ...item, connection: e.target.value })}><option>series</option><option>shunt</option></select></label>
        <label>Grade<select value={String(m.grade)} onChange={e => updatePassive(i, { ...item, model: { ...m, ...(kind === "resistor" ? rec(grades[e.target.value]) : {}), grade: e.target.value } })}>{Object.keys(grades).map(g => <option key={g}>{g}</option>)}</select></label>
        <label>Parameter corner<select value={String(m.corner)} onChange={e => updatePassive(i, { ...item, model: { ...m, corner: e.target.value } })}><option>nominal</option><option>min</option><option>max</option></select></label></div>
      <NumericFields value={m} onChange={v => updatePassive(i, { ...item, model: v })} />
      <button onClick={() => change("passives", passives.filter((_, j) => j !== i))}><Trash2 size={14} />Remove part</button>
    </fieldset>; })}
    <p>Min/max combine tolerance and capacitor temperature-envelope bounds. Resistor temperature uses its TCR. These are deterministic parameter corners, not probability or yield estimates. Use the same temperature for the study and attached parts.</p>
  </>}
  {step === "ibis" && <><h3>IBIS library, pins, tables and binding</h3><label className="si-file"><Upload size={15} />Import .ibs<input disabled={!desktop} type="file" accept=".ibs" onChange={e => { void loadFile(e.target.files?.[0], "ibis"); e.target.value = ""; }} /></label>
    <p>Inspect typ/min/max I/V tables, package values and model selectors. Binding uses one selected I/V slope and ramp-derived edge times. Nonlinear switching, clamp conduction and AMI are not simulated; unsupported electrical keywords block reduction.</p>
    {ibis && <><p>{String(ibis.name)} · IBIS {String(ibis.version)} · SHA256 {String(ibis.sha256).slice(0, 16)}</p>
      <div className="si-fields"><label>Model<select value={ibisModel} onChange={e => setIbisModel(e.target.value)}>{Object.keys(rec(ibis.models)).map(key => <option key={key}>{key}</option>)}</select></label>
      <label>Component<select value={ibisComponent} onChange={e => { setIbisComponent(e.target.value); setIbisPin(""); }}><option value="">No package binding</option>{Object.keys(rec(ibis.components)).map(key => <option key={key}>{key}</option>)}</select></label>
      <label>Pin<select value={ibisPin} onChange={e => setIbisPin(e.target.value)}><option value="">Select pin</option>{records(rec(rec(ibis.components)[ibisComponent]).pins).map(p => <option key={String(p.pin)} value={String(p.pin)}>{String(p.pin)} · {String(p.signal)} · {String(p.model)}</option>)}</select></label>
      <label>Corner<select value={ibisCorner} onChange={e => setIbisCorner(e.target.value)}>{["typ", "min", "max"].map(c => <option key={c}>{c}</option>)}</select></label>
      <label>Driver state<select value={ibisState} onChange={e => setIbisState(e.target.value)}><option>low</option><option>high</option></select></label>
      <Numeric name="operating_voltage_v" value={ibisVoltage} onChange={setIbisVoltage} />
      <label>Endpoint<select value={ibisTarget} onChange={e => setIbisTarget(e.target.value)}>{[...sources.map((_, i) => `sources:${i}`), ...receivers.map((_, i) => `receivers:${i}`)].map(t => <option key={t}>{t}</option>)}</select></label></div>
      <button onClick={() => { const [key, index] = ibisTarget.split(":"); const endpoint = records(setup[key])[Number(index)]; if (!endpoint) { setError("Select an existing endpoint."); return; } updateEndpoint(key as "sources" | "receivers", Number(index), { ...endpoint, ibis: { text: ibisText, name: ibis.name, model: ibisModel, corner: ibisCorner, state: ibisState, operating_voltage_v: ibisVoltage, ...(ibisComponent ? { component: ibisComponent, pin: ibisPin } : {}) } }); setStep("endpoints"); }}>Bind linearized model to endpoint</button>
      <label>I/V table<select value={ibisTable} onChange={e => setIbisTable(e.target.value)}>{Object.keys(rec(model.tables)).map(k => <option key={k}>{k}</option>)}</select></label>
      <SiPlot title={`${ibisModel}: ${ibisTable}`} curves={["typ", "min", "max"].map((name, index) => ({ name, points: ibisRows.filter(row => row[index + 1] !== null).map(row => ({ x: Number(row[0]), y: Number(row[index + 1]) })) }))} xLabel="Table voltage (V)" yLabel="Current (A)" />
      <details><summary>Waveforms, package, model selectors and unsupported keywords</summary><pre>{pretty({ model, components: ibis.components, selectors: ibis.selectors, unsupported_keywords: ibis.unsupported_keywords })}</pre></details>
    </>}
  </>}
  {step === "edits" && <><h3>Reproducible channel edits</h3><p>Edits run in order on a copy of the original channel. Endpoint port assignments refer to the final order. Port extensions add delay; they do not remove fixtures or repair causality.</p>
    <div className="si-fields"><label>Operation<select value={editKind} onChange={e => { setEditKind(e.target.value); setEditValue(e.target.value === "renormalize" ? "50" : portCount ? Array.from({ length: portCount }, (_, i) => e.target.value === "reorder" ? i + 1 : 0).join(",") : ""); }}><option value="renormalize">Renormalize</option><option value="reorder">Reorder ports</option><option value="port_extension">Add delay per port</option></select></label>
      <label>{editKind === "renormalize" ? "New reference (ohm)" : editKind === "reorder" ? "Port order, 1-based, comma separated" : "Delays (s), comma separated"}<input value={editValue} onChange={e => setEditValue(e.target.value)} /></label></div>
    <div className="si-row"><button onClick={() => { const entries = editValue.split(","), values = entries.map(Number); if (entries.some(v => !v.trim()) || !values.every(Number.isFinite)) { setError("Edit values must be finite numbers."); return; } const edit = editKind === "renormalize" ? { kind: editKind, reference_impedance_ohm: values[0] } : editKind === "reorder" ? { kind: editKind, ports: values.map(p => p - 1) } : { kind: editKind, delay_s: values }; change("edits", [...records(setup.edits), edit]); }}>Add operation</button>
      <label className="si-file">Cascade 2-port Touchstone<input type="file" accept=".s2p" onChange={e => { void loadFile(e.target.files?.[0], "cascade"); e.target.value = ""; }} /></label></div>
    {records(setup.edits).map((edit, i) => <div className="si-row" key={i}><span>{i + 1}. {String(edit.kind)} · {pretty({ ...edit, ...(edit.channel ? { channel: rec(edit.channel).name } : {}) })}</span><button onClick={() => change("edits", records(setup.edits).filter((_, j) => i !== j))}>Remove</button></div>)}
    <label>Touchstone export encoding<select value={String(setup.export_format)} onChange={e => change("export_format", e.target.value)}><option>RI</option><option>MA</option><option>DB</option></select></label>
  </>}
  {step === "json" && <><h3>Complete study setup</h3><p>All units are SI unless specified. JSON port indices are zero-based. Applying updates the form; validation runs in the worker.</p><textarea className="si-json" value={jsonDraft} spellCheck={false} onChange={e => setJsonDraft(e.target.value)} /><button onClick={() => { try { const v = rec(JSON.parse(jsonDraft)); if (v.contract !== "spike/si-workflow-request/v1") throw new Error("Unsupported SI workflow contract."); setSetup(v); setStep("channel"); } catch (e) { setError(message(e)); } }}>Apply JSON</button></>}
  {step === "results" && (!result ? <p>Run a study to inspect network quality, loaded transfers, eyes, TDR, noise and resolved models.</p> : <>
    {stale && <p className="si-note">Setup differs from this saved result. Run again to update results and export.</p>}
    <div className="si-row"><button onClick={() => download("si-result.json", pretty(result))}><Download size={15} />Save complete result</button>
      <button disabled={!rec(result.touchstone).text} onClick={() => download(String(rec(result.touchstone).name), String(rec(result.touchstone).text), "text/plain")}><Download size={15} />Export Touchstone</button></div>
    {rec(result.touchstone).error ? <p className="sparam-error">Export: {String(rec(result.touchstone).error)}</p> : null}
    <p>Time domain: <b>{String(rec(result.time_domain).status)}</b> · Passivity: <b>{String(rec(rec(rec(result.network).checks).passivity).status)}</b> · Reciprocity: <b>{String(rec(rec(rec(result.network).checks).reciprocity).status)}</b> · Compliance: not evaluated</p>
    <SiWorkflowPlots result={result} />
    {result.extraction ? <details><summary>Channel provenance and external port mapping</summary><pre>{pretty(result.extraction)}</pre></details> : null}
    {Array.isArray(result.resonance_fits) && result.resonance_fits.length > 0 ? <details open><summary>Declared RLC resonance / Q fits (not physical-mode qualification)</summary><pre>{pretty(result.resonance_fits)}</pre></details> : null}
    <details open><summary>Noise, effective passive values and model limitations</summary><pre>{pretty({ noise: result.noise, passives: result.passives, ibis: result.ibis, warnings: result.warnings, limitations: result.limitations })}</pre></details>
  </>)}
  </fieldset></div>;
}
