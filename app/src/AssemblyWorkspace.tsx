// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { Boxes, Cable, CircuitBoard, Layers3, Network, RefreshCw, Save, Search, X } from "./icons";
import AssemblyStructureEditor from "./AssemblyStructureEditor";
import AssemblyHandlingBar from "./AssemblyHandlingBar";
import AssemblyWorkspaceViewport from "./AssemblyWorkspaceViewport";
import { boardOccurrences } from "./assemblyBoardManagerModel";
import type { AssemblyDesigns, AssemblyIr } from "./mcadAssembly";
import type { AssemblySnapTarget } from "./assemblySnapTargets";
import type { AssemblyToolViewportData } from "./assemblyToolWindowModel";
import "./assemblyWorkspace.css";

const EMPTY: AssemblyIr = { contract: "spike/assembly-ir/v1", assembly_id: "assembly", name: "Assembly", boards: [], parts: [] };
const itemCount = (value: unknown) => Array.isArray(value) ? value.length : 0;
type Props = { assembly: AssemblyIr | null; designs: AssemblyDesigns | null; visuals: Record<string, { boardModelUrl?: string; componentModelUrl?: string }>; diagnostics: Record<string, string>; viewport?: AssemblyToolViewportData | null;
  projectPath: string | null; manifestDigest: string | null; projectDirty: boolean; desktop: boolean; boardAvailable: boolean; editingLocked?: boolean;
  onSave: () => Promise<boolean>; onUpdated: () => Promise<void>; onStatus: (message: string) => void; onClose: () => void;
  selectedBoardId?: string | null; onSelectBoard: (boardId: string) => void;
  onViewBoard: (boardId: string, mode: "2D" | "3D") => void; onManager: (boardId: string, kind: "layers" | "nets" | "links") => void;
  onOpenCollaboration: (mode: "freecad" | "attachments") => void;
  visibility?: Record<string, boolean>; layerVisibility?: Record<string, Record<string, boolean>>; layerOpacity?: Record<string, Record<string, number>>; layerFocus?: Record<string, string>; linkedNets?: Record<string, string[]>;
  explodedDistanceMm?: number; moveMode?: "translate" | "rotate" | null; snapMode?: "off" | "hole" | "edge"; snapGapMm?: number; snapSourceLabel?: string;
  onVisibility?: (boardId: string, value: boolean) => void; onPlacement?: (boardId: string, transform: number[]) => void;
  onMoveMode?: (mode: "translate" | "rotate") => void; onExplodedDistance?: (value: number) => void;
  onSnapMode?: (mode: "off" | "hole" | "edge") => void; onSnapGapChange?: (value: number) => void; onSnapTarget?: (target: AssemblySnapTarget) => void;
  onLayerFocus?: (boardId: string, layer: string) => void;
  onSelectNet?: (boardId: string, netId: string) => void;
  thermalStudyRequest?: string | null; embedded?: boolean; nativeWindow?: boolean; closeRequested?: number; onDirtyChange?: (dirty: boolean) => void };

export default function AssemblyWorkspace(props: Props) {
  const [section, setSection] = useState<"boards" | "placement" | "links" | "analysis" | undefined>(undefined);
  useEffect(() => { if (props.thermalStudyRequest) setSection("analysis"); }, [props.thermalStudyRequest]);
  const [boardQuery, setBoardQuery] = useState("");
  const [draftDirty, setDraftDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [closeWarning, setCloseWarning] = useState(false);
  const [error, setError] = useState("");
  const closeRequest = useRef(props.closeRequested);
  const boards = props.assembly && props.designs ? boardOccurrences(props.assembly, props.designs) : [];
  const boardNameCounts = new Map<string, number>();
  for (const board of boards) boardNameCounts.set(board.name.toLocaleLowerCase(), (boardNameCounts.get(board.name.toLocaleLowerCase()) ?? 0) + 1);
  const boardNameSeen = new Map<string, number>();
  const namedBoards = boards.map(board => {
    const key = board.name.toLocaleLowerCase(), ordinal = (boardNameSeen.get(key) ?? 0) + 1;
    boardNameSeen.set(key, ordinal);
    return { ...board, label: (boardNameCounts.get(key) ?? 0) > 1 ? `${board.name} (${ordinal})` : board.name };
  });
  const filteredBoards = namedBoards.filter(board => board.label.toLocaleLowerCase().includes(boardQuery.trim().toLocaleLowerCase()));
  const selectedBoard = namedBoards.find(board => board.id === props.selectedBoardId) ?? null;
  const visibility = props.visibility ?? {};
  const layerVisibility = props.layerVisibility ?? {};
  const layerOpacity = props.layerOpacity ?? {};
  // Once retained designs are open, ordinary placement/layer edits make the
  // project dirty and must remain visible so the user can review and save them.
  // A dirty project blocks only the initial package hydration path.
  const ready = props.desktop && Boolean(props.projectPath && props.manifestDigest) && (Boolean(props.designs) || !props.projectDirty);
  const hydrated = useRef("");
  useEffect(() => {
    if (!ready || props.designs) return;
    const key = `${props.projectPath}:${props.manifestDigest}`;
    if (hydrated.current === key) return;
    hydrated.current = key; setBusy(true);
    void props.onUpdated().catch(error => setError(error instanceof Error ? error.message : String(error))).finally(() => setBusy(false));
  }, [ready, props.designs, props.projectPath, props.manifestDigest]);
  useEffect(() => {
    if (props.closeRequested === undefined || props.closeRequested === closeRequest.current) return;
    closeRequest.current = props.closeRequested;
    if (draftDirty) setCloseWarning(true);
    else props.onClose();
  }, [draftDirty, props.closeRequested, props.onClose]);
  const navigate = (action: () => void) => { if (draftDirty) { setError("Save boards and links before leaving this editor. Your draft is still open."); return; } action(); };
  const save = async () => {
    setBusy(true); setError("");
    try { await props.onSave(); }
    catch (error) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  };
  const reload = async () => {
    if (draftDirty) { setError("Save boards and links before reloading the project package. Your draft is still open."); return; }
    setBusy(true); setError("");
    try { await props.onUpdated(); }
    catch (error) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  };
  const handleDirtyChange = (dirty: boolean) => { setDraftDirty(dirty); props.onDirtyChange?.(dirty); };
  return <div className={props.embedded ? "assembly-workspace-host assembly-workspace-host--embedded" : "modal-shade assembly-workspace-shade"}><section className="assembly-workspace" role={props.embedded ? "region" : "dialog"} aria-modal={props.embedded ? undefined : true} aria-label="Multi-board workspace">
    <header><div><small>ECAD–MCAD ASSEMBLY</small><h2>Multi-board assembly workspace</h2><p>Inspect the retained layout, place board occurrences and manage the focused board.</p>{props.embedded && props.nativeWindow && <p className="assembly-workspace-window-hint">This movable native window renders the same retained board sources as the main viewport.</p>}</div>{!props.nativeWindow && <button type="button" className="spike-control--icon" aria-label="Close multi-board workspace" onClick={() => draftDirty ? setCloseWarning(true) : props.onClose()}><X size={18}/></button>}</header>
    {closeWarning && <div className="assembly-workspace-warning" role="alert">Unsaved board/link edits are still in this editor.<button type="button" onClick={() => setCloseWarning(false)}>Keep editing</button><button type="button" onClick={props.onClose}>Discard draft and close</button></div>}
    <div className="assembly-workspace-summary"><b>{boards.length} board occurrences</b><span>{props.designs?.designs.length ?? 0} retained designs</span><span>{props.assembly?.parts.length ?? 0} mechanical parts</span><span>{props.assembly?.harnesses?.length ?? 0} harnesses</span><span>{props.assembly?.connector_mappings?.filter(item => item.kind === "connector-mate").length ?? 0} connector mates</span></div>
    <div className="assembly-workspace-commandbar" role="toolbar" aria-label="Assembly workspace commands">
      <div className="assembly-command-group" aria-label="Project package"><button type="button" disabled={!ready || busy || draftDirty || props.editingLocked} onClick={() => void save()}><Save size={14}/> Save project</button><button type="button" disabled={!ready || busy || props.editingLocked} onClick={() => void reload()}><RefreshCw size={14}/> Reload package</button><button type="button" disabled={!ready || busy} onClick={() => navigate(() => setSection("analysis"))}><Network size={14}/> Studies &amp; results</button></div>
      <div className="assembly-command-group assembly-command-board" aria-label="Focused board commands"><label><span>Focused board</span><select aria-label="Focused board occurrence" value={selectedBoard?.id ?? ""} onChange={event => event.target.value && props.onSelectBoard(event.target.value)}><option value="">Select a board</option>{namedBoards.map(board => <option key={board.id} value={board.id}>{board.label}</option>)}</select></label><button type="button" className="assembly-workspace-layer-action" disabled={!selectedBoard} onClick={() => selectedBoard && navigate(() => props.onManager(selectedBoard.id, "layers"))}><Layers3 size={14}/> Layers</button><button type="button" disabled={!selectedBoard} onClick={() => selectedBoard && navigate(() => props.onManager(selectedBoard.id, "nets"))}><Network size={14}/> Nets</button><button type="button" disabled={!selectedBoard} onClick={() => selectedBoard && navigate(() => props.onManager(selectedBoard.id, "links"))}><Cable size={14}/> Links</button><button type="button" disabled={!selectedBoard} onClick={() => selectedBoard && props.onViewBoard(selectedBoard.id, "2D")}>Main 2D</button><button type="button" disabled={!selectedBoard} onClick={() => selectedBoard && props.onViewBoard(selectedBoard.id, "3D")}>Main 3D</button></div>
      <div className="assembly-command-group" aria-label="Mechanical collaboration"><button type="button" disabled={!ready || draftDirty} onClick={() => props.onOpenCollaboration("freecad")}><Boxes size={14}/> FreeCAD collaboration</button><button type="button" disabled={!ready || draftDirty} onClick={() => props.onOpenCollaboration("attachments")}><Boxes size={14}/> MCAD attachments</button></div>
    </div>
    {error && <p role="alert" className="assembly-workspace-warning">{error}</p>}
    <div className="assembly-workspace-content">
      {!ready ? <section className="assembly-workspace-start"><h3>{props.desktop ? "Save the current board to start an assembly" : "Open SPIKE desktop for native assembly import"}</h3><p>{props.projectDirty ? "Save your current project changes before editing its retained assembly records." : "The .spike project retains each source design, board occurrence, connector mapping and setup."}</p><button type="button" disabled={busy || !props.desktop || !props.boardAvailable} onClick={() => void save()}><Save size={15}/>{busy ? "Saving project…" : "Save project and continue"}</button>{!props.boardAvailable && <p>Import a PCB first using Home → Import.</p>}</section> : <>
        {props.assembly && props.designs && <div className="assembly-workspace-visual-shell">
          <AssemblyWorkspaceViewport assembly={props.assembly} designs={props.designs} viewport={props.viewport ?? null}
            selectedBoardId={props.selectedBoardId ?? null} visibility={visibility} layerVisibility={layerVisibility} layerOpacity={layerOpacity} layerFocus={props.layerFocus ?? {}} linkedNets={props.linkedNets ?? {}}
            explodedDistanceMm={props.explodedDistanceMm ?? 0} moveMode={props.editingLocked ? null : props.moveMode ?? null} snapMode={props.editingLocked ? "off" : props.snapMode ?? "off"}
            onSelectBoard={props.onSelectBoard} onSelectNet={(boardId, netId) => props.onSelectNet?.(boardId, netId)}
            onPlacement={(boardId, transform) => { if (!props.editingLocked) props.onPlacement?.(boardId, transform); }} onLayerFocus={(boardId, layer) => props.onLayerFocus?.(boardId, layer)} onSnapTarget={target => { if (!props.editingLocked) props.onSnapTarget?.(target); }}/>
          <fieldset className="assembly-workspace-handling-scope" disabled={props.editingLocked}><AssemblyHandlingBar assembly={props.assembly} designs={props.designs} selectedBoardId={props.selectedBoardId ?? null} visibility={visibility}
            explodedDistanceMm={props.explodedDistanceMm ?? 0} snapMode={props.snapMode ?? "off"} snapGapMm={props.snapGapMm ?? 0} snapSourceLabel={props.snapSourceLabel}
            onSelectBoard={props.onSelectBoard} onVisibility={(boardId, value) => props.onVisibility?.(boardId, value)}
            onPlacement={(boardId, transform) => props.onPlacement?.(boardId, transform)} onMoveMode={mode => props.onMoveMode?.(mode)}
            onExplodedDistance={value => props.onExplodedDistance?.(value)} onSnapMode={mode => props.onSnapMode?.(mode)} onSnapGapChange={value => props.onSnapGapChange?.(value)}/></fieldset>
        </div>}
        <section className="assembly-workspace-inventory-shell" aria-labelledby="assembly-board-inventory-title"><div className="assembly-workspace-inventory-heading"><div><small>BOARDS & ORGANIZATION</small><h3 id="assembly-board-inventory-title">Board inventory</h3><p>Select an occurrence to scope viewport and manager commands.</p></div><label className="assembly-workspace-search"><Search size={14}/><input type="search" value={boardQuery} onChange={event => setBoardQuery(event.target.value)} placeholder="Find board by name" aria-label="Find board by name"/></label></div>
        <div className="assembly-workspace-inventory" aria-label="Retained board occurrences">{filteredBoards.map(board => {
          const visual = props.visuals[board.designId];
          const design = props.designs?.designs.find(item => item.design_id === board.designId);
          const selected = board.id === props.selectedBoardId;
          return <article key={board.id} className={selected ? "selected" : ""}><button type="button" className="assembly-workspace-board-select" aria-pressed={selected} onClick={() => props.onSelectBoard(board.id)}><span><h4 title={board.label}>{board.label}</h4><small>{selected ? "Focused board occurrence" : "Focus board occurrence"}</small></span><CircuitBoard size={18}/></button><dl><div><dt>Components</dt><dd>{itemCount(design?.components)}</dd></div><div><dt>Nets</dt><dd>{itemCount(design?.nets)}</dd></div><div><dt>Layers</dt><dd>{itemCount(design?.layers)}</dd></div></dl><p className="assembly-workspace-graphics">{visual?.boardModelUrl ? "Board graphics ready" : visual ? "Board source ready; 3D graphics preparing" : "Preparing retained board source"}{visual?.componentModelUrl ? " · Component graphics ready" : ""}</p>{props.diagnostics[board.designId] && <p className="assembly-workspace-diagnostic">{props.diagnostics[board.designId]}</p>}<div className="assembly-workspace-board-actions"><button type="button" className="assembly-workspace-layer-action" onClick={() => navigate(() => props.onManager(board.id, "layers"))}><Layers3 size={14}/> Layers for focused board</button><button type="button" onClick={() => props.embedded ? props.onViewBoard(board.id, "2D") : navigate(() => props.onViewBoard(board.id, "2D"))}>2D layout</button><button type="button" onClick={() => props.embedded ? props.onViewBoard(board.id, "3D") : navigate(() => props.onViewBoard(board.id, "3D"))}>3D placement</button><button type="button" onClick={() => navigate(() => props.onManager(board.id, "nets"))}><Network size={14}/> Nets</button><button type="button" onClick={() => navigate(() => props.onManager(board.id, "links"))}><Cable size={14}/> Pin links</button></div></article>;
        })}{!boards.length && <p>Load the saved board records, then add a duplicate or import another board.</p>}{boards.length > 0 && !filteredBoards.length && <p>No board names match this filter.</p>}</div></section>
        {!props.designs && <button type="button" onClick={() => void props.onUpdated().catch(error => setError(String(error)))}>Load saved board records</button>}
        <section className="assembly-workspace-editor-shell" aria-label="Assembly definition tools">
          <div className="assembly-workspace-editor-heading"><div><small>DEFINITION TOOLS</small><h3>Structure, links and bounded studies</h3></div><nav aria-label="Assembly workflow"><button className={!section || section === "boards" ? "selected" : ""} aria-pressed={!section || section === "boards"} onClick={() => setSection("boards")}><CircuitBoard size={15}/> Boards</button><button className={section === "placement" ? "selected" : ""} aria-pressed={section === "placement"} onClick={() => setSection("placement")}><Boxes size={15}/> Mechanics</button><button className={section === "links" ? "selected" : ""} aria-pressed={section === "links"} onClick={() => setSection("links")}><Cable size={15}/> Links & harnesses</button><button className={section === "analysis" ? "selected" : ""} aria-pressed={section === "analysis"} onClick={() => setSection("analysis")}><Network size={15}/> Coupled studies</button></nav></div>
          <p className="assembly-workspace-note">The focused board scopes layers and nets. Equal net names on separate boards remain independent until a saved connector or harness mapping links them. Coupled studies use bounded reduced models; full-wave assembly EM remains unsupported.</p>
          <fieldset className="assembly-workspace-definition-scope" disabled={props.editingLocked}><AssemblyStructureEditor projectPath={props.projectPath} projectManifestDigest={props.manifestDigest} assemblyIr={props.assembly ?? EMPTY} assemblyDesigns={props.designs} focusSection={section === "placement" ? "boards" : section} onDirtyChange={handleDirtyChange} onUpdated={props.onUpdated} onStatus={props.onStatus}/></fieldset>
        </section>
      </>}
    </div>
  </section></div>;
}
