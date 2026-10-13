// SPDX-License-Identifier: Apache-2.0
export function defaultTransientSettings(materials: any[]) {
  return { contract: "spike/assembly-tetra-transient-settings/v1", duration_s: 60, time_step_s: 1,
    output_interval_s: 1, initial_temperature_k: 293.15,
    material_heat_capacity: materials.map(material => ({ material_id: material.id, density_kg_m3: null, specific_heat_j_kgk: null })) };
}
export default function AssemblyTransientControls({ settings, disabled, onChange }: { settings: any; disabled: boolean; onChange: (settings: any) => void }) {
  const edit = (key: string, value: string) => onChange({ ...settings, [key]: value === "" ? null : Number(value) });
  return <fieldset disabled={disabled} className="assembly-transient-controls"><legend>Transient thermal setup</legend>
    <p>Enter physical density and heat capacity for every retained material. Initial temperatures and loads are explicit; no package properties are inferred.</p>
    {Object.entries({ duration_s: "Duration (s)", time_step_s: "Maximum time step (s)", output_interval_s: "Output interval (s)", initial_temperature_k: "Initial temperature (K)" }).map(([key, label]) => <label key={key}>{label}<input type="number" step="any" value={typeof settings[key] === "number" ? settings[key] : ""} onChange={e => edit(key, e.target.value)} /></label>)}
    {(settings.material_heat_capacity ?? []).map((material: any, index: number) => <div key={material.material_id}>
      <strong>{material.material_id}</strong>
      {Object.entries({ density_kg_m3: "Density (kg/m³)", specific_heat_j_kgk: "Specific heat (J/kg K)" }).map(([key, label]) => <label key={key}>{label}<input type="number" min="0" step="any" value={material[key] ?? ""} onChange={e => {
        const rows = settings.material_heat_capacity.map((row: any, i: number) => i === index ? { ...row, [key]: e.target.value === "" ? null : Number(e.target.value) } : row);
        onChange({ ...settings, material_heat_capacity: rows });
      }} /></label>)}
    </div>)}
    <details><summary>Advanced initial temperatures and power schedule</summary><label>Transient settings JSON<textarea rows={8} defaultValue={JSON.stringify(settings, null, 2)} key={JSON.stringify(settings)} onBlur={e => { try { const parsed = JSON.parse(e.target.value); if (!parsed || Array.isArray(parsed) || typeof parsed !== "object" || !Array.isArray(parsed.material_heat_capacity) || parsed.material_heat_capacity.some((row: any) => !row || typeof row.material_id !== "string")) throw new Error("Invalid settings"); onChange(parsed); e.target.setCustomValidity(""); } catch { e.target.setCustomValidity("Enter valid JSON."); e.target.reportValidity(); } }} /></label></details>
    <p>Use a smaller time step to check temporal convergence. Live updates show computed output frames; solver speed may differ from wall-clock time.</p>
  </fieldset>;
}
