import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { Crosshair, Magnet, Plus, ShieldCheck } from "lucide-react";
import type { AssemblyIr } from "./mcadAssembly";
import {
  topologyEntityOptions,
  type AssemblyPackageShapesIndex,
  type TopologyBinding,
  type TopologyConstraint,
  type TopologyKind,
  type TopologyReference,
} from "./assemblyPackageShapes";
import { runNativeProjectWorker } from "./workerBridge";

type Props = {
  projectPath: string | null;
  projectManifestDigest: string | null;
  assemblyIr: AssemblyIr;
  index: AssemblyPackageShapesIndex;
  focusedReference: TopologyReference | null;
  onUpdated: () => Promise<void>;
  onStatus: (message: string) => void;
};

const ALL = new Set<TopologyKind>(["solid", "shell", "face", "edge", "axis", "vertex"]);
const FACE = new Set<TopologyKind>(["face"]);
const ELECTRICAL = new Set<TopologyKind>(["face", "edge", "vertex"]);
const constraintKinds: TopologyConstraint["kind"][] = ["face", "edge", "axis", "concentric", "coincident", "distance", "angle"];
const identity = (prefix: string) => `${prefix}-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;

function allowedForConstraint(kind: TopologyConstraint["kind"]): ReadonlySet<TopologyKind> {
  if (kind === "face") return FACE;
  if (kind === "edge") return new Set<TopologyKind>(["edge"]);
  if (kind === "axis" || kind === "concentric") return new Set<TopologyKind>(["axis"]);
  return ALL;
}

function ReferenceSelect({ value, options, onChange }: {
  value: TopologyReference | undefined;
  options: ReturnType<typeof topologyEntityOptions>;
  onChange: (reference: TopologyReference) => void;
}) {
  const selectedPresent = options.some(option => option.key === value?.topology_id);
  return <select value={value?.topology_id ?? ""} onChange={event => {
    const option = options.find(item => item.key === event.target.value);
    if (option) onChange(option.reference);
  }}>
    <option value="">Select exact topology</option>
    {value && !selectedPresent && <option value={value.topology_id}>{value.part_id} · {value.topology_kind} · {value.topology_id}</option>}
    {options.map(option => <option key={option.key} value={option.key}>{option.label}</option>)}
  </select>;
}

export default function AssemblyTopologyEditor({ projectPath, projectManifestDigest, assemblyIr, index, focusedReference, onUpdated, onStatus }: Props) {
  const [constraints, setConstraints] = useState<TopologyConstraint[]>([]);
  const [thermalBindings, setThermalBindings] = useState<TopologyBinding[]>([]);
  const [electricalBindings, setElectricalBindings] = useState<TopologyBinding[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setConstraints(structuredClone(index.constraints));
    setThermalBindings(structuredClone(index.thermal_contact_bindings));
    setElectricalBindings(structuredClone(index.electrical_bond_bindings));
  }, [index]);
  useEffect(() => {
    if (focusedReference) setQuery(focusedReference.topology_id);
  }, [focusedReference]);

  const options = useMemo(() => ({
    all: topologyEntityOptions(index, ALL, query),
    face: topologyEntityOptions(index, FACE, query),
    electrical: topologyEntityOptions(index, ELECTRICAL, query),
  }), [index, query]);
  const topologyCount = index.shapes.reduce((sum, shape) => sum + shape.entities.length, 0);
  const contactIds = (assemblyIr.thermal_contacts ?? []).flatMap(item => typeof item.id === "string" ? [item.id] : []);
  const bondIds = (assemblyIr.electrical_bonds ?? []).flatMap(item => typeof item.id === "string" ? [item.id] : []);
  const patchConstraint = (constraintId: string, update: Partial<TopologyConstraint>) => setConstraints(current => current.map(item => item.constraint_id === constraintId ? { ...item, ...update } : item));
  const patchBinding = (setter: Dispatch<SetStateAction<TopologyBinding[]>>, entityId: string, update: Partial<TopologyBinding>) => setter(current => current.map(item => item.assembly_entity_id === entityId ? { ...item, ...update } : item));

  const addConstraint = () => {
    const first = options.face[0]?.reference ?? options.all[0]?.reference;
    if (!first) return;
    const second = (options.face.length > 1 ? options.face : options.all).find(item => item.reference.part_id !== first.part_id)?.reference;
    setConstraints(current => [...current, {
      constraint_id: identity("topology-constraint"), kind: "face",
      references: second ? [first, second] : [first], value_mm: null, value_deg: null, status: "defined",
    }]);
  };
  const addBinding = (kind: "thermal" | "electrical") => {
    const choices = kind === "thermal" ? options.face : options.electrical;
    const ids = kind === "thermal" ? contactIds : bondIds;
    const used = new Set((kind === "thermal" ? thermalBindings : electricalBindings).map(item => item.assembly_entity_id));
    const entityId = ids.find(id => !used.has(id));
    if (!entityId || choices.length < 2) return;
    const binding = { assembly_entity_id: entityId, endpoint_a: choices[0].reference, endpoint_b: choices[1].reference };
    (kind === "thermal" ? setThermalBindings : setElectricalBindings)(current => [...current, binding]);
  };

  const save = async () => {
    if (!projectPath || !projectManifestDigest || busy) return;
    setBusy(true);
    try {
      const response = await runNativeProjectWorker({
        method: "update_assembly_topology_setup_in_project",
        params: {
          project_path: projectPath,
          expected_manifest_payload_sha256: projectManifestDigest,
          constraints,
          thermal_contact_bindings: thermalBindings,
          electrical_bond_bindings: electricalBindings,
        },
      });
      if (!response.ok) throw new Error(response.error ?? "Exact topology setup was rejected.");
      await onUpdated();
      onStatus(`Saved ${constraints.length} topology definitions, ${thermalBindings.length} thermal bindings, and ${electricalBindings.length} electrical bindings. No solver geometry was inferred.`);
    } catch (error) {
      onStatus(error instanceof Error ? `Exact topology setup failed: ${error.message}` : "Exact topology setup failed");
    } finally {
      setBusy(false);
    }
  };

  const applyConstraint = async (constraint: TopologyConstraint) => {
    if (!projectPath || !projectManifestDigest || busy || constraint.references.length !== 2) return;
    setBusy(true);
    try {
      const response = await runNativeProjectWorker({
        method: "apply_assembly_geometric_constraint_in_project",
        params: {
          project_path: projectPath,
          expected_manifest_payload_sha256: projectManifestDigest,
          constraint_id: constraint.constraint_id,
          moving_part_id: constraint.references[1].part_id,
        },
      });
      if (!response.ok) throw new Error(response.error ?? "Exact geometric constraint application was rejected.");
      await onUpdated();
      onStatus(`Applied ${constraint.kind} ${constraint.constraint_id}: endpoint B moved to endpoint A from exact BREP descriptors. This was one deterministic snap, not a constraint-graph, collision, contact, or solver solve.`);
    } catch (error) {
      onStatus(error instanceof Error ? `Exact geometric snap failed: ${error.message}` : "Exact geometric snap failed");
    } finally {
      setBusy(false);
    }
  };

  return <section className="mcad-semantics-editor mcad-topology-editor">
    <h3><Crosshair size={15} /> Exact topology-addressed setup</h3>
    <p className="mcad-gate"><ShieldCheck size={13} /> {index.shapes.length} digest-bound package shapes expose {topologyCount.toLocaleString()} owned selectors. Newly extracted analytic selectors can drive one explicit B-to-A snap. Selection has no triangle picking, placement solve, collision/contact solve, mesh qualification, or solver readiness; the snap is exact descriptor math, not a graph solve.</p>
    <label>FILTER EXACT SELECTORS<input value={query} onChange={event => setQuery(event.target.value)} placeholder="Part, kind, native ID, or topology ID" /></label>
    <small>Each selector list shows at most 200 exact matches. Refine the filter to address another owned entity.</small>
    {focusedReference && <p className="mcad-gate">Scene-selected exact {focusedReference.topology_kind}: <code>{focusedReference.topology_id}</code>. Use it in a typed definition below; selection alone does not apply or solve a constraint.</p>}

    <h4>Topology constraints</h4>
    <table className="data-table"><thead><tr><th>ID</th><th>Kind</th><th>Endpoint A (anchor)</th><th>Endpoint B (moves)</th><th>Value</th><th /></tr></thead><tbody>
      {constraints.map(item => {
        const scoped = topologyEntityOptions(index, allowedForConstraint(item.kind), query);
        const persisted = index.constraints.find(candidate => candidate.constraint_id === item.constraint_id);
        const applicable = item.references.length === 2
          && item.references[0].part_id !== item.references[1].part_id
          && item.references.every(reference => index.shapes.find(shape => shape.shape_id === reference.shape_id)?.entities.find(entity => entity.topology_id === reference.topology_id)?.geometry?.representation !== undefined)
          && JSON.stringify(persisted) === JSON.stringify(item);
        return <tr key={item.constraint_id}>
          <td><input value={item.constraint_id} onChange={event => patchConstraint(item.constraint_id, { constraint_id: event.target.value })} /></td>
          <td><select value={item.kind} onChange={event => {
            const kind = event.target.value as TopologyConstraint["kind"];
            patchConstraint(item.constraint_id, { kind, value_mm: kind === "distance" ? 0 : null, value_deg: kind === "angle" ? 0 : null });
          }}>{constraintKinds.map(kind => <option key={kind}>{kind}</option>)}</select></td>
          <td><ReferenceSelect value={item.references[0]} options={scoped} onChange={reference => patchConstraint(item.constraint_id, { references: [reference, ...item.references.slice(1)] })} /></td>
          <td><ReferenceSelect value={item.references[1]} options={scoped} onChange={reference => patchConstraint(item.constraint_id, { references: [item.references[0], reference] })} /></td>
          <td>{item.kind === "distance" ? <input type="number" min="0" step="any" value={item.value_mm ?? 0} onChange={event => patchConstraint(item.constraint_id, { value_mm: Number(event.target.value) })} /> : item.kind === "angle" ? <input type="number" min="0" max="180" step="any" value={item.value_deg ?? 0} onChange={event => patchConstraint(item.constraint_id, { value_deg: Number(event.target.value) })} /> : "—"}</td>
          <td><button className="secondary-btn" disabled={!applicable || busy} title={applicable ? "Move endpoint B to endpoint A using exact BREP descriptors" : "Save a valid two-part descriptor-backed definition before applying"} onClick={() => void applyConstraint(item)}><Magnet size={13} /> Apply B→A</button> <button className="secondary-btn" onClick={() => setConstraints(current => current.filter(row => row.constraint_id !== item.constraint_id))}>Remove</button></td>
        </tr>;
      })}
    </tbody></table>
    <button className="secondary-btn" onClick={addConstraint} disabled={!options.all.length}><Plus size={13} /> Add topology definition</button>

    <h4>Thermal contact face bindings</h4>
    <table className="data-table"><thead><tr><th>Contact ID</th><th>Face A</th><th>Face B</th><th /></tr></thead><tbody>{thermalBindings.map(item => <tr key={item.assembly_entity_id}>
      <td><select value={item.assembly_entity_id} onChange={event => patchBinding(setThermalBindings, item.assembly_entity_id, { assembly_entity_id: event.target.value })}>{contactIds.map(id => <option key={id}>{id}</option>)}</select></td>
      <td><ReferenceSelect value={item.endpoint_a} options={options.face} onChange={reference => patchBinding(setThermalBindings, item.assembly_entity_id, { endpoint_a: reference })} /></td>
      <td><ReferenceSelect value={item.endpoint_b} options={options.face} onChange={reference => patchBinding(setThermalBindings, item.assembly_entity_id, { endpoint_b: reference })} /></td>
      <td><button className="secondary-btn" onClick={() => setThermalBindings(current => current.filter(row => row.assembly_entity_id !== item.assembly_entity_id))}>Remove</button></td>
    </tr>)}</tbody></table>
    <button className="secondary-btn" onClick={() => addBinding("thermal")} disabled={!contactIds.length || options.face.length < 2}><Plus size={13} /> Bind thermal contact faces</button>

    <h4>Electrical bond topology bindings</h4>
    <table className="data-table"><thead><tr><th>Bond ID</th><th>Endpoint A</th><th>Endpoint B</th><th /></tr></thead><tbody>{electricalBindings.map(item => <tr key={item.assembly_entity_id}>
      <td><select value={item.assembly_entity_id} onChange={event => patchBinding(setElectricalBindings, item.assembly_entity_id, { assembly_entity_id: event.target.value })}>{bondIds.map(id => <option key={id}>{id}</option>)}</select></td>
      <td><ReferenceSelect value={item.endpoint_a} options={options.electrical} onChange={reference => patchBinding(setElectricalBindings, item.assembly_entity_id, { endpoint_a: reference })} /></td>
      <td><ReferenceSelect value={item.endpoint_b} options={options.electrical} onChange={reference => patchBinding(setElectricalBindings, item.assembly_entity_id, { endpoint_b: reference })} /></td>
      <td><button className="secondary-btn" onClick={() => setElectricalBindings(current => current.filter(row => row.assembly_entity_id !== item.assembly_entity_id))}>Remove</button></td>
    </tr>)}</tbody></table>
    <button className="secondary-btn" onClick={() => addBinding("electrical")} disabled={!bondIds.length || options.electrical.length < 2}><Plus size={13} /> Bind electrical bond topology</button>

    <div><button className="run-btn" disabled={!projectPath || !projectManifestDigest || busy} onClick={() => void save()}>{busy ? "Saving topology setup..." : "Save topology-addressed setup"}</button></div>
  </section>;
}
