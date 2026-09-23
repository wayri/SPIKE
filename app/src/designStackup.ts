// SPDX-License-Identifier: Apache-2.0
import type { ParsedStackupLayer } from "./boardParser";

type Row = Record<string, any>;
const object = (value: unknown): Row => value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};

const retainedRow = (row: ParsedStackupLayer): Row => ({
  name: row.name, type: row.type,
  ...(row.color ? { color: row.color } : {}),
  ...(row.thickness === undefined ? {} : { thickness: row.thickness, thickness_mm: row.thickness }),
  ...(row.material ? { material: row.material, material_name: row.material } : {}),
  ...(row.epsilonR === undefined ? {} : { epsilon_r: row.epsilonR, relative_permittivity: row.epsilonR }),
  ...(row.lossTangent === undefined ? {} : { loss_tangent: row.lossTangent }),
});

/** Update every authoritative DesignIR v2 stackup projection used by the worker. */
export function applyStackupToDesignIr(value: unknown, stackup: ParsedStackupLayer[]): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const design = structuredClone(value) as Row;
  const retained = stackup.map(retainedRow), byName = new Map(retained.map(row => [String(row.name), row]));
  const materials = Array.isArray(design.materials) ? design.materials as Row[] : [];
  let zMm = 0;
  const zByName = new Map<string, number>();
  for (const row of retained) {
    zByName.set(String(row.name), zMm);
    const thickness = Number(row.thickness_mm);
    if (Number.isFinite(thickness)) zMm += thickness;
  }
  if (Array.isArray(design.layers)) design.layers = design.layers.map((source: unknown, index: number) => {
    const layer = object(source), row = byName.get(String(layer.name ?? ""));
    if (!row) return layer;
    const thickness = Number(row.thickness_mm);
    const materialId = typeof layer.material_id === "string" && layer.material_id ? layer.material_id : `stackup-material-${index + 1}`;
    const next = { ...layer, material_id: materialId, z_mm: zByName.get(String(layer.name)) ?? 0, thickness_mm: Number.isFinite(thickness) ? thickness : null,
      extensions: { ...object(layer.extensions), "spike.v1.stackup": { ...row } } };
    let material = materials.find(item => item.id === materialId);
    if (!material) { material = { id: materialId }; materials.push(material); }
    material.name = String(row.material ?? row.type ?? material.name ?? "unspecified");
    material.material_class = String(row.type ?? material.material_class ?? "unspecified");
    material.extensions = { ...object(material.extensions), "spike.v1": { ...row } };
    if (row.relative_permittivity !== undefined) material.relative_permittivity = Number(row.relative_permittivity);
    else delete material.relative_permittivity;
    if (row.loss_tangent !== undefined) material.loss_tangent = Number(row.loss_tangent);
    else delete material.loss_tangent;
    return next;
  });
  design.materials = materials;
  design.vendor_extensions = { ...object(design.vendor_extensions), "spike.v1": { ...object(object(design.vendor_extensions)["spike.v1"]), stackup: retained } };
  design.metadata = { ...object(design.metadata), "spike.v1.stackup": retained };
  return design;
}
