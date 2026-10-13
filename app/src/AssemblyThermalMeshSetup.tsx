// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { runLocalWorker, runNativeProjectWorker, type WorkerResponse } from "./workerBridge";
import type { FieldObject } from "./assemblyFieldStudyPresentation";
import ThermalComponentPromotion from "./ThermalComponentPromotion";
import AssemblyEncapsulationSetup, { type EncapsulationDraft } from "./AssemblyEncapsulationSetup";
import type { AssemblyIr } from "./mcadAssembly";

type Inventory = { boards: Array<{ design_id: string; name: string; layers: Array<{ id: string; name: string; layer_type: string }> }>; parts: Array<{ id: string; name: string; model_id: string }>; components?: FieldObject[]; thermal_materials?: FieldObject[]; part_material_assignments?: Record<string,string> };
const value = (response: WorkerResponse): FieldObject => {
  if (!response.ok || !response.result) throw new Error(response.error || "Volume preparation returned no data.");
  return response.result;
};

/** Physical properties are reviewed user inputs; geometry comes from the project. */
export default function AssemblyThermalMeshSetup({ projectPath, manifestDigest, disabled, onBusyChange, onPrepared, onProjectUpdated, initialMesher = "gmsh", assembly, onSetupReady }: {
  assembly?: AssemblyIr; onSetupReady?: (setup: FieldObject) => void;
  initialMesher?: "internal" | "gmsh";
  projectPath: string; manifestDigest: string; disabled: boolean;
  onBusyChange: (busy: boolean) => void; onPrepared: (result: FieldObject) => Promise<void>;
  onProjectUpdated?: () => Promise<void>;
}) {
  const [mesher, setMesher] = useState(initialMesher);
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [properties, setProperties] = useState<Record<string, { conductivity: string; provenance: string }>>({});
  const [reviewed, setReviewed] = useState(false);
  const [size, setSize] = useState("1");
  const [limit, setLimit] = useState("20000");
  const [encapsulation, setEncapsulation] = useState<EncapsulationDraft>({ recipes: [], materials: [], valid: true });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [blockers, setBlockers] = useState<FieldObject[]>([]);
  const generation = useRef(0);
  useEffect(() => {
    generation.current++; setInventory(null); setProperties({}); setReviewed(false); setError(""); setBlockers([]);
    return () => { generation.current++; };
  }, [projectPath, manifestDigest]);
  const run = async (work: (current: () => boolean) => Promise<void>) => {
    if (disabled || busy) return;
    const token = generation.current;
    setBusy(true); onBusyChange(true); setError(""); setBlockers([]);
    try { await work(() => token === generation.current); }
    catch (caught) { if (token === generation.current) setError(String(caught)); }
    finally { setBusy(false); onBusyChange(false); }
  };
  const load = () => run(async current => {
    const result = value(await runNativeProjectWorker({ method: "read_assembly_thermal_mesh_setup", params: {
      project_path: projectPath, expected_manifest_payload_sha256: manifestDigest,
    } }));
    if (current()) {
      const saved: Record<string, { conductivity: string; provenance: string }> = {};
      for (const [part, mid] of Object.entries(result.part_material_assignments ?? {})) {
        const material = (result.thermal_materials ?? []).find((m: FieldObject) => m.id === mid);
        if (material && typeof material.thermal_conductivity_w_mk === "number") saved[JSON.stringify(["part", part])] = { conductivity: String(material.thermal_conductivity_w_mk), provenance: material.provenance ?? "" };
      }
      setInventory(result as Inventory); setProperties(saved); setReviewed(false);
    }
  });
  const rows = inventory ? [
    ...inventory.boards.flatMap(board => board.layers.map(layer => ({ key: JSON.stringify(["board", board.design_id, layer.id]), label: `${board.name || board.design_id} · ${layer.name || layer.id} (${layer.layer_type})`, board: board.design_id, layer: layer.id, part: "" }))),
    ...inventory.parts.map(part => ({ key: JSON.stringify(["part", part.id]), label: `${part.name || part.id} · closed STEP solid required`, part: part.id, board: "", layer: "" })),
  ] : [];
  const retainedPartIds = new Set(inventory?.parts.map(part => part.id) ?? []);
  const components = inventory?.components ?? [];
  const excludedComponents = components.filter(component =>
    !component.promoted_part_ids?.some((id: string) => retainedPartIds.has(id)));
  const readyComponents = excludedComponents.filter(component => component.models?.some((model: FieldObject) => model.status === "ready"));
  const valid = rows.length > 0 && rows.every(row => {
    const prop = properties[row.key]; return !!prop && prop.conductivity.trim() !== "" && Number.isFinite(Number(prop.conductivity)) && Number(prop.conductivity) > 0 && !!prop.provenance.trim();
  }) && encapsulation.valid && Number(size) >= .000001 && Number.isFinite(Number(size)) && Number.isInteger(Number(limit)) && Number(limit) >= 4 && Number(limit) <= 100000;
  const meshParameters = () => {
    const assignments: FieldObject = { materials: [], boards: {}, parts: {} };
    rows.forEach((row, index) => {
      const id = `reviewed-material-${index}`;
      const prop = properties[row.key];
      assignments.materials.push({ id, provenance: prop.provenance.trim(), thermal_conductivity_w_mk: Number(prop.conductivity) });
      if (row.part) assignments.parts[row.part] = id;
      else {
        assignments.boards[row.board] ??= { representation: "layer_homogenized", layer_materials: {} };
        assignments.boards[row.board].layer_materials[row.layer] = id;
      }
    });
    if (encapsulation.recipes.length) {
      assignments.encapsulation = encapsulation.recipes;
      assignments.materials.push(...encapsulation.materials);
    }
    return { project_path: projectPath, expected_manifest_payload_sha256: manifestDigest, assignments,
      mesh_options: { min_size_mm: Number(size), max_size_mm: Number(size), max_cells: Number(limit), max_vertices: Number(limit) } };
  };
  const generate = () => run(async current => {
    if (!valid || !reviewed) return;
    const parameters = meshParameters();
    const assignments = parameters.assignments;
    onSetupReady?.({ assignments, mesh_options: parameters.mesh_options });
    const response = mesher === "gmsh"
      ? value(await runLocalWorker({ method: "invoke_extension", params: { extension_id: "spike.gmsh-suite", contribution_id: "gmsh-mesh-assembly", context: { parameters } } }))
      : value(await runNativeProjectWorker({ method: "run_assembly_thermal_mesh_in_project", params: parameters }));
    const result = mesher === "gmsh" ? response.data?.assembly_mesh_result : response;
    if (!result) throw new Error("The mesher returned no retained volume result.");
    if (!current()) return;
    if (result.status !== "completed") { setBlockers(result.blockers ?? []); return; }
    if (result.manifest && onProjectUpdated) { await onProjectUpdated(); return; }
    await onPrepared(result);
  });
  return <details><summary>Generate 3D thermal volumes from this project</summary>
    <p>Solid thermal accepts up to 100,000 tetrahedra and nodes, subject to memory, sparse-matrix and geometry-audit budgets. Transient saved-frame budgets can require fewer nodes or frames.</p>
    <p>Boards use explicitly reviewed effective layer materials. Patterned copper, vias and drills are homogenized. Mechanical parts require one closed STEP solid each. Curved outlines, formed flex and decorative display meshes are unsupported.</p>
    <label>Volume mesher<select aria-label="Assembly volume mesher" disabled={disabled || busy} value={mesher} onChange={event => setMesher(event.target.value as "internal" | "gmsh")}><option value="gmsh">Gmsh extension · complete tetrahedral volumes</option><option value="internal">SPIKE development OCC adapter</option></select></label>
    <button type="button" disabled={disabled || busy} onClick={() => void load()}>Read retained geometry and layers</button>
    {busy && <p role="status">Preparing retained assembly volumes…</p>}
    {error && <p role="alert">{error}</p>}
    {!!blockers.length && <ul aria-label="Volume meshing blockers">{blockers.map((item, index) => <li key={index}>{item.occurrence_id} · {item.message}</li>)}</ul>}
    {inventory?.components && <div role="status" aria-label="Thermal component geometry coverage">
      <p>{components.length} component occurrences: {components.length - excludedComponents.length} retained as physical thermal parts; {excludedComponents.length} excluded from volume meshing.</p>
      {!!excludedComponents.length && <>
        <p>{readyComponents.length} excluded components have a retained STEP reference available for placement and material review. Closed-solid eligibility is checked during meshing. Displayed 3D models are not automatically included.</p>
        <p>Excluded: {excludedComponents.slice(0, 12).map(component => `${component.board_occurrence_id}: ${component.reference || component.component_id}`).join(", ")}{excludedComponents.length > 12 ? ` and ${excludedComponents.length - 12} more` : ""}.</p>
        {!onProjectUpdated && <p>Open the saved project's assembly thermal setup to retain reviewed component STEP models.</p>}
      </>}
    </div>}
    {inventory?.components && onProjectUpdated && <ThermalComponentPromotion components={inventory.components} projectPath={projectPath} manifestDigest={manifestDigest}
      disabled={disabled || busy} onBusyChange={onBusyChange} onUpdated={onProjectUpdated} />}
    {inventory && <fieldset disabled={disabled || busy}><legend>Reviewed thermal materials</legend>
      <AssemblyEncapsulationSetup bodies={[...(assembly?.boards ?? []), ...(assembly?.parts ?? [])].map(body => ({ id: String(body.id), name: String(body.name || body.id) }))} disabled={disabled || busy} onChange={setEncapsulation} />
      {rows.map(row => <div className="assembly-field-boundary" key={row.key}><strong>{row.label}</strong>
        <label>Thermal conductivity (W/m·K)<input type="number" step="any" min="0" value={properties[row.key]?.conductivity ?? ""} onChange={event => { setReviewed(false); setProperties(old => ({ ...old, [row.key]: { provenance: old[row.key]?.provenance ?? "", conductivity: event.target.value } })); }} /></label>
        <label>Property source / effective-layer justification<input type="text" maxLength={256} value={properties[row.key]?.provenance ?? ""} onChange={event => { setReviewed(false); setProperties(old => ({ ...old, [row.key]: { conductivity: old[row.key]?.conductivity ?? "", provenance: event.target.value } })); }} /></label>
      </div>)}
      {!rows.length && <p>No physical board layers or mechanical occurrences were retained.</p>}
      <div className="assembly-field-boundary"><label>Mesh target size (mm)<input type="number" step="any" min="0.000001" value={size} onChange={event => setSize(event.target.value)} /></label>
        <label>Maximum total cells and vertices<input type="number" min="4" max="100000" value={limit} onChange={event => setLimit(event.target.value)} /></label></div>
      <label><span><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} /> I reviewed these material values and accept the effective layer approximation for boards.</span></label>
      <button type="button" className="spike-control--primary" disabled={!valid || !reviewed} onClick={() => void generate()}>Generate thermal volume mesh</button>
      {onSetupReady && <button type="button" disabled={!valid || !reviewed || !!encapsulation.recipes.length} onClick={() => {
        const parameters = meshParameters(); onSetupReady({ assignments: parameters.assignments, mesh_options: parameters.mesh_options });
      }}>Use reviewed materials for assembly airflow</button>}
      {!!encapsulation.recipes.length && <p>Generate and retain the encapsulant STEP solids before preparing assembly airflow.</p>}
      <p>Generation replaces the current volume draft and clears its thermal setup and results. Heat sources, matched contact faces and ambient conditions must then be assigned explicitly.</p>
    </fieldset>}
  </details>;
}

export function AssemblyAmbientBoundaries({ request, problem, disabled, onApply }: {
  request: FieldObject; problem: FieldObject; disabled: boolean; onApply: (boundaries: FieldObject[]) => void;
}) {
  const [mode, setMode] = useState("convection");
  const [ambient, setAmbient] = useState("");
  const [coefficient, setCoefficient] = useState("");
  const [emissivity, setEmissivity] = useState("");
  const [radiationTemperature, setRadiationTemperature] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const hasConvection = mode !== "radiation", hasRadiation = mode !== "convection";
  const positive = (value: string) => value.trim() !== "" && Number.isFinite(Number(value)) && Number(value) > 0;
  const valid = (!hasConvection || positive(ambient) && positive(coefficient)) && (!hasRadiation || positive(radiationTemperature) && positive(emissivity) && Number(emissivity) <= 1);
  const key = (face: FieldObject) => JSON.stringify([face.occurrence_id, face.face_id]);
  const assigned = new Set((problem.boundaries ?? []).map((boundary: FieldObject) => key(boundary.face)));
  for (const contact of problem.contacts ?? []) for (const pair of contact.face_pairs ?? []) {
    assigned.add(key(pair.left)); assigned.add(key(pair.right));
  }
  const unassigned = (request.bodies ?? []).flatMap((body: FieldObject) => (body.boundary_faces ?? []).map((face: FieldObject) => ({ occurrence_id: body.occurrence_id, face_id: face.id })))
    .filter((face: FieldObject) => !assigned.has(key(face)));
  const apply = () => {
    if (!valid || !reviewed || disabled) return;
    onApply(unassigned.map((face: FieldObject) => ({ face, type: mode,
      ...(hasConvection ? { heat_transfer_coefficient_w_m2k: Number(coefficient), ambient_temperature_k: Number(ambient) } : {}),
      ...(hasRadiation ? { emissivity: Number(emissivity), radiation_temperature_k: Number(radiationTemperature) } : {}),
    })));
    setReviewed(false);
  };
  return <details><summary>Assign ambient exchange to unassigned exterior faces</summary>
    <p>{unassigned.length} unassigned triangles. This applies prescribed ambient exchange to every listed body exterior except existing boundaries and matched contact faces. It does not model enclosure airflow, occlusion or surface-to-surface radiation. Define contact faces first.</p>
    <fieldset disabled={disabled}><label>Ambient exchange<select value={mode} onChange={event => { setMode(event.target.value); setReviewed(false); }}>
      <option value="convection">Convection</option><option value="radiation">Radiation to prescribed surroundings</option><option value="convection_radiation">Convection and ambient radiation</option>
    </select></label><div className="assembly-field-boundary">
      {hasConvection && <><label>Ambient air temperature (K)<input type="number" step="any" value={ambient} onChange={event => { setAmbient(event.target.value); setReviewed(false); }} /></label>
        <label>Convection coefficient (W/m²K)<input type="number" step="any" value={coefficient} onChange={event => { setCoefficient(event.target.value); setReviewed(false); }} /></label></>}
      {hasRadiation && <><label>Radiating surroundings temperature (K)<input type="number" step="any" value={radiationTemperature} onChange={event => { setRadiationTemperature(event.target.value); setReviewed(false); }} /></label>
        <label>Emissivity (0–1)<input type="number" step="any" min="0" max="1" value={emissivity} onChange={event => { setEmissivity(event.target.value); setReviewed(false); }} /></label></>}
    </div><label><span><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} /> I reviewed these ambient values and the exposed faces.</span></label>
      <button type="button" disabled={!valid || !reviewed || !unassigned.length || unassigned.length + (problem.boundaries?.length ?? 0) > 20000} onClick={apply}>Apply to unassigned exterior faces</button>
    </fieldset>
  </details>;
}
