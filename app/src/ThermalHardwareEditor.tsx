import { Fan, Plus, Trash2 } from "lucide-react";
import { onSpreadsheetFocus, onSpreadsheetKeyDown } from "./spreadsheetGrid";
import { thermalMaterials, type ThermalElement } from "./thermalAssembly";
import type { ThermalFan, ThermalHeatsink } from "./thermalScene";

type Props = {
  fans: ThermalFan[];
  heatsinks: ThermalHeatsink[];
  elements: ThermalElement[];
  onFans: (value: ThermalFan[]) => void;
  onHeatsinks: (value: ThermalHeatsink[]) => void;
};

const num = (value: string, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;

export default function ThermalHardwareEditor({ fans, heatsinks, elements, onFans, onHeatsinks }: Props) {
  const editFan = (id: string, patch: Partial<ThermalFan>) => onFans(fans.map(row => row.id === id ? { ...row, ...patch } : row));
  const editHeatsink = (id: string, patch: Partial<ThermalHeatsink>) => onHeatsinks(heatsinks.map(row => row.id === id ? { ...row, ...patch } : row));
  const addFan = () => onFans([...fans, { id: `fan-${Date.now()}`, name: `Fan ${fans.length + 1}`, enabled: true, position: [5, 50, 30], direction: [1, 0, 0], diameter_mm: 80, depth_mm: 25, flow_rate_m3_s: 0.012, static_pressure_pa: 35, rpm: 1800 }]);
  const addHeatsink = () => onHeatsinks([...heatsinks, { id: `heatsink-${Date.now()}`, name: `Heatsink ${heatsinks.length + 1}`, enabled: true, target: "board-total", position: [80, 50, 8], dimensions_mm: { x: 40, y: 40, z: 15 }, material: "aluminum-6061", interface_resistance_c_per_w: 0.15, fin_count: 10, fin_thickness_mm: 1, fin_height_mm: 12 }]);
  const targetOptions = [{ id: "board-total", reference: "Board total" }, ...elements.map(element => ({ id: element.id, reference: element.reference }))];
  const metalMaterials = thermalMaterials.filter(material => material.category === "metal");

  return <div className="wizard-section thermal-assembly-section thermal-hardware-section">
    <div className="thermal-section-heading"><label>FANS</label><span>{fans.length}</span><button onClick={addFan}><Fan size={13} /> Add fan</button></div>
    <p className="thermal-table-note">Position and dimensions are in assembly millimetres. Direction is a non-zero XYZ vector; flow and pressure define the operating point.</p>
    <div className="thermal-table-scroll"><table className="thermal-input-table thermal-spreadsheet" onFocusCapture={onSpreadsheetFocus} onKeyDown={onSpreadsheetKeyDown}><thead><tr><th>#</th><th>On</th><th>Name</th><th>X</th><th>Y</th><th>Z</th><th>Dir X</th><th>Dir Y</th><th>Dir Z</th><th>Diameter</th><th>Depth</th><th>Flow m3/s</th><th>Pressure Pa</th><th>RPM</th><th /></tr></thead><tbody>{fans.map((fan, rowIndex) => <tr key={fan.id}>
      <td className="thermal-row-number">{rowIndex + 1}</td><td><input type="checkbox" checked={fan.enabled} onChange={event => editFan(fan.id, { enabled: event.target.checked })} /></td><td><input value={fan.name} onChange={event => editFan(fan.id, { name: event.target.value })} /></td>
      {[0, 1, 2].map(axis => <td key={`fp-${axis}`}><input type="number" step="0.1" value={fan.position[axis]} onChange={event => editFan(fan.id, { position: fan.position.map((value, index) => index === axis ? num(event.target.value) : value) as [number, number, number] })} /></td>)}
      {[0, 1, 2].map(axis => <td key={`fd-${axis}`}><input type="number" step="0.1" value={fan.direction[axis]} onChange={event => editFan(fan.id, { direction: fan.direction.map((value, index) => index === axis ? num(event.target.value) : value) as [number, number, number] })} /></td>)}
      <td><input type="number" min="1" step="1" value={fan.diameter_mm} onChange={event => editFan(fan.id, { diameter_mm: num(event.target.value) })} /></td><td><input type="number" min="1" step="1" value={fan.depth_mm} onChange={event => editFan(fan.id, { depth_mm: num(event.target.value) })} /></td><td><input type="number" min="0" step="0.001" value={fan.flow_rate_m3_s} onChange={event => editFan(fan.id, { flow_rate_m3_s: num(event.target.value) })} /></td><td><input type="number" min="0" step="1" value={fan.static_pressure_pa} onChange={event => editFan(fan.id, { static_pressure_pa: num(event.target.value) })} /></td><td><input type="number" min="0" step="100" value={fan.rpm} onChange={event => editFan(fan.id, { rpm: num(event.target.value) })} /></td><td><button title="Delete fan" onClick={() => onFans(fans.filter(row => row.id !== fan.id))}><Trash2 size={13} /></button></td>
    </tr>)}</tbody></table></div>

    <div className="thermal-section-heading thermal-subheading"><label>INTEGRATED HEATSINKS</label><span>{heatsinks.length}</span><button onClick={addHeatsink}><Plus size={13} /> Add heatsink</button></div>
    <div className="thermal-table-scroll"><table className="thermal-input-table thermal-spreadsheet" onFocusCapture={onSpreadsheetFocus} onKeyDown={onSpreadsheetKeyDown}><thead><tr><th>#</th><th>On</th><th>Name</th><th>Target</th><th>X</th><th>Y</th><th>Z</th><th>Size X</th><th>Size Y</th><th>Size Z</th><th>Material</th><th>Interface Rth</th><th>Fins</th><th>Fin thick.</th><th>Fin height</th><th /></tr></thead><tbody>{heatsinks.map((sink, rowIndex) => <tr key={sink.id}>
      <td className="thermal-row-number">{rowIndex + 1}</td><td><input type="checkbox" checked={sink.enabled} onChange={event => editHeatsink(sink.id, { enabled: event.target.checked })} /></td><td><input value={sink.name} onChange={event => editHeatsink(sink.id, { name: event.target.value })} /></td><td><select value={sink.target} onChange={event => editHeatsink(sink.id, { target: event.target.value })}>{targetOptions.map(option => <option key={option.id} value={option.id}>{option.reference}</option>)}</select></td>
      {[0, 1, 2].map(axis => <td key={`hp-${axis}`}><input type="number" step="0.1" value={sink.position[axis]} onChange={event => editHeatsink(sink.id, { position: sink.position.map((value, index) => index === axis ? num(event.target.value) : value) as [number, number, number] })} /></td>)}
      {(["x", "y", "z"] as const).map(axis => <td key={`hd-${axis}`}><input type="number" min="0.1" step="0.1" value={sink.dimensions_mm[axis]} onChange={event => editHeatsink(sink.id, { dimensions_mm: { ...sink.dimensions_mm, [axis]: num(event.target.value) } })} /></td>)}
      <td><select value={sink.material} onChange={event => editHeatsink(sink.id, { material: event.target.value })}>{metalMaterials.map(material => <option key={material.id} value={material.id}>{material.name}</option>)}</select></td><td><input type="number" min="0" step="0.01" value={sink.interface_resistance_c_per_w} onChange={event => editHeatsink(sink.id, { interface_resistance_c_per_w: num(event.target.value) })} /></td><td><input type="number" min="0" step="1" value={sink.fin_count} onChange={event => editHeatsink(sink.id, { fin_count: Math.round(num(event.target.value)) })} /></td><td><input type="number" min="0.1" step="0.1" value={sink.fin_thickness_mm} onChange={event => editHeatsink(sink.id, { fin_thickness_mm: num(event.target.value) })} /></td><td><input type="number" min="0" step="0.1" value={sink.fin_height_mm} onChange={event => editHeatsink(sink.id, { fin_height_mm: num(event.target.value) })} /></td><td><button title="Delete heatsink" onClick={() => onHeatsinks(heatsinks.filter(row => row.id !== sink.id))}><Trash2 size={13} /></button></td>
    </tr>)}</tbody></table></div>
  </div>;
}
