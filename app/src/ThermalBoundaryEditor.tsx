// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { ThermalElement } from "./thermalAssembly";
import { createThermalBoundary, presetThermalSurfaces, thermalSurfaceAreaMm2, type ThermalBoundary, type ThermalSurface } from "./thermalBoundaries";

type Props = { elements: ThermalElement[]; boundaries: ThermalBoundary[]; onBoundaries: (value: ThermalBoundary[]) => void };
const surfaceOptions: { value: ThermalSurface; label: string }[] = [
  { value: "whole", label: "Whole object" }, { value: "+X", label: "+X face" }, { value: "-X", label: "−X face" },
  { value: "+Y", label: "+Y face" }, { value: "-Y", label: "−Y face" }, { value: "+Z", label: "+Z face" }, { value: "-Z", label: "−Z face" },
];
const numeric = (value: string) => value === "" ? undefined : Number(value);

export default function ThermalBoundaryEditor({ elements, boundaries, onBoundaries }: Props) {
  const [selectedRef, setSelectedRef] = useState("");
  const [selectedKind, setSelectedKind] = useState<ThermalBoundary["kind"]>("convection");
  const activeElements = elements.filter(element => element.enabled);
  const objectRef = activeElements.some(element => element.reference === selectedRef) ? selectedRef : activeElements[0]?.reference ?? "";
  const update = (id: string, patch: Partial<ThermalBoundary>) => onBoundaries(boundaries.map(item => item.id === id ? { ...item, ...patch } : item));
  const add = () => {
    const element = activeElements.find(item => item.reference === objectRef);
    if (element && boundaries.length < 2048) onBoundaries([...boundaries, createThermalBoundary(element, selectedKind, boundaries.length + 1)]);
  };
  return <section className="wizard-section thermal-boundary-section" aria-label="Object and surface heat transfer">
    <div className="thermal-section-heading"><label>OBJECT AND SURFACE HEAT TRANSFER</label><span>{boundaries.length}/2048</span></div>
    <p className="thermal-table-note">Assign explicit conduction, convection, or radiation to a whole object or one face. Each object is one temperature node, so face choices label the applied area; the solver does not resolve a temperature gradient across that face. These paths add to top/bottom resistance paths. Avoid assigning the same physical path twice.</p>
    <div className="thermal-boundary-add"><label>Object<select aria-label="Boundary object" value={objectRef} onChange={event => setSelectedRef(event.target.value)}>{activeElements.map(element => <option key={element.id} value={element.reference}>{element.reference} · {element.kind}</option>)}</select></label><label>Heat transfer<select aria-label="Boundary heat transfer" value={selectedKind} onChange={event => setSelectedKind(event.target.value as ThermalBoundary["kind"])}><option value="conduction">Conduction</option><option value="convection">Convection</option><option value="radiation">Radiation</option></select></label><button type="button" disabled={!objectRef || boundaries.length >= 2048} onClick={add}><Plus size={14} /> Add boundary</button></div>
    {!activeElements.length && <p className="thermal-table-note">Add or sync an enabled object first. Board fallback remains available for the basic top/bottom model.</p>}
    <div className="thermal-boundary-list">{boundaries.map((boundary, index) => {
      const owner = activeElements.find(element => element.reference === boundary.object_ref);
      const targetRefs = activeElements.filter(element => element.reference !== boundary.object_ref).map(element => element.reference);
      return <div className="thermal-boundary-card" key={boundary.id}>
        <div className="thermal-boundary-heading"><b>Boundary {index + 1}</b><label><input type="checkbox" checked={boundary.enabled} onChange={event => update(boundary.id, { enabled: event.target.checked })} /> Enabled</label><button type="button" aria-label={`Remove boundary ${index + 1}`} onClick={() => onBoundaries(boundaries.filter(item => item.id !== boundary.id))}><Trash2 size={14} /></button></div>
        <div className="thermal-boundary-fields">
          <label>Object<select value={boundary.object_ref} onChange={event => update(boundary.id, { object_ref: event.target.value })}>{!owner && <option value={boundary.object_ref}>{boundary.object_ref || "Missing object"}</option>}{activeElements.map(element => <option key={element.id} value={element.reference}>{element.reference}</option>)}</select></label>
          <label>Surface<select value={presetThermalSurfaces.has(boundary.surface) ? boundary.surface : "custom"} onChange={event => { const surface = event.target.value === "custom" ? "" : event.target.value as ThermalSurface; update(boundary.id, { surface, area_mm2: owner && presetThermalSurfaces.has(surface) ? thermalSurfaceAreaMm2(owner, surface) : undefined }); }}>{surfaceOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}<option value="custom">Named surface</option></select></label>
          {!presetThermalSurfaces.has(boundary.surface) && <label>Surface name<input aria-label={`Boundary ${index + 1} surface name`} value={boundary.surface} placeholder="CAD face or surface ID" maxLength={128} onChange={event => update(boundary.id, { surface: event.target.value })} /></label>}
          <label>Mechanism<select value={boundary.kind} onChange={event => update(boundary.id, { kind: event.target.value as ThermalBoundary["kind"] })}><option value="conduction">Conduction</option><option value="convection">Convection</option><option value="radiation">Radiation</option></select></label>
          {boundary.kind === "conduction" ? <><label>To<select value={boundary.target_ref || "ambient"} onChange={event => update(boundary.id, { target_ref: event.target.value })}><option value="ambient">Ambient sink</option>{!targetRefs.includes(boundary.target_ref ?? "") && boundary.target_ref && boundary.target_ref !== "ambient" && <option value={boundary.target_ref}>{boundary.target_ref} (missing)</option>}{targetRefs.map(ref => <option key={ref} value={ref}>{ref}</option>)}</select></label><label>Resistance K/W<input aria-label={`Boundary ${index + 1} conduction resistance`} type="number" min="0" step="0.1" value={boundary.resistance_c_per_w ?? ""} onChange={event => update(boundary.id, { resistance_c_per_w: numeric(event.target.value) })} /></label>{(!boundary.target_ref || boundary.target_ref === "ambient") && <label>Sink °C (optional)<input type="number" step="0.1" placeholder="Scenario ambient" value={boundary.ambient_temperature_c ?? ""} onChange={event => update(boundary.id, { ambient_temperature_c: numeric(event.target.value) })} /></label>}</> : <><label>Exposed area mm²<input aria-label={`Boundary ${index + 1} exposed area`} type="number" min="0" step="1" value={boundary.area_mm2 ?? ""} onChange={event => update(boundary.id, { area_mm2: numeric(event.target.value) })} /></label>{boundary.kind === "convection" ? <><label>h W/m²K<input aria-label={`Boundary ${index + 1} convection coefficient`} type="number" min="0" step="0.1" value={boundary.heat_transfer_coefficient_w_m2_k ?? ""} onChange={event => update(boundary.id, { heat_transfer_coefficient_w_m2_k: numeric(event.target.value) })} /></label><label>Fluid °C (optional)<input type="number" step="0.1" placeholder="Scenario ambient" value={boundary.ambient_temperature_c ?? ""} onChange={event => update(boundary.id, { ambient_temperature_c: numeric(event.target.value) })} /></label></> : <><label>Emissivity 0–1<input aria-label={`Boundary ${index + 1} emissivity`} type="number" min="0" max="1" step="0.01" value={boundary.emissivity ?? ""} onChange={event => update(boundary.id, { emissivity: numeric(event.target.value) })} /></label><label>Surroundings °C (optional)<input type="number" step="0.1" placeholder="Scenario ambient" value={boundary.surroundings_temperature_c ?? ""} onChange={event => update(boundary.id, { surroundings_temperature_c: numeric(event.target.value) })} /></label></>}</>}
        </div>
        {owner && boundary.kind !== "conduction" && <small>{presetThermalSurfaces.has(boundary.surface) ? `Suggested ${boundary.surface} area from object dimensions: ${thermalSurfaceAreaMm2(owner, boundary.surface).toFixed(1)} mm². ` : "Named surfaces need a measured exposed area. "}Enter the actual exposed area.</small>}
      </div>;
    })}</div>
  </section>;
}
