import { useEffect, useState } from "react";
import type { BoardImportProgress } from "./boardImportProgress";
import "./boardImportPanel.css";

export default function BoardImportPanel({ progress, onHide, onCancel, onLocate, onRetry }: {
  progress: BoardImportProgress; onHide: () => void; onCancel: () => void;
  onLocate: (source: string) => void; onRetry: () => void;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!progress.busy) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [progress.busy]);
  const elapsed = Math.max(0, Math.floor((now - progress.startedAt) / 1000));
  return <aside className="board-import-panel" aria-label="Board import" aria-busy={progress.busy}>
    <header><div><small>BOARD IMPORT</small><strong>{progress.fileName}</strong></div><button onClick={onHide} aria-label="Hide import progress">×</button></header>
    <p role="status">{progress.label}</p>
    <progress max={100} value={progress.percent} aria-label="Completed import stages" />
    <div className="board-import-progress-caption"><span>{progress.percent}% · completed stages</span>{progress.busy && <span>{elapsed}s elapsed</span>}</div>
    {progress.busy && <p className="board-import-help">You can continue using completed layers while the remaining views load.</p>}
    {progress.problems.length > 0 && <section>
      <h3>Locate missing models</h3>
      <p>Automatic search could not find these files. Choose a replacement once to update every listed part, or continue with placeholders.</p>
      {progress.problems.map(problem => <div className="board-import-problem" key={problem.source}>
        <strong>{problem.source.replace(/\\/g, "/").split("/").pop()}</strong>
        <span>{problem.references.join(", ") || "Referenced model"}</span>
        <small>{problem.source}</small>
        <button disabled={progress.busy} onClick={() => onLocate(problem.source)}>Locate model…</button>
      </div>)}
    </section>}
    {progress.warnings.length > 0 && <section><h3>Import details</h3>{progress.warnings.map((warning, index) => <p key={index} className="board-import-warning">{warning}</p>)}</section>}
    <footer>
      {progress.busy && progress.stage !== "parsing" && <button onClick={onCancel}>Stop import</button>}
      {!progress.busy && (progress.warnings.length > 0 || progress.stage === "cancelled") && <button onClick={onRetry}>Retry automatically</button>}
      <button onClick={onHide}>{progress.busy ? "Work while importing" : progress.problems.length ? "Continue with placeholders" : "Done"}</button>
    </footer>
  </aside>;
}
