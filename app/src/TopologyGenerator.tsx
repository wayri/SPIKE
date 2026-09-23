import { useMemo, useState } from "react";
import type { ParsedBoard } from "./boardParser";
import { type TopologyDomain, type TopologyModel } from "./powerTree";
import TopologyPreview from "./TopologyPreview";
import { generateTopology, type TopologyInputs } from "./topologyGeneration";

export default function TopologyGenerator({ domain, board, onApply, onClose }: {
  domain: TopologyDomain; board: ParsedBoard | null; onApply: (model: TopologyModel, replace: boolean) => void; onClose: () => void;
}) {
  const [input, setInput] = useState<TopologyInputs>({ source: "", net: "", sinks: "", voltage: "", current: "", sourcePad: "", sinkPad: "" });
  const [mode, setMode] = useState("manual");
  const [replace, setReplace] = useState(false);
  const [preview, setPreview] = useState<TopologyModel | null>(null);
  const [error, setError] = useState("");
  const patch = (key: keyof TopologyInputs, value: string) => { setInput(current => ({ ...current, [key]: value })); setPreview(null); setError(""); };
  const pads = useMemo(() => (board?.pads ?? []).filter(p => p.net).sort((a, b) => `${a.ref}.${a.name}`.localeCompare(`${b.ref}.${b.name}`, undefined, { numeric: true })), [board]);
  return <section className="topology-generator" role="dialog" aria-label="Generate schematic from inputs" onPointerDown={event => event.stopPropagation()}>
    <header><div><b>Generate {domain === "pi" ? "power" : "signal"} schematic</b><p>1. Define endpoints · 2. Preview connections · 3. Add to sheet</p></div><button onClick={onClose} aria-label="Close generator">×</button></header>
    <label>Input method<select value={mode} onChange={event => { setMode(event.target.value); setPreview(null); setError(""); }}><option value="manual">Enter source, net, and destinations</option><option value="board" disabled={!board}>Choose board endpoints</option></select></label>
    {mode === "manual" ? <><label>{domain === "pi" ? "Supply name" : "Driver name"}<input value={input.source} onChange={e => patch("source", e.target.value)} placeholder={domain === "pi" ? "12 V input" : "U1 transmitter"} /></label><label>Net name<input value={input.net} onChange={e => patch("net", e.target.value)} placeholder={domain === "pi" ? "+12V" : "SPI_CLK"} /></label><label>{domain === "pi" ? "Loads" : "Receivers"} — one per line<textarea rows={3} value={input.sinks} onChange={e => patch("sinks", e.target.value)} placeholder={domain === "pi" ? "Controller\nSensor" : "U2 receiver"} /></label></> : <>{(["sourcePad", "sinkPad"] as const).map((key, index) => <label key={key}>{index ? "Destination pad" : "Source pad"}<select value={input[key]} onChange={e => patch(key, e.target.value)}><option value="">Choose a pad</option>{pads.map(pad => <option key={pad.id} value={pad.id}>{pad.ref}.{pad.name} · {pad.net}</option>)}</select></label>)}</>}
    {domain === "pi" && <div className="topology-generator-values"><label>Source voltage (V)<input type="number" min="0" step="any" value={input.voltage} onChange={e => patch("voltage", e.target.value)} /></label><label>Current per load (A)<input type="number" min="0" step="any" value={input.current} onChange={e => patch("current", e.target.value)} /></label></div>}
    <button onClick={() => { try { setPreview(generateTopology(domain, mode === "manual" ? { ...input, sourcePad: "", sinkPad: "" } : input, board)); setError(""); } catch (e) { setError(e instanceof Error ? e.message : "Generation failed"); } }}>Preview schematic</button>
    {error && <p role="alert">{error}</p>}
    {preview && <><p>{preview.nodes.length} symbols · {preview.edges.length} connections</p><TopologyPreview model={preview} />{preview.extraction.warnings.map(warning => <p key={warning}>{warning}</p>)}<label>Apply as<select value={replace ? "replace" : "add"} onChange={e => setReplace(e.target.value === "replace")}><option value="add">Add to existing sheet</option><option value="replace">Replace entire sheet</option></select></label><button className="primary" onClick={() => onApply(preview, replace)}>{replace ? "Replace sheet with preview" : "Add preview to sheet"}</button></>}
  </section>;
}
