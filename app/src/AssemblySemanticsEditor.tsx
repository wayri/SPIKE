import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { Link2, Plus } from "lucide-react";
import type { AssemblyIr } from "./mcadAssembly";
import { runNativeProjectWorker } from "./workerBridge";

type Row = Record<string, unknown> & { id: string };

type Props = {
  projectPath: string | null;
  projectManifestDigest: string | null;
  assemblyIr: AssemblyIr;
  onUpdated: () => Promise<void>;
  onStatus: (message: string) => void;
};

const rows = (value: unknown): Row[] => Array.isArray(value)
  ? value.filter(item => item && typeof item === "object" && !Array.isArray(item) && typeof (item as Row).id === "string") as Row[]
  : [];
const text = (value: unknown) => typeof value === "string" ? value : "";
const number = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : "";
const optionalNumber = (value: string): number | null => value.trim() === "" ? null : Number(value);
const identity = (prefix: string) => `${prefix}-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;
const base = (id: string, name = ""): Row => ({ id, source_id: "", name, extensions: {} });

export default function AssemblySemanticsEditor({ projectPath, projectManifestDigest, assemblyIr, onUpdated, onStatus }: Props) {
  const [materials, setMaterials] = useState<Row[]>([]);
  const [contacts, setContacts] = useState<Row[]>([]);
  const [bonds, setBonds] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setMaterials(rows(assemblyIr.materials));
    setContacts(rows(assemblyIr.thermal_contacts));
    setBonds(rows(assemblyIr.electrical_bonds));
  }, [assemblyIr]);

  const patch = (setter: Dispatch<SetStateAction<Row[]>>, id: string, update: Record<string, unknown>) =>
    setter(current => current.map(item => item.id === id ? { ...item, ...update } : item));
  const remove = (setter: Dispatch<SetStateAction<Row[]>>, id: string) =>
    setter(current => current.filter(item => item.id !== id));

  const save = async () => {
    if (!projectPath || !projectManifestDigest || busy) return;
    setBusy(true);
    try {
      const response = await runNativeProjectWorker({
        method: "update_assembly_semantics_in_project",
        params: {
          project_path: projectPath,
          expected_manifest_payload_sha256: projectManifestDigest,
          materials,
          thermal_contacts: contacts,
          electrical_bonds: bonds,
        },
      });
      if (!response.ok) throw new Error(response.error ?? "Assembly semantics were rejected.");
      await onUpdated();
      onStatus(`Saved ${materials.length} assembly materials, ${contacts.length} thermal contacts, and ${bonds.length} electrical bonds.`);
    } catch (error) {
      onStatus(error instanceof Error ? `Assembly semantics update failed: ${error.message}` : "Assembly semantics update failed");
    } finally {
      setBusy(false);
    }
  };

  return <section className="mcad-semantics-editor">
    <h3><Link2 size={15} /> Explicit assembly semantics</h3>
    <p className="mcad-gate">Endpoint strings and reviewed properties are retained as setup data. They do not create contact geometry or qualify a solver.</p>

    <h4>Materials</h4>
    <table className="data-table"><thead><tr><th>ID</th><th>Name</th><th>Class</th><th>Thermal k (W/mK)</th><th /></tr></thead><tbody>
      {materials.map(item => <tr key={item.id}>
        <td><input value={item.id} onChange={event => patch(setMaterials, item.id, { id: event.target.value })} /></td>
        <td><input value={text(item.name)} onChange={event => patch(setMaterials, item.id, { name: event.target.value })} /></td>
        <td><input value={text(item.material_class)} onChange={event => patch(setMaterials, item.id, { material_class: event.target.value })} /></td>
        <td><input type="number" min="0" step="any" value={number(item.thermal_conductivity_w_per_mk)} onChange={event => patch(setMaterials, item.id, { thermal_conductivity_w_per_mk: optionalNumber(event.target.value) })} /></td>
        <td><button className="secondary-btn" onClick={() => remove(setMaterials, item.id)}>Remove</button></td>
      </tr>)}
    </tbody></table>
    <button className="secondary-btn" onClick={() => setMaterials(current => [...current, { ...base(identity("material"), "Assembly material"), material_class: "unspecified", thermal_conductivity_w_per_mk: null }])}><Plus size={13} /> Add material</button>

    <h4>Thermal contacts</h4>
    <table className="data-table"><thead><tr><th>ID</th><th>Endpoint A</th><th>Endpoint B</th><th>Type</th><th>Material</th><th>Area mm²</th><th>R K/W</th><th /></tr></thead><tbody>
      {contacts.map(item => <tr key={item.id}>
        <td><input value={item.id} onChange={event => patch(setContacts, item.id, { id: event.target.value })} /></td>
        {(["endpoint_a", "endpoint_b", "contact_type", "material_id"] as const).map(field => <td key={field}><input value={text(item[field])} onChange={event => patch(setContacts, item.id, { [field]: event.target.value })} /></td>)}
        {(["contact_area_mm2", "thermal_resistance_k_per_w"] as const).map(field => <td key={field}><input type="number" min="0" step="any" value={number(item[field])} onChange={event => patch(setContacts, item.id, { [field]: optionalNumber(event.target.value) })} /></td>)}
        <td><button className="secondary-btn" onClick={() => remove(setContacts, item.id)}>Remove</button></td>
      </tr>)}
    </tbody></table>
    <button className="secondary-btn" onClick={() => setContacts(current => [...current, { ...base(identity("thermal-contact"), "Thermal contact"), endpoint_a: "", endpoint_b: "", contact_type: "mechanical", material_id: "", contact_area_mm2: null, thermal_resistance_k_per_w: null }])}><Plus size={13} /> Add thermal contact</button>

    <h4>Electrical bonds</h4>
    <table className="data-table"><thead><tr><th>ID</th><th>Endpoint A</th><th>Endpoint B</th><th>Type</th><th>Electrical material</th><th>Thermal material</th><th>Area mm²</th><th>Thickness mm</th><th>R Ω</th><th /></tr></thead><tbody>
      {bonds.map(item => <tr key={item.id}>
        <td><input value={item.id} onChange={event => patch(setBonds, item.id, { id: event.target.value })} /></td>
        {(["endpoint_a", "endpoint_b", "bond_type", "electrical_material_id", "thermal_material_id"] as const).map(field => <td key={field}><input value={text(item[field])} onChange={event => patch(setBonds, item.id, { [field]: event.target.value })} /></td>)}
        {(["contact_area_mm2", "thickness_mm", "electrical_resistance_ohm"] as const).map(field => <td key={field}><input type="number" min="0" step="any" value={number(item[field])} onChange={event => patch(setBonds, item.id, { [field]: optionalNumber(event.target.value) })} /></td>)}
        <td><button className="secondary-btn" onClick={() => remove(setBonds, item.id)}>Remove</button></td>
      </tr>)}
    </tbody></table>
    <button className="secondary-btn" onClick={() => setBonds(current => [...current, { ...base(identity("electrical-bond"), "Electrical bond"), endpoint_a: "", endpoint_b: "", bond_type: "electrical", electrical_material_id: "", thermal_material_id: "", contact_area_mm2: null, thickness_mm: null, electrical_resistance_ohm: null }])}><Plus size={13} /> Add electrical bond</button>

    <div><button className="run-btn" disabled={!projectPath || !projectManifestDigest || busy} onClick={() => void save()}>{busy ? "Saving semantics..." : "Save assembly semantics"}</button></div>
  </section>;
}
