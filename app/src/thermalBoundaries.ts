// SPDX-License-Identifier: Apache-2.0
import type { ThermalElement } from "./thermalAssembly";

export type ThermalSurface = "whole" | "+X" | "-X" | "+Y" | "-Y" | "+Z" | "-Z" | (string & {});
export type ThermalBoundary = {
  id: string;
  enabled: boolean;
  object_ref: string;
  surface: ThermalSurface;
  kind: "conduction" | "convection" | "radiation";
  target_ref?: string;
  resistance_c_per_w?: number;
  heat_transfer_coefficient_w_m2_k?: number;
  area_mm2?: number;
  emissivity?: number;
  ambient_temperature_c?: number;
  surroundings_temperature_c?: number;
};
export type ComponentThermalInput = { component_ref: string; power_w: number; resistance_top_c_per_w?: number; resistance_bottom_c_per_w?: number; thermal_capacitance_j_per_c?: number; initial_temperature_c?: number };

const optionalNumber = (value: unknown): number | undefined => value === null || value === undefined || value === "" || !Number.isFinite(Number(value)) ? undefined : Number(value);
export const presetThermalSurfaces = new Set<string>(["whole", "+X", "-X", "+Y", "-Y", "+Z", "-Z"]);
const kinds = new Set<ThermalBoundary["kind"]>(["conduction", "convection", "radiation"]);

export function normalizeThermalBoundaries(value: unknown): ThermalBoundary[] {
  return Array.isArray(value) ? value.filter(item => item && typeof item === "object").map((item, index) => {
    const row = item as Partial<ThermalBoundary>;
    return {
      id: String(row.id || `thermal-boundary-${index + 1}`), enabled: row.enabled !== false,
      object_ref: String(row.object_ref ?? ""), surface: typeof row.surface === "string" && row.surface.trim() ? row.surface : "whole",
      kind: kinds.has(row.kind as ThermalBoundary["kind"]) ? row.kind! : "convection",
      target_ref: row.target_ref === undefined ? undefined : String(row.target_ref),
      resistance_c_per_w: optionalNumber(row.resistance_c_per_w),
      heat_transfer_coefficient_w_m2_k: optionalNumber(row.heat_transfer_coefficient_w_m2_k),
      area_mm2: optionalNumber(row.area_mm2), emissivity: optionalNumber(row.emissivity),
      ambient_temperature_c: optionalNumber(row.ambient_temperature_c),
      surroundings_temperature_c: optionalNumber(row.surroundings_temperature_c),
    };
  }) : [];
}

export function thermalSurfaceAreaMm2(element: ThermalElement, surface: ThermalSurface): number {
  const { x, y, z } = element.dimensions_mm;
  if (surface === "+X" || surface === "-X") return y * z;
  if (surface === "+Y" || surface === "-Y") return x * z;
  if (surface === "+Z" || surface === "-Z") return x * y;
  return surface === "whole" ? 2 * (x * y + x * z + y * z) : 0;
}

export function createThermalBoundary(element: ThermalElement, kind: ThermalBoundary["kind"], index: number): ThermalBoundary {
  return {
    id: `thermal-boundary-${Date.now()}-${index}`, enabled: true, object_ref: element.reference,
    surface: "whole", kind, target_ref: "ambient", resistance_c_per_w: 10,
    heat_transfer_coefficient_w_m2_k: 5, area_mm2: thermalSurfaceAreaMm2(element, "whole"),
    emissivity: element.emissivity,
  };
}

export function nativeThermalInputs(elements: ThermalElement[], boundaries: ThermalBoundary[], boardFallback: ComponentThermalInput): { components: ComponentThermalInput[]; selectedObjects: ThermalElement[]; boardPowerUsed: boolean } {
  const referenced = new Set<string>();
  for (const boundary of boundaries.filter(item => item.enabled)) {
    referenced.add(boundary.object_ref);
    if (boundary.kind === "conduction" && boundary.target_ref && boundary.target_ref !== "ambient") referenced.add(boundary.target_ref);
  }
  const selectedObjects = elements.filter(item => item.enabled && (item.power_w > 0 || item.initial_temperature_c !== undefined || referenced.has(item.reference)));
  const components: ComponentThermalInput[] = selectedObjects.map(item => ({
    component_ref: item.reference, power_w: item.power_w,
    resistance_top_c_per_w: item.theta_top_c_per_w, resistance_bottom_c_per_w: item.theta_bottom_c_per_w,
    thermal_capacitance_j_per_c: item.thermal_capacitance_j_per_c, initial_temperature_c: item.initial_temperature_c,
  }));
  const boardPowerUsed = selectedObjects.length === 0;
  if (!selectedObjects.some(item => item.reference === "BOARD") && (boardPowerUsed || referenced.has("BOARD"))) {
    components.push({ ...boardFallback, power_w: boardPowerUsed ? boardFallback.power_w : 0 });
  }
  return { components, selectedObjects, boardPowerUsed };
}
