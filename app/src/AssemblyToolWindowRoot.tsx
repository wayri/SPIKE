// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import AssemblyWorkspace from "./AssemblyWorkspace";
import AssemblyHandlingBar from "./AssemblyHandlingBar";
import AssemblyBoardManagers from "./AssemblyBoardManagers";
import { connectAssemblyToolChild, onAssemblyToolCloseRequest } from "./assemblyToolWindows";
import type { AssemblyToolAction, AssemblyToolKind, AssemblyToolSnapshot, AssemblyToolViewportData } from "./assemblyToolWindowModel";
import { APP_SETTINGS_STORAGE_KEY, loadAppSettings } from "./appSettings";
import "./assemblyToolWindows.css";

export default function AssemblyToolWindowRoot({ kind }: { kind: AssemblyToolKind }) {
  const nativeWindow = "__TAURI_INTERNALS__" in window;
  const [snapshot, setSnapshot] = useState<AssemblyToolSnapshot | null>(null);
  const [viewport, setViewport] = useState<AssemblyToolViewportData | null>(null);
  const [error, setError] = useState(""); const [status, setStatus] = useState("");
  const [closeRequested, setCloseRequested] = useState(0); const [managerCloseWarning, setManagerCloseWarning] = useState(false);
  const dirty = useRef(false); const actRef = useRef<(action: AssemblyToolAction) => Promise<unknown>>(async () => { throw new Error("Waiting for SPIKE workspace."); });
  const requestViewportRef = useRef<(revision: string) => Promise<AssemblyToolViewportData>>(async () => { throw new Error("Waiting for SPIKE workspace."); });
  useEffect(() => {
    let disposed = false; let stop: (() => void) | undefined;
    void connectAssemblyToolChild(kind, value => { if (!disposed) setSnapshot(value); }).then(connection => {
      if (disposed) connection.stop(); else { stop = connection.stop; actRef.current = connection.act; requestViewportRef.current = connection.requestViewport; }
    }).catch(error => { if (!disposed) setError(String(error)); });
    const unload = () => { void actRef.current({ type: "closed" }).catch(() => {}); };
    window.addEventListener("pagehide", unload);
    return () => { disposed = true; stop?.(); window.removeEventListener("pagehide", unload); };
  }, [kind]);
  useEffect(() => {
    const revision = kind === "workspace" ? snapshot?.viewportRevision : null;
    if (!revision || viewport?.revision === revision) return;
    let cancelled = false;
    setViewport(null);
    void requestViewportRef.current(revision).then(value => { if (!cancelled && value.revision === revision) setViewport(value); })
      .catch(error => { if (!cancelled) setError(error instanceof Error ? error.message : String(error)); });
    return () => { cancelled = true; };
  }, [kind, snapshot?.viewportRevision, viewport?.revision]);
  useEffect(() => {
    const sync = () => { document.documentElement.dataset.theme = loadAppSettings().theme; };
    const changed = (event: StorageEvent) => { if (!event.key || event.key === APP_SETTINGS_STORAGE_KEY) sync(); };
    sync(); window.addEventListener("storage", changed); return () => window.removeEventListener("storage", changed);
  }, []);
  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) {
      const protectDraft = (event: BeforeUnloadEvent) => { if (dirty.current) { event.preventDefault(); event.returnValue = ""; } };
      window.addEventListener("beforeunload", protectDraft);
      return () => window.removeEventListener("beforeunload", protectDraft);
    }
    let disposed = false, stop: (() => void) | undefined;
    void onAssemblyToolCloseRequest(prevent => {
        if (!dirty.current) return;
        prevent();
        if (kind === "workspace") setCloseRequested(value => value + 1);
        else setManagerCloseWarning(true);
    }).then(unlisten => {
      if (disposed) unlisten(); else stop = unlisten;
    }).catch(error => setError(String(error)));
    return () => { disposed = true; stop?.(); };
  }, [kind]);
  const request = async (action: AssemblyToolAction) => { setError(""); return actRef.current(action); };
  const act = (action: AssemblyToolAction) => { void request(action).catch(error => setError(error instanceof Error ? error.message : String(error))); };
  const close = () => act({ type: "close" });
  const report = (message: string) => { setStatus(message); act({ type: "status", value: message.slice(0, 2000) }); };
  const reportDirty = (value: boolean) => { if (dirty.current === value) return; dirty.current = value; act({ type: "draft-dirty", value }); };
  if (!snapshot) return <main className="assembly-tool-root"><p role="status">Connecting to SPIKE workspace…</p>{error && <p role="alert">{error}</p>}</main>;
  const s = snapshot;
  const locked = Boolean(s.draftOwner && s.draftOwner !== kind);
  return <main className={`assembly-tool-root assembly-tool-${kind}${nativeWindow ? " assembly-tool-native" : ""}`}>
    {error && <div className="assembly-tool-error" role="alert">{error}</div>}
    {locked && <div className="assembly-tool-error" role="status">Finish or discard edits in the assembly {s.draftOwner} window before editing here.</div>}
    {managerCloseWarning && <div className="assembly-tool-error" role="alert">Unsaved connector rows will be lost.<button onClick={() => setManagerCloseWarning(false)}>Keep editing</button><button onClick={close}>Discard draft and close</button></div>}
    {kind === "workspace" ? <AssemblyWorkspace thermalStudyRequest={s.thermalStudyRequest} embedded nativeWindow={nativeWindow} assembly={s.assembly} designs={s.designs} visuals={s.visuals} diagnostics={s.diagnostics} viewport={viewport}
      projectPath={s.projectPath} manifestDigest={s.manifestDigest} projectDirty={s.projectDirty} desktop={s.desktop} boardAvailable={s.boardAvailable} editingLocked={locked}
      closeRequested={closeRequested} onDirtyChange={reportDirty}
      onSave={async () => Boolean(await request({ type: "save" }))} onUpdated={async () => { await request({ type: "reload" }); }} onStatus={report} onClose={close}
      selectedBoardId={s.selectedBoardId} onSelectBoard={boardId => act({ type: "select-board", boardId })}
      visibility={s.visibility} layerVisibility={s.layerVisibility} layerOpacity={s.layerOpacity} layerFocus={s.layerFocus} linkedNets={s.linkedNets} explodedDistanceMm={s.explodedDistanceMm}
      moveMode={s.moveMode} snapMode={s.snapMode} snapGapMm={s.snapGapMm} snapSourceLabel={s.snapSourceLabel}
      onVisibility={(boardId, value) => act({ type: "visibility", boardId, value })}
      onPlacement={(boardId, transform) => act({ type: "placement", boardId, transform })}
      onMoveMode={mode => act({ type: "move-mode", mode })} onExplodedDistance={value => act({ type: "explode", value })}
      onSnapMode={mode => act({ type: "snap-mode", mode })} onSnapGapChange={value => act({ type: "snap-gap", value })}
      onLayerFocus={(boardId, layer) => act({ type: "layer-focus", boardId, value: layer })}
      onSnapTarget={target => act({ type: "snap-target", boardId: target.occurrenceId, value: target.id })}
      onSelectNet={(boardId, netId) => act({ type: "select-net", boardId, netId })}
      onViewBoard={(boardId, mode) => act({ type: "view", boardId, mode })} onManager={(boardId, mode) => act({ type: "manager", boardId, mode })}
      onOpenCollaboration={mode => act({ type: "collaboration", mode })}/> : <>
      {!nativeWindow && <header className="assembly-tool-heading"><div><small>SPIKE ASSEMBLY</small><h1>{kind === "placement" ? "Board placement" : "Board layers, nets & links"}</h1></div><button onClick={() => { if (dirty.current) setManagerCloseWarning(true); else close(); }}>Close tool</button></header>}
      <fieldset className="assembly-tool-edit-scope" disabled={locked}>{s.assembly && s.designs ? kind === "placement" ? <>
        <AssemblyHandlingBar assembly={s.assembly} designs={s.designs} selectedBoardId={s.selectedBoardId} visibility={s.visibility} explodedDistanceMm={s.explodedDistanceMm}
          snapMode={s.snapMode} snapGapMm={s.snapGapMm} snapSourceLabel={s.snapSourceLabel}
          onSelectBoard={boardId => act({ type: "select-board", boardId })} onVisibility={(boardId, value) => act({ type: "visibility", boardId, value })}
          onPlacement={(boardId, transform) => act({ type: "placement", boardId, transform })} onMoveMode={mode => act({ type: "move-mode", mode })}
          onExplodedDistance={value => act({ type: "explode", value })} onSnapMode={mode => act({ type: "snap-mode", mode })} onSnapGapChange={value => act({ type: "snap-gap", value })}/>
        <p className="assembly-tool-hint">Choose Move or Rotate, then click a viewport arrow or ring. Type a signed distance in mm or angle in degrees; Enter applies, Escape cancels.</p>
        <section className="assembly-tool-options"><label><input type="checkbox" checked={s.passThroughHighlight} onChange={event => act({ type: "pass-through", value: event.target.checked })}/> Pass through components (exclude ground)</label><button onClick={() => act({ type: "export-diagram" })}>Export diagram PNG</button><button onClick={() => act({ type: "load-overlay" })}>Load result overlay</button></section>
        {s.overlayMessages.map((message, index) => <p className="assembly-tool-hint" key={index}>{message}</p>)}
      </> : <AssemblyBoardManagers embedded nativeWindow={nativeWindow} assembly={s.assembly} designs={s.designs} selectedBoardId={s.selectedBoardId} initialTab={s.managerTab}
        showNetNames={s.showNetNames === true} onShowNetNames={value => act({type:"net-names",value})}
        onFocusBoard={boardId => act({ type: "select-board", boardId })}
        assemblyLayerVisibility={s.layerVisibility} assemblyLayerOpacity={s.layerOpacity} onDirtyChange={reportDirty}
        onAssemblyLayerVisibility={(boardId, layer, value) => act({ type: "layer-visibility", boardId, layer, value })}
        onAssemblyLayerOpacity={(boardId, layer, value) => act({ type: "layer-opacity", boardId, layer, value })}
        onAssemblyLayersChange={(boardId, layerVisibility, layerOpacity) => act({ type: "layer-state", boardId, layerVisibility, layerOpacity })}
        onSelectNet={(occurrence, netId) => act({ type: "select-net", boardId: occurrence.split("::")[0], netId })}
        onUpdated={assembly => act({ type: "update-assembly", assembly })} onStatus={report} onClose={() => { if (dirty.current) setManagerCloseWarning(true); else close(); }}/>
        : <p>Open a retained multiboard assembly in the main workspace.</p>}</fieldset>
    </>}
    {status && <footer className="assembly-tool-status" role="status">{status}</footer>}
  </main>;
}
