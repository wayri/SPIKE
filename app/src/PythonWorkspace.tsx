import { Code2, FolderOpen, Play, Save, Square, X } from "lucide-react";
import { useRef, useState } from "react";
import { extensionAnalysisResult } from "./extensionAnalysisResult";
import { cancelLocalWorker, isDesktopShell, openNativeTextFile, runLocalWorker, saveNativeTextFile } from "./workerBridge";

const STARTER = `# SPIKE Python workspace
# The current design and latest result are available through the spike API.
# Run scripts in the desktop app. Output from print() appears below.
print("SPIKE Python is ready")
print("Design available:", spike.design is not None)
print("Results available:", spike.results is not None)
`;

type ScriptResult = {
  contract?: string;
  status?: string;
  stdout?: string;
  stderr?: string;
  return_code?: number;
  duration_ms?: number;
  published_result?: unknown;
};

const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

export default function PythonWorkspace({ design, results, onClose, onStatus }: {
  design: Record<string, unknown> | null;
  results: unknown;
  onClose: () => void;
  onStatus: (message: string) => void;
}) {
  const [code, setCode] = useState(STARTER);
  const [fileName, setFileName] = useState("untitled.py");
  const [dirty, setDirty] = useState(false);
  const [running, setRunning] = useState(false);
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);
  const [stopping, setStopping] = useState(false);
  const [output, setOutput] = useState<ScriptResult | null>(null);
  const [message, setMessage] = useState("Ready to run a Python script in the SPIKE desktop worker.");
  const fileInput = useRef<HTMLInputElement>(null);
  const activeRun = useRef<string | null>(null);
  const desktop = isDesktopShell();

  const loadFile = async (file: File) => {
    try {
      const contents = await file.text();
      setCode(contents); setFileName(file.name); setDirty(false); setOutput(null);
      setMessage(`Opened ${file.name}`);
    } catch (error) { setMessage(`Open failed: ${errorText(error)}`); }
  };
  const open = async () => {
    if (dirty && !window.confirm("Discard unsaved Python script changes?")) return;
    if (!desktop) { fileInput.current?.click(); return; }
    try {
      const file = await openNativeTextFile("script");
      if (!file) return;
      setCode(file.contents); setFileName(file.fileName); setDirty(false); setOutput(null);
      setMessage(`Opened ${file.path}`);
    } catch (error) { setMessage(`Open failed: ${errorText(error)}`); }
  };
  const save = async () => {
    const suggestedName = fileName.toLowerCase().endsWith(".py") ? fileName : `${fileName}.py`;
    if (desktop) {
      try {
        const path = await saveNativeTextFile(suggestedName, code, "script");
        if (path) { setFileName(path.split(/[\\/]/).pop() ?? suggestedName); setDirty(false); setMessage(`Saved ${path}`); }
      } catch (error) { setMessage(`Save failed: ${errorText(error)}`); }
      return;
    }
    const url = URL.createObjectURL(new Blob([code], { type: "text/x-python;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url; link.download = suggestedName; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setDirty(false); setMessage(`Downloaded ${suggestedName}`);
  };
  const run = async () => {
    if (!desktop || activeRun.current || !code.trim()) return;
    const id = crypto.randomUUID();
    activeRun.current = id; setRunning(true); setStopping(false); setOutput(null); setMessage("Running Python script…");
    try {
      const response = await runLocalWorker({ id, method: "run_python_script", params: { code, design, results, timeout_seconds: timeoutSeconds } });
      const result = response.result as ScriptResult | undefined;
      if (result?.contract === "spike/python-script-result/v1") {
        setOutput(result);
        if (result.published_result) {
          const provenance = (result.published_result as Record<string, unknown>)?.provenance as Record<string, unknown> | undefined;
          const published = extensionAnalysisResult("analyses", "spike/v1", {
            analysis_result: result.published_result,
            input_design_sha256: provenance?.design_digest_sha256,
          });
          if (published) window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: published }));
          else setMessage("Script finished, but its published result could not be displayed.");
        }
      } else if (!response.ok && response.error) setOutput({ status: "failed", stderr: response.error });
      if (!response.ok) setMessage(response.error ?? result?.stderr ?? "Python script failed.");
      else if (result?.status === "failed" || (result?.return_code ?? 0) !== 0) setMessage(`Script failed (exit ${result?.return_code ?? "unknown"}).`);
      else if (!result) setMessage("The worker returned no Python script result.");
      else setMessage(`Script completed${typeof result.duration_ms === "number" ? ` in ${(result.duration_ms / 1000).toFixed(2)} s` : ""}.`);
    } catch (error) { setMessage(`Run failed: ${errorText(error)}`); }
    finally { activeRun.current = null; setRunning(false); setStopping(false); }
  };
  const stop = async () => {
    if (!activeRun.current || stopping) return;
    setStopping(true); setMessage("Stopping Python script…");
    const accepted = await cancelLocalWorker(activeRun.current);
    setMessage(accepted ? "Stop requested; waiting for the worker to finish." : "No active Python worker operation accepted the stop request.");
    if (!accepted) setStopping(false);
  };
  const close = () => {
    if (running) return;
    if (dirty && !window.confirm("Discard unsaved Python script changes?")) return;
    onClose();
  };

  return <div className="modal-shade python-workspace-shade"><section className="python-workspace" role="dialog" aria-modal="true" aria-label="Python workspace">
    <header><div><Code2 size={20} /><span><b>PYTHON WORKSPACE</b><small>Edit and run scripts with the local SPIKE worker</small></span></div><button className="canvas-icon" onClick={close} disabled={running} aria-label="Close Python workspace"><X size={16} /></button></header>
    <div className="python-workspace-toolbar">
      <span className="python-workspace-file">{fileName}{dirty ? " •" : ""}</span>
      <input ref={fileInput} type="file" accept=".py,text/x-python,text/plain" className="hidden-input" aria-label="Open Python script" onChange={event => { const file = event.target.files?.[0]; if (file) void loadFile(file); event.target.value = ""; }} />
      <button className="secondary-btn" onClick={() => void open()} disabled={running}><FolderOpen size={14} /> Open</button>
      <button className="secondary-btn" onClick={() => void save()} disabled={running}><Save size={14} /> {desktop ? "Save as" : "Download"}</button>
      <label className="python-workspace-timeout">Limit <input type="number" min={1} max={600} value={timeoutSeconds} disabled={running} onChange={event => setTimeoutSeconds(Math.max(1, Math.min(600, Number(event.target.value) || 1)))} /> sec</label>
      <button className="run-btn" onClick={() => void (running ? stop() : run())} disabled={!running && (!desktop || !code.trim()) || stopping}>{running ? <Square size={14} /> : <Play size={14} />}{running ? stopping ? "Stopping…" : "Stop" : "Run"}</button>
    </div>
    <div className="python-workspace-main"><div className="python-workspace-editor"><label htmlFor="python-workspace-code">Script <small>Ctrl+Enter to run · Tab to indent</small></label><textarea id="python-workspace-code" value={code} onChange={event => { setCode(event.target.value); setDirty(true); }} onKeyDown={event => {
      if (event.ctrlKey && event.key === "Enter") { event.preventDefault(); void run(); }
      if (event.key === "Tab") {
        event.preventDefault(); const element = event.currentTarget;
        const start = element.selectionStart, end = element.selectionEnd;
        setCode(current => `${current.slice(0, start)}    ${current.slice(end)}`); setDirty(true);
        requestAnimationFrame(() => { element.selectionStart = element.selectionEnd = start + 4; });
      }
    }} spellCheck={false} disabled={running} /></div>
      <aside className="python-workspace-guide"><h3>Script context</h3><p><code>spike.design</code> is the current board. <code>spike.results</code> is the selected result context; check <code>complete</code> before reading <code>result</code>.</p><p>Use <code>print()</code> for output and <code>spike.call(method, params)</code> for worker operations.</p><p><code>spike.invoke_extension(id, contribution, options)</code> runs a trusted external adapter.</p><p><code>spike.publish_scalar_field(name, samples)</code> displays a computed board field after validation.</p><p>Scripts run as local Python with your file and package access.</p><p>{design ? "Current design attached" : "No design loaded"} · {results ? "Analysis result attached" : "No analysis result"}</p></aside>
    </div>
    <div className="python-workspace-output"><div><b>OUTPUT</b>{output && <span>Exit {output.return_code ?? "—"} · {output.status ?? "unknown"}</span>}</div><pre aria-label="Python standard output">{output?.stdout || "Standard output will appear here."}</pre>{output?.stderr && <pre className="python-workspace-stderr" aria-label="Python standard error">{output.stderr}</pre>}</div>
    <footer><span role="status">{message}</span>{!desktop && <small>Run requires the desktop app.</small>}<button className="secondary-btn" onClick={() => { if (!dirty) onStatus(message); close(); }} disabled={running}>Close</button></footer>
  </section></div>;
}
