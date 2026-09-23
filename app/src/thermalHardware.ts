import type { ThermalFan, ThermalHeatsink } from "./thermalScene";

const point = (value: unknown, fallback: [number, number, number]): [number, number, number] => {
  const source = Array.isArray(value) ? value : [];
  return [0, 1, 2].map(index => Number.isFinite(Number(source[index])) ? Number(source[index]) : fallback[index]) as [number, number, number];
};

export function normalizeThermalFans(value: unknown, volume = { x: 160, y: 100, z: 60 }): ThermalFan[] {
  if (!Array.isArray(value)) return [{ id: "fan-1", name: "Fan 1", enabled: true, position: [5, volume.y / 2, volume.z / 2], direction: [1, 0, 0], diameter_mm: 80, depth_mm: 25, flow_rate_m3_s: 0.012, static_pressure_pa: 35, rpm: 1800 }];
  return value.map((entry, index) => {
    const row = entry as Partial<ThermalFan>;
    return { id: String(row.id || `fan-${index + 1}`), name: String(row.name || `Fan ${index + 1}`), enabled: row.enabled !== false, position: point(row.position, [5, volume.y / 2, volume.z / 2]), direction: point(row.direction, [1, 0, 0]), diameter_mm: Math.max(1, Number(row.diameter_mm) || 80), depth_mm: Math.max(1, Number(row.depth_mm) || 25), flow_rate_m3_s: Math.max(0, Number(row.flow_rate_m3_s) || 0), static_pressure_pa: Math.max(0, Number(row.static_pressure_pa) || 0), rpm: Math.max(0, Number(row.rpm) || 0) };
  });
}

export function normalizeThermalHeatsinks(value: unknown): ThermalHeatsink[] {
  if (!Array.isArray(value)) return [];
  return value.map((entry, index) => {
    const row = entry as Partial<ThermalHeatsink>;
    const dimensions = row.dimensions_mm ?? { x: 40, y: 40, z: 15 };
    return { id: String(row.id || `heatsink-${index + 1}`), name: String(row.name || `Heatsink ${index + 1}`), enabled: row.enabled !== false, target: String(row.target || "board-total"), position: point(row.position, [80, 50, 8]), dimensions_mm: { x: Math.max(0.1, Number(dimensions.x) || 40), y: Math.max(0.1, Number(dimensions.y) || 40), z: Math.max(0.1, Number(dimensions.z) || 15) }, material: String(row.material || "aluminum-6061"), interface_resistance_c_per_w: Math.max(0, Number(row.interface_resistance_c_per_w) || 0), fin_count: Math.max(0, Math.round(Number(row.fin_count) || 0)), fin_thickness_mm: Math.max(0.1, Number(row.fin_thickness_mm) || 1), fin_height_mm: Math.max(0, Number(row.fin_height_mm) || 0) };
  });
}
