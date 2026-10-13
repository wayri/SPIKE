export type AssemblyFrame = {
  frame_id: string;
  parent_frame_id: string;
  units: "mm";
  handedness: "right";
  transform: number[];
};

export type AssemblyPart = {
  id: string;
  source_id: string;
  name: string;
  part_type: string;
  model_id: string;
  material_id: string;
  frame: AssemblyFrame;
  placement_policy?: AssemblyPlacementPolicy | null;
  extensions: Record<string, unknown>;
};

export type AssemblyPlacementPolicy = {
  contract: "spike/assembly-placement-policy/v1";
  translation_snap_mm: number | null;
  rotation_snap_deg: number | null;
};

export type AssemblyIr = Record<string, unknown> & {
  contract: "spike/assembly-ir/v1";
  assembly_id: string;
  name: string;
  frame?: AssemblyFrame;
  boards: Array<Record<string, unknown>>;
  harnesses?: Array<Record<string, unknown>>;
  connector_mappings?: Array<Record<string, unknown>>;
  rigid_flex_links?: Array<Record<string, unknown>>;
  parts: AssemblyPart[];
  materials?: Array<Record<string, unknown>>;
  thermal_contacts?: Array<Record<string, unknown>>;
  electrical_bonds?: Array<Record<string, unknown>>;
};

export type AssemblyDesigns = {
  contract: "spike/assembly-designs/v1";
  active_design_id: string;
  designs: Array<Record<string, unknown> & { design_id: string; name?: string }>;
};

export function normalizeAssemblyDesigns(value: unknown, options: { copyDesigns?: boolean } = {}): AssemblyDesigns | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const raw = value as Record<string, unknown>;
  if (raw.contract !== "spike/assembly-designs/v1" || typeof raw.active_design_id !== "string" || !raw.active_design_id) return null;
  if (!Array.isArray(raw.designs) || raw.designs.length < 1 || raw.designs.length > 30) return null;
  const designs: AssemblyDesigns["designs"] = [];
  const identities = new Set<string>();
  for (const value of raw.designs) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const design = value as Record<string, unknown>;
    if (design.contract !== "spike/design-ir/v2" || typeof design.design_id !== "string" || !design.design_id || identities.has(design.design_id)) return null;
    identities.add(design.design_id);
    designs.push((options.copyDesigns === false ? design : structuredClone(design)) as AssemblyDesigns["designs"][number]);
  }
  if (!identities.has(raw.active_design_id)) return null;
  return { contract: "spike/assembly-designs/v1", active_design_id: raw.active_design_id, designs };
}

export type ModelReference = Record<string, unknown> & {
  id: string;
  source_id: string;
  name: string;
  model_type: "step" | "gltf" | "glb";
  uri: string;
  digest: string;
  transform: number[];
  extensions: Record<string, unknown>;
};

export type ModelIndex = Record<string, unknown> & {
  contract: "spike/model-index/v1";
  models: ModelReference[];
};

export type AssemblySceneModel = {
  partId: string;
  modelId: string;
  name: string;
  modelType: "gltf" | "glb";
  url: string;
  partTransform: number[];
  modelTransform: number[];
  visible: boolean;
  opacity: number;
};

export type AssemblySelectorPreviewModel = {
  shapeId: string;
  partId: string;
  url: string;
  partTransform: number[];
  modelTransform: number[];
  visible: boolean;
  references: ReadonlyMap<string, TopologyReference>;
};

export type AssemblyPartVisual = { visible: boolean; opacity: number };

/**
 * Viewport-only status for one AssemblyIR part.  This is deliberately not
 * persisted in AssemblyIR: it describes the current verified package read and
 * renderer outcome, not CAD or solver semantics.
 */
export type AssemblyPartViewportLoadState =
  | "pending"
  | "ready"
  | "failed"
  | "hidden"
  | "step_requires_tessellation"
  | "unavailable";
export type AssemblyPartViewportStates = Readonly<Record<string, AssemblyPartViewportLoadState>>;
/** Temporary viewport-only clipping controls. These values are never serialized into AssemblyIR. */
export type AssemblySectionPlane = {
  id: string;
  enabled: boolean;
  /** Assembly-space unitless normal. It is normalized before reaching the renderer. */
  normal: readonly [number, number, number];
  /** Signed distance from the assembly origin along the normalized normal, in mm. */
  offsetMm: number;
  /** Reverses the retained half-space without changing the geometric plane. */
  flipped: boolean;
};

export const MAX_ASSEMBLY_SECTION_PLANES = 6;

export type AssemblySection = {
  enabled: boolean;
  mode: "plane" | "planes" | "box";
  axis: "x" | "y" | "z";
  offsetMm: number;
  minXMm: number;
  maxXMm: number;
  minYMm: number;
  maxYMm: number;
  minZMm: number;
  maxZMm: number;
  planes: AssemblySectionPlane[];
};

export const DEFAULT_ASSEMBLY_SECTION: AssemblySection = {
  enabled: false,
  mode: "plane",
  axis: "x",
  offsetMm: 0,
  minXMm: -100,
  maxXMm: 100,
  minYMm: -100,
  maxYMm: 100,
  minZMm: -100,
  maxZMm: 100,
  planes: [],
};

export type AssemblySectionClippingPlane = {
  normal: readonly [number, number, number];
  point: readonly [number, number, number];
};

export type AssemblySectionViewportTransform = { centerX: number; centerY: number; scale: number };

const sectionNumber = (value: unknown, fallback: number): number => typeof value === "number" && Number.isFinite(value) ? value : fallback;

/** Accepts saved presentation state while keeping malformed inputs from hiding the scene. */
export function normalizeAssemblySection(value: unknown): AssemblySection {
  if (!value || typeof value !== "object" || Array.isArray(value)) return { ...DEFAULT_ASSEMBLY_SECTION, planes: [] };
  const raw = value as Record<string, unknown>;
  const mode = raw.mode === "box" || raw.mode === "planes" ? raw.mode : "plane";
  const axis = raw.axis === "y" || raw.axis === "z" ? raw.axis : "x";
  const ids = new Set<string>();
  const planes: AssemblySectionPlane[] = [];
  if (Array.isArray(raw.planes)) for (const candidate of raw.planes) {
    if (planes.length >= MAX_ASSEMBLY_SECTION_PLANES) break;
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) continue;
    const plane = candidate as Record<string, unknown>;
    const normal = Array.isArray(plane.normal) ? plane.normal : [];
    const x = sectionNumber(normal[0], Number.NaN), y = sectionNumber(normal[1], Number.NaN), z = sectionNumber(normal[2], Number.NaN);
    const offsetMm = sectionNumber(plane.offsetMm, Number.NaN);
    if (![x, y, z, offsetMm].every(Number.isFinite) || Math.hypot(x, y, z) <= 1e-12) continue;
    const requestedId = typeof plane.id === "string" && plane.id.trim() ? plane.id.trim().slice(0, 80) : `section-plane-${planes.length + 1}`;
    let id = requestedId;
    for (let suffix = 2; ids.has(id); suffix += 1) id = `${requestedId}-${suffix}`;
    ids.add(id);
    planes.push({ id, enabled: plane.enabled !== false, normal: [x, y, z], offsetMm, flipped: plane.flipped === true });
  }
  return {
    enabled: raw.enabled === true,
    mode,
    axis,
    offsetMm: sectionNumber(raw.offsetMm, DEFAULT_ASSEMBLY_SECTION.offsetMm),
    minXMm: sectionNumber(raw.minXMm, DEFAULT_ASSEMBLY_SECTION.minXMm),
    maxXMm: sectionNumber(raw.maxXMm, DEFAULT_ASSEMBLY_SECTION.maxXMm),
    minYMm: sectionNumber(raw.minYMm, DEFAULT_ASSEMBLY_SECTION.minYMm),
    maxYMm: sectionNumber(raw.maxYMm, DEFAULT_ASSEMBLY_SECTION.maxYMm),
    minZMm: sectionNumber(raw.minZMm, DEFAULT_ASSEMBLY_SECTION.minZMm),
    maxZMm: sectionNumber(raw.maxZMm, DEFAULT_ASSEMBLY_SECTION.maxZMm),
    planes,
  };
}

export function nextAssemblySectionPlane(section: Pick<AssemblySection, "planes">): AssemblySectionPlane {
  const used = new Set(section.planes.map(plane => plane.id));
  let index = 1;
  while (used.has(`section-plane-${index}`)) index += 1;
  return { id: `section-plane-${index}`, enabled: true, normal: [1, 0, 0], offsetMm: 0, flipped: false };
}

function viewportSectionPlane(
  normal: readonly [number, number, number],
  offsetMm: number,
  flipped: boolean,
  transform: AssemblySectionViewportTransform,
): AssemblySectionClippingPlane | null {
  const length = Math.hypot(...normal);
  if (!Number.isFinite(length) || length <= 1e-12 || !Number.isFinite(offsetMm)) return null;
  const assemblyNormal: readonly [number, number, number] = [normal[0] / length, normal[1] / length, normal[2] / length];
  const direction = flipped ? -1 : 1;
  const viewportNormal: readonly [number, number, number] = [
    assemblyNormal[0] * direction,
    -assemblyNormal[1] * direction,
    assemblyNormal[2] * direction,
  ];
  const assemblyPoint: readonly [number, number, number] = [
    assemblyNormal[0] * offsetMm,
    assemblyNormal[1] * offsetMm,
    assemblyNormal[2] * offsetMm,
  ];
  const viewportPoint: readonly [number, number, number] = [
    (assemblyPoint[0] - transform.centerX) * transform.scale,
    (transform.centerY - assemblyPoint[1]) * transform.scale,
    assemblyPoint[2] * transform.scale,
  ];
  if (![...viewportNormal, ...viewportPoint].every(Number.isFinite)) return null;
  const clean = (value: number) => Math.abs(value) <= 1e-15 ? 0 : value;
  return {
    normal: [clean(viewportNormal[0]), clean(viewportNormal[1]), clean(viewportNormal[2])],
    point: [clean(viewportPoint[0]), clean(viewportPoint[1]), clean(viewportPoint[2])],
  };
}

/**
 * Produces renderer-local clipping planes from temporary assembly-mm controls.
 * Invalid values deliberately produce no planes so malformed presentation state cannot hide a model.
 */
export function buildAssemblySectionClippingPlanes(
  section: AssemblySection,
  transform: AssemblySectionViewportTransform,
): AssemblySectionClippingPlane[] {
  if (!section.enabled || !Number.isFinite(transform.centerX) || !Number.isFinite(transform.centerY)
    || !Number.isFinite(transform.scale) || transform.scale <= 0) return [];
  if (section.mode === "plane") {
    const normal: readonly [number, number, number] = section.axis === "x" ? [1, 0, 0]
      : section.axis === "y" ? [0, 1, 0] : [0, 0, 1];
    const plane = viewportSectionPlane(normal, section.offsetMm, false, transform);
    return plane ? [plane] : [];
  }
  if (section.mode === "planes") {
    return section.planes.slice(0, MAX_ASSEMBLY_SECTION_PLANES).flatMap(plane => {
      if (!plane.enabled) return [];
      const built = viewportSectionPlane(plane.normal, plane.offsetMm, plane.flipped, transform);
      return built ? [built] : [];
    });
  }
  const bounds = [section.minXMm, section.maxXMm, section.minYMm, section.maxYMm, section.minZMm, section.maxZMm];
  if (section.mode !== "box" || !bounds.every(Number.isFinite)
    || section.minXMm > section.maxXMm || section.minYMm > section.maxYMm || section.minZMm > section.maxZMm) return [];
  return [
    viewportSectionPlane([1, 0, 0], section.minXMm, false, transform),
    viewportSectionPlane([-1, 0, 0], -section.maxXMm, false, transform),
    viewportSectionPlane([0, 1, 0], section.minYMm, false, transform),
    viewportSectionPlane([0, -1, 0], -section.maxYMm, false, transform),
    viewportSectionPlane([0, 0, 1], section.minZMm, false, transform),
    viewportSectionPlane([0, 0, -1], -section.maxZMm, false, transform),
  ].filter((plane): plane is AssemblySectionClippingPlane => plane !== null);
}

/** Mirrors Three.js clipping: negative Plane.distanceToPoint values are clipped. */
export function assemblySectionPointVisible(
  point: readonly [number, number, number],
  planes: readonly AssemblySectionClippingPlane[],
  tolerance = 1e-7,
): boolean {
  return planes.every(plane => plane.normal[0] * (point[0] - plane.point[0])
    + plane.normal[1] * (point[1] - plane.point[1])
    + plane.normal[2] * (point[2] - plane.point[2]) >= -tolerance);
}

/** True when any part of a line segment survives all active clip half-spaces. */
export function assemblySectionSegmentVisible(
  start: readonly [number, number, number],
  end: readonly [number, number, number],
  planes: readonly AssemblySectionClippingPlane[],
  tolerance = 1e-7,
): boolean {
  let lower = 0, upper = 1;
  for (const plane of planes) {
    const startDistance = plane.normal[0] * (start[0] - plane.point[0])
      + plane.normal[1] * (start[1] - plane.point[1])
      + plane.normal[2] * (start[2] - plane.point[2]) + tolerance;
    const endDistance = plane.normal[0] * (end[0] - plane.point[0])
      + plane.normal[1] * (end[1] - plane.point[1])
      + plane.normal[2] * (end[2] - plane.point[2]) + tolerance;
    if (startDistance >= 0 && endDistance >= 0) continue;
    if (startDistance < 0 && endDistance < 0) return false;
    const crossing = startDistance / (startDistance - endDistance);
    if (startDistance < 0) lower = Math.max(lower, crossing);
    else upper = Math.min(upper, crossing);
    if (lower > upper) return false;
  }
  return true;
}
const DEFAULT_PART_VISUAL: AssemblyPartVisual = { visible: true, opacity: 1 };

export function partVisualSettings(part: AssemblyPart): AssemblyPartVisual {
  const value = part.extensions?.["spike.visual"];
  if (!value || typeof value !== "object" || Array.isArray(value)) return { ...DEFAULT_PART_VISUAL };
  const raw = value as Record<string, unknown>;
  return {
    visible: typeof raw.visible === "boolean" ? raw.visible : true,
    opacity: typeof raw.opacity === "number" && Number.isFinite(raw.opacity)
      ? Math.max(0, Math.min(1, raw.opacity))
      : 1,
  };
}

export function placementPolicySettings(part: AssemblyPart): { translationSnapMm: number; rotationSnapDeg: number } {
  const policy = part.placement_policy;
  if (!policy || policy.contract !== "spike/assembly-placement-policy/v1") {
    return { translationSnapMm: 0, rotationSnapDeg: 0 };
  }
  return {
    translationSnapMm: typeof policy.translation_snap_mm === "number" && Number.isFinite(policy.translation_snap_mm) && policy.translation_snap_mm > 0
      ? policy.translation_snap_mm : 0,
    rotationSnapDeg: typeof policy.rotation_snap_deg === "number" && Number.isFinite(policy.rotation_snap_deg) && policy.rotation_snap_deg > 0 && policy.rotation_snap_deg <= 180
      ? policy.rotation_snap_deg : 0,
  };
}

const IDENTITY_TRANSFORM = [
  1, 0, 0, 0,
  0, 1, 0, 0,
  0, 0, 1, 0,
  0, 0, 0, 1,
];

export type AssemblyPlacement = {
  xMm: number;
  yMm: number;
  zMm: number;
  rxDeg: number;
  ryDeg: number;
  rzDeg: number;
};

const degrees = (value: number) => value * 180 / Math.PI;
const radians = (value: number) => value * Math.PI / 180;

export function placementFromTransform(value: unknown): AssemblyPlacement {
  const matrix = canonicalTransform(value);
  const sy = Math.max(-1, Math.min(1, -matrix[8]));
  const ry = Math.asin(sy);
  const cy = Math.cos(ry);
  const rx = Math.abs(cy) > 1e-8
    ? Math.atan2(matrix[9], matrix[10])
    : Math.atan2(-matrix[6], matrix[5]);
  const rz = Math.abs(cy) > 1e-8 ? Math.atan2(matrix[4], matrix[0]) : 0;
  return {
    xMm: matrix[3], yMm: matrix[7], zMm: matrix[11],
    rxDeg: degrees(rx), ryDeg: degrees(ry), rzDeg: degrees(rz),
  };
}

export function transformFromPlacement(placement: AssemblyPlacement): number[] {
  const values = Object.values(placement);
  if (!values.every(Number.isFinite)) throw new Error("Assembly placement values must be finite numbers.");
  const x = radians(placement.rxDeg);
  const y = radians(placement.ryDeg);
  const z = radians(placement.rzDeg);
  const sx = Math.sin(x), cx = Math.cos(x);
  const sy = Math.sin(y), cy = Math.cos(y);
  const sz = Math.sin(z), cz = Math.cos(z);
  return [
    cy * cz, sx * sy * cz - cx * sz, cx * sy * cz + sx * sz, placement.xMm,
    cy * sz, sx * sy * sz + cx * cz, cx * sy * sz - sx * cz, placement.yMm,
    -sy, sx * cy, cx * cy, placement.zMm,
    0, 0, 0, 1,
  ];
}

function canonicalTransform(value: unknown): number[] {
  return Array.isArray(value) && value.length === 16 && value.every(item => typeof item === "number" && Number.isFinite(item))
    ? [...value]
    : [...IDENTITY_TRANSFORM];
}

function multiplyRowMajor(left: number[], right: number[]): number[] {
  const result = new Array<number>(16).fill(0);
  for (let row = 0; row < 4; row += 1) {
    for (let column = 0; column < 4; column += 1) {
      for (let index = 0; index < 4; index += 1) {
        result[row * 4 + column] += left[row * 4 + index] * right[index * 4 + column];
      }
    }
  }
  return result;
}

function inverseRowMajor(value: number[]): number[] | null {
  const matrix = canonicalTransform(value);
  const rows = Array.from({ length: 4 }, (_, row) => [
    ...matrix.slice(row * 4, row * 4 + 4),
    ...IDENTITY_TRANSFORM.slice(row * 4, row * 4 + 4),
  ]);
  for (let column = 0; column < 4; column += 1) {
    let pivot = column;
    for (let row = column + 1; row < 4; row += 1) {
      if (Math.abs(rows[row][column]) > Math.abs(rows[pivot][column])) pivot = row;
    }
    if (Math.abs(rows[pivot][column]) < 1e-12) return null;
    [rows[column], rows[pivot]] = [rows[pivot], rows[column]];
    const divisor = rows[column][column];
    rows[column] = rows[column].map(item => item / divisor);
    for (let row = 0; row < 4; row += 1) {
      if (row === column) continue;
      const factor = rows[row][column];
      rows[row] = rows[row].map((item, index) => item - factor * rows[column][index]);
    }
  }
  const inverse = rows.flatMap(row => row.slice(4));
  return inverse.every(Number.isFinite) ? inverse : null;
}

function assemblyFrames(assembly: AssemblyIr): Map<string, AssemblyFrame> {
  const frames = new Map<string, AssemblyFrame>();
  if (assembly.frame?.frame_id) frames.set(assembly.frame.frame_id, assembly.frame);
  for (const board of assembly.boards) {
    const frame = board.frame;
    if (frame && typeof frame === "object" && !Array.isArray(frame) && typeof (frame as AssemblyFrame).frame_id === "string") {
      frames.set((frame as AssemblyFrame).frame_id, frame as AssemblyFrame);
    }
  }
  for (const part of assembly.parts) if (part.frame?.frame_id) frames.set(part.frame.frame_id, part.frame);
  return frames;
}

export type ReparentTarget = { frameId: string; label: string; kind: "root" | "board" | "part" };

export type AssemblyHierarchyNode = {
  entityId: string;
  frameId: string;
  parentFrameId: string;
  label: string;
  kind: "root" | "board" | "part";
  children: AssemblyHierarchyNode[];
};

export function buildAssemblyHierarchy(assembly: AssemblyIr): AssemblyHierarchyNode {
  const rootFrameId = assembly.frame?.frame_id || "assembly";
  const nodes = new Map<string, AssemblyHierarchyNode>();
  const root: AssemblyHierarchyNode = {
    entityId: assembly.assembly_id, frameId: rootFrameId, parentFrameId: "",
    label: assembly.name || "Assembly", kind: "root", children: [],
  };
  nodes.set(rootFrameId, root);
  for (const board of assembly.boards) {
    const frame = board.frame as AssemblyFrame | undefined;
    if (!frame?.frame_id) continue;
    nodes.set(frame.frame_id, {
      entityId: String(board.id ?? frame.frame_id), frameId: frame.frame_id,
      parentFrameId: frame.parent_frame_id || rootFrameId,
      label: String(board.name || board.id || frame.frame_id), kind: "board", children: [],
    });
  }
  for (const part of assembly.parts) if (part.frame?.frame_id) nodes.set(part.frame.frame_id, {
    entityId: part.id, frameId: part.frame.frame_id,
    parentFrameId: part.frame.parent_frame_id || rootFrameId,
    label: part.name || part.id, kind: "part", children: [],
  });
  for (const node of nodes.values()) {
    if (node === root) continue;
    const parent = nodes.get(node.parentFrameId);
    (parent && parent !== node ? parent : root).children.push(node);
  }
  const seen = new Set<string>([root.frameId]);
  const pending = [root];
  while (pending.length) {
    const node = pending.pop()!;
    node.children = node.children.filter(child => {
      if (seen.has(child.frameId)) return false;
      seen.add(child.frameId);
      pending.push(child);
      return true;
    });
  }
  return root;
}

export type AssemblyHierarchyRow = {
  nodeKey: string;
  entityId: string;
  frameId: string;
  kind: "root" | "board" | "part";
  depth: number;
  label: string;
  detail: string;
  partId?: string;
  viewportState?: AssemblyPartViewportLoadState;
  actionable: boolean;
  resolved: boolean;
};

export function assemblyPartViewportStates(
  assembly: AssemblyIr | null,
  index: ModelIndex,
): Record<string, AssemblyPartViewportLoadState> {
  if (!assembly) return {};
  const resolve = createAssemblyFrameResolver(assembly);
  const models = new Map(index.models.map(model => [model.id, model]));
  return Object.fromEntries(assembly.parts.map(part => {
    const model = models.get(part.model_id);
    const visual = partVisualSettings(part);
    const state: AssemblyPartViewportLoadState = !visual.visible || (part.part_type === "subassembly" && !part.model_id)
      ? "hidden"
      : model?.model_type === "step"
        ? "step_requires_tessellation"
        : !model || (model.model_type !== "gltf" && model.model_type !== "glb")
          || !resolve(part.frame)
          ? "unavailable"
          : "pending";
    return [part.id, state];
  }));
}

export function assemblyPartViewportStatusDetail(state: AssemblyPartViewportLoadState | undefined): string {
  switch (state) {
    case "pending": return "viewport load pending";
    case "ready": return "viewport ready";
    case "failed": return "viewport load failed";
    case "hidden": return "hidden after reopen";
    case "step_requires_tessellation": return "awaiting STEP tessellation";
    case "unavailable": return "viewport unavailable";
    default: return "";
  }
}

export function assemblyHierarchyRows(
  assembly: AssemblyIr,
  index: ModelIndex,
  viewportStates: AssemblyPartViewportStates = {},
): AssemblyHierarchyRow[] {
  const hierarchy = buildAssemblyHierarchy(assembly);
  const resolve = createAssemblyFrameResolver(assembly);
  const parts = new Map(assembly.parts.map(part => [part.id, part]));
  const boards = new Map(assembly.boards.map(board => [String(board.id ?? ""), board]));
  const models = new Map(index.models.map(model => [model.id, model]));
  const knownFrames = new Set([hierarchy.frameId, ...assembly.boards.map(board => String((board.frame as AssemblyFrame | undefined)?.frame_id ?? "")), ...assembly.parts.map(part => part.frame?.frame_id ?? "")].filter(Boolean));
  const rawParent = new Map<string, string>();
  for (const board of assembly.boards) {
    const frame = board.frame as AssemblyFrame | undefined;
    if (frame?.frame_id) rawParent.set(frame.frame_id, frame.parent_frame_id || hierarchy.frameId);
  }
  for (const part of assembly.parts) if (part.frame?.frame_id) rawParent.set(part.frame.frame_id, part.frame.parent_frame_id || hierarchy.frameId);
  const rows: AssemblyHierarchyRow[] = [];
  const visited = new Set<string>();
  const append = (node: AssemblyHierarchyNode, depth: number) => {
    if (visited.has(node.frameId)) return;
    visited.add(node.frameId);
    const parentId = rawParent.get(node.frameId);
    const resolved = node.kind === "root" || Boolean(parentId && knownFrames.has(parentId));
    const part = node.kind === "part" ? parts.get(node.entityId) : undefined;
    const board = node.kind === "board" ? boards.get(node.entityId) : undefined;
    const viewportState = part ? viewportStates[part.id] : undefined;
    const detail = node.kind === "root"
      ? `${assembly.boards.length} board instance${assembly.boards.length === 1 ? "" : "s"} · ${assembly.parts.length} MCAD part${assembly.parts.length === 1 ? "" : "s"}`
      : node.kind === "board"
        ? `${String(board?.design_id ?? "Unresolved design")} · ${node.frameId}`
        : part ? `${part.part_type} · ${partDisplayStatus(part, models.get(part.model_id), assembly, resolve)}${assemblyPartViewportStatusDetail(viewportState) ? `; ${assemblyPartViewportStatusDetail(viewportState)}` : ""}` : `Unresolved part · ${node.frameId}`;
    rows.push({
      nodeKey: `frame:${node.frameId}`, entityId: node.entityId, frameId: node.frameId,
      kind: node.kind, depth, label: node.label, detail: resolved ? detail : `Unresolved frame · ${detail}`,
      ...(part ? { partId: part.id, viewportState } : {}), actionable: Boolean(part && resolved), resolved,
    });
  };
  const pending = [{ node: hierarchy, depth: 0 }];
  while (pending.length) {
    const { node, depth } = pending.pop()!;
    append(node, depth);
    for (let index = node.children.length - 1; index >= 0; index--) pending.push({ node: node.children[index], depth: depth + 1 });
  }
  const rawNodes = [
    ...assembly.boards.map(board => ({ entityId: String(board.id ?? ""), frameId: String((board.frame as AssemblyFrame | undefined)?.frame_id ?? ""), kind: "board" as const, label: String(board.name || board.id || "Unresolved board") })),
    ...assembly.parts.map(part => ({ entityId: part.id, frameId: part.frame?.frame_id ?? "", kind: "part" as const, label: part.name || part.id })),
  ];
  for (const node of rawNodes) if (node.frameId && !visited.has(node.frameId)) {
    const part = node.kind === "part" ? parts.get(node.entityId) : undefined;
    rows.push({ nodeKey: `unresolved:${node.frameId}`, ...node, depth: 1, detail: `Unresolved or cyclic frame · ${node.frameId}`, ...(part ? { partId: part.id, viewportState: viewportStates[part.id] } : {}), actionable: false, resolved: false });
  }
  return rows;
}

export function validReparentTargets(assembly: AssemblyIr, partId: string): ReparentTarget[] {
  const selected = assembly.parts.find(part => part.id === partId);
  if (!selected) return [];
  const rootFrameId = assembly.frame?.frame_id || "assembly";
  const frames = assemblyFrames(assembly);
  const isDescendant = (frame: AssemblyFrame): boolean => {
    let parentId = frame.parent_frame_id || rootFrameId;
    const visited = new Set<string>([frame.frame_id]);
    while (parentId !== rootFrameId) {
      if (parentId === selected.frame.frame_id) return true;
      if (visited.has(parentId)) return true;
      visited.add(parentId);
      const parent = frames.get(parentId);
      if (!parent) return true;
      parentId = parent.parent_frame_id || rootFrameId;
    }
    return false;
  };
  const targets: ReparentTarget[] = [{ frameId: rootFrameId, label: assembly.name || "Assembly root", kind: "root" }];
  for (const board of assembly.boards) {
    const frame = board.frame as AssemblyFrame | undefined;
    if (!frame?.frame_id || frame.frame_id === selected.frame.frame_id || isDescendant(frame)) continue;
    targets.push({ frameId: frame.frame_id, label: String(board.name || board.id || frame.frame_id), kind: "board" });
  }
  for (const part of assembly.parts) {
    if (part.id === partId || !part.frame?.frame_id || isDescendant(part.frame)) continue;
    targets.push({ frameId: part.frame.frame_id, label: part.name || part.id, kind: "part" });
  }
  return targets;
}

/** A resolver is scoped to one immutable projection, so edits never reuse stale
 * frame indexes. Parent chains are composed once, without recursion.
 */
export function createAssemblyFrameResolver(assembly: AssemblyIr): (frame: AssemblyFrame) => number[] | null {
  const rootFrameId = assembly.frame?.frame_id || "assembly";
  const frames = assemblyFrames(assembly);
  const resolved = new Map<AssemblyFrame, number[] | null>();
  return frame => {
    const chain: AssemblyFrame[] = [];
    const visited = new Set<string>();
    let current: AssemblyFrame | undefined = frame;
    let world: number[] | null = null;
    while (current) {
      if (current.frame_id === rootFrameId) { world = [...IDENTITY_TRANSFORM]; break; }
      if (resolved.has(current)) { world = resolved.get(current)!; break; }
      if (!current.frame_id || visited.has(current.frame_id)) break;
      visited.add(current.frame_id);
      chain.push(current);
      const parentId = current.parent_frame_id || rootFrameId;
      if (parentId === rootFrameId) { world = [...IDENTITY_TRANSFORM]; break; }
      current = frames.get(parentId);
    }
    for (let index = chain.length - 1; index >= 0; index--) {
      const child = chain[index];
      world = world ? multiplyRowMajor(world, canonicalTransform(child.transform)) : null;
      resolved.set(child, world);
    }
    return world ? [...world] : null;
  };
}

export function resolveFrameToAssembly(assembly: AssemblyIr, frame: AssemblyFrame): number[] | null {
  return createAssemblyFrameResolver(assembly)(frame);
}

export function localTransformFromAssembly(
  assembly: AssemblyIr,
  part: AssemblyPart,
  assemblyTransform: unknown,
): number[] | null {
  const world = canonicalTransform(assemblyTransform);
  const rootFrameId = assembly.frame?.frame_id || "assembly";
  const parentId = part.frame.parent_frame_id || rootFrameId;
  if (parentId === rootFrameId) return world;
  const parent = assemblyFrames(assembly).get(parentId);
  if (!parent) return null;
  const parentWorld = resolveFrameToAssembly(assembly, parent);
  const inverseParent = parentWorld ? inverseRowMajor(parentWorld) : null;
  return inverseParent ? multiplyRowMajor(inverseParent, world) : null;
}

export function visualModelIds(assembly: AssemblyIr | null, index: ModelIndex): string[] {
  if (!assembly) return [];
  const resolve = createAssemblyFrameResolver(assembly);
  const visualIds = new Set(index.models
    .filter(model => model.model_type === "gltf" || model.model_type === "glb")
    .map(model => model.id));
  return [...new Set(assembly.parts
    .filter(part => partVisualSettings(part).visible && Boolean(resolve(part.frame)))
    .map(part => part.model_id)
    .filter(id => visualIds.has(id)))];
}

export function createAssemblySceneModels(
  assembly: AssemblyIr | null,
  index: ModelIndex,
  artifactUrls: ReadonlyMap<string, string>,
): AssemblySceneModel[] {
  if (!assembly) return [];
  const resolve = createAssemblyFrameResolver(assembly);
  const models = new Map(index.models.map(model => [model.id, model]));
  return assembly.parts.flatMap(part => {
    const partTransform = resolve(part.frame);
    if (!partTransform) return [];
    const model = models.get(part.model_id);
    const url = artifactUrls.get(part.model_id);
    if (!model || !url || (model.model_type !== "gltf" && model.model_type !== "glb")) return [];
    const visual = partVisualSettings(part);
    return [{
      partId: part.id,
      modelId: model.id,
      name: part.name || model.name,
      modelType: model.model_type,
      url,
      partTransform,
      modelTransform: canonicalTransform(model.transform),
      visible: visual.visible,
      opacity: visual.opacity,
    }];
  });
}

export function createAssemblySelectorPreviewModels(
  assembly: AssemblyIr | null,
  index: ModelIndex,
  shapes: AssemblyPackageShapesIndex | null,
  artifactUrls: ReadonlyMap<string, string>,
): AssemblySelectorPreviewModel[] {
  if (!assembly || !shapes) return [];
  const resolve = createAssemblyFrameResolver(assembly);
  const parts = new Map(assembly.parts.map(part => [part.id, part]));
  const models = new Map(index.models.map(model => [model.id, model]));
  return shapes.shapes.flatMap(shape => {
    const part = parts.get(shape.part_id);
    const model = models.get(shape.source_model_id);
    const url = artifactUrls.get(shape.shape_id);
    if (!part || !model || !url || !shape.selector_preview) return [];
    const partTransform = resolve(part.frame);
    if (!partTransform) return [];
    return [{
      shapeId: shape.shape_id, partId: shape.part_id, url, partTransform,
      modelTransform: canonicalTransform(model.transform), visible: partVisualSettings(part).visible,
      references: new Map(shape.entities
        .filter(entity => entity.kind === "face" || entity.kind === "edge" || entity.kind === "axis")
        .map(entity => [entity.topology_id, {
          ref_kind: "package_shape_topology" as const, part_id: shape.part_id,
          shape_id: shape.shape_id, topology_id: entity.topology_id,
          topology_kind: entity.kind,
        }])),
    }];
  });
}

export function normalizeAssemblyIr(value: unknown): AssemblyIr | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const raw = value as Record<string, unknown>;
  if (raw.contract !== "spike/assembly-ir/v1" || !Array.isArray(raw.parts) || !Array.isArray(raw.boards)) return null;
  return raw as AssemblyIr;
}

export function normalizeModelIndex(value: unknown): ModelIndex {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { contract: "spike/model-index/v1", models: [] };
  }
  const raw = value as Record<string, unknown>;
  return raw.contract === "spike/model-index/v1" && Array.isArray(raw.models)
    ? raw as ModelIndex
    : { contract: "spike/model-index/v1", models: [] };
}

export function modelDisplayStatus(model: ModelReference | undefined): string {
  if (!model) return "Model metadata unavailable";
  if (model.model_type === "step") return "STEP retained; tessellation required for viewport display";
  if (model.model_type === "gltf") return "glTF visualizable from a verified desktop package";
  return "GLB visualizable from a verified desktop package";
}

export function partDisplayStatus(part: AssemblyPart, model: ModelReference | undefined, assembly: AssemblyIr | null, resolve?: (frame: AssemblyFrame) => number[] | null): string {
  if (part.part_type === "subassembly" && !part.model_id) return "Assembly group; placement applies to its children";
  const visual = partVisualSettings(part);
  const display = !visual.visible ? "; hidden after reopen" : visual.opacity < 0.999 ? `; ${Math.round(visual.opacity * 100)}% opacity` : "";
  const status = `${modelDisplayStatus(model)}${display}`;
  const rootFrameId = assembly?.frame?.frame_id || "assembly";
  if (model && model.model_type !== "step" && assembly && (part.frame?.parent_frame_id || rootFrameId) !== rootFrameId) {
    return (resolve ? resolve(part.frame) : resolveFrameToAssembly(assembly, part.frame))
      ? `${status}; nested parent-frame transform composed`
      : `${status}; unresolved or cyclic parent-frame chain`;
  }
  return status;
}
import type { AssemblyPackageShapesIndex, TopologyReference } from "./assemblyPackageShapes";
