import { uniqueNetIdsByName } from "./assemblyNetIdentity";
import { resolveFrameToAssembly, type AssemblyDesigns, type AssemblyFrame, type AssemblyIr } from "./mcadAssembly";

export type HarnessPointMm = readonly [number, number, number];

export function harnessConductorSelected(harnessId: string, wireId: string | null, selectedHarnessId: string | null,
  selectedWireId: string | null): boolean {
  return harnessId === selectedHarnessId && (!selectedWireId || wireId === selectedWireId);
}

export type VirtualHarnessEndpoint = {
  boardId: string;
  connectorId: string;
  positionMm: HarnessPointMm;
};

export type HarnessConductorRole = "unspecified" | "power" | "return" | "signal" | "shield" | "other";
export type HarnessConductorPresentation = "schematic" | "twisted" | "bundle-fallback";

export type VirtualHarnessConductor = {
  id: string;
  fromPin: string;
  toPin: string;
  role: HarnessConductorRole;
  returnWireId?: string;
  pairId?: string;
  pairKind?: "differential" | "twisted";
  pairMemberIndex?: 0 | 1;
  twisted: boolean;
  twistPitchMm?: number;
};

export type HarnessConductorGeometry = {
  harnessId: string;
  wireId: string | null;
  role: HarnessConductorRole;
  pairId?: string;
  presentation: HarnessConductorPresentation;
  pointsMm: HarnessPointMm[];
  samplingCapped: boolean;
};

export type VirtualHarnessVisual = {
  id: string;
  name: string;
  lengthMm: number;
  endpointA: VirtualHarnessEndpoint;
  endpointB: VirtualHarnessEndpoint;
  /** Assembly-space control points; the viewport applies its normal mm transform. */
  routeMm: HarnessPointMm[];
  routedPolyline?: boolean;
  /** Saved, pin-map-validated conductors. Empty means the centerline is a schematic bundle fallback. */
  conductors: VirtualHarnessConductor[];
  selectedConductorId?: string;
};

export type HarnessVisualizationDiagnostic = {
  code: "duplicate_harness_id" | "invalid_harness_id" | "invalid_endpoint" | "unresolved_board" | "unresolved_connector" | "invalid_connector_position" | "visualization_limit" | "conductor_visualization_limit" | "invalid_conductor_metadata" | "incomplete_twist_metadata" | "stale_route";
  harnessId?: string;
  message: string;
};

export type HarnessVisualizationProjection = {
  visuals: VirtualHarnessVisual[];
  diagnostics: HarnessVisualizationDiagnostic[];
  totalHarnesses: number;
  unresolvedHarnesses: number;
  truncatedHarnesses: number;
  conductorVisuals: number;
  truncatedConductors: number;
};

export type VirtualBoardVisual = {
  netIdsByName?: Record<string, string>;
  netNamesById?: Record<string, string>;
  id: string;
  name: string;
  designId: string;
  /** Retained source identity; may differ from the assembly design UUID. */
  sourceNativeId?: string;
  active: boolean;
  widthMm: number;
  heightMm: number;
  localCenterMm: readonly [number, number, number];
  transform: number[];
  thicknessMm?: number;
};

export type VirtualBoardProjection = {
  visuals: VirtualBoardVisual[];
  unresolvedBoardIds: string[];
};

/** The viewport never creates an unbounded number of interactive line objects. */
export const MAX_VIRTUAL_HARNESS_VISUALS = 512;
/** Bounds both scene objects and CPU work when large imported looms are opened. */
export const MAX_HARNESS_CONDUCTOR_VISUALS = 2048;
export const MAX_HARNESS_CONDUCTOR_POINTS = 192;

/** Renderer theme tokens. Selection is applied separately so role identity remains stable. */
export const HARNESS_ROLE_COLOR_TOKENS: Readonly<Record<HarnessConductorRole, number>> = {
  unspecified: 0x78b7c5,
  power: 0xe36f4f,
  return: 0x8090aa,
  signal: 0x55c7dc,
  shield: 0xb2aaa0,
  other: 0xc18ad6,
};
export const HARNESS_SELECTION_COLOR_TOKEN = 0xffb638;

type BoardRecord = Record<string, unknown> & { id?: unknown; frame?: AssemblyFrame; name?: unknown };
type ConnectorRecord = { boardId: string; connectorId: string; positionMm: HarnessPointMm };

const endpointSeparator = "::";
const connectorKey = (boardId: string, connectorId: string) => `${boardId}\u0000${connectorId}`;

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function finitePoint(value: unknown): HarnessPointMm | null {
  if (Array.isArray(value) && value.length >= 2 && value.length <= 3 && value.every(item => typeof item === "number" && Number.isFinite(item))) {
    return [value[0], value[1], value[2] ?? 0];
  }
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const point = value as Record<string, unknown>;
    const x = point.x_mm ?? point.x;
    const y = point.y_mm ?? point.y;
    const z = point.z_mm ?? point.z ?? 0;
    if ([x, y, z].every(item => typeof item === "number" && Number.isFinite(item))) return [x as number, y as number, z as number];
  }
  return null;
}

function endpointReference(value: unknown): { boardId: string; connectorId: string } | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const item = value as Record<string, unknown>;
    const boardId = text(item.board_id ?? item.boardId ?? item.board_instance_id);
    const connectorId = text(item.connector_id ?? item.connectorId ?? item.id);
    return boardId && connectorId ? { boardId, connectorId } : null;
  }
  const raw = text(value);
  const separator = raw.includes(endpointSeparator) ? endpointSeparator : raw.includes(":") ? ":" : "";
  if (!separator) return null;
  const split = raw.indexOf(separator);
  const boardId = raw.slice(0, split).trim();
  const connectorId = raw.slice(split + separator.length).trim();
  return boardId && connectorId ? { boardId, connectorId } : null;
}

function transformPoint(matrix: number[], point: HarnessPointMm): HarnessPointMm {
  return [
    matrix[0] * point[0] + matrix[1] * point[1] + matrix[2] * point[2] + matrix[3],
    matrix[4] * point[0] + matrix[5] * point[1] + matrix[6] * point[2] + matrix[7],
    matrix[8] * point[0] + matrix[9] * point[1] + matrix[10] * point[2] + matrix[11],
  ];
}

function connectorCandidates(item: Record<string, unknown>): unknown[] {
  const data = item.data && typeof item.data === "object" && !Array.isArray(item.data) ? item.data as Record<string, unknown> : {};
  return [
    { ...data, connector_id: data.connector_id ?? data.connectorId ?? item.connector_id ?? item.connectorId ?? item.id },
    ...(Array.isArray(data.endpoints) ? data.endpoints : []),
    data.endpoint_a,
    data.endpoint_b,
  ].filter(Boolean);
}

function indexConnectors(assembly: AssemblyIr): Map<string, ConnectorRecord> {
  const connectors = new Map<string, ConnectorRecord>();
  for (const mapping of assembly.connector_mappings ?? []) {
    if (!mapping || typeof mapping !== "object" || Array.isArray(mapping)) continue;
    for (const candidate of connectorCandidates(mapping)) {
      if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) continue;
      const item = candidate as Record<string, unknown>;
      const boardId = text(item.board_id ?? item.boardId ?? item.board_instance_id);
      const connectorId = text(item.connector_id ?? item.connectorId ?? item.id);
      const positionMm = finitePoint(item.position_mm ?? item.positionMm ?? item.position ?? item.origin_mm ?? item.origin
        ?? (item.x_mm !== undefined || item.x !== undefined ? item : null));
      if (boardId && connectorId && positionMm && !connectors.has(connectorKey(boardId, connectorId))) {
        connectors.set(connectorKey(boardId, connectorId), { boardId, connectorId, positionMm });
      }
    }
  }
  return connectors;
}

function boardTransforms(assembly: AssemblyIr): Map<string, number[]> {
  const result = new Map<string, number[]>();
  for (const rawBoard of assembly.boards as BoardRecord[]) {
    const boardId = text(rawBoard.id);
    if (!boardId || !rawBoard.frame) continue;
    const transform = resolveFrameToAssembly(assembly, rawBoard.frame);
    if (transform) result.set(boardId, transform);
  }
  return result;
}

function retainedBoardEnvelope(design: Record<string, unknown>): { widthMm: number; heightMm: number; center: readonly [number, number, number] } | null {
  const metadata = design.metadata && typeof design.metadata === "object" && !Array.isArray(design.metadata)
    ? design.metadata as Record<string, unknown> : {};
  const bounds = metadata.board_bounds_mm;
  if (Array.isArray(bounds) && bounds.length === 4 && bounds.every(item => typeof item === "number" && Number.isFinite(item))) {
    const [minX, minY, maxX, maxY] = bounds as number[];
    if (maxX > minX && maxY > minY) return { widthMm: maxX - minX, heightMm: maxY - minY, center: [(minX + maxX) / 2, (minY + maxY) / 2, 0] };
  }
  const size = metadata.board_size_mm;
  if (Array.isArray(size) && size.length === 2 && size.every(item => typeof item === "number" && Number.isFinite(item) && item > 0)) {
    return { widthMm: size[0] as number, heightMm: size[1] as number, center: [0, 0, 0] };
  }
  const legacy = metadata.board_bbox;
  if (legacy && typeof legacy === "object" && !Array.isArray(legacy)) {
    const item = legacy as Record<string, unknown>;
    const values = [item.min_x, item.min_y, item.max_x, item.max_y];
    if (values.every(value => typeof value === "number" && Number.isFinite(value))) {
      const [minX, minY, maxX, maxY] = values as number[];
      if (maxX > minX && maxY > minY) return { widthMm: maxX - minX, heightMm: maxY - minY, center: [(minX + maxX) / 2, (minY + maxY) / 2, 0] };
    }
  }
  return null;
}

/** Project occurrence transforms and bounds; full geometry is rendered from retained designs. */
export function buildVirtualBoardVisualization(assembly: AssemblyIr | null, designs: AssemblyDesigns | null): VirtualBoardProjection {
  if (!assembly || !designs) return { visuals: [], unresolvedBoardIds: (assembly?.boards ?? []).map(board => text(board.id)) };
  const designIndex = new Map(designs.designs.map(design => [design.design_id, design]));
  const transforms = boardTransforms(assembly);
  const visuals: VirtualBoardVisual[] = [];
  const unresolvedBoardIds: string[] = [];
  for (const rawBoard of assembly.boards.slice(0, 30) as BoardRecord[]) {
    const id = text(rawBoard.id);
    const designId = text((rawBoard as Record<string, unknown>).design_id);
    const design = designIndex.get(designId);
    const transform = transforms.get(id);
    const envelope = design ? retainedBoardEnvelope(design) : null;
    if (!id || !designId || !transform || !envelope || envelope.widthMm > 1000 || envelope.heightMm > 1000) {
      if (id) unresolvedBoardIds.push(id);
      continue;
    }
    const netNamesById = Object.fromEntries((Array.isArray(design?.nets) ? design.nets : []).map((net: any) => [net.id, net.name]));
    const netIdsByName = uniqueNetIdsByName(netNamesById);
    const source = design?.source;
    const sourceNativeId = source && typeof source === "object" && !Array.isArray(source)
      ? text((source as Record<string, unknown>).native_id) || undefined : undefined;
    visuals.push({ netNamesById, netIdsByName, id, name: text(rawBoard.name) || id, designId, sourceNativeId, active: designId === designs.active_design_id && !visuals.some(board => board.active), widthMm: envelope.widthMm, heightMm: envelope.heightMm, localCenterMm: envelope.center, transform });
  }
  return { visuals, unresolvedBoardIds };
}

function routeBetween(start: HarnessPointMm, end: HarnessPointMm, lengthMm: number): HarnessPointMm[] {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const dz = end[2] - start[2];
  const direct = Math.hypot(dx, dy, dz);
  const lift = Math.max(2, Math.min(60, Math.max(direct, lengthMm) * 0.12));
  return [
    start,
    [start[0] + dx * 0.28, start[1] + dy * 0.28, Math.max(start[2], end[2]) + lift],
    [start[0] + dx * 0.72, start[1] + dy * 0.72, Math.max(start[2], end[2]) + lift],
    end,
  ];
}

function conductorProjection(
  harness: Record<string, unknown>,
  harnessId: string,
  available: number,
  diagnostics: HarnessVisualizationDiagnostic[],
): { conductors: VirtualHarnessConductor[]; truncated: number } {
  const extensions = harness.extensions && typeof harness.extensions === "object" && !Array.isArray(harness.extensions)
    ? harness.extensions as Record<string, unknown> : {};
  const rawExtension = extensions["spike.harness-conductors"];
  if (rawExtension === undefined) return { conductors: [], truncated: 0 };
  if (!rawExtension || typeof rawExtension !== "object" || Array.isArray(rawExtension)) {
    diagnostics.push({ code: "invalid_conductor_metadata", harnessId, message: `Harness ${harnessId} conductor extension is malformed; displaying one schematic bundle path.` });
    return { conductors: [], truncated: 0 };
  }
  const extension = rawExtension as Record<string, unknown>;
  if (extension.contract !== "spike/assembly-harness-conductors/v1" || !Array.isArray(extension.wires)) {
    diagnostics.push({ code: "invalid_conductor_metadata", harnessId, message: `Harness ${harnessId} conductor extension has an unsupported contract; displaying one schematic bundle path.` });
    return { conductors: [], truncated: 0 };
  }
  const rawPinMap = harness.pin_map;
  const pinMap = rawPinMap && typeof rawPinMap === "object" && !Array.isArray(rawPinMap)
    ? rawPinMap as Record<string, unknown> : {};
  const conductors: VirtualHarnessConductor[] = [];
  const ids = new Set<string>();
  let truncated = 0;
  for (const value of extension.wires) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      diagnostics.push({ code: "invalid_conductor_metadata", harnessId, message: `Harness ${harnessId} contains a malformed conductor record that is not drawn.` });
      continue;
    }
    const wire = value as Record<string, unknown>;
    const id = text(wire.id), fromPin = text(wire.from_pin), toPin = text(wire.to_pin);
    const rawRole = text(wire.role) || "unspecified";
    const role = (["unspecified", "power", "return", "signal", "shield", "other"] as const).find(item => item === rawRole);
    if (!id || ids.has(id) || !fromPin || !toPin || pinMap[fromPin] !== toPin || !role) {
      diagnostics.push({ code: "invalid_conductor_metadata", harnessId, message: `Harness ${harnessId} conductor ${id || "<unnamed>"} does not match a unique saved pin-map entry and supported role; it is not drawn.` });
      continue;
    }
    ids.add(id);
    if (conductors.length >= available) { truncated += 1; continue; }
    const returnWireId = text(wire.return_wire_id) || undefined;
    conductors.push({ id, fromPin, toPin, role, ...(returnWireId ? { returnWireId } : {}), twisted: false });
  }

  const byId = new Map(conductors.map(wire => [wire.id, wire]));
  const paired = new Set<string>();
  const pairIds = new Set<string>();
  for (const wire of conductors) if (wire.returnWireId && !ids.has(wire.returnWireId)) {
    diagnostics.push({ code: "invalid_conductor_metadata", harnessId, message: `Harness ${harnessId} conductor ${wire.id} references unknown return conductor ${wire.returnWireId}; the reference is withheld.` });
    delete wire.returnWireId;
  }
  for (const value of Array.isArray(extension.pairs) ? extension.pairs : []) {
    if (!value || typeof value !== "object" || Array.isArray(value)) continue;
    const pair = value as Record<string, unknown>;
    const pairId = text(pair.id);
    const kind = pair.kind === "differential" || pair.kind === "twisted" ? pair.kind : null;
    const wireIds = Array.isArray(pair.wire_ids) ? pair.wire_ids.map(text) : [];
    const first = byId.get(wireIds[0]), second = byId.get(wireIds[1]);
    if (!pairId || pairIds.has(pairId) || !kind || wireIds.length !== 2 || wireIds[0] === wireIds[1]
      || !ids.has(wireIds[0]) || !ids.has(wireIds[1])) {
      diagnostics.push({ code: "invalid_conductor_metadata", harnessId, message: `Harness ${harnessId} has an invalid or overlapping conductor pair ${pairId || "<unnamed>"}; its admitted wires remain schematic.` });
      continue;
    }
    pairIds.add(pairId);
    // One or both valid wires may be beyond the global display cap. Do not
    // report persisted metadata as invalid merely because it was not rendered.
    if (!first || !second) continue;
    if (paired.has(first.id) || paired.has(second.id)) {
      diagnostics.push({ code: "invalid_conductor_metadata", harnessId, message: `Harness ${harnessId} has an overlapping conductor pair ${pairId}; its admitted wires remain schematic.` });
      continue;
    }
    const requestsTwist = kind === "twisted" || pair.twisted === true;
    const pitch = typeof pair.twist_pitch_mm === "number" && Number.isFinite(pair.twist_pitch_mm) && pair.twist_pitch_mm > 0
      ? pair.twist_pitch_mm : undefined;
    if (requestsTwist && pitch === undefined) diagnostics.push({
      code: "incomplete_twist_metadata", harnessId,
      message: `Harness ${harnessId} pair ${pairId} declares a twist without a positive saved pitch; displaying a schematic pair.`,
    });
    for (const [memberIndex, wire] of [first, second].entries()) Object.assign(wire, {
      pairId, pairKind: kind, pairMemberIndex: memberIndex as 0 | 1,
      twisted: requestsTwist && pitch !== undefined,
      ...(requestsTwist && pitch !== undefined ? { twistPitchMm: pitch } : {}),
    });
    paired.add(first.id); paired.add(second.id);
  }
  return { conductors, truncated };
}

function routeDistances(route: HarnessPointMm[]): { cumulative: number[]; total: number } {
  const cumulative = [0];
  for (let index = 1; index < route.length; index++) cumulative.push(cumulative[index - 1] + Math.hypot(
    route[index][0] - route[index - 1][0], route[index][1] - route[index - 1][1], route[index][2] - route[index - 1][2]));
  return { cumulative, total: cumulative[cumulative.length - 1] ?? 0 };
}

function pointAtDistance(route: HarnessPointMm[], cumulative: number[], distance: number): HarnessPointMm {
  if (route.length < 2 || distance <= 0) return route[0];
  const last = cumulative[cumulative.length - 1];
  if (distance >= last) return route[route.length - 1];
  let segment = 1;
  while (segment < cumulative.length && cumulative[segment] < distance) segment += 1;
  const span = cumulative[segment] - cumulative[segment - 1];
  const fraction = span > 0 ? (distance - cumulative[segment - 1]) / span : 0;
  const a = route[segment - 1], b = route[segment];
  return [a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction, a[2] + (b[2] - a[2]) * fraction];
}

function transverseBasis(before: HarnessPointMm, after: HarnessPointMm): [HarnessPointMm, HarnessPointMm] {
  const dx = after[0] - before[0], dy = after[1] - before[1], dz = after[2] - before[2];
  const length = Math.hypot(dx, dy, dz) || 1;
  const tangent: HarnessPointMm = [dx / length, dy / length, dz / length];
  const reference: HarnessPointMm = Math.abs(tangent[2]) < 0.9 ? [0, 0, 1] : [0, 1, 0];
  const nx = tangent[1] * reference[2] - tangent[2] * reference[1];
  const ny = tangent[2] * reference[0] - tangent[0] * reference[2];
  const nz = tangent[0] * reference[1] - tangent[1] * reference[0];
  const normalLength = Math.hypot(nx, ny, nz) || 1;
  const normal: HarnessPointMm = [nx / normalLength, ny / normalLength, nz / normalLength];
  const binormal: HarnessPointMm = [
    tangent[1] * normal[2] - tangent[2] * normal[1],
    tangent[2] * normal[0] - tangent[0] * normal[2],
    tangent[0] * normal[1] - tangent[1] * normal[0],
  ];
  return [normal, binormal];
}

function boundedSampleDistances(cumulative: number[], total: number, requestedPoints: number): { distances: number[]; capped: boolean } {
  if (total <= 0) return { distances: [0, 0], capped: false };
  const uniqueRouteDistances = [...new Set(cumulative)];
  const idealPointCount = Math.max(uniqueRouteDistances.length, requestedPoints)
    + Math.max(0, Math.min(uniqueRouteDistances.length, requestedPoints) - 2);
  if (uniqueRouteDistances.length >= MAX_HARNESS_CONDUCTOR_POINTS) {
    const distances = Array.from({ length: MAX_HARNESS_CONDUCTOR_POINTS }, (_, index) =>
      uniqueRouteDistances[Math.round(index * (uniqueRouteDistances.length - 1) / (MAX_HARNESS_CONDUCTOR_POINTS - 1))]);
    return { distances, capped: uniqueRouteDistances.length > MAX_HARNESS_CONDUCTOR_POINTS || requestedPoints > 2 };
  }
  const distances = new Set(uniqueRouteDistances);
  // Endpoints already occupy two route slots. Fill only the remaining budget
  // with uniform arc-length samples so authored corners stay present.
  const uniformCount = Math.min(requestedPoints, MAX_HARNESS_CONDUCTOR_POINTS - uniqueRouteDistances.length + 2);
  for (let index = 0; index < uniformCount; index++) distances.add(total * index / Math.max(1, uniformCount - 1));
  return { distances: [...distances].sort((a, b) => a - b), capped: idealPointCount > MAX_HARNESS_CONDUCTOR_POINTS };
}

/** Builds display-only conductor separation while retaining exact connector endpoints. */
export function buildHarnessConductorGeometry(harness: VirtualHarnessVisual): HarnessConductorGeometry[] {
  const route = harness.routeMm;
  if (route.length < 2) return [];
  const conductors = harness.conductors.length ? harness.conductors : [null];
  const { cumulative, total } = routeDistances(route);
  const pairCenters = new Map<string, number>();
  for (const conductor of harness.conductors) if (conductor.pairId && !pairCenters.has(conductor.pairId)) {
    const members = harness.conductors.map((wire, index) => wire.pairId === conductor.pairId ? index : -1).filter(index => index >= 0);
    pairCenters.set(conductor.pairId, members.reduce((sum, index) => sum + index, 0) / Math.max(1, members.length));
  }
  return conductors.map((conductor, index) => {
    const pitch = conductor?.twisted ? conductor.twistPitchMm : undefined;
    const requestedPoints = pitch && total > 0 ? Math.ceil(total / pitch * 8) + 1 : Math.max(route.length, 24);
    const { distances, capped: samplingCapped } = boundedSampleDistances(cumulative, total, requestedPoints);
    const laneIndex = (conductor?.pairId ? pairCenters.get(conductor.pairId) ?? index : index) - (conductors.length - 1) / 2;
    const points = distances.map((distance, sampleIndex): HarnessPointMm => {
      const base = pointAtDistance(route, cumulative, distance);
      if (sampleIndex === 0 || sampleIndex === distances.length - 1 || conductor === null) return base;
      const delta = Math.max(Math.min(distance - distances[sampleIndex - 1], distances[sampleIndex + 1] - distance), 1e-6);
      const before = pointAtDistance(route, cumulative, Math.max(0, distance - delta));
      const after = pointAtDistance(route, cumulative, Math.min(total, distance + delta));
      const [normal, binormal] = transverseBasis(before, after);
      const laneOffset = laneIndex * 0.55;
      let normalOffset = laneOffset, binormalOffset = 0;
      if (pitch && conductor.twisted) {
        const phase = 2 * Math.PI * distance / pitch + (conductor.pairMemberIndex === 1 ? Math.PI : 0);
        normalOffset += Math.cos(phase) * 0.42;
        binormalOffset = Math.sin(phase) * 0.42;
      }
      return [
        base[0] + normal[0] * normalOffset + binormal[0] * binormalOffset,
        base[1] + normal[1] * normalOffset + binormal[1] * binormalOffset,
        base[2] + normal[2] * normalOffset + binormal[2] * binormalOffset,
      ];
    });
    return {
      harnessId: harness.id,
      wireId: conductor?.id ?? null,
      role: conductor?.role ?? "unspecified",
      ...(conductor?.pairId ? { pairId: conductor.pairId } : {}),
      presentation: conductor === null ? "bundle-fallback" : conductor.twisted ? "twisted" : "schematic",
      pointsMm: points,
      samplingCapped,
    };
  });
}

/**
 * Resolves virtual-harness endpoints through maps keyed by stable board and
 * connector IDs. It intentionally does not inspect board features, so the
 * cost is O(boards + connector mappings + harnesses), independent of board
 * component or net density.
 *
 * Endpoint strings use `board-instance-id::connector-id`; a single-colon form
 * remains accepted for existing draft projects. Connector mappings provide
 * `data.board_id`, `data.connector_id`, and `data.position_mm` in board-local mm.
 */
export function buildVirtualHarnessVisualization(
  assembly: AssemblyIr | null,
  maxVisuals = MAX_VIRTUAL_HARNESS_VISUALS,
  maxConductors = MAX_HARNESS_CONDUCTOR_VISUALS,
): HarnessVisualizationProjection {
  if (!assembly) return { visuals: [], diagnostics: [], totalHarnesses: 0, unresolvedHarnesses: 0, truncatedHarnesses: 0, conductorVisuals: 0, truncatedConductors: 0 };
  const boards = boardTransforms(assembly);
  const connectors = indexConnectors(assembly);
  const diagnostics: HarnessVisualizationDiagnostic[] = [];
  const visuals: VirtualHarnessVisual[] = [];
  const seenIds = new Set<string>();
  let unresolvedHarnesses = 0;
  let truncatedHarnesses = 0;
  let conductorVisuals = 0;
  let truncatedConductors = 0;
  const visualLimit = Math.max(0, Math.floor(maxVisuals));
  const conductorLimit = Math.max(0, Math.floor(maxConductors));
  const resolveEndpoint = (value: unknown, harnessId: string, label: "A" | "B"): VirtualHarnessEndpoint | null => {
    const reference = endpointReference(value);
    if (!reference) {
      diagnostics.push({ code: "invalid_endpoint", harnessId, message: `Harness ${harnessId} endpoint ${label} must use board-instance-id::connector-id.` });
      return null;
    }
    const boardTransform = boards.get(reference.boardId);
    if (!boardTransform) {
      diagnostics.push({ code: "unresolved_board", harnessId, message: `Harness ${harnessId} endpoint ${label} references unresolved board instance ${reference.boardId}.` });
      return null;
    }
    const connector = connectors.get(connectorKey(reference.boardId, reference.connectorId));
    if (!connector) {
      diagnostics.push({ code: "unresolved_connector", harnessId, message: `Harness ${harnessId} endpoint ${label} references unresolved connector ${reference.boardId}::${reference.connectorId}.` });
      return null;
    }
    return { ...connector, positionMm: transformPoint(boardTransform, connector.positionMm) };
  };
  for (const rawHarness of assembly.harnesses ?? []) {
    if (!rawHarness || typeof rawHarness !== "object" || Array.isArray(rawHarness)) continue;
    const harness = rawHarness as Record<string, unknown>;
    const id = text(harness.id);
    if (!id) {
      diagnostics.push({ code: "invalid_harness_id", message: "A virtual harness has no stable AssemblyIR ID." });
      unresolvedHarnesses += 1;
      continue;
    }
    if (seenIds.has(id)) {
      diagnostics.push({ code: "duplicate_harness_id", harnessId: id, message: `Harness ID ${id} is duplicated and cannot be selected unambiguously.` });
      unresolvedHarnesses += 1;
      continue;
    }
    seenIds.add(id);
    const endpointA = resolveEndpoint(harness.endpoint_a, id, "A");
    const endpointB = resolveEndpoint(harness.endpoint_b, id, "B");
    if (!endpointA || !endpointB) {
      unresolvedHarnesses += 1;
      continue;
    }
    if (visuals.length >= visualLimit) {
      truncatedHarnesses += 1;
      continue;
    }
    const lengthMm = typeof harness.length_mm === "number" && Number.isFinite(harness.length_mm) && harness.length_mm >= 0 ? harness.length_mm : 0;
    const extensions = harness.extensions as Record<string, unknown> | undefined;
    const routing = extensions?.["spike.harness-routing"] as Record<string, unknown> | undefined;
    let savedRoute: HarnessPointMm[] | null = null;
    if (routing && Array.isArray(routing.route_mm)) {
      const points = routing.route_mm.map(finitePoint);
      const first = points[0], last = points[points.length - 1];
      const matches = (a: HarnessPointMm, b: HarnessPointMm) => Math.hypot(...a.map((v, i) => v - b[i]) as [number, number, number]) < 1e-6;
      if (points.length >= 2 && points.length <= 100000 && points.every(p => p !== null) && first && last && matches(first, endpointA.positionMm) && matches(last, endpointB.positionMm)) savedRoute = points as HarnessPointMm[];
      else diagnostics.push({ code: "stale_route", harnessId: id, message: `Harness ${id} has a stale or invalid route; regenerate after changing placement.` });
    }
    const projectedConductors = conductorProjection(harness, id, Math.max(0, conductorLimit - conductorVisuals), diagnostics);
    conductorVisuals += projectedConductors.conductors.length;
    truncatedConductors += projectedConductors.truncated;
    visuals.push({
      id,
      name: text(harness.name) || id,
      lengthMm,
      endpointA,
      endpointB,
      routeMm: savedRoute ?? routeBetween(endpointA.positionMm, endpointB.positionMm, lengthMm),
      routedPolyline: savedRoute !== null,
      conductors: projectedConductors.conductors,
    });
  }
  if (truncatedHarnesses) diagnostics.push({ code: "visualization_limit", message: `Virtual-harness display is bounded to ${visualLimit}; ${truncatedHarnesses} resolved harnesses are not drawn.` });
  if (truncatedConductors) diagnostics.push({ code: "conductor_visualization_limit", message: `Individual-conductor display is bounded to ${conductorLimit}; ${truncatedConductors} saved conductors are not drawn.` });
  return { visuals, diagnostics, totalHarnesses: seenIds.size, unresolvedHarnesses, truncatedHarnesses, conductorVisuals, truncatedConductors };
}
