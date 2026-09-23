import type { ReactNode } from "react";

export type OwnedCircuitResult = {
  status?: string;
  model_status?: string;
  netlist_sha256?: string;
  circuit_result?: Record<string, unknown>;
  issues?: Array<{ code?: string; message?: string }>;
};

/** One descriptor per line so a differential V(node_a,node_b) stays intact. */
export function parseOwnedProbeDescriptors(value: string): string[] {
  return value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
}

function circuitValues(value: unknown): string {
  if (typeof value === "number") return Number.isFinite(value) ? value.toPrecision(7) : "not finite";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return `${value.length} sample${value.length === 1 ? "" : "s"}: ${value.slice(0, 5).map(circuitValues).join(", ")}${value.length > 5 ? " …" : ""}`;
  if (value && typeof value === "object") return Object.entries(value as Record<string, unknown>).slice(0, 5).map(([key, item]) => `${key}: ${circuitValues(item)}`).join("; ");
  return String(value ?? "—");
}

const resultRows = (title: string, entries: [string, unknown][]): ReactNode => entries.length > 0 && <><b>{title}</b>{entries.map(([name, value]) => <p key={name}><code>{name}</code> {circuitValues(value)}</p>)}</>;

export function OwnedCircuitResultView({ result }: { result: OwnedCircuitResult | null }) {
  const circuit = result?.circuit_result;
  if (!result) return null;
  const probes = circuit?.probes && typeof circuit.probes === "object" ? Object.entries(circuit.probes as Record<string, unknown>) : [];
  const measurements = circuit?.measurements && typeof circuit.measurements === "object" ? Object.entries(circuit.measurements as Record<string, unknown>) : [];
  const data = circuit?.data && typeof circuit.data === "object" ? circuit.data as Record<string, unknown> : {};
  const waveforms = Object.entries(data).filter(([, value]) => Array.isArray(value) || (value && typeof value === "object" && Object.values(value as Record<string, unknown>).some(Array.isArray)));
  return <section className="spice-owned-results" aria-label="SPIKES owned circuit result">
    <div className="spice-section-heading"><div><b>OWNED CIRCUIT RESULT</b><small>{result.status ?? "unknown"} | {result.model_status ?? "unknown"} | no board overlay</small></div><code>{result.netlist_sha256?.slice(0, 12) ?? "no digest"}</code></div>
    {resultRows("Probes", probes)}
    {resultRows("Measurements", measurements)}
    {resultRows("Waveform / sweep data", waveforms)}
    {!probes.length && !measurements.length && !waveforms.length && <p>No probes or waveform data were requested. Add explicit probe descriptors to inspect circuit quantities.</p>}
  </section>;
}
