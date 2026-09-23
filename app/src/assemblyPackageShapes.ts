export type TopologyKind = "solid" | "shell" | "face" | "edge" | "axis" | "vertex";

export type TopologyEntity = {
  topology_id: string;
  kind: TopologyKind;
  native_persistent_id: string;
  fingerprint_sha256: string;
  support: {
    surface_kind: string | null;
    curve_kind: string | null;
    axis_topology_id: string | null;
  };
  geometry?: {
    contract: "spike/package-shape-selector-geometry/v1";
    coordinate_space: "shape_local_mm";
    representation: "unsupported" | "point" | "line" | "circle" | "plane" | "axis";
    origin_mm: [number, number, number] | null;
    direction: [number, number, number] | null;
    radius_mm: number | null;
  };
};

export type PackageShape = {
  shape_id: string;
  part_id: string;
  source_model_id: string;
  source_artifact_uri: string;
  source_sha256: string;
  topology_artifact_uri: string;
  topology_artifact_sha256: string;
  kernel: { id: string; contract: "spike/package-shape-kernel/v1"; version: string };
  extraction: {
    status: "complete";
    source_format: "step";
    source_model_transform_sha256: string;
    topology_ready: true;
    solver_ready: false;
  };
  entities: TopologyEntity[];
  selector_preview?: {
    contract: "spike/package-shape-selector-preview/v1";
    artifact_uri: string;
    artifact_sha256: string;
    source_sha256: string;
    topology_artifact_sha256: string;
    selector_inventory_sha256: string;
    freecad_version: string;
    linear_deflection_mm: number;
    face_count: number;
    edge_count: number;
    axis_count: number;
    visual_only: true;
    solver_ready: false;
  };
  extensions: Record<string, unknown>;
};

export type TopologyReference = {
  ref_kind: "package_shape_topology";
  part_id: string;
  shape_id: string;
  topology_id: string;
  topology_kind: TopologyKind;
};

export type TopologyConstraint = {
  constraint_id: string;
  kind: "face" | "edge" | "axis" | "concentric" | "coincident" | "distance" | "angle";
  references: TopologyReference[];
  value_mm: number | null;
  value_deg: number | null;
  status: "defined";
};

export type TopologyBinding = {
  assembly_entity_id: string;
  endpoint_a: TopologyReference;
  endpoint_b: TopologyReference;
};

export type AssemblyPackageShapesIndex = Record<string, unknown> & {
  contract: "spike/assembly-package-shapes/v1";
  assembly_id: string;
  shapes: PackageShape[];
  constraints: TopologyConstraint[];
  thermal_contact_bindings: TopologyBinding[];
  electrical_bond_bindings: TopologyBinding[];
  extensions: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

const object = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const kinds = new Set<TopologyKind>(["solid", "shell", "face", "edge", "axis", "vertex"]);

export function normalizeAssemblyPackageShapes(value: unknown): AssemblyPackageShapesIndex | null {
  if (!object(value) || value.contract !== "spike/assembly-package-shapes/v1" || typeof value.assembly_id !== "string") return null;
  if (!Array.isArray(value.shapes) || !Array.isArray(value.constraints) || !Array.isArray(value.thermal_contact_bindings) || !Array.isArray(value.electrical_bond_bindings)) return null;
  const validShapes = value.shapes.every(shape => object(shape)
    && typeof shape.shape_id === "string"
    && typeof shape.part_id === "string"
    && typeof shape.source_model_id === "string"
    && object(shape.extraction)
    && shape.extraction.topology_ready === true
    && shape.extraction.solver_ready === false
    && Array.isArray(shape.entities)
    && shape.entities.every(entity => object(entity)
      && typeof entity.topology_id === "string"
      && typeof entity.native_persistent_id === "string"
      && kinds.has(entity.kind as TopologyKind)
      && object(entity.support)
      && (entity.geometry === undefined || (object(entity.geometry)
        && entity.geometry.contract === "spike/package-shape-selector-geometry/v1"
        && entity.geometry.coordinate_space === "shape_local_mm"))));
  return validShapes ? value as AssemblyPackageShapesIndex : null;
}

export function packageShapeForPart(index: AssemblyPackageShapesIndex | null, partId: string): PackageShape | null {
  return index?.shapes.find(shape => shape.part_id === partId) ?? null;
}

export function topologyReference(shape: PackageShape, entity: TopologyEntity): TopologyReference {
  return {
    ref_kind: "package_shape_topology",
    part_id: shape.part_id,
    shape_id: shape.shape_id,
    topology_id: entity.topology_id,
    topology_kind: entity.kind,
  };
}

export function topologyEntityOptions(
  index: AssemblyPackageShapesIndex | null,
  allowedKinds: ReadonlySet<TopologyKind>,
  query = "",
  limit = 200,
): Array<{ key: string; label: string; reference: TopologyReference }> {
  const needle = query.trim().toLowerCase();
  const options: Array<{ key: string; label: string; reference: TopologyReference }> = [];
  for (const shape of index?.shapes ?? []) {
    for (const entity of shape.entities) {
      if (!allowedKinds.has(entity.kind)) continue;
      const label = `${shape.part_id} · ${entity.kind} · ${entity.native_persistent_id}`;
      if (needle && !label.toLowerCase().includes(needle) && !entity.topology_id.toLowerCase().includes(needle)) continue;
      options.push({ key: entity.topology_id, label, reference: topologyReference(shape, entity) });
      if (options.length >= limit) return options;
    }
  }
  return options;
}
