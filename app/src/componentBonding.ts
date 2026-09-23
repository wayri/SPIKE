import type { ParsedBoard, ParsedComponent, ParsedPad, Point } from "./boardParser";
import type { BondRecord, BondStatus, BondValidationResult } from "./BondManager";

export const COMPONENT_BONDS_CONTRACT = "spike/component-bonds/v1";
export const DEFAULT_BOND_SEARCH_DISTANCE_MM = 0.25;
export const MAX_BOND_SEARCH_DISTANCE_MM = 10;

export type SolverComponentBond = {
  id: string;
  enabled: boolean;
  source: "authoritative-pad" | "nearest-pad" | "manual";
  component_id?: string;
  component_ref: string;
  pad_id?: string;
  pad_number: string;
  net_name: string;
  position_mm?: Point;
  connected_layers: string[];
  search_distance_mm: number;
  material: string;
  electrical: {
    resistance_ohm: number;
    current_limit_a: number;
  };
  thermal: {
    conductivity_w_mk: number;
    contact_area_mm2: number;
  };
  status: BondStatus;
};

const copperLayersForPad = (board: ParsedBoard, pad: ParsedPad): string[] => {
  const boardCopper = board.layers.filter(layer => layer.endsWith(".Cu"));
  const declared = pad.layers?.length ? pad.layers : [pad.layer];
  if (declared.includes("*.Cu")) return boardCopper;
  const copper = declared.filter(layer => layer.endsWith(".Cu"));
  if (!copper.length && pad.layer.endsWith(".Cu")) copper.push(pad.layer);
  return [...new Set(copper)];
};

const contactArea = (pad: ParsedPad): number => {
  const gross = Math.max(pad.width, 0) * Math.max(pad.height, 0);
  const hole = pad.drill > 0 ? Math.PI * Math.pow(pad.drill / 2, 2) : 0;
  return Math.max(gross - hole, 0.0001);
};

const distance = (a: Point, b: Point) => Math.hypot(a[0] - b[0], a[1] - b[1]);

const bondFrom = (
  board: ParsedBoard,
  component: ParsedComponent,
  pad: ParsedPad,
  source: SolverComponentBond["source"],
  searchDistanceMm: number,
): BondRecord => {
  const layers = copperLayersForPad(board, pad);
  const status: BondStatus = pad.net && layers.length ? "ready" : "warning";
  return {
    id: `bond:${component.id}:${pad.id}`,
    componentId: component.id,
    padId: pad.id,
    position: pad.at,
    connectedLayers: layers,
    source,
    part: component.value || component.library || "Component",
    reference: component.ref,
    pad: pad.name || "?",
    net: pad.net ?? "",
    surface: layers.join(" / ") || pad.layer || component.layer,
    searchDistanceMm,
    electricalResistanceOhm: 0.001,
    currentLimitA: 1,
    thermalConductivityWmK: 50,
    contactAreaMm2: Number(contactArea(pad).toFixed(6)),
    bondMaterial: "SAC305 solder (project default)",
    status,
    enabled: true,
  };
};

/**
 * Builds one reviewed terminal-to-pad bond per imported pad. KiCad footprint
 * ownership is authoritative. Spatial search is only used when an imported
 * component has no owned pads, and an ambiguous nearest candidate is not used.
 */
export function inferComponentBonds(board: ParsedBoard, requestedDistanceMm = DEFAULT_BOND_SEARCH_DISTANCE_MM): BondRecord[] {
  const searchDistanceMm = Math.min(MAX_BOND_SEARCH_DISTANCE_MM, Math.max(0.001, requestedDistanceMm));
  const bonds: BondRecord[] = [];
  const claimedFallbackPads = new Set<string>();
  for (const component of board.components) {
    const owned = board.pads.filter(pad => pad.ref === component.ref);
    if (owned.length) {
      owned.forEach(pad => bonds.push(bondFrom(board, component, pad, "authoritative-pad", searchDistanceMm)));
      continue;
    }
    const candidates = board.pads
      .map(pad => ({ pad, distanceMm: distance(component.at, pad.at) }))
      .filter(item => item.distanceMm <= searchDistanceMm && !claimedFallbackPads.has(item.pad.id))
      .sort((a, b) => a.distanceMm - b.distanceMm || a.pad.id.localeCompare(b.pad.id));
    if (!candidates.length) continue;
    const nearest = candidates[0];
    const ambiguous = candidates.length > 1 && Math.abs(candidates[1].distanceMm - nearest.distanceMm) < 0.001;
    if (ambiguous) continue;
    claimedFallbackPads.add(nearest.pad.id);
    bonds.push(bondFrom(board, component, nearest.pad, "nearest-pad", searchDistanceMm));
  }
  return bonds.sort((a, b) => a.reference.localeCompare(b.reference, undefined, { numeric: true }) || a.pad.localeCompare(b.pad, undefined, { numeric: true }));
}

export function validateComponentBonds(bonds: readonly BondRecord[], board: ParsedBoard | null): BondValidationResult[] {
  const issues: BondValidationResult[] = [];
  const padById = new Map(board?.pads.map(pad => [pad.id, pad]) ?? []);
  const componentById = new Map(board?.components.map(component => [component.id, component]) ?? []);
  const seen = new Set<string>();
  for (const bond of bonds) {
    if (!bond.enabled) continue;
    const key = `${bond.componentId ?? bond.reference}:${bond.padId ?? bond.pad}`;
    if (seen.has(key)) issues.push({ bondId: bond.id, status: "invalid", message: "Duplicate component-to-pad bond." });
    seen.add(key);
    const pad = bond.padId ? padById.get(bond.padId) : undefined;
    const component = bond.componentId ? componentById.get(bond.componentId) : undefined;
    if (!bond.reference || !bond.padId || !pad) issues.push({ bondId: bond.id, status: "invalid", message: "Bond does not resolve to an imported pad." });
    else if (component && pad.ref && pad.ref !== component.ref) issues.push({ bondId: bond.id, status: "invalid", message: "Pad belongs to a different component." });
    else if (pad.net && bond.net && pad.net !== bond.net) issues.push({ bondId: bond.id, status: "invalid", message: "Edited bond net differs from the pad net." });
    if (!bond.net) issues.push({ bondId: bond.id, status: "warning", message: "No electrical net is assigned; this bond is thermal-only until reviewed." });
    if (!bond.connectedLayers.length) issues.push({ bondId: bond.id, status: "warning", message: "No copper layer is connected." });
    if (!(bond.searchDistanceMm > 0 && bond.searchDistanceMm <= MAX_BOND_SEARCH_DISTANCE_MM)) issues.push({ bondId: bond.id, status: "invalid", message: "Search distance must be greater than 0 and at most 10 mm." });
    if (bond.electricalResistanceOhm < 0 || bond.currentLimitA <= 0) issues.push({ bondId: bond.id, status: "invalid", message: "Electrical resistance must be non-negative and current limit positive." });
    if (bond.thermalConductivityWmK <= 0 || bond.contactAreaMm2 <= 0) issues.push({ bondId: bond.id, status: "invalid", message: "Thermal conductivity and contact area must be positive." });
  }
  return issues.length ? issues : [{ status: "ready", message: `${bonds.filter(bond => bond.enabled).length} enabled bonds passed structural validation.` }];
}

export function bondsForSolver(bonds: readonly BondRecord[]): SolverComponentBond[] {
  return bonds.map(bond => ({
    id: bond.id,
    enabled: bond.enabled,
    source: bond.source ?? "manual",
    component_id: bond.componentId,
    component_ref: bond.reference,
    pad_id: bond.padId,
    pad_number: bond.pad,
    net_name: bond.net,
    position_mm: bond.position,
    connected_layers: [...bond.connectedLayers],
    search_distance_mm: bond.searchDistanceMm,
    material: bond.bondMaterial,
    electrical: { resistance_ohm: bond.electricalResistanceOhm, current_limit_a: bond.currentLimitA },
    thermal: { conductivity_w_mk: bond.thermalConductivityWmK, contact_area_mm2: bond.contactAreaMm2 },
    status: bond.status,
  }));
}
