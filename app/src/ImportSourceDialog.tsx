// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { FolderOpen, Upload, X } from "./icons";
import { cancelLocalWorker, readApprovedSourceFile, runLocalWorker, selectNativeImportFile, selectNativeWorkbenchFile, type NativeSelectedFile } from "./workerBridge";
import { classifyOpenSource, HARNESS_COLUMNS, type ImportSourceKind, type PreparedSource } from "./importSourceRouting";
import { connectionColumnMap, connectionListHeader, OPTIONAL_HARNESS_COLUMNS } from "./harnessConnectionColumns";
import "./importSourceDialog.css";

type Props = { initialSource?: NativeSelectedFile; initialKind?: ImportSourceKind; onApply: (source: PreparedSource) => Promise<void>; onClose: () => void };
const labels: Record<ImportSourceKind, string> = { kicad: "KiCad board", normalized: "SPIKE normalized design", "odb++": "ODB++ job", ipc2581: "IPC-2581 board", harness: "Harness connections", mcad: "Mechanical model" };

export default function ImportSourceDialog({ initialSource, initialKind = "kicad", onApply, onClose }: Props) {
  const [source, setSource] = useState(initialSource ?? null);
  const [kind, setKind] = useState<ImportSourceKind>(initialKind);
  const [steps, setSteps] = useState<string[]>([]);
  const [step, setStep] = useState("");
  const [delimiter, setDelimiter] = useState(initialSource?.fileName.toLowerCase().endsWith(".tsv") ? "\t" : ",");
  const [columns, setColumns] = useState<Record<string, string>>({});
  const [prepared, setPrepared] = useState<PreparedSource | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const generation = useRef(0);
  const operation = useRef<string | null>(null);
  const alive = useRef(true);
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    alive.current = true;
    const previousFocus = typeof document !== "undefined" ? document.activeElement : null;
    closeButton.current?.focus();
    return () => {
      alive.current = false; generation.current++;
      if (operation.current) void cancelLocalWorker(operation.current);
      if (typeof HTMLElement !== "undefined" && previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);
  const invalidate = () => { generation.current++; setPrepared(null); setError(""); };
  const run = async (method: string, params: Record<string, unknown>) => {
    const id = `source-import-${crypto.randomUUID()}`;
    operation.current = id;
    try { const response = await runLocalWorker({ id, method, params }); if (!response.ok) throw new Error(response.error ?? "Import worker failed."); return response.result ?? {}; }
    finally { if (operation.current === id) operation.current = null; }
  };
  const choose = async (directory = false) => {
    const token = ++generation.current;
    setBusy("Choosing source…"); setError(""); setPrepared(null);
    try {
      const file = directory ? await selectNativeImportFile("board", true) : await selectNativeWorkbenchFile();
      if (!file || !alive.current || token !== generation.current) return;
      let detected = directory ? "odb++" : classifyOpenSource(file.fileName);
      if (detected === "unknown" && file.fileName.toLowerCase().endsWith(".json")) {
        const text = await readApprovedSourceFile(file.path);
        if (!alive.current || token !== generation.current) return;
        detected = classifyOpenSource(file.fileName, JSON.parse(text.contents));
      }
      if (detected === "project" || detected === "results") throw new Error("Use Open file or project to restore a saved SPIKE project or results package.");
      setSource(file); setKind(detected === "unknown" ? kind : detected); setSteps([]); setStep(""); setColumns({});
      setDelimiter(file.fileName.toLowerCase().endsWith(".tsv") ? "\t" : ",");
    } catch (e) { if (alive.current && token === generation.current) setError(String(e instanceof Error ? e.message : e)); }
    finally { if (alive.current && token === generation.current) setBusy(""); }
  };
  const inspect = async () => {
    if (!source) return;
    const token = ++generation.current; setBusy("Reading ODB++ steps…"); setError(""); setPrepared(null);
    try {
      const result = await run("invoke_extension", { extension_id: "spike.odb-import", contribution_id: "odb-inspect", context: { source: { path: source.path } } });
      if (!alive.current || token !== generation.current) return;
      const data = result.data as { steps?: string[]; default_step?: string };
      if (!Array.isArray(data?.steps) || !data.steps.length) throw new Error("No importable ODB++ steps were found.");
      setSteps(data.steps); setStep(data.default_step ?? "");
    } catch (e) { if (alive.current && token === generation.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (alive.current && token === generation.current) setBusy(""); }
  };
  const prepare = async () => {
    if (!source) return;
    const token = ++generation.current; setBusy("Preparing import…"); setError(""); setPrepared(null);
    try {
      let next: PreparedSource;
      if (kind === "mcad") next = { kind: "mcad", ...source };
      else if (kind === "harness") {
        const tabular = /\.(csv|tsv)$/i.test(source.fileName);
        const text = tabular ? await readApprovedSourceFile(source.path) : null;
        if (!alive.current || token !== generation.current) return;
        const column_map = text ? connectionColumnMap(connectionListHeader(text.contents, delimiter), columns) : undefined;
        const result = await run("invoke_extension", { extension_id: "spike.harness", contribution_id: "harness-import", context: { parameters: { path: source.path, delimiter, ...(column_map ? { column_map } : {}) } } });
        const document = result.data as Record<string, unknown>;
        if (document?.contract !== "spike/harness/v1") throw new Error("The importer returned an invalid harness document.");
        next = { kind: "harness", document };
      } else if (kind === "kicad" || kind === "normalized") {
        const text = await readApprovedSourceFile(source.path);
        next = { kind: "board", fileName: kind === "normalized" ? `${source.fileName.replace(/\.spike-design\.json$/i, "")}.spike-design.json` : source.fileName, source: text.contents, sourcePath: source.path };
      } else {
        const result = await run("import_design_v2", { path: source.path, format_hint: kind, options: kind === "odb++" ? { step } : {}, include_snapshot: true, snapshot_only: true });
        if (!result.snapshot) throw new Error("The importer returned no design snapshot.");
        next = { kind: "board", fileName: `${source.fileName}.spike-design.json`, source: JSON.stringify(result.snapshot), report: (result.snapshot as Record<string, unknown>).report ?? result.report };
      }
      if (alive.current && token === generation.current) setPrepared(next);
    } catch (e) { if (alive.current && token === generation.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (alive.current && token === generation.current) setBusy(""); }
  };
  const apply = async () => {
    if (!prepared) return;
    setBusy("Opening imported content…"); setError("");
    try { await onApply(prepared); }
    catch (e) { if (alive.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (alive.current) setBusy(""); }
  };
  const cancel = async () => {
    generation.current++; setPrepared(null); setBusy("Cancelling import…");
    try { if (operation.current) await cancelLocalWorker(operation.current); }
    finally { if (alive.current) { setBusy(""); setError("Import cancelled. The current project is unchanged."); } }
  };
  return <div className="modal-shade import-source-shade" onKeyDown={event => {
    event.stopPropagation();
    if (event.key === "Escape" && !busy) onClose();
    if (event.key === "Tab") { const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), summary')).filter(control => control.getClientRects().length > 0 && !control.closest("fieldset:disabled")); const first = controls[0], last = controls[controls.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); } }
  }}>
    <section className="import-source-dialog" role="dialog" aria-modal="true" aria-labelledby="import-source-title">
      <header><div><h2 id="import-source-title">Import into SPIKE</h2><p>Boards, manufacturing data, harness connections and mechanical models</p></div><button ref={closeButton} className="canvas-icon" aria-label="Close import" disabled={!!busy} onClick={onClose}><X size={18} /></button></header>
      <div className="import-source-body">
        <div className="import-source-actions"><button className="secondary-btn" disabled={!!busy} onClick={() => choose()}><Upload size={16} /> Choose file</button><button className="secondary-btn" disabled={!!busy} onClick={() => choose(true)}><FolderOpen size={16} /> ODB++ folder</button></div>
        <div className="import-source-path" title={source?.path}>{source?.path ?? "Choose a source file or an extracted ODB++ job folder."}</div>
        <label>Source format<select value={kind} disabled={!!busy} onChange={e => { invalidate(); setKind(e.target.value as ImportSourceKind); setSteps([]); setStep(""); }}>{Object.entries(labels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
        {kind === "odb++" && <div className="import-source-options"><label>Job step{steps.length ? <select value={step} disabled={!!busy} onChange={e => { invalidate(); setStep(e.target.value); }}><option value="">Select a board or panel step</option>{steps.map(name => <option key={name}>{name}</option>)}</select> : <input value={step} disabled={!!busy} placeholder="Automatic for single-step jobs" onChange={e => { invalidate(); setStep(e.target.value); }} />}</label><button className="secondary-btn" disabled={!source || !!busy} onClick={() => void inspect()}>Read job steps</button><small>ZIP, TGZ, TAR, TAR.GZ or extracted jobs. Multi-step jobs require an explicit step. Missing models and unsupported features are reported by the importer.</small></div>}
        {kind === "harness" && /\.(csv|tsv)$/i.test(source?.fileName ?? "") && <fieldset disabled={!!busy}><legend>Connection-list columns</legend><label>Delimiter<select value={delimiter} onChange={e => { invalidate(); setDelimiter(e.target.value); }}>{[[",", "Comma"], ["\t", "Tab"], [";", "Semicolon"], ["|", "Pipe"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>{HARNESS_COLUMNS.map(key => <label key={key}>{key.replace(/_/g, " ")}<input placeholder={key} value={columns[key] ?? ""} onChange={e => { invalidate(); setColumns({ ...columns, [key]: e.target.value }); }} /></label>)}<details className="import-source-optional-columns"><summary>Optional wire fields and electrical properties</summary><p>Canonical headers are retained automatically when present. Map vendor headers explicitly; lengths use mm, area uses mm2, resistance uses ohm and inductance uses H.</p><div className="import-source-column-grid">{OPTIONAL_HARNESS_COLUMNS.map(key => <label key={key}>{key.replace(/_/g, " ")}<input placeholder={`${key} (if present)`} value={columns[key] ?? ""} onChange={e => { invalidate(); setColumns({ ...columns, [key]: e.target.value }); }} /></label>)}</div></details></fieldset>}
        <p className="import-source-note">{kind === "harness" ? "Imports the harness document into this project and opens the harness editor. Existing harness content is replaced when applied." : kind === "mcad" ? "Opens the assembly attachment tool with this model selected. Save the project before attaching the model." : "Starts a new project from the imported board. Save or discard any current changes before applying."}</p>
        {busy && <p role="status" aria-live="polite">{busy}</p>}
        {error && <p className="import-source-error" role="alert">{error}</p>}
        {prepared && <div className="import-source-review"><b>Source ready</b><p>{source?.fileName}</p>{(kind === "kicad" || kind === "normalized") && <p>Board geometry is parsed and checked when you apply the import.</p>}{prepared.kind === "harness" && <p>{Array.isArray(prepared.document.connectors) ? prepared.document.connectors.length : 0} connectors · {Array.isArray(prepared.document.wires) ? prepared.document.wires.length : 0} wires</p>}{prepared.kind === "board" && prepared.report != null && <details><summary>Import coverage and diagnostics</summary><pre>{JSON.stringify(prepared.report, null, 2)}</pre></details>}</div>}
      </div>
      <footer><button className="secondary-btn" disabled={busy === "Opening imported content…"} onClick={busy ? cancel : onClose}>{busy ? "Cancel import" : "Close"}</button>{prepared ? <button className="run-btn" disabled={!!busy} onClick={() => void apply()}>{kind === "mcad" ? "Open attachment tool" : "Apply import"}</button> : <button className="run-btn" disabled={!source || !!busy || (steps.length > 1 && !step)} onClick={() => void prepare()}>Prepare import</button>}</footer>
    </section>
  </div>;
}
