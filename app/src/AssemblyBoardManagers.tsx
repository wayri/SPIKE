// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import { Layers3, Link2, Network, Search, X } from "./icons";
import type { AssemblyDesigns, AssemblyIr } from "./mcadAssembly";
import { applyExplicitNetLink, boardOccurrences, explicitNetLinkRows, netOccurrences, removeExplicitNetLink, replaceExplicitNetLink, validateExplicitNetLink, type ExplicitNetLinkRow } from "./assemblyBoardManagerModel";
import LayerManager from "./LayerManager";
import NetCatalog from "./NetCatalog";
import { assemblyManagerPresentation, managerDefaultLayerVisible } from "./assemblyManagerPresentation";
import { buildLayerManagerInventory } from "./layerInventory";
import AssemblyConnectorLinks from "./AssemblyConnectorLinks";
import "./assemblyBoardManagers.css";

type Props = { embedded?: boolean; nativeWindow?: boolean; onDirtyChange?: (dirty: boolean) => void; assembly: AssemblyIr; designs: AssemblyDesigns; selectedBoardId?: string | null; initialTab?: "layers" | "nets" | "links"; assemblyLayerVisibility: Readonly<Record<string, Readonly<Record<string, boolean>>>>; assemblyLayerOpacity: Readonly<Record<string, Readonly<Record<string, number>>>>;
  onAssemblyLayerVisibility: (boardId: string, layerName: string, visible: boolean) => void; onAssemblyLayerOpacity: (boardId: string, layerName: string, opacity: number) => void;
  onAssemblyLayersChange?: (boardId: string, visibility: Record<string, boolean>, opacity?: Record<string, number>) => void;
  onSelectNet: (occurrenceId: string, canonicalNetId: string) => void;
  showNetNames?: boolean; onShowNetNames?: (visible: boolean) => void;
  onFocusBoard?: (boardId: string) => void;
  onUpdated: (assembly: AssemblyIr) => void; onStatus: (message: string) => void; onClose: () => void };
const blank = (): ExplicitNetLinkRow => ({ id: `connector-mate-${crypto.randomUUID()}`, endpointA: "", pinA: "", endpointB: "", pinB: "", applied: false });

export default function AssemblyBoardManagers({ embedded = false, nativeWindow = false, onDirtyChange, assembly, designs, selectedBoardId, initialTab = "layers", assemblyLayerVisibility, assemblyLayerOpacity, onAssemblyLayerVisibility, onAssemblyLayerOpacity, onAssemblyLayersChange, onSelectNet, showNetNames = false, onShowNetNames, onFocusBoard, onUpdated, onStatus, onClose }: Props) {
  const [tab, setTab] = useState<"layers" | "nets" | "links">(initialTab);
  const [boardId, setBoardId] = useState(() => boardOccurrences(assembly, designs).find(board => board.id === selectedBoardId)?.id ?? boardOccurrences(assembly, designs)[0]?.id ?? "");
  const [drafts, setDrafts] = useState<ExplicitNetLinkRow[]>([]);
  const [edits, setEdits] = useState<Record<string, ExplicitNetLinkRow>>({});
  const [netQuery, setNetQuery] = useState("");
  const [activeNetId, setActiveNetId] = useState("");
  useEffect(() => setTab(initialTab), [initialTab]);
  useEffect(() => { onDirtyChange?.(drafts.length > 0 || Object.keys(edits).length > 0); }, [drafts, edits, onDirtyChange]);
  const boards = useMemo(() => boardOccurrences(assembly, designs), [assembly, designs]);
  useEffect(() => { if (selectedBoardId && boards.some(board => board.id === selectedBoardId)) setBoardId(selectedBoardId); }, [selectedBoardId, boards]);
  useEffect(() => { if (!boards.some(board => board.id === boardId)) setBoardId(boards[0]?.id ?? ""); }, [boards, boardId]);
  const presentation = useMemo(() => assemblyManagerPresentation(assembly, designs, boardId), [assembly, designs, boardId]);
  const layerNames = useMemo(() => buildLayerManagerInventory(presentation.definitions, presentation.stackup).drawableNames, [presentation]);
  const nets = useMemo(() => netOccurrences(assembly, designs), [assembly, designs]);
  const savedLinks = useMemo(() => explicitNetLinkRows(assembly), [assembly]);
  useEffect(() => { setActiveNetId(""); setNetQuery(""); }, [boardId]);
  const boardVisibility = assemblyLayerVisibility[boardId] ?? Object.fromEntries(layerNames.map(name => [name, managerDefaultLayerVisible(name)]));
  const updateLayers = (visibility: Record<string, boolean>, opacity?: Record<string, number>) => {
    if (onAssemblyLayersChange) onAssemblyLayersChange(boardId, visibility, opacity);
    else { Object.entries(visibility).forEach(([name, value]) => onAssemblyLayerVisibility(boardId, name, value)); Object.entries(opacity ?? {}).forEach(([name, value]) => onAssemblyLayerOpacity(boardId, name, value)); }
  };
  const setLayersVisible = (names: string[], visible: boolean) => updateLayers(Object.fromEntries(names.map(name => [name, visible])));
  const filteredNets = presentation.catalog.filter(net => net.name.toLowerCase().includes(netQuery.trim().toLowerCase()));
  const selectNet = (id: string) => { const net = nets.find(net => net.boardId === boardId && net.netId === id); if (!net) return; setActiveNetId(id); onSelectNet(net.occurrenceId, net.netId); };
  const patch = (id: string, value: Partial<ExplicitNetLinkRow>) => setDrafts(items => items.map(item => item.id === id ? { ...item, ...value } : item));
  const apply = (row: ExplicitNetLinkRow) => { try { validateExplicitNetLink(assembly, designs, row); onUpdated(applyExplicitNetLink(assembly, row)); setDrafts(items => items.filter(item => item.id !== row.id)); onStatus("Applied one explicit connector pin link; matching net names elsewhere remain separate."); } catch (error) { onStatus(error instanceof Error ? error.message : "Could not apply connector link."); } };
  const save = (original: ExplicitNetLinkRow, row: ExplicitNetLinkRow) => { try { validateExplicitNetLink(assembly, designs, row); onUpdated(replaceExplicitNetLink(assembly, original, row)); setEdits(current => { const next = { ...current }; delete next[original.id]; return next; }); onStatus("Saved the explicit connector pin link."); } catch (error) { onStatus(error instanceof Error ? error.message : "Could not save connector link."); } };
  return <div className={embedded ? "assembly-manager-shade" : "modal-shade assembly-manager-shade"}><section className="assembly-board-managers" role={embedded ? "region" : "dialog"} aria-modal={embedded ? undefined : true} aria-label="Assembly board managers">
    <header><div><b>ASSEMBLY BOARD MANAGERS</b><small>Board occurrence scoped layers, nets, and explicit connector links</small></div>{!nativeWindow && <button onClick={onClose} aria-label="Close assembly board managers"><X size={17}/></button>}</header>
    <nav><button className={tab === "layers" ? "selected" : ""} onClick={() => setTab("layers")}><Layers3 size={14}/> Layers</button><button className={tab === "nets" ? "selected" : ""} onClick={() => setTab("nets")}><Network size={14}/> Nets</button><button className={tab === "links" ? "selected" : ""} onClick={() => setTab("links")}><Link2 size={14}/> Connector links</button></nav>
    {tab !== "links" && <label className="assembly-board-picker">Focused board<select value={boardId} onChange={event => { setBoardId(event.target.value); onFocusBoard?.(event.target.value); }}>{boards.map(board => <option key={board.id} value={board.id}>{board.name} · {board.id}</option>)}</select></label>}
    <div className="assembly-manager-content">
      {onShowNetNames && tab !== "links" && <label className="assembly-net-name-toggle"><input type="checkbox" checked={showNetNames} onChange={event => onShowNetNames(event.target.checked)} /> Show net names on boards</label>}
      {tab === "layers" && <LayerManager embedded showSceneControls={false} definitions={presentation.definitions} stackup={presentation.stackup}
        layers={boardVisibility} opacity={assemblyLayerOpacity[boardId] ?? {}}
        toggleLayer={name => onAssemblyLayerVisibility(boardId, name, boardVisibility[name] === false)}
        setLayersVisible={setLayersVisible} showOnlyLayer={name => updateLayers(Object.fromEntries(layerNames.map(layer => [layer, layer === name])))}
        changeOpacity={(name, value) => onAssemblyLayerOpacity(boardId, name, value)} beginOpacityChange={() => {}}
        restoreDefaults={() => updateLayers(Object.fromEntries(layerNames.map(name => [name, managerDefaultLayerVisible(name)])), Object.fromEntries(layerNames.map(name => [name, 1])))}
        onClose={onClose}/>}
      {tab === "nets" && <section className="assembly-net-manager" aria-label="Board Net Manager">
        <div className="net-manager-toolbar"><label><Search size={14}/><input value={netQuery} onChange={event => setNetQuery(event.target.value)} placeholder="Find net by name" aria-label="Find net by name"/>{netQuery && <button onClick={() => setNetQuery("")} aria-label="Clear net search"><X size={13}/></button>}</label></div>
        <div className="net-manager-body"><aside><h3>BOARD NETS</h3><div className="net-manager-guidance"><Network size={16}/><p>Select a net to highlight its copper and explicitly linked boards. Configure board circuits and connector properties in <b>Coupled studies</b>.</p></div>
          {presentation.catalog.find(net => net.id === activeNetId) && <p className="assembly-net-selected">Selected: <b>{presentation.catalog.find(net => net.id === activeNetId)!.name}</b></p>}
        </aside><NetCatalog rows={filteredNets} activeId={activeNetId} onSelect={selectNet}/></div>
        <footer><span>{presentation.catalog.length} imported nets · {filteredNets.length} shown</span></footer>
      </section>}
      {tab === "links" && <AssemblyConnectorLinks assembly={assembly} designs={designs} rows={[...savedLinks, ...drafts]} edits={edits}
        onChange={(original, value) => {
          if (!original.applied) { patch(original.id, value); return; }
          setEdits(current => {
            const next = { ...current }, row = { ...(current[original.id] ?? original), ...value };
            if (row.pinA === original.pinA && row.pinB === original.pinB) delete next[original.id]; else next[original.id] = row;
            return next;
          });
        }} onApply={apply} onSave={save} onRemove={original => { onUpdated(removeExplicitNetLink(assembly, original)); setEdits(current => { const next = { ...current }; delete next[original.id]; return next; }); }}
        onDiscard={original => { if (original.applied) setEdits(current => { const next = { ...current }; delete next[original.id]; return next; }); else setDrafts(current => current.filter(row => row.id !== original.id)); }}
        onAdd={() => setDrafts(items => [...items, blank()])}/>}
    </div>
  </section></div>;
}
