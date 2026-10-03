import { useEffect, useMemo, useState } from "react";
import { Cable, CircleHelp, Network, Plus, RefreshCw } from "lucide-react";
import type { AssemblyDesigns, AssemblyIr } from "./mcadAssembly";
import { ambiguousNets, graphConnectors, graphLinks, suggestedPairs, suggestionForPair, type GraphConnector } from "./connectorGraphModel";
import DataTable from "./DataTable";
import { runLocalWorker } from "./workerBridge";
import "./connectorGraphEditor.css";

type HarnessPlan = { harnesses: Array<Record<string, unknown>>; connector_mappings: Array<Record<string, unknown>>;
  wire_list: Array<Record<string, unknown>>; diagnostics: Array<{ message: string }>; total_wire_length_mm: number };
type Props = { assembly: AssemblyIr; designs: AssemblyDesigns | null; version: string | null;
  onAddMate: (endpointA: string, endpointB: string, pinMap: Record<string, string>, connectors: GraphConnector[]) => void;
  onAddConnector: (boardId: string, connectorId: string, positionMm: [number, number, number], pins: Record<string, string>) => void;
  onApplyHarness: (plan: HarnessPlan) => void; onRemoveLink: (id: string, kind: "mate" | "harness") => void;
  onStatus: (message: string) => void };

function parseArray(text: string, label: string): unknown[] {
  const parsed = JSON.parse(text);
  if (!Array.isArray(parsed)) throw new Error(`${label} must be a JSON array.`);
  return parsed;
}

export default function ConnectorGraphEditor({ assembly, designs, version, onAddMate, onAddConnector, onApplyHarness, onRemoveLink, onStatus }: Props) {
  const [rawConnectors, setRawConnectors] = useState<Record<string, unknown>>({});
  const [diagnostics, setDiagnostics] = useState<Array<{ message: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [endpointA, setEndpointA] = useState("");
  const [endpointB, setEndpointB] = useState("");
  const [pinMap, setPinMap] = useState<Record<string, string>>({});
  const [newSourcePin, setNewSourcePin] = useState("");
  const [newTargetPin, setNewTargetPin] = useState("");
  const [linkKind, setLinkKind] = useState<"mate" | "harness">("harness");
  const [search, setSearch] = useState("");
  const [selectedLinkId, setSelectedLinkId] = useState("");
  const [slack, setSlack] = useState(10);
  const [allowance, setAllowance] = useState(10);
  const [gauge, setGauge] = useState(24);
  const [clearance, setClearance] = useState(2);
  const [waypoints, setWaypoints] = useState("[]");
  const [keepouts, setKeepouts] = useState("[]");
  const [preview, setPreview] = useState<HarnessPlan | null>(null);
  const [previewFingerprint, setPreviewFingerprint] = useState("");
  const [manualBoard, setManualBoard] = useState("");
  const [manualConnector, setManualConnector] = useState("");
  const [manualPosition, setManualPosition] = useState("0, 0, 0");
  const [manualPins, setManualPins] = useState('{"1":"","2":""}');

  const discoveryKey = JSON.stringify({ version, boards: assembly.boards.map(row => [row.id, row.design_id, row.frame]),
    mappings: assembly.connector_mappings, harnesses: (assembly.harnesses ?? []).map(row => [row.id, row.endpoint_a, row.endpoint_b, row.pin_map]),
    designIds: designs?.designs.map(row => row.design_id) });
  const discover = async () => {
    if (!designs || assembly.boards.length < 2) { setRawConnectors({}); return; }
    setLoading(true);
    try {
      const response = await runLocalWorker({ method: "plan_assembly_harnesses", params: { request: {
        assembly, designs: Object.fromEntries(designs.designs.map(row => [row.design_id, row])), pairs: [],
      } } });
      if (!response.ok || !response.result) throw new Error(response.error ?? "Connector discovery failed.");
      const result = response.result as Record<string, unknown>;
      setRawConnectors(result.connectors && typeof result.connectors === "object" ? result.connectors as Record<string, unknown> : {});
      setDiagnostics(Array.isArray(result.diagnostics) ? result.diagnostics as Array<{ message: string }> : []);
    } catch (error) {
      setRawConnectors({});
      onStatus(error instanceof Error ? `Connector discovery failed: ${error.message}` : "Connector discovery failed");
    } finally { setLoading(false); }
  };
  useEffect(() => { void discover(); }, [discoveryKey]);

  const connectors = useMemo(() => graphConnectors(rawConnectors, assembly), [rawConnectors, discoveryKey]);
  const links = useMemo(() => graphLinks(assembly), [discoveryKey]);
  const suggestions = useMemo(() => suggestedPairs(connectors, links), [connectors, links]);
  const ambiguous = useMemo(() => ambiguousNets(connectors, links), [connectors, links]);
  const selectedLink = links.find(link => `${link.kind}:${link.id}` === selectedLinkId);
  const byKey = useMemo(() => new Map(connectors.map(row => [row.key, row])), [connectors]);
  const first = byKey.get(endpointA), second = byKey.get(endpointB);
  const separationMm = first?.assemblyPositionMm && second?.assemblyPositionMm
    ? Math.hypot(first.assemblyPositionMm[0] - second.assemblyPositionMm[0],
      first.assemblyPositionMm[1] - second.assemblyPositionMm[1],
      first.assemblyPositionMm[2] - second.assemblyPositionMm[2]) : null;
  const occupied = useMemo(() => {
    const pins = new Set<string>();
    for (const link of links) for (const [a, b] of Object.entries(link.pinMap)) {
      pins.add(`${link.endpointA}\u0000${a}`); pins.add(`${link.endpointB}\u0000${b}`);
    }
    return pins;
  }, [links]);
  const selectPair = (a: string, b: string) => {
    setEndpointA(a); setEndpointB(b); setPinMap(suggestionForPair(suggestions, a, b)); setNewSourcePin(""); setNewTargetPin(""); setPreview(null);
  };
  const selectNode = (connector: GraphConnector) => {
    if (!endpointA || endpointB || endpointA === connector.key) {
      setEndpointA(connector.key); setEndpointB(""); setPinMap({}); setPreview(null); return;
    }
    selectPair(endpointA, connector.key);
  };
  const pairIssue = !first || !second ? "Select two connector nodes on different boards."
    : first.boardId === second.boardId ? "Connections must join different board instances."
    : !Object.keys(pinMap).length ? "Add a reviewed pin pair. Shared net names are suggestions, not an inferred connection."
    : Object.keys(pinMap).length > 512 ? "A link can map at most 512 pin pairs."
    : Object.entries(pinMap).some(([a, b]) => !(a in first.pins) || !(b in second.pins)) ? "A selected pin is absent from a connector."
    : new Set(Object.values(pinMap)).size !== Object.keys(pinMap).length ? "Each destination pin can be used only once."
    : Object.entries(pinMap).some(([a, b]) => occupied.has(`${endpointA}\u0000${a}`) || occupied.has(`${endpointB}\u0000${b}`)) ? "A pin is already used by a saved or draft link."
    : "";
  const crossoverPins = first && second ? Object.entries(pinMap).filter(([a, b]) => first.pins[a] && second.pins[b] && first.pins[a] !== second.pins[b]) : [];
  const fingerprint = JSON.stringify({ discoveryKey, endpointA, endpointB, pinMap, slack, allowance, gauge, clearance, waypoints, keepouts });
  const planHarness = async () => {
    if (pairIssue) { onStatus(pairIssue); return; }
    setLoading(true);
    try {
      const response = await runLocalWorker({ method: "plan_assembly_harnesses", params: { request: {
        assembly, designs: Object.fromEntries((designs?.designs ?? []).map(row => [row.design_id, row])),
        pairs: [{ endpoint_a: endpointA, endpoint_b: endpointB, pin_map: pinMap, waypoints_mm: parseArray(waypoints, "Waypoints") }],
        keepouts: parseArray(keepouts, "Keepouts"), slack_percent: slack, termination_allowance_mm: allowance,
        gauge_awg: gauge, clearance_mm: clearance,
      } } });
      if (!response.ok || !response.result) throw new Error(response.error ?? "Virtual harness planning failed.");
      const plan = response.result as unknown as HarnessPlan;
      setPreview(plan); setPreviewFingerprint(fingerprint);
      onStatus(plan.harnesses.length ? "Virtual harness route ready for review. Add it to the draft, then save boards and links." : "No routable conductor was proposed; inspect diagnostics and pin map.");
    } catch (error) { setPreview(null); onStatus(error instanceof Error ? error.message : String(error)); }
    finally { setLoading(false); }
  };
  const addManualConnector = () => {
    try {
      const boardId = manualBoard || String(assembly.boards[0]?.id ?? "");
      const connectorId = manualConnector.trim();
      if (!boardId || !connectorId || connectorId.includes(":")) throw new Error("Choose a board and enter a connector reference without a colon.");
      if (byKey.has(`${boardId}::${connectorId}`) || (assembly.connector_mappings ?? []).some(row => {
        const data = row.data as Record<string, unknown> | undefined;
        return data?.board_id === boardId && data?.connector_id === connectorId;
      })) throw new Error("That connector already exists on this board.");
      const numbers = manualPosition.split(",").map(value => Number(value.trim()));
      if (numbers.length !== 3 || !numbers.every(Number.isFinite)) throw new Error("Enter X, Y, Z in assembly millimetres.");
      const pins = JSON.parse(manualPins);
      if (!pins || typeof pins !== "object" || Array.isArray(pins) || !Object.keys(pins).length
        || Object.entries(pins).some(([pin, net]) => !pin.trim() || typeof net !== "string")) throw new Error("Pins must be a nonempty JSON object mapping pin numbers to net names.");
      onAddConnector(boardId, connectorId, numbers as [number, number, number], pins);
      setManualConnector(""); onStatus(`Connector ${boardId}::${connectorId} added to the draft. Review pin identities before linking.`);
    } catch (error) { onStatus(error instanceof Error ? error.message : String(error)); }
  };

  const visible = connectors.filter(row => `${row.boardId} ${row.connectorId} ${Object.values(row.pins).join(" ")}`.toLowerCase().includes(search.toLowerCase())).slice(0, 240);
  const boardIndex = new Map(assembly.boards.map((row, index) => [String(row.id), index]));
  const boardNodes = assembly.boards.map(row => visible.filter(connector => connector.boardId === row.id));
  const width = Math.max(600, assembly.boards.length * 260 + 30);
  const maxRows = boardNodes.reduce((maximum, rows) => Math.max(maximum, rows.length), 0);
  const height = Math.max(260, maxRows * 46 + 115);
  const nodePositions = new Map<string, { x: number; y: number }>();
  boardNodes.forEach((rows, column) => rows.forEach((row, index) => nodePositions.set(row.key, { x: column * 260 + 134, y: 108 + index * 46 })));
  return <section className="connector-graph-editor" aria-label="Inter-board connector graph editor">
    <header><div><h4><Network size={15} /> Connector graph</h4><p>Pick two ports to define a link. Lines show saved and draft links; suggestions need your review before they become connections.</p></div><button className="secondary-btn" disabled={loading || !designs} onClick={() => void discover()}><RefreshCw size={13} /> {loading ? "Discovering…" : "Refresh connectors"}</button></header>
    <div className="connector-graph-toolbar"><label>Find connector or net <input value={search} onChange={event => setSearch(event.target.value)} placeholder="J1, GND, board name…" /></label><span>{connectors.length} connectors · {links.length} links · {suggestions.length} candidate pairs</span></div>
    <div className="connector-graph-canvas" tabIndex={0} aria-label="Board and connector graph; use the endpoint selectors below for keyboard access">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {boardNodes.map((rows, column) => { const board = assembly.boards[column]; return <g key={String(board.id)}><rect className="connector-graph-board" x={column * 260 + 10} y={12} width={244} height={height - 24} rx={9} /><text className="connector-graph-board-title" x={column * 260 + 24} y={39}>{String(board.name ?? board.id).slice(0, 27)}</text><text className="connector-graph-board-id" x={column * 260 + 24} y={57}>{String(board.id).slice(0, 30)}</text>{rows.length === 0 && <text className="connector-graph-empty" x={column * 260 + 24} y={105}>No connectors found</text>}</g>; })}
        {links.slice(0, 512).map(link => { const a = nodePositions.get(link.endpointA), b = nodePositions.get(link.endpointB); if (!a || !b) return null; const mid = (a.x + b.x) / 2; return <path key={`${link.kind}:${link.id}`} className={`connector-graph-edge ${link.kind} ${selectedLinkId === `${link.kind}:${link.id}` ? "selected" : ""}`} role="button" tabIndex={0} aria-label={`Inspect ${link.kind === "mate" ? "direct mate" : "virtual harness"} ${link.endpointA} to ${link.endpointB}`} onClick={() => setSelectedLinkId(`${link.kind}:${link.id}`)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedLinkId(`${link.kind}:${link.id}`); } }} d={`M ${a.x} ${a.y} C ${mid} ${a.y}, ${mid} ${b.y}, ${b.x} ${b.y}`}><title>{link.kind === "mate" ? "Direct mate" : "Virtual harness"}: {link.endpointA} → {link.endpointB}</title></path>; })}
        {endpointA && endpointB && nodePositions.has(endpointA) && nodePositions.has(endpointB) && <line className="connector-graph-pending" x1={nodePositions.get(endpointA)!.x} y1={nodePositions.get(endpointA)!.y} x2={nodePositions.get(endpointB)!.x} y2={nodePositions.get(endpointB)!.y} />}
        {boardNodes.flatMap(rows => rows).map(row => { const p = nodePositions.get(row.key)!; return <g key={row.key} className={`connector-graph-node ${endpointA === row.key || endpointB === row.key ? "selected" : ""}`} role="button" tabIndex={0} aria-label={`Select ${row.key}, ${Object.keys(row.pins).length} pins`} onClick={() => selectNode(row)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectNode(row); } }}><rect x={p.x - 110} y={p.y - 15} width={220} height={30} rx={6} /><circle cx={p.x} cy={p.y} r={5} /><text x={p.x - 96} y={p.y + 4}>{row.connectorId} · {Object.keys(row.pins).length} pins</text><title>{row.key}</title></g>; })}
      </svg>
    </div>
    {selectedLink && <div className="connector-graph-selected-link"><b>{selectedLink.kind === "mate" ? "Direct mate" : "Virtual harness"}: {selectedLink.endpointA} → {selectedLink.endpointB}</b><span>{Object.keys(selectedLink.pinMap).length} assigned pin pairs</span><button className="secondary-btn" onClick={() => { onRemoveLink(selectedLink.id, selectedLink.kind); setSelectedLinkId(""); }}>Remove from draft</button></div>}
    {connectors.length > visible.length && <p className="connector-graph-note">Showing {visible.length} of {connectors.length} connectors. Search to focus the graph.</p>}
    <div className="connector-graph-workspace">
      <div className="connector-graph-pair"><h4><Cable size={14} /> Define a link</h4><p>Select ports in the graph or use these lists.</p>
        <div className="field-row"><label>Connector A<select value={endpointA} onChange={event => { setEndpointA(event.target.value); setEndpointB(""); setPinMap({}); setPreview(null); }}><option value="">Choose connector</option>{connectors.map(row => <option key={row.key} value={row.key}>{row.key}</option>)}</select></label><label>Connector B<select value={endpointB} onChange={event => selectPair(endpointA, event.target.value)}><option value="">Choose connector</option>{connectors.filter(row => row.boardId !== first?.boardId).map(row => <option key={row.key} value={row.key}>{row.key}</option>)}</select></label></div>
        <div className="field-row"><label>Connection type<select value={linkKind} onChange={event => { setLinkKind(event.target.value as "mate" | "harness"); setPreview(null); }}><option value="harness">Virtual cable harness</option><option value="mate">Direct board-to-board mate</option></select></label></div>
        {separationMm !== null && <p className="connector-graph-note">Connector exit points are {separationMm.toFixed(1)} mm apart in assembly coordinates. Check mechanical alignment before choosing a direct mate.</p>}
        <p className="connector-graph-note"><CircleHelp size={13} /> Matching net names only suggest pin pairs. Verify connector keying, pin numbering, voltage domains, return paths, contact resistance, and cable ratings.</p>
        {first && second && <><h5>Reviewed pin pairs</h5>
          <DataTable label="Reviewed connector pin pairs" searchable={false} pageSize={100} className="connector-graph-pin-rows">
            <thead><tr><th>Source pin / net</th><th aria-label="Direction" /><th>Destination pin / net</th><th>Actions</th></tr></thead>
            <tbody>{Object.entries(pinMap).map(([a, b]) => <tr key={a}><td><span>{a} <small>{first.pins[a] || "unnamed net"}</small></span></td><td aria-hidden="true">→</td><td><span>{b} <small>{second.pins[b] || "unnamed net"}</small></span></td><td><button className="secondary-btn" onClick={() => setPinMap(current => { const next = { ...current }; delete next[a]; return next; })}>Remove</button></td></tr>)}</tbody>
          </DataTable>
          <div className="field-row"><label>Source pin<select value={newSourcePin} onChange={event => setNewSourcePin(event.target.value)}><option value="">Select pin</option>{Object.keys(first.pins).filter(pin => !(pin in pinMap)).map(pin => <option key={pin} value={pin}>{pin} · {first.pins[pin]}</option>)}</select></label><label>Destination pin<select value={newTargetPin} onChange={event => setNewTargetPin(event.target.value)}><option value="">Select pin</option>{Object.keys(second.pins).filter(pin => !Object.values(pinMap).includes(pin)).map(pin => <option key={pin} value={pin}>{pin} · {second.pins[pin]}</option>)}</select></label><button className="secondary-btn" disabled={!newSourcePin || !newTargetPin} onClick={() => { setPinMap(current => ({ ...current, [newSourcePin]: newTargetPin })); setNewSourcePin(""); setNewTargetPin(""); }}>Add pin pair</button></div><button className="secondary-btn" onClick={() => setPinMap(suggestionForPair(suggestions, endpointA, endpointB))}>Use unambiguous shared-net suggestions</button></>}
        {pairIssue && <p className="connector-graph-error" role="status">{pairIssue}</p>}
        {crossoverPins.length > 0 && <p className="connector-graph-note" role="status">{crossoverPins.length} pin pair{crossoverPins.length === 1 ? "" : "s"} join different net names. Confirm that each crossover is intentional before saving.</p>}
        {linkKind === "mate" ? <button className="run-btn" disabled={Boolean(pairIssue)} onClick={() => { onAddMate(endpointA, endpointB, pinMap, [first!, second!]); setEndpointA(""); setEndpointB(""); setPinMap({}); }}>Add direct mate to draft</button> : <><div className="field-row"><label>Slack %<input type="number" min="0" max="100" value={slack} onChange={event => setSlack(Number(event.target.value))} /></label><label>Allowance/end mm<input type="number" min="0" value={allowance} onChange={event => setAllowance(Number(event.target.value))} /></label><label>AWG<input type="number" min="0" max="40" value={gauge} onChange={event => setGauge(Number(event.target.value))} /></label><label>Clearance mm<input type="number" min="0" value={clearance} onChange={event => setClearance(Number(event.target.value))} /></label></div><details><summary>Route waypoints and keepouts</summary><label>Waypoints XYZ mm<textarea value={waypoints} onChange={event => setWaypoints(event.target.value)} /></label><label>Keepout volumes<textarea value={keepouts} onChange={event => setKeepouts(event.target.value)} /></label></details><button className="secondary-btn" disabled={loading || Boolean(pairIssue)} onClick={() => void planHarness()}>Preview virtual harness route</button>{preview && <div className="connector-graph-preview"><b>{preview.harnesses.length} routed harness · {preview.wire_list.length} conductors · {(preview.total_wire_length_mm / 1000).toFixed(3)} m total cut length</b><p>Approximate route and cut list; bend radius and physical fit remain unqualified.</p>{preview.diagnostics.map((item, index) => <p key={index}>{item.message}</p>)}<button className="run-btn" disabled={previewFingerprint !== fingerprint || !preview.harnesses.length} onClick={() => { onApplyHarness(preview); setPreview(null); }}>Add virtual harness to draft</button></div>}</>}
      </div>
      <div className="connector-graph-help"><h4>Auto help</h4><p>SPIKE suggests pairs only where a net occurs on exactly two free pins across different boards. Shared grounds and multi-drop nets require manual review.</p>{suggestions.slice(0, 20).map(item => <button key={`${item.endpointA}:${item.endpointB}`} onClick={() => selectPair(item.endpointA, item.endpointB)}><b>{item.endpointA} → {item.endpointB}</b><small>{item.netNames.length} candidate net{item.netNames.length === 1 ? "" : "s"}: {item.netNames.slice(0, 4).join(", ")}</small></button>)}{!suggestions.length && <p>No unambiguous free-pin suggestions. Select connectors and map pins explicitly.</p>}{ambiguous.length > 0 && <details><summary>{ambiguous.length} ambiguous multi-drop net{ambiguous.length === 1 ? "" : "s"}</summary>{ambiguous.slice(0, 20).map(item => <p key={item.name}>{item.name}: {item.count} free pins. Choose the intended connector pair and map pins manually.</p>)}</details>}{diagnostics.map((item, index) => <p key={index} className="connector-graph-note">{item.message}</p>)}</div>
    </div>
    <details className="connector-graph-manual"><summary><Plus size={13} /> Add an explicit connector missing from the imported design</summary><p>Use the board-local connector exit point. Enter physical pin numbers and their board net names; blank net names are allowed for manual wiring.</p><div className="field-row"><label>Board<select value={manualBoard} onChange={event => setManualBoard(event.target.value)}>{assembly.boards.map(row => <option key={String(row.id)} value={String(row.id)}>{String(row.name ?? row.id)}</option>)}</select></label><label>Connector reference<input value={manualConnector} onChange={event => setManualConnector(event.target.value)} placeholder="J1" /></label><label>Local XYZ mm<input value={manualPosition} onChange={event => setManualPosition(event.target.value)} /></label></div><label>Pins as JSON<textarea value={manualPins} onChange={event => setManualPins(event.target.value)} /></label><button className="secondary-btn" onClick={addManualConnector}>Add connector to draft</button></details>
  </section>;
}
