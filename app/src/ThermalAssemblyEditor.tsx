import { Plus, RefreshCw, Trash2 } from "lucide-react";
import type { ParsedBoard } from "./boardParser";
import { onSpreadsheetFocus, onSpreadsheetKeyDown } from "./spreadsheetGrid";
import { componentThermalElements, screenThermalElements, thermalMaterials, ThermalElement, ThermalLink, thermalSurfaceFinishes } from "./thermalAssembly";

type Props = { board: ParsedBoard | null; ambientC: number; elements: ThermalElement[]; links: ThermalLink[]; onElements: (value: ThermalElement[]) => void; onLinks: (value: ThermalLink[]) => void };
const num = (value: string, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;

export default function ThermalAssemblyEditor({ board, ambientC, elements, links, onElements, onLinks }: Props) {
  const screening = screenThermalElements(elements, ambientC);
  const edit = (id: string, patch: Partial<ThermalElement>) => onElements(elements.map(row => row.id === id ? { ...row, ...patch } : row));
  const editLink = (id: string, patch: Partial<ThermalLink>) => onLinks(links.map(row => row.id === id ? { ...row, ...patch } : row));
  const syncParts = () => {
    const parts = componentThermalElements(board);
    const source = new Map(parts.map(row => [row.object_id, row]));
    const existing = new Set(elements.map(row => row.object_id));
    const retained = elements.map(prior => {
      const row = prior.kind === "pcb_component" ? source.get(prior.object_id) : undefined;
      return row ? { ...prior, position: row.position, dimensions_mm: row.dimensions_mm, coordinate_frame: "board_local" as const } : prior;
    });
    onElements([...retained, ...parts.filter(row => !existing.has(row.object_id)).slice(0, Math.max(0, 256 - retained.length))]);
  };
  const addMechanical = () => {
    const element: ThermalElement = { id: `thermal-mechanical-${Date.now()}`, reference: `M${elements.length + 1}`, name: "Assembly object", kind: "mechanical", model_path: "", material_id: "", surface_finish_id: "as-modeled", enabled: true, coordinate_frame: "domain_local", position: [0, 0, 5], dimensions_mm: { x: 20, y: 20, z: 5 }, power_w: 0, emissivity: 0.8, max_case_c: 120 };
    onElements([...elements, element].slice(0, 256));
  };
  const addLink = () => onLinks([...links, { id: `thermal-link-${Date.now()}`, from_id: elements[0]?.id ?? "", to_id: elements[1]?.id ?? "", kind: "solder", enabled: true, resistance_c_per_w: 0.2, contact_area_mm2: 4, thickness_mm: 0.1, material_id: "sac305" }]);
  const optionalFields = ["theta_top_c_per_w", "theta_bottom_c_per_w", "theta_jc_c_per_w", "max_junction_c", "max_case_c"] as const;
  return <>
    <div className="wizard-section thermal-assembly-section">
      <div className="thermal-section-heading"><label>PARTS, BOARDS, AND MECHANICAL OBJECTS</label><span>{elements.length}/256</span><button disabled={!board} onClick={syncParts}><RefreshCw size={13} /> Sync board parts</button><button disabled={elements.length >= 256} onClick={addMechanical}><Plus size={13} /> Mechanical object</button></div>
      <p className="thermal-table-note">These solver inputs manipulate thermal representations without changing source CAD. Blank resistance or limit cells remain explicitly unspecified.</p>
      {(elements.length >= 256 || (board?.components.length ?? 0) > 256) && <p className="thermal-table-note">Sync preserves existing inputs and fills only available rows up to 256. Remove unused rows to add other board parts, or import a BOM containing the required references.</p>}
      <div className="thermal-table-scroll"><table className="thermal-input-table thermal-spreadsheet" onFocusCapture={onSpreadsheetFocus} onKeyDown={onSpreadsheetKeyDown}><thead><tr><th>#</th><th>On</th><th>Object</th><th>Type</th><th>Model / STEP</th><th>Power W</th><th>Heat capacity J/K</th><th>Initial °C</th><th>Material</th><th>Surface</th><th>Emiss.</th><th>Rth top</th><th>Rth bottom</th><th>Rth JC</th><th>Tj max</th><th>Tcase max</th><th>X</th><th>Y</th><th>Z</th><th>Size X</th><th>Size Y</th><th>Size Z</th><th>Screen</th><th /></tr></thead><tbody>{elements.map((element, rowIndex) => {
        const check = screening.find(item => item.element_id === element.id);
        return <tr key={element.id} className={`thermal-screen-${check?.status ?? "unrated"}`}>
          <td className="thermal-row-number">{rowIndex + 1}</td>
          <td><input type="checkbox" checked={element.enabled} onChange={event => edit(element.id, { enabled: event.target.checked })} /></td>
          <td><input value={element.reference} onChange={event => edit(element.id, { reference: event.target.value })} title={element.name} /></td>
          <td><select value={element.kind} onChange={event => edit(element.id, { kind: event.target.value as ThermalElement["kind"] })}><option value="pcb_component">PCB part</option><option value="board">Board</option><option value="mechanical">Mechanical</option><option value="heatsink">Heatsink</option><option value="enclosure">Enclosure</option></select></td>
          <td><input value={element.model_path ?? ""} onChange={event => edit(element.id, { model_path: event.target.value })} placeholder="Path or model ID" /></td>
          <td><input type="number" min="0" step="0.01" value={element.power_w} onChange={event => edit(element.id, { power_w: num(event.target.value) })} /></td>
          <td><input type="number" min="0" step="0.1" value={element.thermal_capacitance_j_per_c ?? ""} onChange={event => edit(element.id, { thermal_capacitance_j_per_c: event.target.value === "" ? undefined : num(event.target.value) })} /></td>
          <td><input type="number" min="-273.15" step="0.1" value={element.initial_temperature_c ?? ""} onChange={event => edit(element.id, { initial_temperature_c: event.target.value === "" ? undefined : num(event.target.value) })} /></td>
          <td><select value={element.material_id} onChange={event => { const material = thermalMaterials.find(item => item.id === event.target.value); edit(element.id, { material_id: event.target.value, emissivity: material?.emissivity ?? element.emissivity }); }}><option value="">Select material</option>{thermalMaterials.map(material => <option key={material.id} value={material.id}>{material.name}</option>)}</select></td>
          <td><select value={element.surface_finish_id} onChange={event => { const finish = thermalSurfaceFinishes.find(item => item.id === event.target.value); edit(element.id, { surface_finish_id: event.target.value, emissivity: finish?.emissivity ?? element.emissivity }); }}>{thermalSurfaceFinishes.map(finish => <option key={finish.id} value={finish.id}>{finish.name}</option>)}</select></td>
          <td><input type="number" min="0" max="1" step="0.01" value={element.emissivity} onChange={event => edit(element.id, { emissivity: num(event.target.value) })} /></td>
          {optionalFields.map(field => <td key={field}><input type="number" min="0" step="0.1" value={element[field] ?? ""} onChange={event => edit(element.id, { [field]: event.target.value === "" ? undefined : num(event.target.value) })} /></td>)}
          {[0, 1, 2].map(axis => <td key={`p-${axis}`}><input type="number" step="0.1" value={element.position[axis]} onChange={event => edit(element.id, { position: element.position.map((value, index) => index === axis ? num(event.target.value) : value) as [number, number, number] })} /></td>)}
          {(["x", "y", "z"] as const).map(axis => <td key={`d-${axis}`}><input type="number" min="0.01" step="0.1" value={element.dimensions_mm[axis]} onChange={event => edit(element.id, { dimensions_mm: { ...element.dimensions_mm, [axis]: num(event.target.value) } })} /></td>)}
          <td><span className={`thermal-screen-badge ${check?.status ?? "unrated"}`} title={check?.estimated_junction_c === null ? "Add thermal resistance data" : `Estimated ${check?.estimated_junction_c?.toFixed(1)} C; margin ${check?.margin_c?.toFixed(1)} C`}>{check?.status ?? "unrated"}</span></td>
          <td><button onClick={() => onElements(elements.filter(row => row.id !== element.id))}><Trash2 size={13} /></button></td>
        </tr>;
      })}</tbody></table></div>
    </div>
    <div className="wizard-section thermal-assembly-section">
      <div className="thermal-section-heading"><label>THERMAL LINKS AND CONTACTS</label><span>{links.length}</span><button disabled={elements.length < 2} onClick={addLink}><Plus size={13} /> Add link</button></div>
      <div className="thermal-table-scroll"><table className="thermal-input-table thermal-link-table thermal-spreadsheet" onFocusCapture={onSpreadsheetFocus} onKeyDown={onSpreadsheetKeyDown}><thead><tr><th>#</th><th>On</th><th>From</th><th>To</th><th>Interface</th><th>Rth C/W</th><th>Area mm2</th><th>Thickness mm</th><th>Material</th><th /></tr></thead><tbody>{links.map((link, rowIndex) => <tr key={link.id}>
        <td className="thermal-row-number">{rowIndex + 1}</td>
        <td><input type="checkbox" checked={link.enabled} onChange={event => editLink(link.id, { enabled: event.target.checked })} /></td>
        <td><select value={link.from_id} onChange={event => editLink(link.id, { from_id: event.target.value })}>{elements.map(element => <option key={element.id} value={element.id}>{element.reference}</option>)}</select></td>
        <td><select value={link.to_id} onChange={event => editLink(link.id, { to_id: event.target.value })}>{elements.map(element => <option key={element.id} value={element.id}>{element.reference}</option>)}</select></td>
        <td><select value={link.kind} onChange={event => editLink(link.id, { kind: event.target.value as ThermalLink["kind"] })}><option value="solder">Solder</option><option value="thermal_pad">Thermal pad</option><option value="thermal_paste">Thermal paste</option><option value="bond">Bond</option><option value="mechanical_contact">Mechanical contact</option><option value="custom">Custom</option></select></td>
        {(["resistance_c_per_w", "contact_area_mm2", "thickness_mm"] as const).map(field => <td key={field}><input type="number" min="0" step="0.01" value={link[field]} onChange={event => editLink(link.id, { [field]: num(event.target.value) })} /></td>)}
        <td><select value={link.material_id} onChange={event => editLink(link.id, { material_id: event.target.value })}>{thermalMaterials.filter(material => material.category === "interface" || material.category === "metal").map(material => <option key={material.id} value={material.id}>{material.name}</option>)}</select></td>
        <td><button onClick={() => onLinks(links.filter(row => row.id !== link.id))}><Trash2 size={13} /></button></td>
      </tr>)}</tbody></table></div>
    </div>
    <details className="wizard-section thermal-material-library"><summary>MATERIAL PROPERTY LIBRARY <span>{thermalMaterials.length} materials · {thermalSurfaceFinishes.length} finishes</span></summary><div className="thermal-table-scroll"><table className="thermal-input-table"><thead><tr><th>Material</th><th>Class</th><th>k W/mK</th><th>Density</th><th>Cp</th><th>Emiss.</th><th>Max C</th><th>Tg C</th></tr></thead><tbody>{thermalMaterials.map(material => <tr key={material.id}><td>{material.name}</td><td>{material.category}</td><td>{material.conductivity_w_mk}</td><td>{material.density_kg_m3}</td><td>{material.specific_heat_j_kgk}</td><td>{material.emissivity}</td><td>{material.max_temperature_c ?? "-"}</td><td>{material.glass_transition_c ?? "-"}</td></tr>)}</tbody></table></div></details>
  </>;
}
