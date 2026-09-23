import type { ParsedBoard } from "./boardParser";
import type { ThermalCoordinateFrame, ThermalPoint3 } from "./thermalScene";

export type ThermalMaterial = {
  id: string;
  name: string;
  category: "metal" | "pcb" | "polymer" | "ceramic" | "interface" | "fluid" | "glass";
  conductivity_w_mk: number;
  density_kg_m3: number;
  specific_heat_j_kgk: number;
  emissivity: number;
  max_temperature_c?: number;
  glass_transition_c?: number;
};

export type ThermalSurfaceFinish = {
  id: string;
  name: string;
  emissivity: number;
  contact_multiplier: number;
};

export type ThermalElement = {
  id: string;
  object_id?: string;
  reference: string;
  name: string;
  kind: "pcb_component" | "board" | "mechanical" | "heatsink" | "enclosure";
  model_path?: string;
  material_id: string;
  surface_finish_id: string;
  enabled: boolean;
  position: ThermalPoint3;
  coordinate_frame: ThermalCoordinateFrame;
  dimensions_mm: { x: number; y: number; z: number };
  power_w: number;
  emissivity: number;
  theta_top_c_per_w?: number;
  theta_bottom_c_per_w?: number;
  theta_jc_c_per_w?: number;
  max_junction_c?: number;
  max_case_c?: number;
  initial_temperature_c?: number;
};

export type ThermalLink = {
  id: string;
  from_id: string;
  to_id: string;
  kind: "solder" | "thermal_pad" | "thermal_paste" | "bond" | "mechanical_contact" | "custom";
  enabled: boolean;
  resistance_c_per_w: number;
  contact_area_mm2: number;
  thickness_mm: number;
  material_id: string;
};

export type ThermalScreening = {
  element_id: string;
  reference: string;
  estimated_junction_c: number | null;
  limit_c: number | null;
  margin_c: number | null;
  status: "ok" | "warning" | "critical" | "unrated";
};

export const thermalMaterials: ThermalMaterial[] = [
  { id: "copper", name: "Copper C110", category: "metal", conductivity_w_mk: 385, density_kg_m3: 8960, specific_heat_j_kgk: 385, emissivity: 0.12, max_temperature_c: 300 },
  { id: "aluminum-6061", name: "Aluminum 6061-T6", category: "metal", conductivity_w_mk: 167, density_kg_m3: 2700, specific_heat_j_kgk: 896, emissivity: 0.09, max_temperature_c: 200 },
  { id: "stainless-304", name: "Stainless steel 304", category: "metal", conductivity_w_mk: 16.2, density_kg_m3: 8000, specific_heat_j_kgk: 500, emissivity: 0.59, max_temperature_c: 600 },
  { id: "fr4-standard", name: "FR-4 standard", category: "pcb", conductivity_w_mk: 0.3, density_kg_m3: 1850, specific_heat_j_kgk: 1100, emissivity: 0.9, max_temperature_c: 130, glass_transition_c: 135 },
  { id: "fr4-high-tg", name: "FR-4 high Tg", category: "pcb", conductivity_w_mk: 0.35, density_kg_m3: 1900, specific_heat_j_kgk: 1050, emissivity: 0.9, max_temperature_c: 170, glass_transition_c: 180 },
  { id: "polyimide", name: "Polyimide flex", category: "pcb", conductivity_w_mk: 0.2, density_kg_m3: 1420, specific_heat_j_kgk: 1090, emissivity: 0.88, max_temperature_c: 200, glass_transition_c: 260 },
  { id: "alumina", name: "Alumina 96%", category: "ceramic", conductivity_w_mk: 24, density_kg_m3: 3720, specific_heat_j_kgk: 880, emissivity: 0.82, max_temperature_c: 1000 },
  { id: "aluminum-nitride", name: "Aluminum nitride", category: "ceramic", conductivity_w_mk: 170, density_kg_m3: 3260, specific_heat_j_kgk: 740, emissivity: 0.78, max_temperature_c: 900 },
  { id: "silicon", name: "Silicon", category: "ceramic", conductivity_w_mk: 130, density_kg_m3: 2330, specific_heat_j_kgk: 700, emissivity: 0.7, max_temperature_c: 150 },
  { id: "sac305", name: "SAC305 solder", category: "interface", conductivity_w_mk: 58, density_kg_m3: 7400, specific_heat_j_kgk: 220, emissivity: 0.35, max_temperature_c: 217 },
  { id: "thermal-paste", name: "Thermal paste", category: "interface", conductivity_w_mk: 5, density_kg_m3: 2500, specific_heat_j_kgk: 1000, emissivity: 0.9, max_temperature_c: 180 },
  { id: "silicone-pad", name: "Silicone thermal pad", category: "interface", conductivity_w_mk: 3, density_kg_m3: 2100, specific_heat_j_kgk: 1100, emissivity: 0.92, max_temperature_c: 200 },
  { id: "epoxy-potting", name: "Thermally conductive epoxy", category: "polymer", conductivity_w_mk: 0.8, density_kg_m3: 1600, specific_heat_j_kgk: 1000, emissivity: 0.91, max_temperature_c: 150, glass_transition_c: 120 },
  { id: "abs", name: "ABS", category: "polymer", conductivity_w_mk: 0.18, density_kg_m3: 1040, specific_heat_j_kgk: 1300, emissivity: 0.94, max_temperature_c: 85, glass_transition_c: 105 },
  { id: "polycarbonate", name: "Polycarbonate", category: "polymer", conductivity_w_mk: 0.2, density_kg_m3: 1200, specific_heat_j_kgk: 1200, emissivity: 0.91, max_temperature_c: 115, glass_transition_c: 147 },
  { id: "glass", name: "Soda-lime glass", category: "glass", conductivity_w_mk: 1.05, density_kg_m3: 2500, specific_heat_j_kgk: 840, emissivity: 0.92, max_temperature_c: 250, glass_transition_c: 560 },
  { id: "air", name: "Air at 25 C", category: "fluid", conductivity_w_mk: 0.0262, density_kg_m3: 1.184, specific_heat_j_kgk: 1007, emissivity: 0 },
  { id: "silicone-coating", name: "Silicone conformal coating", category: "polymer", conductivity_w_mk: 0.2, density_kg_m3: 1050, specific_heat_j_kgk: 1500, emissivity: 0.94, max_temperature_c: 200 },
];

export const thermalSurfaceFinishes: ThermalSurfaceFinish[] = [
  { id: "as-modeled", name: "As modeled", emissivity: 0.8, contact_multiplier: 1 },
  { id: "bare-metal", name: "Bare metal", emissivity: 0.12, contact_multiplier: 1 },
  { id: "black-anodized", name: "Black anodized", emissivity: 0.88, contact_multiplier: 1.05 },
  { id: "clear-anodized", name: "Clear anodized", emissivity: 0.77, contact_multiplier: 1.05 },
  { id: "painted-matte", name: "Matte painted", emissivity: 0.92, contact_multiplier: 1.12 },
  { id: "painted-gloss", name: "Gloss painted", emissivity: 0.86, contact_multiplier: 1.12 },
  { id: "polished", name: "Polished metal", emissivity: 0.05, contact_multiplier: 0.95 },
  { id: "oxidized", name: "Oxidized metal", emissivity: 0.72, contact_multiplier: 1.05 },
  { id: "conformal-coated", name: "Conformal coated", emissivity: 0.94, contact_multiplier: 1.08 },
];

export function componentThermalElements(board: ParsedBoard | null): ThermalElement[] {
  if (!board) return [];
  const boardZ = board.stackup.reduce((sum, layer) => sum + (Number(layer.thickness) || 0), 0) || 1.6;
  return board.components.map(component => {
    const height = Math.max(Math.min(component.width, component.height) * 0.45, 0.3);
    const bottomMounted = component.layer.startsWith("B.");
    return ({
    id: `thermal-${component.id}`,
    object_id: component.id,
    reference: component.ref,
    name: component.value || component.library || component.ref,
    kind: "pcb_component",
    model_path: component.modelPath,
    material_id: "",
    surface_finish_id: "as-modeled",
    enabled: true,
    coordinate_frame: "board_local",
    position: [component.at[0] - board.bounds.minX, component.at[1] - board.bounds.minY, bottomMounted ? -boardZ / 2 - height : boardZ / 2],
    dimensions_mm: { x: Math.max(component.width, 0.4), y: Math.max(component.height, 0.4), z: height },
    power_w: 0,
    emissivity: 0.8,
    max_junction_c: 125,
    max_case_c: 100,
    });
  });
}

export function normalizeThermalElements(value: unknown): ThermalElement[] {
  return Array.isArray(value) ? value.filter(item => item && typeof item === "object").map((item, index) => {
    const row = item as Partial<ThermalElement>;
    return {
      id: String(row.id || `thermal-element-${index + 1}`), object_id: row.object_id, reference: String(row.reference || `E${index + 1}`),
      name: String(row.name || row.reference || `Thermal element ${index + 1}`), kind: row.kind ?? "mechanical", model_path: row.model_path,
      material_id: String(row.material_id || ""), surface_finish_id: String(row.surface_finish_id || "as-modeled"), enabled: row.enabled !== false,
      position: (row.position ?? [0, 0, 0]) as ThermalPoint3,
      coordinate_frame: row.coordinate_frame ?? (row.kind === "pcb_component" || row.kind === "board" ? "board_local" : "domain_local"),
      dimensions_mm: { x: Number(row.dimensions_mm?.x) || 1, y: Number(row.dimensions_mm?.y) || 1, z: Number(row.dimensions_mm?.z) || 1 },
      power_w: Number(row.power_w) || 0, emissivity: Number.isFinite(Number(row.emissivity)) ? Number(row.emissivity) : 0.8,
      theta_top_c_per_w: numericOptional(row.theta_top_c_per_w), theta_bottom_c_per_w: numericOptional(row.theta_bottom_c_per_w),
      theta_jc_c_per_w: numericOptional(row.theta_jc_c_per_w), max_junction_c: numericOptional(row.max_junction_c),
      max_case_c: numericOptional(row.max_case_c), initial_temperature_c: numericOptional(row.initial_temperature_c),
    };
  }) : [];
}

export function normalizeThermalLinks(value: unknown): ThermalLink[] {
  return Array.isArray(value) ? value.filter(item => item && typeof item === "object").map((item, index) => {
    const row = item as Partial<ThermalLink>;
    return { id: String(row.id || `thermal-link-${index + 1}`), from_id: String(row.from_id || ""), to_id: String(row.to_id || ""), kind: row.kind ?? "solder", enabled: row.enabled !== false, resistance_c_per_w: Math.max(0, Number(row.resistance_c_per_w) || 0), contact_area_mm2: Math.max(0, Number(row.contact_area_mm2) || 0), thickness_mm: Math.max(0, Number(row.thickness_mm) || 0), material_id: String(row.material_id || "sac305") };
  }) : [];
}

export function screenThermalElements(elements: ThermalElement[], ambientC: number): ThermalScreening[] {
  return elements.filter(element => element.enabled).map(element => {
    const paths = [element.theta_top_c_per_w, element.theta_bottom_c_per_w].filter((value): value is number => Number.isFinite(value) && value! > 0);
    const parallelTheta = paths.length ? 1 / paths.reduce((sum, value) => sum + 1 / value, 0) : null;
    const effectiveTheta = parallelTheta === null && element.theta_jc_c_per_w === undefined ? null : (element.theta_jc_c_per_w ?? 0) + (parallelTheta ?? 0);
    const estimated = effectiveTheta === null ? null : ambientC + Math.max(0, element.power_w) * effectiveTheta;
    const limit = element.max_junction_c ?? element.max_case_c ?? thermalMaterials.find(material => material.id === element.material_id)?.max_temperature_c ?? null;
    const margin = estimated === null || limit === null ? null : limit - estimated;
    return { element_id: element.id, reference: element.reference, estimated_junction_c: estimated, limit_c: limit, margin_c: margin, status: margin === null ? "unrated" : margin <= 0 ? "critical" : margin <= 10 ? "warning" : "ok" };
  });
}

export function thermalAssemblyIssues(elements: ThermalElement[], links: ThermalLink[]): string[] {
  const ids = new Set(elements.map(element => element.id));
  const issues: string[] = [];
  elements.forEach(element => {
    if (!thermalMaterials.some(material => material.id === element.material_id)) issues.push(`${element.reference}: material is not in the project library`);
    if (element.emissivity < 0 || element.emissivity > 1) issues.push(`${element.reference}: emissivity must be between 0 and 1`);
    if (element.power_w < 0) issues.push(`${element.reference}: dissipation cannot be negative`);
    if ([element.dimensions_mm.x, element.dimensions_mm.y, element.dimensions_mm.z].some(value => !(value > 0))) issues.push(`${element.reference}: all dimensions must be positive`);
  });
  links.filter(link => link.enabled).forEach(link => {
    if (!ids.has(link.from_id) || !ids.has(link.to_id)) issues.push(`${link.id}: thermal link endpoint is missing`);
    if (link.from_id === link.to_id) issues.push(`${link.id}: thermal link cannot connect an object to itself`);
    if (link.resistance_c_per_w <= 0 && link.contact_area_mm2 <= 0) issues.push(`${link.id}: define resistance or contact area`);
  });
  return issues;
}

function numericOptional(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}
