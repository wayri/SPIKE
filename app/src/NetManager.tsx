import { useEffect, useMemo, useState } from "react";
import { CircleDot, ListTree, MousePointer2, Network, Play, Plus, Search, Trash2, Waypoints, X } from "lucide-react";
import type { ParsedBoard } from "./boardParser";
import { previewViewportTarget } from "./BoardViewport";
import type { BoardObject } from "./BoardViewport";
import { resolveBoardCopperLayers } from "./copperLayerSelection";

type NetRole = "source" | "return" | "series" | "unassigned";
type LoopExtractionSetup = {
  id: string;
  name: string;
  forwardNet: string;
  returnNet: string;
  forwardStartPadId: string;
  forwardEndPadId: string;
  returnStartPadId: string;
  returnEndPadId: string;
  pathGroupId: string;
};

type NetManagerProps = {
  board: ParsedBoard | null;
  selectedNet?: string;
  selectedObject?: BoardObject;
  managedNets: string[];
  setManagedNets: (nets: string[]) => void;
  loopExtractions: LoopExtractionSetup[];
  setLoopExtractions: (items: LoopExtractionSetup[]) => void;
  pathGroups: { id: string; label: string }[];
  onSelectNet: (net: string) => void;
  onOpenPowerPaths: () => void;
  onOpenSeriesAnalysis: () => void;
  onStatus: (message: string) => void;
  onClose: () => void;
};

const isReturnName = (net: string) => /(^|[\/_-])(gnd|ground|return|0v)([\/_-]|$)/i.test(net);

export default function NetManager({
  board,
  selectedNet,
  selectedObject,
  managedNets,
  setManagedNets,
  loopExtractions,
  setLoopExtractions,
  pathGroups,
  onSelectNet,
  onOpenPowerPaths,
  onOpenSeriesAnalysis,
  onStatus,
  onClose,
}: NetManagerProps) {
  const [query, setQuery] = useState("");
  const [activeNet, setActiveNet] = useState(selectedNet ?? managedNets[0] ?? "");
  const [view, setView] = useState<"nets" | "loops">("nets");
  const [activeLoopId, setActiveLoopId] = useState(loopExtractions[0]?.id ?? "");

  const nets = useMemo(() => {
    const names = new Set<string>();
    Object.values(board?.nets ?? {}).forEach(name => name && names.add(name));
    board?.tracks.forEach(item => item.net && names.add(item.net));
    board?.vias.forEach(item => item.net && names.add(item.net));
    board?.pads.forEach(item => item.net && names.add(item.net));
    board?.zones.forEach(item => item.net && names.add(item.net));
    return [...names].sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  }, [board]);

  useEffect(() => {
    if (selectedNet) setActiveNet(selectedNet);
  }, [selectedNet]);

  const sourceNet = managedNets[0] ?? "";
  const returnNet = managedNets.find((net, index) => index > 0 && isReturnName(net)) ?? managedNets[1] ?? "";
  const roleFor = (net: string): NetRole => net === sourceNet
    ? "source"
    : net === returnNet
      ? "return"
      : managedNets.includes(net) ? "series" : "unassigned";

  const assignRole = (net: string, role: NetRole) => {
    const remaining = managedNets.filter(item => item !== net);
    let next = remaining;
    if (role === "source") next = [net, ...remaining];
    else if (role === "return") {
      const currentSource = remaining[0];
      next = currentSource ? [currentSource, net, ...remaining.slice(1).filter(item => item !== net)] : [net];
    } else if (role === "series") next = [...remaining, net];
    setManagedNets([...new Set(next)]);
    setActiveNet(net);
    onSelectNet(net);
    onStatus(role === "unassigned" ? `${net} removed from the PI net set` : `${net} assigned as ${role} in the PI Net Manager`);
  };

  const metrics = useMemo(() => new Map(nets.map(net => {
    const tracks = board?.tracks.filter(item => item.net === net) ?? [];
    const vias = board?.vias.filter(item => item.net === net) ?? [];
    const pads = board?.pads.filter(item => item.net === net) ?? [];
    const zones = board?.zones.filter(item => item.net === net) ?? [];
    const layers = new Set([
      ...tracks.flatMap(item => resolveBoardCopperLayers(board?.layers ?? [], [item.layer])),
      ...vias.flatMap(item => resolveBoardCopperLayers(board?.layers ?? [], item.layers)),
      ...pads.flatMap(item => resolveBoardCopperLayers(board?.layers ?? [], item.layers)),
      ...zones.flatMap(item => resolveBoardCopperLayers(board?.layers ?? [], [item.layer])),
    ]);
    const parts = new Set(pads.map(item => item.ref).filter(Boolean));
    return [net, { tracks: tracks.length, vias: vias.length, pads: pads.length, zones: zones.length, layers: layers.size, parts: parts.size }];
  })), [board, nets]);

  const filtered = nets.filter(net => net.toLowerCase().includes(query.trim().toLowerCase()));
  const activeLoop = loopExtractions.find(item => item.id === activeLoopId) ?? loopExtractions[0];
  const padsFor = (net: string) => (board?.pads ?? []).filter(pad => pad.net === net).sort((left, right) => `${left.ref}.${left.name}`.localeCompare(`${right.ref}.${right.name}`, undefined, { numeric: true }));
  const padLabel = (pad: ParsedBoard["pads"][number]) => `${pad.ref || "?"}.${pad.name} | ${pad.at[0].toFixed(3)}, ${pad.at[1].toFixed(3)} mm | ${pad.layers.join("/") || pad.layer}`;
  const selectedPad = selectedObject?.type === "pad" ? board?.pads.find(item => item.id === selectedObject.id) : undefined;
  const previewPad = (padId: string) => {
    const pad = board?.pads.find(item => item.id === padId);
    previewViewportTarget(pad ? { kind: "object", id: pad.id, type: "pad", net: pad.net, ref: pad.ref, layer: pad.layer, position: pad.at, label: padLabel(pad) } : null);
  };
  const addLoop = () => {
    const forwardNet = sourceNet || nets.find(net => !isReturnName(net)) || "";
    const returnCandidate = returnNet || nets.find(isReturnName) || "";
    const id = `loop-${Date.now().toString(36)}`;
    const forwardPads = padsFor(forwardNet);
    const returnPads = padsFor(returnCandidate);
    const next: LoopExtractionSetup = {
      id,
      name: `Power loop ${loopExtractions.length + 1}`,
      forwardNet,
      returnNet: returnCandidate,
      forwardStartPadId: forwardPads[0]?.id ?? "",
      forwardEndPadId: forwardPads[forwardPads.length - 1]?.id ?? "",
      returnStartPadId: returnPads[returnPads.length - 1]?.id ?? "",
      returnEndPadId: returnPads[0]?.id ?? "",
      pathGroupId: pathGroups[0]?.id ?? "",
    };
    setLoopExtractions([...loopExtractions, next]);
    setActiveLoopId(id);
    setView("loops");
    onStatus("Added an explicit forward/return loop extraction request; review all four pad endpoints");
  };
  const patchLoop = (patch: Partial<LoopExtractionSetup>) => {
    if (!activeLoop) return;
    setLoopExtractions(loopExtractions.map(item => item.id === activeLoop.id ? { ...item, ...patch } : item));
  };
  const useSelectedPad = (field: "forwardStartPadId" | "forwardEndPadId" | "returnStartPadId" | "returnEndPadId", expectedNet: string, endpoint: string) => {
    if (!selectedPad) {
      onStatus(`Select a pad in the board viewport before assigning the ${endpoint}`);
      return;
    }
    if (selectedPad.net !== expectedNet) {
      onStatus(`Selected pad ${selectedPad.ref || "?"}.${selectedPad.name} is on ${selectedPad.net || "no net"}, not ${expectedNet}`);
      return;
    }
    patchLoop({ [field]: selectedPad.id });
    previewPad(selectedPad.id);
    onStatus(`${endpoint} assigned to ${padLabel(selectedPad)}`);
  };
  const changeLoopNet = (role: "forward" | "return", net: string) => {
    const pads = padsFor(net);
    patchLoop(role === "forward" ? {
      forwardNet: net,
      forwardStartPadId: pads[0]?.id ?? "",
      forwardEndPadId: pads[pads.length - 1]?.id ?? "",
    } : {
      returnNet: net,
      returnStartPadId: pads[pads.length - 1]?.id ?? "",
      returnEndPadId: pads[0]?.id ?? "",
    });
  };
  const selectRow = (net: string) => {
    setActiveNet(net);
    onSelectNet(net);
  };
  const useViewportSelection = () => {
    if (!selectedNet) return;
    if (managedNets.includes(selectedNet)) {
      selectRow(selectedNet);
      onStatus(`${selectedNet} is already managed as ${roleFor(selectedNet)}`);
      return;
    }
    const suggestedRole: NetRole = managedNets.length === 0
      ? "source"
      : isReturnName(selectedNet) ? "return" : "series";
    assignRole(selectedNet, suggestedRole);
  };

  return <div className="modal-shade net-manager-shade" onPointerDown={event => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section className="net-manager" role="dialog" aria-modal="true" aria-label="PI Net Manager">
      <header>
        <div><b>PI NET MANAGER</b><small>Imported copper nets, simulation roles, and cross-net paths</small></div>
        <button onClick={onClose} title="Close Net Manager" aria-label="Close Net Manager"><X size={17} /></button>
      </header>

      <div className="net-manager-toolbar">
        <div className="net-manager-tabs"><button className={view === "nets" ? "selected" : ""} onClick={() => setView("nets")}><Network size={14} /> Nets</button><button className={view === "loops" ? "selected" : ""} onClick={() => setView("loops")}><Waypoints size={14} /> Loop RLC</button></div>
        {view === "nets" && <label><Search size={14} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Find net by name" autoFocus /></label>}
        {view === "loops" && <button onClick={addLoop}><Plus size={15} /> Add loop</button>}
        <button disabled={!selectedNet} onClick={useViewportSelection} title="Add the net currently selected in the board viewport using a safe suggested role"><MousePointer2 size={15} /> Use viewport selection</button>
        <button className="primary" onClick={onOpenPowerPaths} title="Open the component-level series diagram for these managed nets"><ListTree size={15} /> Open Power Tree</button>
        <button disabled={!pathGroups.length} onClick={onOpenSeriesAnalysis} title={pathGroups.length ? "Configure a cross-net solve using a reviewed Power Tree path" : "Create and review a Power Tree path first"}><Play size={15} /> Analyze series path</button>
      </div>

      <div className="net-manager-body">
        <aside>
          <h3>{view === "nets" ? "MANAGED NETS" : "LOOP EXTRACTIONS"}</h3>
          {view === "nets" && (managedNets.length ? managedNets.map(net => <button key={net} className={activeNet === net ? "active" : ""} onClick={() => selectRow(net)} onMouseEnter={() => previewViewportTarget({ kind: "net", net, label: net })} onMouseLeave={() => previewViewportTarget(null)}>
            <span className={`net-role-dot ${roleFor(net)}`} />
            <b>{net}</b><small>{roleFor(net)}</small>
          </button>) : <p>No nets assigned. Select an imported net and choose a role.</p>)}
          {view === "loops" && (loopExtractions.length ? loopExtractions.map(item => <button key={item.id} className={activeLoop?.id === item.id ? "active" : ""} onClick={() => setActiveLoopId(item.id)}>
            <span className="net-role-dot series" /><b>{item.name}</b><small>{item.forwardNet && item.returnNet && item.forwardStartPadId && item.forwardEndPadId && item.returnStartPadId && item.returnEndPadId ? "ready" : "incomplete"}</small>
          </button>) : <p>No loop extraction is configured. Add one to define explicit forward and return paths.</p>)}
          <div className="net-manager-guidance"><Network size={16} /><p>A copper net is one connected conductor name. Open the <b>Power Tree</b> to visualize and edit the ordered source-to-load series diagram, including components that bridge these net segments.</p></div>
        </aside>

        {view === "nets" ? <div className="net-catalog">
          <div className="net-table header"><span>Net</span><span>Role</span><span>Layers</span><span>Tracks</span><span>Vias</span><span>Pads</span><span>Zones</span><span>Parts</span></div>
          <div className="net-table-scroll">
            {filtered.map(net => {
              const item = metrics.get(net)!;
              return <div key={net} className={`net-table row ${activeNet === net ? "active" : ""}`} onClick={() => selectRow(net)} onMouseEnter={() => previewViewportTarget({ kind: "net", net, label: net })} onMouseLeave={() => previewViewportTarget(null)}>
                <span className="net-name"><CircleDot size={13} /><b title={net}>{net}</b></span>
                <select value={roleFor(net)} onClick={event => event.stopPropagation()} onChange={event => assignRole(net, event.target.value as NetRole)} aria-label={`Role for ${net}`}>
                  <option value="unassigned">Unassigned</option>
                  <option value="source">Source</option>
                  <option value="return">Return</option>
                  <option value="series">Series segment</option>
                </select>
                <span>{item.layers}</span><span>{item.tracks}</span><span>{item.vias}</span><span>{item.pads}</span><span>{item.zones}</span><span>{item.parts}</span>
              </div>;
            })}
            {!filtered.length && <div className="net-manager-empty">No imported net matches this filter.</div>}
          </div>
        </div> : <div className="loop-editor">
          {activeLoop ? <>
            <div className="loop-editor-heading"><div><b>PAD-TO-PAD LOOP EXTRACTION</b><small>Forward current travels source to load; return current travels load side back to source side.</small></div><button onClick={() => { const next = loopExtractions.filter(item => item.id !== activeLoop.id); setLoopExtractions(next); setActiveLoopId(next[0]?.id ?? ""); }} title="Delete loop"><Trash2 size={15} /></button></div>
            <label className="loop-name">Name<input aria-label="Loop name" value={activeLoop.name} onChange={event => patchLoop({ name: event.target.value })} /></label>
            <div className="loop-conductor-grid">
              <section><header><span className="net-role-dot source" /><b>FORWARD PATH</b></header>
                <label>Net<select aria-label="Forward net" value={activeLoop.forwardNet} onChange={event => changeLoopNet("forward", event.target.value)}><option value="">Select forward net</option>{nets.filter(net => net !== activeLoop.returnNet).map(net => <option key={net} value={net}>{net}</option>)}</select></label>
                <div className="loop-pad-control"><label>Source-side pad<select aria-label="Forward source-side pad" value={activeLoop.forwardStartPadId} onChange={event => patchLoop({ forwardStartPadId: event.target.value })} onMouseMove={event => previewPad((event.currentTarget as HTMLSelectElement).value)} onMouseLeave={() => previewViewportTarget(null)}><option value="">Select pad</option>{padsFor(activeLoop.forwardNet).map(pad => <option key={pad.id} value={pad.id}>{padLabel(pad)}</option>)}</select></label><button disabled={!selectedPad || selectedPad.net !== activeLoop.forwardNet} onClick={() => useSelectedPad("forwardStartPadId", activeLoop.forwardNet, "forward source-side endpoint")} title="Use the pad selected in the board viewport"><MousePointer2 size={14} /> Use selected</button></div>
                <div className="loop-pad-control"><label>Load-side pad<select aria-label="Forward load-side pad" value={activeLoop.forwardEndPadId} onChange={event => patchLoop({ forwardEndPadId: event.target.value })} onMouseMove={event => previewPad((event.currentTarget as HTMLSelectElement).value)} onMouseLeave={() => previewViewportTarget(null)}><option value="">Select pad</option>{padsFor(activeLoop.forwardNet).map(pad => <option key={pad.id} value={pad.id}>{padLabel(pad)}</option>)}</select></label><button disabled={!selectedPad || selectedPad.net !== activeLoop.forwardNet} onClick={() => useSelectedPad("forwardEndPadId", activeLoop.forwardNet, "forward load-side endpoint")} title="Use the pad selected in the board viewport"><MousePointer2 size={14} /> Use selected</button></div>
              </section>
              <section><header><span className="net-role-dot return" /><b>RETURN PATH</b></header>
                <label>Net<select aria-label="Return net" value={activeLoop.returnNet} onChange={event => changeLoopNet("return", event.target.value)}><option value="">Select return net</option>{nets.filter(net => net !== activeLoop.forwardNet).map(net => <option key={net} value={net}>{net}</option>)}</select></label>
                <div className="loop-pad-control"><label>Load-side return pad<select aria-label="Return load-side pad" value={activeLoop.returnStartPadId} onChange={event => patchLoop({ returnStartPadId: event.target.value })} onMouseMove={event => previewPad((event.currentTarget as HTMLSelectElement).value)} onMouseLeave={() => previewViewportTarget(null)}><option value="">Select pad</option>{padsFor(activeLoop.returnNet).map(pad => <option key={pad.id} value={pad.id}>{padLabel(pad)}</option>)}</select></label><button disabled={!selectedPad || selectedPad.net !== activeLoop.returnNet} onClick={() => useSelectedPad("returnStartPadId", activeLoop.returnNet, "return load-side endpoint")} title="Use the pad selected in the board viewport"><MousePointer2 size={14} /> Use selected</button></div>
                <div className="loop-pad-control"><label>Source-side return pad<select aria-label="Return source-side pad" value={activeLoop.returnEndPadId} onChange={event => patchLoop({ returnEndPadId: event.target.value })} onMouseMove={event => previewPad((event.currentTarget as HTMLSelectElement).value)} onMouseLeave={() => previewViewportTarget(null)}><option value="">Select pad</option>{padsFor(activeLoop.returnNet).map(pad => <option key={pad.id} value={pad.id}>{padLabel(pad)}</option>)}</select></label><button disabled={!selectedPad || selectedPad.net !== activeLoop.returnNet} onClick={() => useSelectedPad("returnEndPadId", activeLoop.returnNet, "return source-side endpoint")} title="Use the pad selected in the board viewport"><MousePointer2 size={14} /> Use selected</button></div>
              </section>
            </div>
            <div className="loop-selection-note"><MousePointer2 size={15} /><span>To use an exact board location, select a pad in the viewport before opening this manager, then choose <b>Use selected</b>. Pad lists remain available for direct assignment.</span></div>
            <div className="loop-model-link"><label>Power Tree path<select aria-label="Power Tree path" value={activeLoop.pathGroupId} onChange={event => patchLoop({ pathGroupId: event.target.value })}><option value="">Copper geometry only</option>{pathGroups.map(group => <option key={group.id} value={group.id}>{group.label}</option>)}</select></label><button onClick={onOpenPowerPaths}><ListTree size={15} /> Review component models</button></div>
            <div className="loop-validity"><b>Extraction contract</b><p>The PEEC solve uses the full mutual partial-inductance matrix for both conductors, including selected vias, planes, zones, and connected layers. Stackup permittivity is used for a bounded capacitance estimate. Reviewed Power Tree series models add package and component R/L; nonlinear MOSFET behavior remains in the linked SPICE solve.</p></div>
          </> : <div className="net-manager-empty"><Waypoints size={24} /><p>Add a loop extraction to select two nets and four explicit pad endpoints.</p><button onClick={addLoop}><Plus size={15} /> Add loop extraction</button></div>}
        </div>}
      </div>

      <footer>
        <span>{nets.length} imported nets | {managedNets.length} managed | {managedNets.filter(net => roleFor(net) === "series").length} series segments</span>
        <button onClick={onClose}>Done</button>
      </footer>
    </section>
  </div>;
}
