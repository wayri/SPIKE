import { AlertTriangle, CheckCircle2, Gauge, Play, X, XCircle } from "./icons";
import { useState } from "react";
import { runLocalWorker } from "./workerBridge";

type BenchmarkRow = { name: string; status: string; measured: number | null; expected: number | null; relative_error: number | null; tolerance: number | null; units: string; detail: string };
type BenchmarkReport = { contract: string; status: string; summary: { total: number; passed: number; failed: number; skipped: number }; benchmarks: BenchmarkRow[]; limitations: string[] };

export default function BenchmarkCenter({ onClose, onStatus }: { onClose: () => void; onStatus: (message: string) => void }) {
  const [report, setReport] = useState<BenchmarkReport | null>(null);
  const [running, setRunning] = useState(false);
  const run = async () => {
    setRunning(true);
    onStatus("Running the local solver verification corpus");
    try {
      const response = await runLocalWorker({ method: "benchmarks", params: {} });
      if (!response.ok) throw new Error(response.error ?? "Benchmark worker failed");
      const next = response.result as unknown as BenchmarkReport;
      setReport(next);
      onStatus(`Solver verification ${next.status}: ${next.summary.passed} passed, ${next.summary.failed} failed, ${next.summary.skipped} skipped`);
    } catch (error) {
      onStatus(error instanceof Error ? error.message : "Solver verification failed");
    } finally { setRunning(false); }
  };
  return <div className="modal-shade" role="dialog" aria-modal="true" aria-label="Solver verification"><section className="benchmark-center">
    <header><div><Gauge size={18} /><span><b>Solver verification</b><small>Deterministic analytical, topology, convergence, and native-kernel checks</small></span></div><button className="canvas-icon" onClick={onClose}><X size={16} /></button></header>
    <div className="validation-gates">
      <Gate status={report?.status === "passed" ? "pass" : "pending"} title="Analytical and convergence corpus" detail={report ? `${report.summary.passed} passed · ${report.summary.failed} failed · ${report.summary.skipped} skipped` : "Run on this installed runtime"} />
      <Gate status="pending" title="Independent trusted-solver correlation" detail="Required before arbitrary-board sign-off claims" />
      <Gate status="pending" title="Measured fixture correlation" detail="Required before certified or compliance claims" />
    </div>
    <div className="benchmark-toolbar"><p>Passing this corpus verifies bounded implementation properties. It does not certify arbitrary PCB geometries, full-wave behavior, or measurement agreement.</p><button className="run-btn" onClick={() => void run()} disabled={running}><Play size={14} />{running ? "Running…" : "Run verification"}</button></div>
    <div className="benchmark-table"><div className="benchmark-row header"><span>Check</span><span>Status</span><span>Measured</span><span>Expected</span><span>Error / tolerance</span></div>{report?.benchmarks.map(row => <div className="benchmark-row" key={row.name} title={row.detail}><b>{row.name.replace(/_/g, " ")}</b><span className={row.status}>{row.status}</span><span>{format(row.measured)} {row.units}</span><span>{format(row.expected)}</span><span>{formatPercent(row.relative_error)} / {formatPercent(row.tolerance)}</span></div>) ?? <div className="benchmark-empty">No verification run has been loaded.</div>}</div>
    {report && <section className="benchmark-limitations"><h3><AlertTriangle size={14} /> Published limits</h3>{report.limitations.map(item => <p key={item}>{item}</p>)}</section>}
    <footer><span>{report?.contract ?? "spike/solver-benchmark-report/v1"}</span><button className="secondary-btn" onClick={onClose}>Close</button></footer>
  </section></div>;
}

function Gate({ status, title, detail }: { status: "pass" | "pending" | "fail"; title: string; detail: string }) {
  const Icon = status === "pass" ? CheckCircle2 : status === "fail" ? XCircle : AlertTriangle;
  return <div className={`validation-gate ${status}`}><Icon size={17} /><span><b>{title}</b><small>{detail}</small></span></div>;
}
function format(value: number | null) { return value === null || !Number.isFinite(value) ? "—" : value.toExponential(5); }
function formatPercent(value: number | null) { return value === null || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(4)}%`; }

