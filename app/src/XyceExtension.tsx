// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { ExternalSolverResults } from "./ExternalSolverResults";
import { defaultXyceParameters, readSolverText, solverRecord, solverResultData, xyceParameters, type ExternalSolverProps } from "./solverExtensionModel";
import "./buttonStandard.css";
import "./ExternalSolver.css";
export { defaultXyceParameters, xyceParameters } from "./solverExtensionModel";
export function XyceExtension(props: ExternalSolverProps) {
  const [error, setError] = useState(""), [working, setWorking] = useState(false);
  const value = { ...defaultXyceParameters(), ...props.parameters }, options = solverRecord(value.engine_options);
  const libraries = Array.isArray(value.libraries) ? value.libraries.map(solverRecord) : [];
  const blocked = props.disabled || props.busy || working;
  const patch = (update: Record<string, unknown>) => { props.onParameters({ ...value, ...update, case_id: undefined }); setError(""); };
  const execute = async (id: string, operation: string) => {
    setError(""); setWorking(true);
    try { const parameters = operation === "inspect" ? { ...value, operation, case_id: solverResultData(props.result).case_id ?? value.case_id } : xyceParameters(value, operation); if (operation === "inspect" && !parameters.case_id) throw new Error("Prepare a case before inspecting retained outputs."); await props.onExecute(id, parameters); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); } finally { setWorking(false); }
  };
  const load = async (file: File | undefined, library: boolean) => { if (!file) return; try { const text = await readSolverText(file); patch(library ? { libraries: [...libraries, { name: file.name, text }] } : { netlist: text }); } catch (cause) { setError(String(cause)); } };
  return <section className="external-solver" aria-label="Xyce circuit workbench">
    <div><h4>Xyce circuit workbench</h4><small>Author a native netlist, stage model libraries, and inspect actual solver waveforms. This adapter is experimental; circuit admission and numerical validity remain worker checks.</small></div>
    <fieldset disabled={blocked}><legend>1. Circuit and model libraries</legend><label>Import netlist<input type="file" accept=".cir,.sp,.spice,.net,.txt" onChange={event => { void load(event.target.files?.[0], false); event.target.value = ""; }} /></label><label>Native Xyce netlist<textarea className="solver-netlist" spellCheck={false} value={String(value.netlist)} placeholder="Enter a complete native circuit, analysis directives, output requests and .END" onChange={event => patch({ netlist: event.target.value })} /></label><small>Use relative .include names matching the staged libraries below. Native code plugins are disabled by the worker.</small><label>Add model library<input type="file" accept=".lib,.model,.cir,.txt" onChange={event => { void load(event.target.files?.[0], true); event.target.value = ""; }} /></label>
      {libraries.map((library, index) => <div className="solver-library" key={index}><label>Library {index + 1} relative name<input value={String(library.name ?? "")} onChange={event => patch({ libraries: libraries.map((item, i) => i === index ? { ...item, name: event.target.value } : item) })} /></label><details><summary>Edit library content</summary><label>Library {index + 1} text<textarea spellCheck={false} value={String(library.text ?? "")} onChange={event => patch({ libraries: libraries.map((item, i) => i === index ? { ...item, text: event.target.value } : item) })} /></label></details><button type="button" onClick={() => patch({ libraries: libraries.filter((_, i) => i !== index) })}>Remove library {index + 1}</button></div>)}
    </fieldset>
    <fieldset disabled={blocked}><legend>2. Runtime and resource limits</legend><div className="solver-fields"><label>Xyce executable<input value={String(options.executable ?? "")} placeholder="Auto-detect installed Xyce" onChange={event => patch({ engine_options: { ...options, executable: event.target.value } })} /></label>{[["timeout_seconds", "Timeout (s)"], ["memory_limit_mib", "Memory limit (MiB)"]].map(([key, label]) => <label key={key}>{label}<input type="number" min="1" step="1" value={String(options[key] ?? "")} onChange={event => patch({ engine_options: { ...options, [key]: event.target.value } })} /></label>)}</div><small>Install Xyce separately. Runtime checks discover the executable without solving a circuit.</small></fieldset>
    <div className="solver-actions"><button type="button" disabled={blocked} onClick={() => void execute("xyce-circuit", "preflight")}>Check runtime</button><button type="button" disabled={blocked} onClick={() => void execute("xyce-circuit", "prepare")}>Prepare case</button><button type="button" disabled={blocked} onClick={() => void execute("xyce-validate", "validate")}>Validate netlist</button><button type="button" className="spike-control--primary" disabled={blocked} onClick={() => void execute("xyce-run", "run")}>Run Xyce</button><button type="button" disabled={blocked || !solverResultData(props.result).case_id} onClick={() => void execute("xyce-inspect", "inspect")}>Inspect retained case</button>{props.onCancel && <button type="button" disabled={!props.busy && !working} onClick={props.onCancel}>Cancel run</button>}</div>
    {(props.busy || working) && <p role="status">Xyce worker operation in progress...</p>}{error && <p role="alert">{error} Correct the input or runtime path and retry.</p>}
    <ExternalSolverResults result={props.result} engine="Xyce" />
  </section>;
}
