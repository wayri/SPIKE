// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import ScopedWorkspaceView from "./ScopedWorkspaceView";
import { connectWorkspaceViewChild } from "./workspaceViewWindows";
import type { WorkspaceViewAction, WorkspaceViewSnapshot, WorkspaceViewViewportData } from "./workspaceViewModel";
import { APP_SETTINGS_STORAGE_KEY, loadAppSettings } from "./appSettings";
import "./buttonStandard.css";
import "./WorkspaceViewTabs.css";

export default function WorkspaceViewWindowRoot({ viewId }: { viewId: string }) {
  const [snapshot, setSnapshot] = useState<WorkspaceViewSnapshot | null>(null);
  const [viewport, setViewport] = useState<WorkspaceViewViewportData | null>(null);
  const [viewportProject, setViewportProject] = useState("");
  const [connected, setConnected] = useState(true); const [error, setError] = useState("");
  const act = useRef<(action: WorkspaceViewAction) => Promise<unknown>>(async () => { throw new Error("Waiting for the owning workspace."); });
  const requestViewport = useRef<(revision: string) => Promise<WorkspaceViewViewportData>>(async () => { throw new Error("Waiting for the owning workspace."); });
  useEffect(() => {
    let disposed = false, stop: (() => void) | undefined;
    void connectWorkspaceViewChild(viewId, { onSnapshot: value => { if (!disposed) setSnapshot(value); }, onOwnerConnection: value => { if (!disposed) setConnected(value); } }).then(connection => {
      if (disposed) connection.stop(); else { stop = connection.stop; act.current = connection.act; requestViewport.current = connection.requestViewport; }
    }).catch(cause => { if (!disposed) { setConnected(false); setError(cause instanceof Error ? cause.message : String(cause)); } });
    const leaving = () => { void act.current({ type: "closed" }).catch(() => {}); };
    window.addEventListener("pagehide", leaving); return () => { disposed = true; stop?.(); window.removeEventListener("pagehide", leaving); };
  }, [viewId]);
  useEffect(() => {
    const revision = snapshot?.viewportRevision;
    if (!revision) { setViewport(null); setViewportProject(""); return; }
    if (viewport?.revision === revision && viewportProject === snapshot?.projectSession) return;
    let cancelled = false; setViewport(null);
    void requestViewport.current(revision).then(value => { if (!cancelled && value.revision === revision) { setViewport(value); setViewportProject(snapshot?.projectSession ?? ""); } }).catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { cancelled = true; };
  }, [snapshot?.projectSession, snapshot?.viewportRevision, viewport?.revision, viewportProject]);
  useEffect(() => { const sync = () => { document.documentElement.dataset.theme = loadAppSettings().theme; }; const changed = (event: StorageEvent) => { if (!event.key || event.key === APP_SETTINGS_STORAGE_KEY) sync(); }; sync(); window.addEventListener("storage", changed); return () => window.removeEventListener("storage", changed); }, []);
  const run = (action: WorkspaceViewAction) => { setError(""); void Promise.resolve().then(() => act.current(action)).catch(cause => setError(cause instanceof Error ? cause.message : String(cause))); };
  if (!snapshot) return <main className="workspace-view-window"><p role="status">Connecting to SPIKE workspace…</p>{error && <p role="alert">{error}</p>}</main>;
  return <main className="workspace-view-window"><div className="workspace-view-window-actions"><button type="button" disabled={!connected} onClick={() => run({ type: "focus-owner" })}>Show owner</button><button type="button" onClick={() => run({ type: "redock" })}>Dock back</button></div>{error && <p role="alert">{error}</p>}<ScopedWorkspaceView snapshot={snapshot} viewport={viewport} connected={connected} onAction={action => act.current(action)}/></main>;
}
