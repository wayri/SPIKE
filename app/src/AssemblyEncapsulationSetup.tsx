// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import type { FieldObject } from "./assemblyFieldStudyPresentation";

type Draft = { id: string; kind: "coating" | "potting"; bodies: string[]; thickness: string; conductivity: string; provenance: string; bounds: string };
export type EncapsulationDraft = { recipes: FieldObject[]; materials: FieldObject[]; valid: boolean };
export function compileEncapsulation(drafts: Draft[]): EncapsulationDraft {
  const recipes: FieldObject[] = [], materials: FieldObject[] = [];
  let valid = true;
  for (const row of drafts) {
    const material_id = `material-${row.id}`, k = Number(row.conductivity);
    if (!row.conductivity.trim() || !Number.isFinite(k) || k <= 0 || !row.provenance.trim()) valid = false;
    materials.push({ id: material_id, thermal_conductivity_w_mk: k, provenance: row.provenance.trim() });
    if (row.kind === "coating") {
      const thickness = Number(row.thickness);
      if (!row.bodies.length || !row.thickness.trim() || !Number.isFinite(thickness) || thickness <= 0 || thickness > 100) valid = false;
      recipes.push({ id: row.id, kind: row.kind, material_id, body_ids: row.bodies, thickness_mm: thickness });
    } else {
      const values = row.bounds.trim().split(/[\s,]+/).map(Number);
      if (values.length !== 6 || values.some(n => !Number.isFinite(n)) || values[3] <= values[0] || values[4] <= values[1] || values[5] <= values[2]) valid = false;
      const [x0, y0, z0, x1, y1, z1] = values;
      recipes.push({ id: row.id, kind: row.kind, material_id, fill_region: { kind: "polygon_prism", outer_mm: [[x0,y0],[x1,y0],[x1,y1],[x0,y1]], holes_mm: [], z_min_mm: z0, z_max_mm: z1 }, exclusions: [] });
    }
  }
  return { recipes, materials, valid };
}

/** Author physical material volumes; the CAD worker proves closed geometry. */
export default function AssemblyEncapsulationSetup({ bodies, disabled, onChange }: {
  bodies: Array<{ id: string; name: string }>; disabled: boolean; onChange: (value: EncapsulationDraft) => void;
}) {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  useEffect(() => { onChange(compileEncapsulation(drafts)); }, [drafts, onChange]);
  const edit = (id: string, change: Partial<Draft>) => setDrafts(old => old.map(row => row.id === id ? { ...row, ...change } : row));
  const add = (kind: Draft["kind"]) => setDrafts(old => [...old, { id: `automatic-${kind}-${Date.now()}`, kind, bodies: [], thickness: "", conductivity: "", provenance: "", bounds: "" }]);
  return <details><summary>Physical coating and potting volumes</summary>
    <p>Generate material solids around selected bodies or subtract retained bodies from a potting fill region. Coating currently supports box-shaped bodies, including rotated boxes, with mitered corners; curved or irregular surfaces are blocked. Rendered component meshes do not become thermal solids.</p>
    <fieldset disabled={disabled}><legend>Encapsulation geometry and reviewed material</legend>
      <div className="assembly-field-actions"><button type="button" disabled={drafts.length >= 8 || drafts.some(r => r.kind === "potting")} onClick={() => add("coating")}>Add coating</button><button type="button" disabled={drafts.length >= 8} onClick={() => add("potting")}>Add potting</button></div>
      {drafts.map(row => <fieldset key={row.id}><legend>{row.kind === "coating" ? "Coating" : "Potting"}</legend>
        {row.kind === "coating" ? <>
          <div role="group" aria-label="Bodies to coat">{bodies.map(body => <label key={body.id}><span><input type="checkbox" checked={row.bodies.includes(body.id)} onChange={e => edit(row.id, { bodies: e.target.checked ? [...row.bodies, body.id] : row.bodies.filter(id => id !== body.id) })} />{body.name || body.id}</span></label>)}</div>
          <label>Coating thickness (mm)<input type="number" min="0.000001" max="100" step="any" value={row.thickness} onChange={e => edit(row.id, { thickness: e.target.value })} /></label>
        </> : <label>World fill bounds Xmin, Ymin, Zmin, Xmax, Ymax, Zmax (mm)<input value={row.bounds} placeholder="Enter six coordinates" onChange={e => edit(row.id, { bounds: e.target.value })} /></label>}
        <label>Material conductivity (W/m·K)<input type="number" min="0" step="any" value={row.conductivity} onChange={e => edit(row.id, { conductivity: e.target.value })} /></label>
        <label>Material property source<input maxLength={256} value={row.provenance} onChange={e => edit(row.id, { provenance: e.target.value })} /></label>
        <button type="button" onClick={() => setDrafts(old => old.filter(r => r.id !== row.id))}>Remove {row.kind}</button>
      </fieldset>)}
      {!!drafts.length && !compileEncapsulation(drafts).valid && <p role="status">Complete the dimensions, body selection and reviewed material before generating.</p>}
      <p>Coatings precede potting. Potting excludes all retained physical bodies automatically; advanced exclusions require the API. Generation retains the new STEP solids in the project and invalidates earlier simulation results.</p>
    </fieldset>
  </details>;
}
