// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { ExternalSolverResults } from "./ExternalSolverResults";
import { defaultPalaceParameters, palaceParameters, parseSolverJson, readSolverText, solverRecord, solverResultData, type ExternalSolverProps } from "./solverExtensionModel";
import "./buttonStandard.css";
import "./ExternalSolver.css";
export { defaultPalaceParameters, palaceParameters } from "./solverExtensionModel";
const sections = ["Problem", "Model", "Domains", "Boundaries", "Solver"] as const;
export function PalaceExtension(props: ExternalSolverProps) {
  const [error, setError] = useState(""), [working, setWorking] = useState(false), [drafts, setDrafts] = useState<Record<string, string>>({});
  const value = { ...defaultPalaceParameters(), ...props.parameters }, config = solverRecord(value.config);
  const blocked = props.disabled || props.busy || working;
  const data = solverResultData(props.result), retained = solverRecord(data.case);
  const patch = (update: Record<string, unknown>) => { props.onParameters({ ...value, ...update }); setError(""); };
  const effective = () => ({ ...value, config: sections.reduce((current, name) => ({ ...current, [name]: drafts[name] === undefined ? config[name] : parseSolverJson(drafts[name], name) }), { ...config }) });
  const execute = async (id: string, operation: string) => {
    setError(""); setWorking(true);
    try { const parameters = operation === "import" ? { job_id: retained.job_id } : palaceParameters(operation === "discover" ? value : effective(), operation); props.onParameters(operation === "import" ? value : parameters); await props.onExecute(id, parameters); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); } finally { setWorking(false); }
  };
  const loadConfig = async (file: File | undefined) => { if (!file) return; try { const imported = parseSolverJson(await readSolverText(file), "PALACE configuration"); patch({ config: imported }); setDrafts({}); } catch (cause) { setError(String(cause)); } };
  const editSection = (name: string, text: string) => { setDrafts(current => ({ ...current, [name]: text })); try { const parsed = parseSolverJson(text, name); patch({ config: { ...config, [name]: parsed } }); } catch { /* Preserve incomplete authoring text; the action reports syntax errors. */ } };
  return <section className="external-solver" aria-label="PALACE electromagnetic workbench">
    <div><h4>PALACE electromagnetic workbench</h4><small>Use a native PALACE configuration and an explicit local mesh. Materials, boundary attributes, excitation and solver settings are authored in their native sections. Results remain experimental and require engineering review.</small></div>
    <fieldset disabled={blocked}><legend>1. Native configuration and mesh</legend><div className="solver-fields"><label>Import PALACE configuration<input type="file" accept=".json" onChange={event => { void loadConfig(event.target.files?.[0]); event.target.value = ""; }} /></label><label>Problem mode<select value={String(solverRecord(config.Problem).Type ?? "Driven")} onChange={event => { const problem = { ...solverRecord(config.Problem), Type: event.target.value }; patch({ config: { ...config, Problem: problem } }); setDrafts(current => ({ ...current, Problem: JSON.stringify(problem, null, 2) })); }}>{["Driven", "Eigenmode", "Electrostatic", "Magnetostatic", "Transient", "BoundaryMode"].map(name => <option key={name} value={name}>{name}</option>)}</select></label></div>
      <label>Absolute mesh file path<input value={String(value.mesh_path)} placeholder="C:\\studies\\case\\mesh.msh" onChange={event => patch({ mesh_path: event.target.value, expected_mesh_sha256: "" })} /></label><small>The worker reads and hashes this local mesh. Changing the path clears its reviewed digest. Set a positive native Model.L0 to declare the mesh length scale.</small>
      {sections.map(name => <details key={name} open={name === "Problem"}><summary>{name}{name === "Domains" ? " - materials and volume attributes" : name === "Boundaries" ? " - boundary attributes and ports" : name === "Solver" ? " - frequency, time and numerical options" : name === "Model" ? " - mesh and geometry options" : " - analysis mode and output"}</summary><label>{name} native JSON<textarea spellCheck={false} value={drafts[name] ?? JSON.stringify(config[name] ?? {}, null, 2)} onChange={event => editSection(name, event.target.value)} /></label></details>)}
      <label>Reviewed mesh SHA-256<input value={String(value.expected_mesh_sha256 ?? "")} onChange={event => patch({ expected_mesh_sha256: event.target.value })} /></label>{Boolean(retained.mesh_sha256) && <><small>Prepared mesh digest: {String(retained.mesh_sha256)}</small><button type="button" onClick={() => patch({ expected_mesh_sha256: retained.mesh_sha256 })}>Accept prepared mesh digest</button></>}
    </fieldset>
    <fieldset disabled={blocked}><legend>2. Runtime and resource limits</legend><div className="solver-fields"><label>PALACE executable path<input value={String(value.runtime_path ?? "")} placeholder="Discover separately installed PALACE" onChange={event => patch({ runtime_path: event.target.value })} /></label>{[["timeout_s", "Timeout (s)", 1, 3300], ["memory_limit_mb", "Memory limit (MiB)", 256, 32768], ["threads", "Serial execution rank", 1, 1]].map(([key, label, min, max]) => <label key={key}>{label}<input type="number" min={min} max={max} step="1" value={String(value[String(key)] ?? "")} onChange={event => patch({ [String(key)]: event.target.value })} /></label>)}</div><small>This contained adapter uses one serial execution rank. Resource limits bound execution; they do not establish mesh convergence or physical accuracy.</small></fieldset>
    <div className="solver-actions"><button type="button" disabled={blocked} onClick={() => void execute("palace-discover", "discover")}>Discover runtime</button><button type="button" disabled={blocked} onClick={() => void execute("palace-validate", "validate")}>Validate configuration</button><button type="button" disabled={blocked} onClick={() => void execute("palace-prepare", "prepare")}>Prepare case</button><button type="button" className="spike-control--primary" disabled={blocked} onClick={() => void execute("palace-run", "run")}>Run PALACE</button><button type="button" disabled={blocked || !retained.job_id} onClick={() => void execute("palace-import", "import")}>Import retained results</button>{props.onCancel && <button type="button" disabled={!props.busy && !working} onClick={props.onCancel}>Cancel run</button>}</div>
    {(props.busy || working) && <p role="status">PALACE worker operation in progress...</p>}{error && <p role="alert">{error} Review the configuration or runtime path and retry.</p>}
    <ExternalSolverResults result={props.result} engine="PALACE" />
  </section>;
}
