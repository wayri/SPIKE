// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { FileOutput, FolderOpen, ListChecks, X } from "./icons";
import type { SpiceModel } from "./spiceWorkspace";
import { runLocalWorker } from "./workerBridge";
import { optionMatchesQuery } from "./optionSearch";
import SectionHelpButton from "./SectionHelpButton";
import { emptyLibraryImport, SpiceModelLibrarySession } from "./spiceModelLibrarySession";
import "./SpiceModelLibraryImport.css";

export default function SpiceModelLibraryImport({ disabled, onAdd, onClose }: { disabled: boolean; onAdd: (model: SpiceModel) => void; onClose: () => void }) {
  const [state, setState] = useState(emptyLibraryImport);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [locator, setLocator] = useState("");
  const [license, setLicense] = useState("");
  const addRef = useRef(onAdd); addRef.current = onAdd;
  const session = useMemo(() => new SpiceModelLibrarySession(runLocalWorker, setState, model => addRef.current(model)), []);
  useEffect(() => { session.activate(); return () => session.dispose(); }, [session]);
  const locked = disabled || state.busy;
  const candidates = state.inspection?.candidates ?? [];
  const filtered = candidates.filter(row => optionMatchesQuery(`${row.subcircuit_name} ${row.pins.join(" ")}`, query));
  const selected = candidates.find(row => row.subcircuit_name === state.selected);
  return <section className="spice-library-import" aria-label="Import a user circuit model library" aria-busy={state.busy}>
    <header><div><strong>1. Inspect a library · 2. Choose a model · 3. Add and map pins</strong><small>Structural import only. Adding a model never assigns a part or starts a solver.</small></div><SectionHelpButton topic="doc:docs/SPICE_WORKSPACE.md" anchor="import-a-model-library" label="Circuit model library import" /><button type="button" className="spike-control--icon" aria-label="Close model library import" onClick={onClose}><X size={15} /></button></header>
    <fieldset disabled={locked}>
      <div className="spice-library-actions"><label><FolderOpen size={14} /> Choose library<input aria-label="Choose SPICE model library" type="file" accept=".lib,.mod,.cir,.sp,.spice,.net,.txt" onChange={event => { const file = event.currentTarget.files?.[0]; if (file) { setOffset(0); setQuery(""); void session.readFile(file); } event.currentTarget.value = ""; }} /></label><button type="button" onClick={() => void session.inspect()} disabled={!state.text.trim()}><ListChecks size={14} /> Inspect pasted source</button></div>
      <label>Library name<input maxLength={256} value={state.name} onChange={event => session.setSource(state.text, event.target.value)} /></label>
      <label>Library source (maximum 2 MiB)<textarea aria-label="SPICE library source" rows={5} spellCheck={false} value={state.text} onChange={event => { session.setSource(event.target.value); setOffset(0); }} placeholder={".subckt my_filter in out ref params: R=1k\nR1 in out {R}\nC1 out ref 1n\n.ends my_filter"} /></label>
      {state.inspection?.valid && <div className="spice-library-review"><div><label>Find a model<input type="search" maxLength={256} placeholder="Name or pins; * and ? supported" value={query} onChange={event => { setQuery(event.target.value); setOffset(0); }} /></label><div className="spice-library-choices" role="group" aria-label="Library model entry points">{filtered.slice(offset, offset + 12).map(row => <button type="button" key={row.id} aria-pressed={row.subcircuit_name === state.selected} onClick={() => session.select(row.subcircuit_name)}><strong>{row.subcircuit_name}</strong><small>{row.pins.length} pins · {row.dependency_names.length} dependencies</small></button>)}</div><nav aria-label="Model result pages"><button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 12))}>Previous</button><span>{filtered.length ? `${offset + 1}–${Math.min(offset + 12, filtered.length)}` : "0"} / {filtered.length}</span><button type="button" disabled={offset + 12 >= filtered.length} onClick={() => setOffset(offset + 12)}>Next</button></nav></div><div>{selected && <><strong>{selected.subcircuit_name}</strong><p>Pin order: {selected.pins.join(" → ")}</p><p>Defaults: {Object.entries(selected.default_parameters).map(([key, value]) => `${key}=${value}`).join(", ") || "none"}</p><p>Dependencies: {selected.dependency_names.join(", ") || "none"}</p><small>Execution route: external ngspice, subject to runtime and model review.</small></>}<label>Source or vendor reference (optional)<input maxLength={2048} value={locator} onChange={event => setLocator(event.target.value)} /></label><label>License / private-use note (optional)<input maxLength={1024} value={license} onChange={event => setLicense(event.target.value)} /></label><button type="button" className="spike-control--primary" disabled={!selected} onClick={() => void session.importSelected(locator, license)}><FileOutput size={14} /> Add selected model to project</button></div></div>}
    </fieldset>
    <div role="status">{state.busy ? "Inspecting model data; no simulation is running…" : state.error}</div>
    {state.inspection?.diagnostics.map((issue, index) => <p key={`${issue.code}-${index}`} role={issue.severity === "error" ? "alert" : undefined}><strong>{issue.code}</strong>{issue.line > 0 && ` · line ${issue.line}`} — {issue.message}</p>)}
    <small>Supported subset: .subckt entry points, continuations, parameters and their declared local dependencies. Include files, encrypted models, nested subcircuits and .model-only libraries are not imported. Record redistribution rights before sharing a project containing third-party models.</small>
  </section>;
}
