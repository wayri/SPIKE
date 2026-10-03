// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { PythonDebugSnapshot } from "./pythonWorkspaceModel";

export default function PythonDebugPanel({ snapshot, breakpoints, onLine, onClear, onRemove }: {
  snapshot: PythonDebugSnapshot | null; breakpoints: number[];
  onLine: (line: number, filename?: string) => void; onClear: () => void; onRemove: (line: number) => void;
}) {
  const [tab, setTab] = useState<"variables" | "stack" | "breakpoints">("variables");
  const [frameIndex, setFrameIndex] = useState(0);
  const frames = snapshot?.frames ?? [];
  const frame = frames[Math.min(frameIndex, Math.max(0, frames.length - 1))];
  return <aside className="python-debug-inspector" aria-label="Python debugger">
    <div className="python-pane-heading"><b>DEBUGGER</b><span className={`python-debug-state ${snapshot?.status ?? "idle"}`}>{snapshot?.status ?? "idle"}</span></div>
    <div className="python-debug-tabs" role="tablist" aria-label="Debugger views">{(["variables", "stack", "breakpoints"] as const).map(value => <button type="button" role="tab" aria-selected={tab === value} key={value} onClick={() => setTab(value)}>{value === "variables" ? "Variables" : value === "stack" ? "Stack" : "Breakpoints"}</button>)}</div>
    {tab === "variables" && <div className="python-debug-contents">{frames.length > 1 && <label>Frame<select value={Math.min(frameIndex, frames.length - 1)} onChange={event => setFrameIndex(Number(event.target.value))}>{frames.map((entry, index) => <option value={index} key={index}>{entry.name} · line {entry.line}</option>)}</select></label>}{snapshot?.status !== "paused" ? <p className="python-pane-note">Variables appear when the script pauses. Click a line number to add a breakpoint, then Debug.</p> : !frame || !Object.keys(frame.locals).length ? <p className="python-pane-note">No local variables in this frame.</p> : <dl className="python-variable-list">{Object.entries(frame.locals).map(([name, value]) => <div key={name}><dt>{name}</dt><dd title={value}>{value}</dd></div>)}</dl>}</div>}
    {tab === "stack" && <div className="python-debug-contents">{snapshot?.status !== "paused" ? <p className="python-pane-note">The call stack appears while paused.</p> : frames.map((entry, index) => <button type="button" className="python-stack-frame" key={index} onClick={() => { setFrameIndex(index); onLine(entry.line, entry.filename); }}><b>{entry.name}</b><span title={entry.filename}>{entry.filename.split(/[\\/]/).pop()}:{entry.line}</span></button>)}</div>}
    {tab === "breakpoints" && <div className="python-debug-contents">{breakpoints.length ? <><button type="button" className="secondary-btn" onClick={onClear}>Clear breakpoints</button>{breakpoints.map(line => <div className="python-breakpoint-row" key={line}><button type="button" onClick={() => onLine(line)}>● Line {line}</button><button type="button" onClick={() => onRemove(line)} aria-label={`Remove breakpoint at line ${line}`}>×</button></div>)}</> : <p className="python-pane-note">No breakpoints. Click the editor gutter or press F9.</p>}</div>}
    {snapshot?.reason && <p className="python-pane-note">{snapshot.reason}</p>}
  </aside>;
}
