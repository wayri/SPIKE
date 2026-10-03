import { useEffect, useMemo, useRef, useState } from "react";
import DataTable from "./DataTable";
import TableIdentityInput from "./TableIdentityInput";
import { cancelLocalWorker, cancelLocalWorkerCleanup, runLocalWorker } from "./workerBridge";

type Endpoint = { connector: string; pin: string } | { splice: string };
type Terminal = { id: string; type: "voltage_source" | "current_load"; positive: Endpoint; negative: Endpoint; value: number };
type Contact = { id: string; from: Endpoint; to: Endpoint; resistance_ohm: number };
type Setup = { ground?: Endpoint; terminals: Terminal[]; contacts: Contact[] };
type Props = { value: Record<string, any>; onChange: (value: Record<string, any>) => void };
const emptyEndpoint = (): Endpoint => ({ connector: "", pin: "" });
const endpointKey = (endpoint?: Endpoint) => endpoint && "splice" in endpoint ? JSON.stringify(["splice", endpoint.splice]) : endpoint ? JSON.stringify(["connector", endpoint.connector, endpoint.pin]) : "";
const finiteNonnegative = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value >= 0;
const numericInput = (raw: string) => raw.trim() === "" ? Number.NaN : Number(raw);

export default function HarnessPiPanel({ value, onChange }: Props) {
  const rawSetup = value.extensions?.["spike.harness-pi"];
  const setupMalformed = rawSetup !== undefined && (!rawSetup || typeof rawSetup !== "object" || Array.isArray(rawSetup) || !Array.isArray(rawSetup.terminals) || !Array.isArray(rawSetup.contacts));
  const setup: Setup = setupMalformed ? { terminals: [], contacts: [] } : { ground: rawSetup?.ground, terminals: rawSetup?.terminals ?? [], contacts: rawSetup?.contacts ?? [] };
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [result, setResult] = useState<Record<string, any> | null>(null);
  const [resultInput, setResultInput] = useState(""); const requestId = useRef<string | null>(null);
  const inputIdentity = JSON.stringify(value);
  const endpoints = useMemo(() => [
    ...(Array.isArray(value.connectors) ? value.connectors : []).flatMap((connector: any) => (connector.pins ?? []).map((pin: any) => ({ label: `${connector.id} / ${pin.id}`, value: { connector: String(connector.id), pin: String(pin.id) } as Endpoint }))),
    ...(Array.isArray(value.splices) ? value.splices : []).map((splice: any) => ({ label: `Splice ${splice.id}`, value: { splice: String(splice.id) } as Endpoint })),
  ], [inputIdentity]);
  useEffect(() => () => { if (requestId.current) void cancelLocalWorkerCleanup(requestId.current); }, []);
  const persist = (next: Setup) => onChange({ ...value, extensions: { ...(value.extensions ?? {}), "spike.harness-pi": next } });
  const chooseEndpoint = (key: string) => endpoints.find(item => endpointKey(item.value) === key)?.value ?? emptyEndpoint();
  const endpointSelect = (label: string, endpoint: Endpoint | undefined, change: (next: Endpoint) => void) => <select aria-label={label} value={endpointKey(endpoint)} onChange={event => change(chooseEndpoint(event.target.value))}><option value="">Select terminal…</option>{endpoints.map(item => <option key={endpointKey(item.value)} value={endpointKey(item.value)}>{item.label}</option>)}</select>;
  const validate = () => {
    if (!setup.ground || !endpointKey(setup.ground)) throw new Error("Select an explicit ground terminal.");
    if (!setup.terminals.length || !setup.terminals.some(item => item.type === "voltage_source")) throw new Error("Add at least one voltage source.");
    const ids = new Set<string>();
    for (const row of setup.terminals) {
      if (!row.id.trim() || ids.has(`t:${row.id}`) || !endpointKey(row.positive) || !endpointKey(row.negative) || endpointKey(row.positive) === endpointKey(row.negative) || !finiteNonnegative(row.value)) throw new Error(`Terminal ${row.id || "<unnamed>"} is incomplete or invalid.`);
      ids.add(`t:${row.id}`);
    }
    for (const row of setup.contacts) {
      if (!row.id.trim() || ids.has(`c:${row.id}`) || !endpointKey(row.from) || !endpointKey(row.to) || endpointKey(row.from) === endpointKey(row.to) || !finiteNonnegative(row.resistance_ohm) || row.resistance_ohm <= 0) throw new Error(`Contact ${row.id || "<unnamed>"} is incomplete or invalid.`);
      ids.add(`c:${row.id}`);
    }
  };
  const run = async () => {
    try {
      validate(); setBusy(true); setError(""); setResult(null);
      const frozen = structuredClone({ contract: "spike/harness-pi-request/v1", harness: value, ground: setup.ground, terminals: setup.terminals, contacts: setup.contacts });
      const frozenIdentity = inputIdentity; const id = globalThis.crypto?.randomUUID?.() ?? `harness-pi-${Date.now()}`; requestId.current = id;
      const response = await runLocalWorker({ id, method: "run_harness_pi", params: { request: frozen } });
      if (requestId.current !== id) return;
      if (!response.ok || !response.result) throw new Error(response.error ?? "Harness PI worker returned no result.");
      setResult(response.result); setResultInput(frozenIdentity);
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { requestId.current = null; setBusy(false); }
  };
  const patchTerminal = (index: number, update: Partial<Terminal>) => persist({ ...setup, terminals: setup.terminals.map((item, i) => i === index ? { ...item, ...update } : item) });
  const patchContact = (index: number, update: Partial<Contact>) => persist({ ...setup, contacts: setup.contacts.map((item, i) => i === index ? { ...item, ...update } : item) });
  const stale = Boolean(result && resultInput !== inputIdentity);
  return <section className="harness-pi-panel" aria-label="Harness PI DC screening"><h4>Harness PI DC screening</h4>
    <p>This experimental lumped linear DC screen solves explicit wires, sources, loads, returns, and mated-contact resistances. It is not a PCB/board field solve, connector thermal model, or SI qualification. Connector preset resistance is metadata only; add each resistance below to include it in this run.</p>
    {setupMalformed ? <button className="secondary-btn" onClick={() => persist({ terminals: [], contacts: [] })}>Reset malformed Harness PI setup</button> : <label>Ground {endpointSelect("Harness PI ground", setup.ground, ground => persist({ ...setup, ground }))}</label>}
    <h5>Sources and loads</h5><DataTable label="Harness sources and loads" className="data-table"><thead><tr><th>ID</th><th>Type</th><th>Positive</th><th>Negative / return</th><th>Value</th><th /></tr></thead><tbody>{setup.terminals.map((row, index) => <tr key={`${row.id}-${index}`}>
      <td><TableIdentityInput value={row.id} onCommit={id => patchTerminal(index, { id })} validate={id => !id.trim() ? "Terminal ID cannot be blank." : id !== row.id && setup.terminals.some(item => item.id === id) ? "Terminal ID already exists." : ""} /></td><td><select value={row.type} onChange={event => patchTerminal(index, { type: event.target.value as Terminal["type"] })}><option value="voltage_source">Voltage source</option><option value="current_load">Current load</option></select></td>
      <td>{endpointSelect(`${row.id} positive`, row.positive, positive => patchTerminal(index, { positive }))}</td><td>{endpointSelect(`${row.id} negative`, row.negative, negative => patchTerminal(index, { negative }))}</td>
      <td><input aria-label={`${row.id} value`} type="number" min="0" step="any" value={Number.isFinite(row.value) ? row.value : ""} onChange={event => patchTerminal(index, { value: numericInput(event.target.value) })} /> {row.type === "voltage_source" ? "V" : "A"}</td><td><button className="secondary-btn" onClick={() => persist({ ...setup, terminals: setup.terminals.filter((_, i) => i !== index) })}>Remove</button></td>
    </tr>)}</tbody></DataTable><button className="secondary-btn" disabled={setupMalformed} onClick={() => persist({ ...setup, terminals: [...setup.terminals, { id: `terminal-${setup.terminals.length + 1}`, type: setup.terminals.some(item => item.type === "voltage_source") ? "current_load" : "voltage_source", positive: emptyEndpoint(), negative: emptyEndpoint(), value: 0 }] })}>Add source / load</button>
    <h5>Mated contacts</h5><DataTable label="Harness mated contacts" className="data-table"><thead><tr><th>ID</th><th>From</th><th>To</th><th>Resistance (Ω)</th><th /></tr></thead><tbody>{setup.contacts.map((row, index) => <tr key={`${row.id}-${index}`}><td><TableIdentityInput value={row.id} onCommit={id => patchContact(index, { id })} validate={id => !id.trim() ? "Contact ID cannot be blank." : id !== row.id && setup.contacts.some(item => item.id === id) ? "Contact ID already exists." : ""} /></td><td>{endpointSelect(`${row.id} from`, row.from, from => patchContact(index, { from }))}</td><td>{endpointSelect(`${row.id} to`, row.to, to => patchContact(index, { to }))}</td><td><input type="number" min="0.000000000001" step="any" value={Number.isFinite(row.resistance_ohm) ? row.resistance_ohm : ""} onChange={event => patchContact(index, { resistance_ohm: numericInput(event.target.value) })} /></td><td><button className="secondary-btn" onClick={() => persist({ ...setup, contacts: setup.contacts.filter((_, i) => i !== index) })}>Remove</button></td></tr>)}</tbody></DataTable>
    <button className="secondary-btn" disabled={setupMalformed} onClick={() => persist({ ...setup, contacts: [...setup.contacts, { id: `contact-${setup.contacts.length + 1}`, from: emptyEndpoint(), to: emptyEndpoint(), resistance_ohm: 0.01 }] })}>Add mated contact</button>
    <div><button className={busy ? "run-btn stop" : "run-btn"} disabled={setupMalformed} onClick={() => void (busy && requestId.current ? cancelLocalWorker(requestId.current) : run())}>{busy ? "Stop harness PI" : "Run harness PI DC"}</button></div>
    {setupMalformed && <p role="alert">Saved Harness PI setup is malformed. Review the project source before using the explicit reset; it will replace only this invalid setup extension.</p>}{error && <p role="alert">{error}</p>}{stale && <p role="alert">Inputs changed after this run; results below are stale.</p>}
    {result && <div className="harness-pi-results"><p><b>{String(result.status).toUpperCase()}</b> · experimental / not production qualified · wire loss {typeof result.total_wire_loss_w === "number" ? `${Number(result.total_wire_loss_w).toPrecision(5)} W` : "unavailable"} · contact loss {typeof result.total_contact_loss_w === "number" ? `${Number(result.total_contact_loss_w).toPrecision(5)} W` : "unavailable"}</p>
      {result.status !== "completed" && <pre>{JSON.stringify(result.native_result ?? { diagnostic: "No native diagnostic was returned." }, null, 2)}</pre>}
      <DataTable label="Harness connection results" className="data-table"><thead><tr><th>Element</th><th>Voltage (V)</th><th>Current (A)</th><th>Power (W)</th></tr></thead><tbody>{(result.connections ?? []).map((row: any) => <tr key={`${row.kind}:${row.id}`}><td>{row.kind} · {row.id}</td><td>{Number(row.voltage_v).toPrecision(6)}</td><td>{Number(row.current_a).toPrecision(6)}</td><td>{Number(row.power_w).toPrecision(6)}</td></tr>)}</tbody></DataTable>
      <DataTable label="Harness wire results" className="data-table"><thead><tr><th>Wire</th><th>R (Ω)</th><th>Current (A)</th><th>Loss (W)</th></tr></thead><tbody>{(result.wires ?? []).map((row: any) => <tr key={row.wire_id}><td>{row.wire_id}</td><td>{Number(row.resistance_ohm).toPrecision(6)}</td><td>{Number(row.current_a).toPrecision(6)}</td><td>{Number(row.loss_w).toPrecision(6)}</td></tr>)}</tbody></DataTable>
      <details><summary>Node voltages and limitations</summary><pre>{JSON.stringify(result.node_voltages_v ?? {}, null, 2)}</pre><ul>{(result.limitations ?? []).map((item: string) => <li key={item}>{item}</li>)}</ul></details></div>}
  </section>;
}
