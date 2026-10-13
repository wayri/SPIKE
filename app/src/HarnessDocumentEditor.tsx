// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import DataTable from "./DataTable";
import TableIdentityInput from "./TableIdentityInput";
import { CONNECTOR_PRESETS, formatPinMappings, mergeConnectorPins, parsePinMappings, reconcilePairWires } from "./connectorPresets";
import HarnessDiagram, { type HarnessDiagramSelection } from "./HarnessDiagram";
import {
  addHarnessSplice, addHarnessWire, assignHarnessPair, deleteHarnessConnector, deleteHarnessSplice, deleteHarnessWire, nextHarnessId,
  pairCandidateWires, renameHarnessConnector, renameHarnessSplice, setHarnessWireRole, updateHarnessPair, wirePair, type HarnessEndpoint, type HarnessWireRole,
} from "./HarnessDiagramModel";
import HarnessPiPanel from "./HarnessPiPanel";
import HarnessSignalPanel from "./HarnessSignalPanel";

type Props = { value: Record<string, any> | null; onChange: (value: Record<string, any>) => void };
const optionalNumber = (raw: string) => raw === "" ? undefined : Number(raw);
const endpointLabel = (endpoint: any) => endpoint?.connector ? `${endpoint.connector} / ${endpoint.pin}` : `Splice ${endpoint?.splice ?? "?"}`;
const spliceOwnerPrefix = "\u0000splice:";
const spliceOwner = (id: string) => `${spliceOwnerPrefix}${id}`;
const ownerSpliceId = (owner: string) => owner.startsWith(spliceOwnerPrefix) ? owner.slice(spliceOwnerPrefix.length) : "";
const ownerEndpoint = (owner: string, pin: string): HarnessEndpoint => ownerSpliceId(owner) ? { splice: ownerSpliceId(owner) } : { connector: owner, pin };
const wireRoles: Array<{ value: HarnessWireRole; label: string }> = [
  { value: "unspecified", label: "Unspecified" }, { value: "power", label: "Power" }, { value: "return", label: "Return" },
  { value: "signal", label: "Signal" }, { value: "other", label: "Other" }, { value: "shield", label: "Shield" },
];

export default function HarnessDocumentEditor({ value, onChange }: Props) {
  const [draft, setDraft] = useState(""); const [error, setError] = useState("");
  const [bulkFrom, setBulkFrom] = useState(""); const [bulkTo, setBulkTo] = useState(""); const [mappingText, setMappingText] = useState("");
  const [selection, setSelection] = useState<HarnessDiagramSelection>(null); const [deletePending, setDeletePending] = useState<HarnessDiagramSelection>(null);
  const [fromConnector, setFromConnector] = useState(""); const [fromPin, setFromPin] = useState("");
  const [toConnector, setToConnector] = useState(""); const [toPin, setToPin] = useState(""); const [wireId, setWireId] = useState("");
  const [pairMate, setPairMate] = useState("");
  const issuedConnectorIds = useRef(new Set<string>()); const issuedSpliceIds = useRef(new Set<string>()); const issuedWireIds = useRef(new Set<string>());
  const connectors = value && Array.isArray(value.connectors) ? value.connectors : [];
  const splices = value && Array.isArray(value.splices) ? value.splices : [];
  const wires = value && Array.isArray(value.wires) ? value.wires : [];
  const identity = JSON.stringify([
    connectors.map((item: any) => [item.id, (item.pins ?? []).map((pin: any) => pin.id)]),
    splices.map((item: any) => item.id),
    wires.map((item: any) => item.id),
  ]);

  useEffect(() => {
    connectors.forEach((item: any) => issuedConnectorIds.current.add(String(item.id)));
    splices.forEach((item: any) => issuedSpliceIds.current.add(String(item.id)));
    wires.forEach((item: any) => issuedWireIds.current.add(String(item.id)));
    if (!connectors.some((item: any) => item.id === bulkFrom)) setBulkFrom(connectors[0]?.id ?? "");
    if (!connectors.some((item: any) => item.id === bulkTo)) setBulkTo(connectors[1]?.id ?? connectors[0]?.id ?? "");
    const ownerExists = (owner: string) => ownerSpliceId(owner) ? splices.some((item: any) => item.id === ownerSpliceId(owner)) : connectors.some((item: any) => item.id === owner);
    if (!ownerExists(fromConnector)) setFromConnector(connectors[0]?.id ?? (splices[0] ? spliceOwner(splices[0].id) : ""));
    if (!ownerExists(toConnector)) setToConnector(connectors[1]?.id ?? connectors[0]?.id ?? (splices[0] ? spliceOwner(splices[0].id) : ""));
    if (selection?.kind === "connector" && !connectors.some((item: any) => item.id === selection.id)) setSelection(null);
    if (selection?.kind === "splice" && !splices.some((item: any) => item.id === selection.id)) setSelection(null);
    if (selection?.kind === "wire" && !wires.some((item: any) => item.id === selection.id)) setSelection(null);
  }, [identity, bulkFrom, bulkTo, fromConnector, toConnector, selection]);
  const fromPins = ownerSpliceId(fromConnector) ? [] : connectors.find((item: any) => item.id === fromConnector)?.pins ?? [];
  const toPins = ownerSpliceId(toConnector) ? [] : connectors.find((item: any) => item.id === toConnector)?.pins ?? [];
  useEffect(() => { if (!fromPins.some((pin: any) => String(pin.id) === fromPin)) setFromPin(String(fromPins[0]?.id ?? "")); }, [fromConnector, identity, fromPin]);
  useEffect(() => { if (!toPins.some((pin: any) => String(pin.id) === toPin)) setToPin(String(toPins[0]?.id ?? "")); }, [toConnector, identity, toPin]);

  const selectedConnector = selection?.kind === "connector" ? connectors.find((item: any) => item.id === selection.id) : undefined;
  const selectedSplice = selection?.kind === "splice" ? splices.find((item: any) => item.id === selection.id) : undefined;
  const selectedWire = selection?.kind === "wire" ? wires.find((item: any) => item.id === selection.id) : undefined;
  const selectedPair = value && selectedWire ? wirePair(value, selectedWire.id) : undefined;
  const pairCandidates = useMemo(() => value && selectedWire ? pairCandidateWires(value, selectedWire.id) : [], [value, selectedWire?.id]);
  useEffect(() => {
    setDeletePending(null);
    setPairMate(selectedPair?.wire_ids?.find((id: string) => id !== selectedWire?.id) ?? "");
  }, [selection?.kind, selection?.id, selectedPair?.id]);

  const updateConnector = (index: number, update: Record<string, unknown>) => value && onChange({ ...value, connectors: connectors.map((item: any, i: number) => i === index ? { ...item, ...update } : item) });
  const updateProperties = (index: number, update: Record<string, unknown>) => {
    const properties = { ...(connectors[index].properties ?? {}), ...update };
    Object.keys(properties).forEach(key => properties[key] === undefined && delete properties[key]);
    updateConnector(index, { properties });
  };
  const updateWire = (index: number, key: string, content: unknown) => {
    if (!value) return;
    const next = wires.map((wire: any, i: number) => i === index ? { ...wire } : wire);
    if (content === "" || content === undefined) delete next[index][key]; else next[index][key] = content;
    onChange({ ...value, wires: next });
  };
  const updateWireElectrical = (index: number, raw: string) => {
    if (!value) return; const next = wires.map((wire: any, i: number) => i === index ? { ...wire, electrical: { ...(wire.electrical ?? {}) } } : wire);
    if (!raw) { delete next[index].electrical.resistance_ohm; if (!Object.keys(next[index].electrical).length) delete next[index].electrical; }
    else next[index].electrical.resistance_ohm = Number(raw);
    onChange({ ...value, wires: next });
  };
  const applyMappings = () => {
    if (!value) return;
    try {
      if (!bulkFrom || !bulkTo || bulkFrom === bulkTo) throw new Error("Choose two different connectors.");
      const mapping = parsePinMappings(mappingText);
      const fromIds = new Set((connectors.find((item: any) => item.id === bulkFrom)?.pins ?? []).map((pin: any) => String(pin.id)));
      const toIds = new Set((connectors.find((item: any) => item.id === bulkTo)?.pins ?? []).map((pin: any) => String(pin.id)));
      for (const [a, b] of Object.entries(mapping)) if (!fromIds.has(a) || !toIds.has(b)) throw new Error(`Unknown pin in ${a}=${b}. Add it to the connector first.`);
      let next = value;
      const reconciled = reconcilePairWires(wires, bulkFrom, bulkTo, mapping);
      const retainedIds = new Set(reconciled.map((wire: any) => String(wire.id)));
      for (const wire of wires) if (!retainedIds.has(String(wire.id))) next = deleteHarnessWire(next, String(wire.id));
      onChange({ ...next, wires: reconciled }); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
  };
  const createWire = () => {
    if (!value) return;
    try {
      const id = wireId.trim() || nextHarnessId("W", issuedWireIds.current);
      const next = addHarnessWire(value, id, ownerEndpoint(fromConnector, fromPin), ownerEndpoint(toConnector, toPin));
      issuedWireIds.current.add(id); onChange(next); setWireId(""); setSelection({ kind: "wire", id }); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
  };
  const commitConnectorRename = (nextId: string) => {
    if (!value || !selectedConnector) return;
    try { onChange(renameHarnessConnector(value, selectedConnector.id, nextId)); issuedConnectorIds.current.add(nextId); setSelection({ kind: "connector", id: nextId }); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
  };
  const commitSpliceRename = (nextId: string) => {
    if (!value || !selectedSplice) return;
    try { onChange(renameHarnessSplice(value, selectedSplice.id, nextId)); issuedSpliceIds.current.add(nextId); setSelection({ kind: "splice", id: nextId }); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
  };
  const changePairKind = (kind: "none" | "differential" | "twisted") => {
    if (!value || !selectedWire) return;
    try {
      if (kind !== "none" && !pairMate) throw new Error("Choose the second wire before assigning a pair.");
      onChange(assignHarnessPair(value, selectedWire.id, pairMate, kind, { twisted: selectedPair?.twisted, twistPitchMm: selectedPair?.twist_pitch_mm })); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
  };
  const selectMate = (mate: string) => {
    setPairMate(mate);
    if (!value || !selectedWire || !selectedPair || !mate) return;
    try { onChange(assignHarnessPair(value, selectedWire.id, mate, selectedPair.kind, { twisted: selectedPair.twisted, twistPitchMm: selectedPair.twist_pitch_mm }, selectedPair.id)); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
  };

  return <section aria-label="Harness document"><h3>Harness document</h3>
    {!value ? <button type="button" className="spike-control--primary" onClick={() => onChange({ contract: "spike/harness/v1", id: `harness-${Date.now()}`, name: "New harness", connectors: [], wires: [] })}>Create harness</button> : <>
      <label>Name <input value={value.name ?? ""} onChange={event => onChange({ ...value, name: event.target.value })} /></label>
      <p>{connectors.length} connectors · {wires.length} wires · {value.splices?.length ?? 0} splices</p>
      <div className="harness-editor-workspace"><HarnessDiagram document={value} selection={selection} onSelect={setSelection} />
        <aside className="harness-inspector" aria-label="Harness selection inspector"><h4>Selection inspector</h4>
          {!selection && <p>Select a connector, splice, or individual wire in the diagram.</p>}
          {selectedConnector && <><p><b>{selectedConnector.name || selectedConnector.id}</b><br />{selectedConnector.pins?.length ?? 0} pins · {wires.filter((wire: any) => wire.from?.connector === selectedConnector.id || wire.to?.connector === selectedConnector.id).length} wires</p>
            <label>Connector ID<TableIdentityInput aria-label="Selected connector ID" value={selectedConnector.id} onCommit={commitConnectorRename} /></label>
            <label>Name<input value={selectedConnector.name ?? ""} onChange={event => updateConnector(connectors.indexOf(selectedConnector), { name: event.target.value })} /></label>
            <div className="harness-inspector-actions">{deletePending?.kind === "connector" && deletePending.id === selectedConnector.id ? <button type="button" className="spike-control--danger" onClick={() => { onChange(deleteHarnessConnector(value, selectedConnector.id)); setSelection(null); setDeletePending(null); }}>Delete connector and dependent wires</button> : <button type="button" className="spike-control--danger" onClick={() => setDeletePending(selection)}>Delete connector…</button>} {deletePending && <button type="button" onClick={() => setDeletePending(null)}>Cancel</button>}</div>
          </>}
          {selectedSplice && <><p><b>Splice {selectedSplice.id}</b><br />{wires.filter((wire: any) => wire.from?.splice === selectedSplice.id || wire.to?.splice === selectedSplice.id).length} branch wires</p>
            <label>Splice ID<TableIdentityInput aria-label="Selected splice ID" value={selectedSplice.id} onCommit={commitSpliceRename} /></label>
            <label>Part number<input value={selectedSplice.part_number ?? ""} onChange={event => onChange({ ...value, splices: splices.map((splice: any) => splice === selectedSplice ? { ...splice, part_number: event.target.value || undefined } : splice) })} /></label>
            <div className="harness-inspector-actions">{deletePending?.kind === "splice" && deletePending.id === selectedSplice.id ? <button type="button" className="spike-control--danger" onClick={() => { onChange(deleteHarnessSplice(value, selectedSplice.id)); setSelection(null); setDeletePending(null); }}>Delete splice and dependent wires</button> : <button type="button" className="spike-control--danger" onClick={() => setDeletePending(selection)}>Delete splice…</button>} {deletePending && <button type="button" onClick={() => setDeletePending(null)}>Cancel</button>}</div>
          </>}
          {selectedWire && <><p><b>{selectedWire.id}</b><br />{endpointLabel(selectedWire.from)} → {endpointLabel(selectedWire.to)}</p>
            <label>Wire role<select value={selectedWire.role ?? "unspecified"} onChange={event => onChange(setHarnessWireRole(value, selectedWire.id, event.target.value as HarnessWireRole))}>{wireRoles.map(role => <option key={role.value} value={role.value}>{role.label}</option>)}</select></label>
            {(selectedWire.role === "power" || selectedWire.role === "signal") && <label>Explicit return wire<select value={selectedWire.return_wire_id ?? ""} onChange={event => updateWire(wires.indexOf(selectedWire), "return_wire_id", event.target.value || undefined)}><option value="">No explicit return</option>{wires.filter((wire: any) => wire.id !== selectedWire.id && wire.role === "return").map((wire: any) => <option key={wire.id} value={wire.id}>{wire.id}</option>)}</select></label>}
            <label>Pair mate<select value={pairMate} onChange={event => selectMate(event.target.value)}><option value="">Select a same-span wire</option>{pairCandidates.map((wire: any) => <option key={wire.id} value={wire.id}>{wire.id}</option>)}</select></label>
            <label>Pair membership<select value={selectedPair?.kind ?? "none"} onChange={event => changePairKind(event.target.value as "none" | "differential" | "twisted")}><option value="none">No pair</option><option value="differential">Differential pair (+ / − order)</option><option value="twisted">Twisted pair</option></select></label>
            {selectedPair?.kind === "differential" && <label><span><input type="checkbox" checked={!!selectedPair.twisted} onChange={event => onChange(updateHarnessPair(value, selectedPair.id, { twisted: event.target.checked, twistPitchMm: selectedPair.twist_pitch_mm }))} /> Physically twisted differential pair</span></label>}
            {selectedPair?.twisted && <label>Twist pitch (mm)<input type="number" min="0" step="any" value={selectedPair.twist_pitch_mm ?? ""} onChange={event => onChange(updateHarnessPair(value, selectedPair.id, { twisted: true, twistPitchMm: optionalNumber(event.target.value) }))} /></label>}
            <div className="harness-inspector-actions">{deletePending?.kind === "wire" && deletePending.id === selectedWire.id ? <button type="button" className="spike-control--danger" onClick={() => { onChange(deleteHarnessWire(value, selectedWire.id)); setSelection(null); setDeletePending(null); }}>Delete wire</button> : <button type="button" className="spike-control--danger" onClick={() => setDeletePending(selection)}>Delete wire…</button>} {deletePending && <button type="button" onClick={() => setDeletePending(null)}>Cancel</button>}</div>
          </>}
        </aside>
      </div>
      <h4>Add an individual wire</h4><div className="harness-wire-creator"><label>Wire ID<input value={wireId} placeholder={nextHarnessId("W", issuedWireIds.current)} onChange={event => setWireId(event.target.value)} /></label><label>From endpoint<select value={fromConnector} onChange={event => setFromConnector(event.target.value)}>{connectors.map((item: any) => <option key={`connector:${item.id}`} value={item.id}>Connector {item.id}</option>)}{splices.map((item: any) => <option key={`splice:${item.id}`} value={spliceOwner(item.id)}>Splice {item.id}</option>)}</select></label><label>From pin<select value={fromPin} disabled={!!ownerSpliceId(fromConnector)} onChange={event => setFromPin(event.target.value)}>{ownerSpliceId(fromConnector) ? <option value="">Junction</option> : fromPins.map((pin: any) => <option key={pin.id}>{pin.id}</option>)}</select></label><label>To endpoint<select value={toConnector} onChange={event => setToConnector(event.target.value)}>{connectors.map((item: any) => <option key={`connector:${item.id}`} value={item.id}>Connector {item.id}</option>)}{splices.map((item: any) => <option key={`splice:${item.id}`} value={spliceOwner(item.id)}>Splice {item.id}</option>)}</select></label><label>To pin<select value={toPin} disabled={!!ownerSpliceId(toConnector)} onChange={event => setToPin(event.target.value)}>{ownerSpliceId(toConnector) ? <option value="">Junction</option> : toPins.map((pin: any) => <option key={pin.id}>{pin.id}</option>)}</select></label><button type="button" className="spike-control--primary" disabled={!fromConnector || (!ownerSpliceId(fromConnector) && !fromPin) || !toConnector || (!ownerSpliceId(toConnector) && !toPin)} onClick={createWire}>Add wire</button></div>
      <h4>Connectors and contact assumptions</h4><p>Presets are editable engineering estimates, not manufacturer-guaranteed ratings. Replace them from the selected part datasheet or leave them unspecified.</p>
      <DataTable label="Harness connectors" className="data-table"><thead><tr><th>ID / name</th><th>Preset family</th><th>Contact R (Ω)</th><th>Pin width × height (mm)</th><th>Pins (comma separated)</th><th /></tr></thead><tbody>{connectors.map((connector: any, index: number) => { const props = connector.properties ?? {}; return <tr key={connector.id ?? index}><td><TableIdentityInput aria-label={`connector ${index + 1} id`} value={connector.id ?? ""} onCommit={id => { try { onChange(renameHarnessConnector(value, connector.id, id)); issuedConnectorIds.current.add(id); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); } }} /><input aria-label={`${connector.id} name`} value={connector.name ?? ""} onChange={event => updateConnector(index, { name: event.target.value })} /></td>
        <td><select aria-label={`${connector.id} preset`} value={props.connector_preset ?? "unspecified"} onChange={event => { const preset = CONNECTOR_PRESETS.find(item => item.id === event.target.value)!; updateProperties(index, { connector_preset: preset.id, connector_family: preset.family, contact_resistance_ohm: preset.contactResistanceOhm, pin_width_mm: preset.pinWidthMm, pin_height_mm: preset.pinHeightMm, estimate_note: preset.note }); }}>{CONNECTOR_PRESETS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select><small>{props.estimate_note}</small></td>
        <td><input aria-label={`${connector.id} contact resistance`} type="number" min="0" step="any" value={props.contact_resistance_ohm ?? ""} onChange={event => updateProperties(index, { contact_resistance_ohm: optionalNumber(event.target.value) })} /></td>
        <td><input aria-label={`${connector.id} pin width`} type="number" min="0" step="any" value={props.pin_width_mm ?? ""} onChange={event => updateProperties(index, { pin_width_mm: optionalNumber(event.target.value) })} /> × <input aria-label={`${connector.id} pin height`} type="number" min="0" step="any" value={props.pin_height_mm ?? ""} onChange={event => updateProperties(index, { pin_height_mm: optionalNumber(event.target.value) })} /></td>
        <td><input aria-label={`${connector.id} pins`} value={(connector.pins ?? []).map((pin: any) => pin.id).join(", ")} onChange={event => updateConnector(index, { pins: mergeConnectorPins(connector.pins ?? [], event.target.value.split(",").map(id => id.trim()).filter(Boolean)) })} /></td>
        <td><button type="button" onClick={() => setSelection({ kind: "connector", id: connector.id })}>Inspect</button></td></tr>; })}</tbody></DataTable>
      <button type="button" className="secondary-btn" onClick={() => { const id = nextHarnessId("J", issuedConnectorIds.current); issuedConnectorIds.current.add(id); onChange({ ...value, connectors: [...connectors, { id, name: id, pins: [{ id: "1" }] }] }); setSelection({ kind: "connector", id }); }}>Add connector</button>
      <h4>Splices</h4><DataTable label="Harness splices"><thead><tr><th>ID</th><th>Part number</th><th>Connected wires</th><th /></tr></thead><tbody>{splices.map((splice: any) => <tr key={splice.id}><td>{splice.id}</td><td>{splice.part_number || "Unspecified"}</td><td>{wires.filter((wire: any) => wire.from?.splice === splice.id || wire.to?.splice === splice.id).length}</td><td><button type="button" onClick={() => setSelection({ kind: "splice", id: splice.id })}>Inspect</button></td></tr>)}</tbody></DataTable>
      <button type="button" className="secondary-btn" onClick={() => { if (!value) return; const id = nextHarnessId("S", issuedSpliceIds.current); issuedSpliceIds.current.add(id); onChange(addHarnessSplice(value, id)); setSelection({ kind: "splice", id }); }}>Add splice</button>
      <h4>Connector-to-connector pin matching</h4><div className="field-row"><label>From <select value={bulkFrom} onChange={event => setBulkFrom(event.target.value)}>{connectors.map((item: any) => <option key={item.id}>{item.id}</option>)}</select></label><label>To <select value={bulkTo} onChange={event => setBulkTo(event.target.value)}>{connectors.map((item: any) => <option key={item.id}>{item.id}</option>)}</select></label></div>
      <textarea aria-label="Bulk pin mappings" rows={6} placeholder={'1=1\n2=2\n# source=destination'} value={mappingText} onChange={event => setMappingText(event.target.value)} />
      <button type="button" className="secondary-btn" onClick={() => { const map: Record<string, string> = {}; for (const wire of wires) if (wire.from?.connector === bulkFrom && wire.to?.connector === bulkTo) map[String(wire.from.pin)] = String(wire.to.pin); setMappingText(formatPinMappings(map)); }}>Load pair</button> <button type="button" className="secondary-btn" onClick={applyMappings}>Apply pair mappings</button>
      <DataTable label="Harness wires"><thead><tr><th>Wire</th><th>From</th><th>To</th><th>Role</th><th>Net</th><th>Length (mm)</th><th>Explicit DC R (Ω)</th><th /></tr></thead><tbody>{wires.map((wire: any, index: number) => wire && typeof wire === "object" ? <tr key={wire.id ?? index}><td>{wire.id}</td><td>{endpointLabel(wire.from)}</td><td>{endpointLabel(wire.to)}</td><td><select aria-label={`${wire.id} role`} value={wire.role ?? "unspecified"} onChange={event => onChange(setHarnessWireRole(value, wire.id, event.target.value as HarnessWireRole))}>{wireRoles.map(role => <option key={role.value} value={role.value}>{role.label}</option>)}</select></td><td><input aria-label={`${wire.id} net`} value={wire.net ?? ""} onChange={event => updateWire(index, "net", event.target.value)} /></td><td><input aria-label={`${wire.id} length`} type="number" min="0" value={wire.length_mm ?? ""} onChange={event => updateWire(index, "length_mm", optionalNumber(event.target.value))} /></td><td><input aria-label={`${wire.id} resistance`} type="number" min="0" step="any" value={wire.electrical?.resistance_ohm ?? ""} onChange={event => updateWireElectrical(index, event.target.value)} /></td><td><button type="button" onClick={() => setSelection({ kind: "wire", id: wire.id })}>Inspect</button></td></tr> : <tr key={index}><td colSpan={8}>Invalid wire entry. Edit the document and run validation.</td></tr>)}</tbody></DataTable>
      <HarnessPiPanel value={value} onChange={onChange} />
      <HarnessSignalPanel value={value} onChange={onChange} />
      <details><summary>Edit complete document as JSON</summary><button type="button" onClick={() => setDraft(JSON.stringify(value, null, 2))}>Load document for editing</button><textarea aria-label="Harness JSON" rows={16} style={{ width: "100%" }} value={draft} onChange={event => setDraft(event.target.value)} /><button type="button" onClick={() => { try { const parsed = JSON.parse(draft); if (parsed?.contract !== "spike/harness/v1" || !Array.isArray(parsed.connectors) || !Array.isArray(parsed.wires)) throw new Error("Expected a SPIKE harness document with connectors and wires."); onChange(parsed); setError(""); } catch (caught) { setError(String(caught)); } }}>Apply draft</button></details>
      {error && <p role="alert">{error}</p>}<p>Run “Check harness connectivity” after editing. Save the project to retain this document.</p>
    </>}
  </section>;
}
