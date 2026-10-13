// SPDX-License-Identifier: Apache-2.0
import type { ParsedBoard } from "./boardParser";
import { projectNormalizedBoard } from "./normalizedBoard";

/** Project validated retained IR into the existing display adapter. Coordinate
 * arrays stay shared with the immutable IR; no source reparse or CAD export is
 * necessary to show copper and explicit component fallback geometry. */
export function projectAssemblyCanonicalBoard(design: Record<string, any>): ParsedBoard {
  if (design.contract !== "spike/design-ir/v2") throw new Error("Unsupported retained board display contract.");
  const layerNames = new Map<string, string>(design.layers.map((row: any) => [row.id, row.name]));
  const components = new Map<string, string>(design.components.map((row: any) => [row.id, row.reference]));
  const legacy = (row: any) => row.extensions?.["spike.v1"] ?? {};
  const layer = (id: string) => {
    if (id === "*.Cu" || id === "*.Mask" || id === "F&B.Cu") return id;
    const name = layerNames.get(id);
    if (!name) throw new Error(`Retained geometry refers to an unavailable layer: ${id}`);
    return name;
  };
  const bounds = design.metadata?.board_bounds_mm;
  if (!Array.isArray(bounds) || bounds.length !== 4 || !bounds.every(Number.isFinite)) {
    throw new Error("Retained board display has no finite native bounds.");
  }
  const snapshot = { canonical_design: design, design: {
    metadata: design.metadata, nets: design.nets,
    layers: design.layers.map((row: any) => ({ id: row.id, name: row.name, type: row.layer_type })),
    stackup: design.metadata["spike.v1.stackup"] ?? design.layers.filter((row: any) => row.thickness_mm > 0)
      .map((row: any) => ({ name: row.name, type: row.layer_type, thickness: row.thickness_mm })),
    tracks: design.tracks.map((row: any) => ({ id: row.id, start: row.start_mm, end: row.end_mm,
      width: row.width_mm, layer: layer(row.layer_id), net_id: row.net_id })),
    vias: design.vias.map((row: any) => ({ ...legacy(row), id: row.id, at: row.center_mm,
      diameter: row.diameter_mm, drill: row.drill_mm, layers: [layer(row.start_layer_id), layer(row.end_layer_id)], net_id: row.net_id })),
    pads: design.pads.map((row: any) => ({ ...legacy(row), ...row, at: row.center_mm, size: row.size_mm,
      drill: row.drill_size_mm?.[0] ?? 0, layers: row.layer_ids.map(layer), layer: layer(row.layer_ids[0]),
      component: components.get(row.component_id), rotation: row.rotation_deg ?? legacy(row).rotation ?? 0 })),
    components: design.components.map((row: any) => ({ ...legacy(row), ...row, at: row.position_mm,
      rotation: row.rotation_deg })),
    zones: design.zones.flatMap((row: any) => row.layer_ids.map((id: string) => ({ ...row, layer: layer(id) }))),
    regions: design.regions ?? [], bends: design.bends ?? [], technology: design.metadata.technology,
  } };
  return projectNormalizedBoard(snapshot);
}
