import { useEffect, useState } from "react";
import DataTable from "./DataTable";
import TableIdentityInput from "./TableIdentityInput";
import { CONNECTOR_PRESETS, formatPinMappings, mergeConnectorPins, parsePinMappings, reconcilePairWires } from "./connectorPresets";
import HarnessPiPanel from "./HarnessPiPanel";

type Props = { value: Record<string, any> | null; onChange: (value: Record<string, any>) => void };
const optionalNumber = (raw: string) => raw === "" ? undefined : Number(raw);

export default function HarnessDocumentEditor({ value, onChange }: Props) {
  const [draft, setDraft] = useState(""); const [error, setError] = useState("");
  const [fromConnector, setFromConnector] = useState(""); const [toConnector, setToConnector] = useState(""); const [mappingText, setMappingText] = useState("");
  const connectors = value && Array.isArray(value.connectors) ? value.connectors : [];
  useEffect(() => {
    if (!connectors.some((item: any) => item.id === fromConnector)) setFromConnector(connectors[0]?.id ?? "");
    if (!connectors.some((item: any) => item.id === toConnector)) setToConnector(connectors[1]?.id ?? connectors[0]?.id ?? "");
  }, [value, fromConnector, toConnector]);
  const updateConnector = (index: number, update: Record<string, unknown>) => value && onChange({ ...value, connectors: connectors.map((item: any, i: number) => i === index ? { ...item, ...update } : item) });
  const updateProperties = (index: number, update: Record<string, unknown>) => {
    const properties = { ...(connectors[index].properties ?? {}), ...update };
    Object.keys(properties).forEach(key => properties[key] === undefined && delete properties[key]);
    updateConnector(index, { properties });
  };
  const updateWire = (index: number, key: string, content: string) => {
    if (!value) return; const wires = value.wires.map((wire: any, i: number) => i === index ? { ...wire } : wire);
    if (!content) delete wires[index][key]; else wires[index][key] = key === "length_mm" ? Number(content) : content;
    onChange({ ...value, wires });
  };
  const updateWireElectrical = (index: number, raw: string) => {
    if (!value) return; const wires = value.wires.map((wire: any, i: number) => i === index ? { ...wire, electrical: { ...(wire.electrical ?? {}) } } : wire);
    if (!raw) { delete wires[index].electrical.resistance_ohm; if (!Object.keys(wires[index].electrical).length) delete wires[index].electrical; }
    else wires[index].electrical.resistance_ohm = Number(raw);
    onChange({ ...value, wires });
  };
  const applyMappings = () => {
    if (!value) return;
    try {
      if (!fromConnector || !toConnector || fromConnector === toConnector) throw new Error("Choose two different connectors.");
      const mapping = parsePinMappings(mappingText);
      const fromPins = new Set((connectors.find((item: any) => item.id === fromConnector)?.pins ?? []).map((pin: any) => String(pin.id)));
      const toPins = new Set((connectors.find((item: any) => item.id === toConnector)?.pins ?? []).map((pin: any) => String(pin.id)));
      for (const [a, b] of Object.entries(mapping)) if (!fromPins.has(a) || !toPins.has(b)) throw new Error(`Unknown pin in ${a}=${b}. Add it to the connector first.`);
      onChange({ ...value, wires: reconcilePairWires(value.wires, fromConnector, toConnector, mapping) }); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
  };
  return <section aria-label="Harness document"><h3>Harness document</h3>
    {!value ? <button onClick={() => onChange({ contract: "spike/harness/v1", id: `harness-${Date.now()}`, name: "New harness", connectors: [], wires: [] })}>Create harness</button> : <>
      <label>Name <input value={value.name ?? ""} onChange={e => onChange({ ...value, name: e.target.value })} /></label>
      <p>{connectors.length} connectors · {value.wires?.length ?? 0} wires · {value.splices?.length ?? 0} splices</p>
      <h4>Connectors and contact assumptions</h4><p>Presets are editable engineering estimates, not manufacturer-guaranteed ratings. Replace them from the selected part datasheet or leave them unspecified.</p>
      <DataTable label="Harness connectors" className="data-table"><thead><tr><th>ID / name</th><th>Preset family</th><th>Contact R (Ω)</th><th>Pin width × height (mm)</th><th>Pins (comma separated)</th><th /></tr></thead><tbody>{connectors.map((connector: any, index: number) => {
        const props = connector.properties ?? {};
        return <tr key={connector.id ?? index}><td><TableIdentityInput aria-label={`connector ${index + 1} id`} value={connector.id ?? ""} onCommit={id => updateConnector(index, { id })} validate={id => !id.trim() ? "Connector ID cannot be blank." : id !== connector.id && connectors.some((item: any) => item.id === id) ? "Connector ID already exists." : ""} /><input aria-label={`${connector.id} name`} value={connector.name ?? ""} onChange={e => updateConnector(index, { name: e.target.value })} /></td>
          <td><select aria-label={`${connector.id} preset`} value={props.connector_preset ?? "unspecified"} onChange={e => { const preset = CONNECTOR_PRESETS.find(item => item.id === e.target.value)!; updateProperties(index, { connector_preset: preset.id, connector_family: preset.family, contact_resistance_ohm: preset.contactResistanceOhm, pin_width_mm: preset.pinWidthMm, pin_height_mm: preset.pinHeightMm, estimate_note: preset.note }); }}>{CONNECTOR_PRESETS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select><small>{props.estimate_note}</small></td>
          <td><input aria-label={`${connector.id} contact resistance`} type="number" min="0" step="any" value={props.contact_resistance_ohm ?? ""} onChange={e => updateProperties(index, { contact_resistance_ohm: optionalNumber(e.target.value) })} /></td>
          <td><input aria-label={`${connector.id} pin width`} type="number" min="0" step="any" value={props.pin_width_mm ?? ""} onChange={e => updateProperties(index, { pin_width_mm: optionalNumber(e.target.value) })} /> × <input aria-label={`${connector.id} pin height`} type="number" min="0" step="any" value={props.pin_height_mm ?? ""} onChange={e => updateProperties(index, { pin_height_mm: optionalNumber(e.target.value) })} /></td>
          <td><input aria-label={`${connector.id} pins`} value={(connector.pins ?? []).map((pin: any) => pin.id).join(", ")} onChange={e => updateConnector(index, { pins: mergeConnectorPins(connector.pins ?? [], e.target.value.split(",").map(id => id.trim()).filter(Boolean)) })} /></td>
          <td><button className="secondary-btn" onClick={() => onChange({ ...value, connectors: connectors.filter((_: any, i: number) => i !== index) })}>Remove</button></td></tr>;
      })}</tbody></DataTable>
      <button className="secondary-btn" onClick={() => onChange({ ...value, connectors: [...connectors, { id: `J${connectors.length + 1}`, pins: [{ id: "1" }] }] })}>Add connector</button>
      <h4>Connector-to-connector pin matching</h4><div className="field-row"><label>From <select value={fromConnector} onChange={e => setFromConnector(e.target.value)}>{connectors.map((item: any) => <option key={item.id}>{item.id}</option>)}</select></label><label>To <select value={toConnector} onChange={e => setToConnector(e.target.value)}>{connectors.map((item: any) => <option key={item.id}>{item.id}</option>)}</select></label></div>
      <textarea aria-label="Bulk pin mappings" rows={6} placeholder={'1=1\n2=2\n# source=destination'} value={mappingText} onChange={e => setMappingText(e.target.value)} />
      <button className="secondary-btn" onClick={() => { const map: Record<string, string> = {}; for (const wire of value.wires ?? []) if (wire.from?.connector === fromConnector && wire.to?.connector === toConnector) map[String(wire.from.pin)] = String(wire.to.pin); setMappingText(formatPinMappings(map)); }}>Load pair</button> <button className="secondary-btn" onClick={applyMappings}>Apply pair mappings</button>
      <DataTable label="Harness wires"><thead><tr><th>Wire</th><th>From</th><th>To</th><th>Net</th><th>Length (mm)</th><th>Explicit DC R (Ω)</th></tr></thead><tbody>{(value.wires ?? []).map((wire: any, index: number) => wire && typeof wire === "object" ? <tr key={wire.id ?? index}><td>{wire.id}</td><td>{wire.from?.connector ? `${wire.from.connector} / ${wire.from.pin}` : `Splice ${wire.from?.splice ?? "?"}`}</td><td>{wire.to?.connector ? `${wire.to.connector} / ${wire.to.pin}` : `Splice ${wire.to?.splice ?? "?"}`}</td><td><input aria-label={`${wire.id} net`} value={wire.net ?? ""} onChange={e => updateWire(index, "net", e.target.value)} /></td><td><input aria-label={`${wire.id} length`} type="number" min="0" value={wire.length_mm ?? ""} onChange={e => updateWire(index, "length_mm", e.target.value)} /></td><td><input aria-label={`${wire.id} resistance`} type="number" min="0" step="any" value={wire.electrical?.resistance_ohm ?? ""} onChange={e => updateWireElectrical(index, e.target.value)} /></td></tr> : <tr key={index}><td colSpan={6}>Invalid wire entry. Edit the document and run validation.</td></tr>)}</tbody></DataTable>
      <HarnessPiPanel value={value} onChange={onChange} />
      <details><summary>Edit complete document as JSON</summary><button onClick={() => setDraft(JSON.stringify(value, null, 2))}>Load document for editing</button><textarea aria-label="Harness JSON" rows={16} style={{ width: "100%" }} value={draft} onChange={e => setDraft(e.target.value)} /><button onClick={() => { try { const parsed = JSON.parse(draft); if (parsed?.contract !== "spike/harness/v1" || !Array.isArray(parsed.connectors) || !Array.isArray(parsed.wires)) throw new Error("Expected a SPIKE harness document with connectors and wires."); onChange(parsed); setError(""); } catch (caught) { setError(String(caught)); } }}>Apply draft</button></details>
      {error && <p role="alert">{error}</p>}<p>Run “Check harness connectivity” after editing. Save the project to retain this document.</p>
    </>}
  </section>;
}
