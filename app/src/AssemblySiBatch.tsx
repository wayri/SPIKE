import { useState } from "react";
import type { AssemblyDesigns, AssemblyIr } from "./mcadAssembly";
import { openNativeTextFile, runLocalWorker, saveNativeTextFile } from "./workerBridge";

/** Explicit per-instance jobs; never replicate a channel setup onto other boards. */
export default function AssemblySiBatch({ assembly, designs, disabled, onStatus }: {
  assembly: AssemblyIr; designs: AssemblyDesigns; disabled: boolean; onStatus: (text: string) => void;
}) {
  const [jobs, setJobs] = useState<Record<string, Record<string, unknown>>>({});
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const boards = assembly.boards.map(board => ({ id: String(board.id), name: String(board.name || board.id), design_id: String(board.design_id) }));
  const load = async (id: string) => {
    try {
      const file = await openNativeTextFile("result");
      if (!file) return;
      if (file.contents.length > 2 * 1024 * 1024) throw new Error("Suite setup exceeds 2 MiB.");
      const suite = JSON.parse(file.contents);
      if (suite?.contract !== "spike/si-protocol-test-suite-request/v1") throw new Error("Select an SI protocol test-suite request JSON, not a result or netlist.");
      setJobs(current => ({ ...current, [id]: suite })); setResult(null);
    } catch (error) { onStatus(String(error)); }
  };
  const run = async () => {
    if (disabled || busy) return;
    setBusy(true); setResult(null);
    try {
      const response = await runLocalWorker({ method: "run_multiboard_si_independent_batch", params: { request: {
        contract: "spike/multiboard-si-independent-batch-request/v1",
        multiboard_request: { contract: "spike/multiboard-analysis-request/v1", domain: "si", mode: "independent_board_batch", assembly,
          designs: Object.fromEntries(designs.designs.map(design => [design.design_id, design])) },
        jobs: boards.filter(board => jobs[board.id]).map(board => ({ board_id: board.id, suite_request: jobs[board.id] })),
      } } });
      if (!response.ok || !response.result) throw new Error(response.error || "No batch result returned.");
      setResult(response.result); onStatus("Independent SI batch completed; cross-board coupling was not included. Export the result to retain this run.");
    } catch (error) { onStatus(`SI batch failed: ${String(error)}`); }
    finally { setBusy(false); }
  };
  const rows = (Array.isArray(result?.jobs) ? result.jobs : []) as Array<{ board_id: string; namespace: string; result?: { status?: string } }>;
  return <section><h4>Independent SI batch execution</h4>
    <p>Assign a reviewed SI suite request to each board to analyze. Unassigned boards are skipped. Harness and cross-board field coupling are excluded. Setups and results here are session-only; export results before closing.</p>
    <table className="data-table"><thead><tr><th>Board</th><th>Design</th><th>Suite setup</th></tr></thead><tbody>{boards.map(board => <tr key={board.id}><td>{board.name || board.id}</td><td>{board.design_id}</td><td><button disabled={disabled || busy} onClick={() => void load(board.id)}>{jobs[board.id] ? "Replace suite JSON" : "Load suite JSON"}</button>{jobs[board.id] && <button disabled={busy} onClick={() => { setJobs(current => { const next = { ...current }; delete next[board.id]; return next; }); setResult(null); }}>Remove</button>}</td></tr>)}</tbody></table>
    <button disabled={disabled || busy || !boards.some(board => jobs[board.id])} onClick={() => void run()}>{busy ? "Running sequential board jobs…" : "Run assigned independent SI jobs"}</button>
    {result && <><button onClick={() => void saveNativeTextFile("assembly-si-batch.json", JSON.stringify(result, null, 2), "result").catch(error => onStatus(String(error)))}>Export batch results</button><table className="data-table"><thead><tr><th>Board</th><th>Namespace</th><th>Status</th></tr></thead><tbody>{rows.map(row => <tr key={row.board_id}><td>{row.board_id}</td><td>{row.namespace}</td><td>{row.result?.status || "Returned"}</td></tr>)}</tbody></table></>}
  </section>;
}
