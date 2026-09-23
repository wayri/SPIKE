import { resolveFrameToAssembly, type AssemblyDesigns, type AssemblyFrame, type AssemblyIr } from "./mcadAssembly";

export type HarnessPointMm = readonly [number, number, number];

export type VirtualHarnessEndpoint = {
  boardId: string;
  connectorId: string;
  positionMm: HarnessPointMm;
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
};

export type HarnessVisualizationDiagnostic = {
  code: "duplicate_harness_id" | "invalid_harness_id" | "invalid_endpoint" | "unresolved_board" | "unresolved_connector" | "invalid_connector_position" | "visualization_limit" | "stale_route";
  harnessId?: string;
  message: string;
};

export type HarnessVisualizationProjection = {
  visuals: VirtualHarnessVisual[];
  diagnostics: HarnessVisualizationDiagnostic[];
  totalHarnesses: number;
  unresolvedHarnesses: number;
  truncatedHarnesses: number;
};

export type VirtualBoardVisual = {
  id: string;
  name: string;
  designId: string;
  active: boolean;
  widthMm: number;
  heightMm: number;
  localCenterMm: readonly [number, number, number];
  transform: number[];
};

export type VirtualBoardProjection = {
  visuals: VirtualBoardVisual[];
  unresolvedBoardIds: string[];
};

/** The viewport never creates an unbounded number of interactive line objects. */
export const MAX_VIRTUAL_HARNESS_VISUALS = 512;

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

/** Build at most one constant-size proxy per retained board; dense features are never scanned. */
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
    visuals.push({ id, name: text(rawBoard.name) || id, designId, active: designId === designs.active_design_id, widthMm: envelope.widthMm, heightMm: envelope.heightMm, localCenterMm: envelope.center, transform });
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
): HarnessVisualizationProjection {
  if (!assembly) return { visuals: [], diagnostics: [], totalHarnesses: 0, unresolvedHarnesses: 0, truncatedHarnesses: 0 };
  const boards = boardTransforms(assembly);
  const connectors = indexConnectors(assembly);
  const diagnostics: HarnessVisualizationDiagnostic[] = [];
  const visuals: VirtualHarnessVisual[] = [];
  const seenIds = new Set<string>();
  let unresolvedHarnesses = 0;
  let truncatedHarnesses = 0;
  const visualLimit = Math.max(0, Math.floor(maxVisuals));
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
    visuals.push({
      id,
      name: text(harness.name) || id,
      lengthMm,
      endpointA,
      endpointB,
      routeMm: savedRoute ?? routeBetween(endpointA.positionMm, endpointB.positionMm, lengthMm),
      routedPolyline: savedRoute !== null,
    });
  }
  if (truncatedHarnesses) diagnostics.push({ code: "visualization_limit", message: `Virtual-harness display is bounded to ${visualLimit}; ${truncatedHarnesses} resolved harnesses are not drawn.` });
  return { visuals, diagnostics, totalHarnesses: seenIds.size, unresolvedHarnesses, truncatedHarnesses };
}
