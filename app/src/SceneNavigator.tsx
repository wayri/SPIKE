import { useDeferredValue, useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity, Boxes, Cable, ChartArea, ChevronDown, CircuitBoard, Component,
  Crosshair, Fan, Layers3, MapPin, Microchip, Network, PackageOpen, RadioTower, Route,
  Search, Spline, ThermometerSun, Workflow, X,
} from "lucide-react";
import { boundedMatches, firstObjectByNet, sceneRowWindow } from "./viewportPerformance";
import type { BoardObject } from "./BoardViewport";
import type { ParsedBoard } from "./boardParser";
import { asThermalScenario } from "./thermalScene";
import { assemblyHierarchyRows, createAssemblyFrameResolver, partDisplayStatus } from "./mcadAssembly";
import type { AssemblyHierarchyRow, AssemblyIr, AssemblyPartViewportStates, ModelIndex } from "./mcadAssembly";

export type SceneNavigatorAction =
  | "board"
  | "assembly"
  | "stackup"
  | "layers"
  | "nets"
  | "components"
  | "models"
  | "mcad"
  | "bonds"
  | "thermal"
  | "probes"
  | "power-paths"
  | "results";

type Props = {
  board: ParsedBoard | null;
  boardName: string;
  query: string;
  onQuery: (query: string) => void;
  probes: BoardObject[];
  modelAssignments: Record<string, string>;
  assemblyIr: AssemblyIr | null;
  modelIndex: ModelIndex;
  assemblyPartViewportStates: AssemblyPartViewportStates;
  bondCount: number;
  sourceCount: number;
  powerPathCount: number;
  resultCount: number;
  thermalScenario: Record<string, unknown> | null;
  importQuality: number;
  onSelect: (object: BoardObject) => void;
  onAssemblyPart: (partId: string) => void;
  onAction: (action: SceneNavigatorAction) => void;
};

type SearchEntry = {
  id: string;
  label: string;
  detail: string;
  category: string;
  keywords: string;
  searchText?: string;
  icon: LucideIcon;
  object?: BoardObject;
  action?: SceneNavigatorAction;
  assemblyPartId?: string;
};

type SummaryRow = {
  id?: string;
  label: string;
  detail: string;
  count?: number;
  icon: LucideIcon;
  action?: SceneNavigatorAction;
};

function SummarySection({ title, badge, rows, onAction }: { title: string; badge?: string; rows: SummaryRow[]; onAction: (action: SceneNavigatorAction) => void }) {
  return <details className="scene-nav-section" open>
    <summary><ChevronDown size={12} /><span>{title}</span>{badge && <em>{badge}</em>}</summary>
    <div>{rows.map(({ id, label, detail, count, icon: Icon, action }) => <button key={id ?? label} disabled={!action} onClick={() => action && onAction(action)} title={detail}>
      <Icon size={14} />
      <span><b>{label}</b><small>{detail}</small></span>
      {count !== undefined && <em>{count.toLocaleString()}</em>}
    </button>)}</div>
  </details>;
}

function AssemblyHierarchySection({ rows, onAssemblyPart, onAction }: { rows: AssemblyHierarchyRow[]; onAssemblyPart: (partId: string) => void; onAction: (action: SceneNavigatorAction) => void }) {
  const [scrollTop, setScrollTop] = useState(0);
  const virtual = rows.length > 120;
  const window = virtual ? sceneRowWindow(rows.length, scrollTop) : { start: 0, end: rows.length, before: 0, after: 0 };
  return <details className="scene-nav-section assembly-hierarchy-section" open>
    <summary><ChevronDown size={12} /><span>Assembly hierarchy</span><em>{Math.max(rows.length - 1, 0)}</em></summary>
    <div role="region" aria-label="Assembly hierarchy rows" tabIndex={virtual ? 0 : undefined}
      style={virtual ? { height: 304, overflowY: "auto", overflowAnchor: "none" } : undefined}
      onScroll={event => setScrollTop(event.currentTarget.scrollTop)}>
      {window.before > 0 && <div aria-hidden style={{ height: window.before }} />}
      {rows.slice(window.start, window.end).map(row => {
      const Icon = row.kind === "board" ? CircuitBoard : row.kind === "part" ? PackageOpen : Boxes;
      const activate = row.partId && row.actionable ? () => onAssemblyPart(row.partId!) : row.resolved ? () => onAction("assembly") : undefined;
      return <button key={row.nodeKey} className={!row.resolved ? "unresolved" : ""} disabled={!activate} onClick={activate} title={row.detail} style={{ height: 38, paddingLeft: `${9 + Math.min(row.depth, 12) * 13}px` }}>
        <Icon size={14} /><span><b>{row.label}</b><small>{row.detail}</small></span><em>{row.kind}</em>
      </button>;
    })}{window.after > 0 && <div aria-hidden style={{ height: window.after }} />}</div>
  </details>;
}

const EMPTY_ITEMS: never[] = [];

const cleanBoardName = (name: string) => name.replace(/\.kicad_pcb$/i, "").replace(/\.spike$/i, "") || "Untitled board";

export default function SceneNavigator({
  board, boardName, query, onQuery, probes, modelAssignments, assemblyIr, modelIndex, assemblyPartViewportStates, bondCount, sourceCount,
  powerPathCount, resultCount, thermalScenario, importQuality, onSelect, onAssemblyPart, onAction,
}: Props) {
  const scenario = useMemo(() => asThermalScenario(thermalScenario), [thermalScenario]);
  const normalizedQuery = useDeferredValue(query.trim().toLowerCase());
  const searchEnabled = Boolean(normalizedQuery);
  const netNames = useMemo(() => board ? [...new Set(Object.values(board.nets).filter(Boolean))] : [], [board]);
  const assignedModels = useMemo(() => board?.components.filter(component => Boolean(modelAssignments[component.ref] || component.modelPath || component.modelUrl || component.model)).length ?? 0, [board, modelAssignments]);
  const thermalElements = scenario?.thermal_elements ?? EMPTY_ITEMS;
  const thermalHardware = (scenario?.fans?.length ?? 0) + (scenario?.virtual_heatsinks?.length ?? 0);
  const attachedParts = assemblyIr?.parts ?? EMPTY_ITEMS;
  const modelsById = useMemo(() => new Map(modelIndex.models.map(model => [model.id, model])), [modelIndex]);
  const hierarchyRows = useMemo(() => assemblyIr ? assemblyHierarchyRows(assemblyIr, modelIndex, assemblyPartViewportStates) : [], [assemblyIr, assemblyPartViewportStates, modelIndex]);

  const searchEntries = useMemo<SearchEntry[]>(() => {
    if (!searchEnabled) return [];
    const resolveFrame = assemblyIr ? createAssemblyFrameResolver(assemblyIr) : undefined;
    const entries: SearchEntry[] = [];
    const add = (entry: SearchEntry) => entries.push({ ...entry, searchText: `${entry.label} ${entry.detail} ${entry.category} ${entry.keywords}`.toLowerCase() });
    if (!board) {
      attachedParts.forEach(part => {
        const model = modelsById.get(part.model_id);
        add({ id: `mcad:${part.id}`, label: part.name || part.id, detail: partDisplayStatus(part, model, assemblyIr, resolveFrame), category: "Attached MCAD", keywords: `assembly mcad ${part.part_type} ${part.material_id} ${model?.model_type ?? ""} ${model?.uri ?? ""}`, icon: PackageOpen, assemblyPartId: part.id });
      });
      probes.forEach(probe => add({ id: `probe:${probe.id}`, label: probe.name, detail: `${probe.net ?? "No net"} | ${probe.layer ?? "No layer"}`, category: "Probe", keywords: `analysis measurement voltage current impedance ${probe.net ?? ""}`, icon: RadioTower, object: probe }));
      return entries;
    }

    const tracksByNet = firstObjectByNet(board.tracks);
    const viasByNet = firstObjectByNet(board.vias);
    const padsByNet = firstObjectByNet(board.pads);
    const zonesByNet = firstObjectByNet(board.zones);
    netNames.forEach(net => {
      const track = tracksByNet.get(net);
      const via = viasByNet.get(net);
      const pad = padsByNet.get(net);
      const zone = zonesByNet.get(net);
      const object: BoardObject | undefined = track
        ? { id: track.id, type: "trace", name: net, net, layer: track.layer, position: track.start }
        : via ? { id: via.id, type: "via", name: net, net, layer: "through", layers: via.layers, position: via.at }
          : pad ? { id: pad.id, type: "pad", name: `${pad.ref ?? ""}.${pad.name}`.replace(/^\./, ""), ref: pad.ref, net, layer: pad.layer, layers: pad.layers, position: pad.at }
            : zone ? { id: zone.id, type: "zone", name: net, net, layer: zone.layer, position: zone.points[0] }
              : undefined;
      add({ id: `net:${net}`, label: net, detail: "Complete electrical net", category: "Net", keywords: `electrical copper signal power return ${net}`, icon: Route, object });
    });
    board.components.forEach(component => add({
      id: `component:${component.id}`, label: component.ref, detail: `${component.value || component.library || "Component"} | ${component.layer}`,
      category: "Component", keywords: `part electrical mechanical ${component.ref} ${component.value} ${component.library} ${modelAssignments[component.ref] ?? component.modelPath ?? ""}`,
      icon: Microchip, object: { id: component.id, type: "component", name: component.ref, ref: component.ref, layer: component.layer, position: component.at, model: Boolean(modelAssignments[component.ref] || component.model) },
    }));
    board.pads.forEach(pad => add({
      id: `pad:${pad.id}`, label: `${pad.ref ?? "?"}.${pad.name}`, detail: `${pad.net ?? "No net"} | ${pad.layers.join(" / ") || pad.layer}`,
      category: "Pad", keywords: `electrical pad terminal ${pad.ref ?? ""} ${pad.net ?? ""} ${pad.layer}`,
      icon: Crosshair, object: { id: pad.id, type: "pad", name: `${pad.ref ?? "?"}.${pad.name}`, ref: pad.ref, net: pad.net, layer: pad.layer, layers: pad.layers, position: pad.at },
    }));
    board.vias.forEach((via, index) => add({
      id: `via:${via.id}`, label: `Via ${index + 1}`, detail: `${via.net ?? "No net"} | ${via.layers.join(" / ")}`,
      category: "Via", keywords: `electrical plated drill ${via.id} ${via.net ?? ""}`,
      icon: MapPin, object: { id: via.id, type: "via", name: `Via ${index + 1}`, net: via.net, layer: "through", layers: via.layers, position: via.at },
    }));
    board.tracks.forEach((track, index) => add({
      id: `track:${track.id}`, label: `${track.net || "Unassigned"} trace ${index + 1}`, detail: `${track.layer} | ${track.width.toFixed(3)} mm`,
      category: "Trace", keywords: `electrical route track ${track.net ?? ""} ${track.layer}`,
      icon: Spline, object: { id: track.id, type: "trace", name: track.net || `Trace ${index + 1}`, net: track.net, layer: track.layer, position: track.start },
    }));
    board.zones.forEach((zone, index) => add({
      id: `zone:${zone.id}`, label: `${zone.net || "Unassigned"} zone ${index + 1}`, detail: `${zone.layer} | ${zone.points.length} vertices`,
      category: "Zone", keywords: `electrical copper fill plane ${zone.net ?? ""} ${zone.layer}`,
      icon: Network, object: { id: zone.id, type: "zone", name: zone.net || `Zone ${index + 1}`, net: zone.net, layer: zone.layer, position: zone.points[0] },
    }));
    board.layerDefinitions.forEach(layer => add({ id: `layer:${layer.id}`, label: layer.userName || layer.name, detail: `${layer.name} | ${layer.kind}`, category: "Layer", keywords: `stackup copper dielectric documentation ${layer.name} ${layer.userName ?? ""}`, icon: Layers3, action: "layers" }));
    (board.regions ?? []).forEach(region => add({ id: `region:${region.id}`, label: region.name, detail: `${region.kind} region | ${region.sourceLayer}`, category: "Board region", keywords: `mechanical ecad mcad rigid flex transition stiffener ${region.name}`, icon: CircuitBoard, action: "thermal" }));
    (board.bendLines ?? []).forEach(bend => add({ id: `bend:${bend.id}`, label: bend.name, detail: `${bend.sourceLayer} bend definition`, category: "Bend", keywords: `mechanical ecad mcad flex radius angle ${bend.name}`, icon: Spline, action: "thermal" }));
    thermalElements.forEach(element => add({ id: `thermal:${element.id}`, label: element.reference || element.name || element.id, detail: `${element.kind || "thermal object"} | ${Number(element.power_w || 0).toFixed(3)} W`, category: "Thermal / MCAD", keywords: `mechanical thermal heat step assembly ${element.reference ?? ""} ${element.name ?? ""} ${element.material_id ?? ""}`, icon: ThermometerSun, action: "thermal" }));
    attachedParts.forEach(part => {
      const model = modelsById.get(part.model_id);
      add({ id: `mcad:${part.id}`, label: part.name || part.id, detail: partDisplayStatus(part, model, assemblyIr, resolveFrame), category: "Attached MCAD", keywords: `assembly mcad ${part.part_type} ${part.material_id} ${model?.model_type ?? ""} ${model?.uri ?? ""}`, icon: PackageOpen, assemblyPartId: part.id });
    });
    probes.forEach(probe => add({ id: `probe:${probe.id}`, label: probe.name, detail: `${probe.net ?? "No net"} | ${probe.layer ?? "No layer"}`, category: "Probe", keywords: `analysis measurement voltage current impedance ${probe.net ?? ""}`, icon: RadioTower, object: probe }));
    return entries;
  }, [searchEnabled, attachedParts, assemblyIr, board, modelAssignments, modelsById, netNames, probes, thermalElements]);

  const matches = useMemo(() => normalizedQuery
    ? boundedMatches(searchEntries, entry => entry.searchText!.includes(normalizedQuery), 120) : [], [searchEntries, normalizedQuery]);
  const attachedMcadEmptySection: { title: string; badge: string; rows: SummaryRow[] } = {
    title: "Attached MCAD",
    badge: "0",
    rows: [{ label: "Attach MCAD part", detail: "Add STEP/STP/glTF/GLB to the saved project package", count: 0, icon: PackageOpen, action: "mcad" }],
  };

  const sections: Array<{ title: string; badge?: string; rows: SummaryRow[] }> = board ? [
    { title: "Boards & Assembly", badge: `${assemblyIr?.boards.length || 1} / 30`, rows: [
      { label: cleanBoardName(boardName), detail: `${board.width.toFixed(1)} x ${board.height.toFixed(1)} mm | ${board.technology ?? "rigid"}`, count: board.layers.length, icon: CircuitBoard, action: "board" },
      { label: "Multi-board assembly", detail: `${assemblyIr?.boards.length || 1} board record${(assemblyIr?.boards.length || 1) === 1 ? "" : "s"}; open board/harness structure editing`, count: assemblyIr?.boards.length || 1, icon: Boxes, action: "assembly" },
      { label: "Layer stack", detail: "Copper, dielectric, finish, rigid-flex regions", count: board.stackup.length, icon: Layers3, action: "stackup" },
    ] },
    { title: "Electrical", rows: [
      { label: "Nets", detail: "Search, assign roles, and form cross-net paths", count: netNames.length, icon: Route, action: "nets" },
      { label: "Components", detail: "Parts, footprints, models, and placement metadata", count: board.components.length, icon: Component, action: "components" },
      { label: "Copper objects", detail: `${board.tracks.length} tracks | ${board.zones.length} zones | ${board.pads.length} pads`, count: board.tracks.length + board.zones.length + board.pads.length, icon: Network, action: "layers" },
      { label: "Vias and bonds", detail: `${board.vias.length} vias | ${bondCount} component bonds`, count: board.vias.length + bondCount, icon: Cable, action: "bonds" },
      { label: "Sources and loads", detail: "Configured PI terminals", count: sourceCount, icon: Activity, action: "nets" },
    ] },
    { title: "Mechanical & MCAD", rows: [
      { label: "3D model assignments", detail: "Source assignments; open models to check loading and missing files", count: assignedModels, icon: Boxes, action: "models" },
      { label: "Attached MCAD", detail: "Persistent AssemblyIR parts and model-index artifacts", count: attachedParts.length, icon: PackageOpen, action: "mcad" },
      { label: "Board regions and bends", detail: `${board.regions?.length ?? 0} regions | ${board.bendLines?.length ?? 0} bend lines`, count: (board.regions?.length ?? 0) + (board.bendLines?.length ?? 0), icon: CircuitBoard, action: "thermal" },
      { label: "Thermal assembly objects", detail: `${thermalHardware} fans and heatsinks | ECAD/MCAD setup`, count: thermalElements.length, icon: Fan, action: "thermal" },
    ] },
    ...(attachedParts.length ? [] : [attachedMcadEmptySection]),
    { title: "Analysis", rows: [
      { label: "Probes", detail: "Persistent point and cross-layer measurements", count: probes.length, icon: RadioTower, action: "probes" },
      { label: "Power and signal paths", detail: "Component-level topology and series interfaces", count: powerPathCount, icon: Workflow, action: "power-paths" },
      { label: "Result records", detail: "Current-session solver result history", count: resultCount, icon: ChartArea, action: "results" },
    ] },
  ] : assemblyIr ? [
    { title: "Boards & Assembly", badge: `${assemblyIr.boards.length} / 30`, rows: [
      { label: assemblyIr.name || "Assembly", detail: `${assemblyIr.boards.length} board record${assemblyIr.boards.length === 1 ? "" : "s"}, ${assemblyIr.harnesses?.length ?? 0} harness${(assemblyIr.harnesses?.length ?? 0) === 1 ? "" : "es"}; edit structure`, count: assemblyIr.boards.length, icon: Boxes, action: "assembly" },
    ] },
    ...(attachedParts.length ? [] : [attachedMcadEmptySection]),
  ] : [];
  const sceneAvailable = Boolean(board || assemblyIr);

  return <div className="scene-navigator">
    <div className="search-field scene-search"><Search size={14} /><input value={query} onChange={event => onQuery(event.target.value)} onKeyDown={event => { if (event.key === "Escape") onQuery(""); }} placeholder="Search scene: nets, parts, MCAD..." aria-label="Search all electrical, mechanical, and analysis objects in the scene" />{query && <button onClick={() => onQuery("")} title="Clear scene search"><X size={12} /></button>}</div>
    <div className="scene-navigator-content">
      {!sceneAvailable && <div className="scene-nav-empty"><CircuitBoard size={20} /><b>No design loaded</b><span>Import a board or open a SPIKE project.</span></div>}
      {sceneAvailable && normalizedQuery && <div className="scene-search-results">
        <header><span>SCENE RESULTS</span><em>{matches.length}{matches.length === 120 ? "+" : ""}</em></header>
        {matches.map(({ id, label, detail, category, icon: Icon, object, action, assemblyPartId }) => <button key={id} onClick={() => object ? onSelect(object) : assemblyPartId ? onAssemblyPart(assemblyPartId) : action && onAction(action)}>
          <Icon size={14} /><span><b>{label}</b><small>{detail}</small></span><em>{category}</em>
        </button>)}
        {!matches.length && <div className="scene-nav-empty"><Search size={18} /><b>No matching scene objects</b><span>Search references, nets, layers, pads, vias, models, or thermal objects.</span></div>}
      </div>}
      {sceneAvailable && !normalizedQuery && hierarchyRows.length > 0 && <AssemblyHierarchySection rows={hierarchyRows} onAssemblyPart={onAssemblyPart} onAction={onAction} />}
      {sceneAvailable && !normalizedQuery && sections.map(section => <SummarySection key={section.title} {...section} onAction={onAction} />)}
    </div>
    <div className="nav-footer"><span>IMPORT QUALITY</span><b>{importQuality}%</b><div className="meter"><i style={{ width: `${importQuality}%` }} /></div></div>
  </div>;
}
