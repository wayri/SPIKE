// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";
import AssemblyBoardManagers from "./AssemblyBoardManagers";
import AssemblyHandlingBar from "./AssemblyHandlingBar";
import AssemblyWorkspace from "./AssemblyWorkspace";
import type {
  AssemblyToolAction,
  AssemblyToolKind,
  AssemblyToolSnapshot,
  AssemblyToolViewportData,
} from "./assemblyToolWindowModel";
import "./assemblyFocus.css";

export type EmbeddedAssemblyToolProps = {
  kind: AssemblyToolKind;
  snapshot: AssemblyToolSnapshot;
  viewportData?: AssemblyToolViewportData;
  onAction: (action: AssemblyToolAction) => unknown | Promise<unknown>;
  onClose: () => void;
};

/** Renders the retained assembly tools inside SPIKE Focus without a native-window bridge. */
export default function EmbeddedAssemblyTool({ kind, snapshot: s, viewportData, onAction, onClose }: EmbeddedAssemblyToolProps) {
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [managerCloseWarning, setManagerCloseWarning] = useState(false);
  const dirty = useRef(false);

  const request = async (action: AssemblyToolAction) => {
    setError("");
    if (action.type === "close" || action.type === "closed") {
      onClose();
      return;
    }
    return onAction(action);
  };
  const act = (action: AssemblyToolAction) => {
    void request(action).catch(cause => setError(cause instanceof Error ? cause.message : String(cause)));
  };
  const close = () => act({ type: "close" });
  const requestManagerClose = () => {
    if (dirty.current) setManagerCloseWarning(true);
    else close();
  };
  const report = (message: string) => {
    setStatus(message);
    act({ type: "status", value: message.slice(0, 2000) });
  };
  const reportDirty = (value: boolean) => {
    if (dirty.current === value) return;
    dirty.current = value;
    act({ type: "draft-dirty", value });
  };
  const locked = Boolean(s.draftOwner && s.draftOwner !== kind);

  return <section className={`spike-focus-assembly spike-focus-assembly--${kind}`} aria-label={kind === "workspace" ? "Multi-board assembly workspace" : kind === "placement" ? "Board placement" : "Assembly board managers"}>
    {error && <div className="spike-focus-assembly-alert" role="alert">{error}</div>}
    {locked && <div className="spike-focus-assembly-alert" role="status">Finish or discard edits in the assembly {s.draftOwner} tool before editing here.</div>}
    {managerCloseWarning && <div className="spike-focus-assembly-alert spike-focus-assembly-close-warning" role="alert">
      <span>Unsaved connector rows will be lost.</span>
      <button type="button" onClick={() => setManagerCloseWarning(false)}>Keep editing</button>
      <button type="button" className="spike-control--danger" onClick={close}>Discard draft and close</button>
    </div>}

    {kind === "workspace" ? <AssemblyWorkspace
      thermalStudyRequest={s.thermalStudyRequest} embedded nativeWindow={false}
      assembly={s.assembly} designs={s.designs} visuals={s.visuals} diagnostics={s.diagnostics} viewport={viewportData ?? null}
      projectPath={s.projectPath} manifestDigest={s.manifestDigest} projectDirty={s.projectDirty} desktop={s.desktop} boardAvailable={s.boardAvailable} editingLocked={locked}
      closeRequested={0} onDirtyChange={reportDirty}
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
      onOpenCollaboration={mode => act({ type: "collaboration", mode })}
    /> : kind === "placement" ? <>
      <header className="spike-focus-assembly-heading"><div><small>SPIKE ASSEMBLY</small><h2>Board placement</h2></div><button type="button" onClick={close}>Close tool</button></header>
      <fieldset className="spike-focus-assembly-edit-scope" disabled={locked}>{s.assembly && s.designs ? <>
        <AssemblyHandlingBar assembly={s.assembly} designs={s.designs} selectedBoardId={s.selectedBoardId} visibility={s.visibility} explodedDistanceMm={s.explodedDistanceMm}
          snapMode={s.snapMode} snapGapMm={s.snapGapMm} snapSourceLabel={s.snapSourceLabel}
          onSelectBoard={boardId => act({ type: "select-board", boardId })} onVisibility={(boardId, value) => act({ type: "visibility", boardId, value })}
          onPlacement={(boardId, transform) => act({ type: "placement", boardId, transform })} onMoveMode={mode => act({ type: "move-mode", mode })}
          onExplodedDistance={value => act({ type: "explode", value })} onSnapMode={mode => act({ type: "snap-mode", mode })} onSnapGapChange={value => act({ type: "snap-gap", value })}/>
        <p className="spike-focus-assembly-hint">Choose Move or Rotate, then click a viewport arrow or ring. Type a signed distance in mm or angle in degrees; Enter applies, Escape cancels.</p>
        <div className="spike-focus-assembly-options"><label><input type="checkbox" checked={s.passThroughHighlight} onChange={event => act({ type: "pass-through", value: event.target.checked })}/> Pass through components (exclude ground)</label><button type="button" onClick={() => act({ type: "export-diagram" })}>Export diagram PNG</button><button type="button" onClick={() => act({ type: "load-overlay" })}>Load result overlay</button></div>
        {s.overlayMessages.map((message, index) => <p className="spike-focus-assembly-hint" key={`${index}-${message}`}>{message}</p>)}
      </> : <p>Open a retained multiboard assembly in the main workspace.</p>}</fieldset>
    </> : <fieldset className="spike-focus-assembly-edit-scope" disabled={locked}>{s.assembly && s.designs ? <AssemblyBoardManagers
      embedded nativeWindow={false} assembly={s.assembly} designs={s.designs} selectedBoardId={s.selectedBoardId} initialTab={s.managerTab}
      showNetNames={s.showNetNames === true} onShowNetNames={value => act({ type: "net-names", value })}
      onFocusBoard={boardId => act({ type: "select-board", boardId })} assemblyLayerVisibility={s.layerVisibility} assemblyLayerOpacity={s.layerOpacity} onDirtyChange={reportDirty}
      onAssemblyLayerVisibility={(boardId, layer, value) => act({ type: "layer-visibility", boardId, layer, value })}
      onAssemblyLayerOpacity={(boardId, layer, value) => act({ type: "layer-opacity", boardId, layer, value })}
      onAssemblyLayersChange={(boardId, layerVisibility, layerOpacity) => act({ type: "layer-state", boardId, layerVisibility, layerOpacity })}
      onSelectNet={(occurrence, netId) => act({ type: "select-net", boardId: occurrence.split("::")[0], netId })}
      onUpdated={assembly => act({ type: "update-assembly", assembly })} onStatus={report} onClose={requestManagerClose}
    /> : <p>Open a retained multiboard assembly in the main workspace.</p>}</fieldset>}
    {status && <footer className="spike-focus-assembly-status" role="status">{status}</footer>}
  </section>;
}
