import type { ParsedBoard, Point } from "./boardParser";

type ResultDatum = {
  x_mm: number;
  y_mm: number;
  layer?: string;
  net?: string;
  element_id?: string;
  vertices_mm?: [number, number, number][];
};

const EPSILON = 1e-9;

type IndexedFeature =
  | { kind: "track"; layer: string; value: ParsedBoard["tracks"][number] }
  | { kind: "zone"; layer: string; value: ParsedBoard["zones"][number] }
  | { kind: "pad"; layers: Set<string>; value: ParsedBoard["pads"][number] }
  | { kind: "via"; layers: Set<string>; value: ParsedBoard["vias"][number] };

type ResultConductorIndex = {
  signature: string;
  cellSizeMm: number;
  buckets: Map<string, IndexedFeature[]>;
  overflowByNet: Map<string, IndexedFeature[]>;
  featureCount: number;
  maximumBucketSize: number;
};

const conductorIndexes = new WeakMap<ParsedBoard, ResultConductorIndex>();
const datumMaskCaches = new WeakMap<ParsedBoard, { signature: string; values: Map<string, boolean> }>();
const MAX_CELLS_PER_FEATURE = 4096;
const MAX_DATUM_MASK_CACHE_ENTRIES = 500_000;

const cellKey = (x: number, y: number) => `${x}:${y}`;

function coordinateExtent(points: Point[], axis: 0 | 1): [number, number] {
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  for (const point of points) {
    const value = point[axis];
    if (!Number.isFinite(value)) continue;
    if (value < minimum) minimum = value;
    if (value > maximum) maximum = value;
  }
  return Number.isFinite(minimum) ? [minimum, maximum] : [0, 0];
}

function boardSignature(board: ParsedBoard): string {
  return [board.tracks.length, board.zones.length, board.pads.length, board.vias.length,
    board.layers.length, board.bounds.minX, board.bounds.minY, board.bounds.maxX, board.bounds.maxY].join(":");
}

function distanceToSegment(point: Point, start: Point, end: Point): number {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared <= EPSILON) return Math.hypot(point[0] - start[0], point[1] - start[1]);
  const ratio = Math.max(0, Math.min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / lengthSquared));
  return Math.hypot(point[0] - start[0] - ratio * dx, point[1] - start[1] - ratio * dy);
}

function pointInPolygon(point: Point, polygon: Point[], tolerance: number): boolean {
  if (polygon.length < 3) return false;
  for (let index = 0; index < polygon.length; index += 1) {
    if (distanceToSegment(point, polygon[index], polygon[(index + 1) % polygon.length]) <= tolerance) return true;
  }
  let inside = false;
  for (let current = 0, previous = polygon.length - 1; current < polygon.length; previous = current, current += 1) {
    const [x1, y1] = polygon[current];
    const [x2, y2] = polygon[previous];
    if ((y1 > point[1]) !== (y2 > point[1])
      && point[0] < (x2 - x1) * (point[1] - y1) / ((y2 - y1) || EPSILON) + x1) inside = !inside;
  }
  return inside;
}

function copperSpan(board: ParsedBoard, layers: string[]): Set<string> {
  if (layers.length < 2) return new Set(layers);
  const first = board.layers.indexOf(layers[0]);
  const last = board.layers.indexOf(layers[layers.length - 1]);
  if (first < 0 || last < 0) return new Set(layers);
  return new Set(board.layers.slice(Math.min(first, last), Math.max(first, last) + 1));
}

function buildConductorIndex(board: ParsedBoard): ResultConductorIndex {
  const featureCount = board.tracks.length + board.zones.length + board.pads.length + board.vias.length;
  const width = Math.max(board.bounds.maxX - board.bounds.minX, 0.001);
  const height = Math.max(board.bounds.maxY - board.bounds.minY, 0.001);
  const cellSizeMm = Math.max(0.25, Math.min(10, Math.sqrt(width * height / Math.max(featureCount * 2, 1))));
  const buckets = new Map<string, IndexedFeature[]>();
  const overflowByNet = new Map<string, IndexedFeature[]>();
  let maximumBucketSize = 0;
  const insert = (net: string | undefined, feature: IndexedFeature, bounds: [number, number, number, number]) => {
    if (!net) return;
    const minX = Math.floor((bounds[0] - board.bounds.minX) / cellSizeMm);
    const minY = Math.floor((bounds[1] - board.bounds.minY) / cellSizeMm);
    const maxX = Math.floor((bounds[2] - board.bounds.minX) / cellSizeMm);
    const maxY = Math.floor((bounds[3] - board.bounds.minY) / cellSizeMm);
    const columns = Math.max(maxX - minX + 1, 1);
    const rows = Math.max(maxY - minY + 1, 1);
    if (columns * rows > MAX_CELLS_PER_FEATURE) {
      const values = overflowByNet.get(net) ?? [];
      values.push(feature);
      overflowByNet.set(net, values);
      return;
    }
    for (let y = minY; y <= maxY; y += 1) for (let x = minX; x <= maxX; x += 1) {
      const key = `${net}\u0000${cellKey(x, y)}`;
      const values = buckets.get(key) ?? [];
      values.push(feature);
      buckets.set(key, values);
      maximumBucketSize = Math.max(maximumBucketSize, values.length);
    }
  };
  board.tracks.forEach(value => {
    const radius = Math.max(value.width / 2, 0);
    insert(value.net, { kind: "track", layer: value.layer, value }, [
      Math.min(value.start[0], value.end[0]) - radius, Math.min(value.start[1], value.end[1]) - radius,
      Math.max(value.start[0], value.end[0]) + radius, Math.max(value.start[1], value.end[1]) + radius,
    ]);
  });
  board.zones.forEach(value => {
    if (value.points.length < 3) return;
    const [minimumX, maximumX] = coordinateExtent(value.points, 0);
    const [minimumY, maximumY] = coordinateExtent(value.points, 1);
    insert(value.net, { kind: "zone", layer: value.layer, value }, [
      minimumX, minimumY, maximumX, maximumY,
    ]);
  });
  board.pads.forEach(value => {
    const radius = Math.hypot(value.width, value.height) / 2;
    insert(value.net, { kind: "pad", layers: copperSpan(board, value.layers), value }, [
      value.at[0] - radius, value.at[1] - radius, value.at[0] + radius, value.at[1] + radius,
    ]);
  });
  board.vias.forEach(value => {
    const radius = value.size / 2;
    insert(value.net, { kind: "via", layers: copperSpan(board, value.layers), value }, [
      value.at[0] - radius, value.at[1] - radius, value.at[0] + radius, value.at[1] + radius,
    ]);
  });
  return { signature: boardSignature(board), cellSizeMm, buckets, overflowByNet, featureCount, maximumBucketSize };
}

function conductorIndex(board: ParsedBoard): ResultConductorIndex {
  const cached = conductorIndexes.get(board);
  const signature = boardSignature(board);
  if (cached?.signature === signature) return cached;
  const index = buildConductorIndex(board);
  conductorIndexes.set(board, index);
  return index;
}

export function resultConductorIndexStats(board: ParsedBoard) {
  const index = conductorIndex(board);
  return {
    featureCount: index.featureCount,
    bucketCount: index.buckets.size,
    overflowCount: [...index.overflowByNet.values()].reduce((total, values) => total + values.length, 0),
    maximumBucketSize: index.maximumBucketSize,
    cellSizeMm: index.cellSizeMm,
  };
}

function datumLayers(layer?: string): string[] {
  if (!layer || layer === "through") return [];
  return layer.split("->").map(entry => entry.trim()).filter(Boolean);
}

function layersOverlap(board: ParsedBoard, featureLayers: string[], resultLayers: string[]): boolean {
  if (!resultLayers.length || !featureLayers.length) return true;
  const expanded = copperSpan(board, featureLayers);
  return resultLayers.some(layer => expanded.has(layer));
}

function pointInPad(point: Point, pad: ParsedBoard["pads"][number], tolerance: number): boolean {
  const radians = -pad.rotation * Math.PI / 180;
  const dx = point[0] - pad.at[0];
  const dy = point[1] - pad.at[1];
  const localX = dx * Math.cos(radians) - dy * Math.sin(radians);
  const localY = dx * Math.sin(radians) + dy * Math.cos(radians);
  const halfWidth = pad.width / 2 + tolerance;
  const halfHeight = pad.height / 2 + tolerance;
  const shape = pad.shape.toLowerCase();
  if (shape.includes("circle") || shape.includes("oval")) {
    if (shape.includes("circle") || Math.abs(pad.width - pad.height) <= tolerance) {
      const radius = Math.max(pad.width, pad.height) / 2 + tolerance;
      return localX * localX + localY * localY <= radius * radius;
    }
    const horizontal = pad.width >= pad.height;
    const radius = Math.min(pad.width, pad.height) / 2 + tolerance;
    const straight = Math.max(pad.width, pad.height) / 2 - Math.min(pad.width, pad.height) / 2;
    const along = horizontal ? localX : localY;
    const across = horizontal ? localY : localX;
    const endpoint = Math.max(-straight, Math.min(straight, along));
    return (along - endpoint) ** 2 + across ** 2 <= radius ** 2;
  }
  return Math.abs(localX) <= halfWidth && Math.abs(localY) <= halfHeight;
}

export function pointOnResultConductor(
  board: ParsedBoard,
  point: Point,
  net?: string,
  layer?: string,
  toleranceMm = 0.035,
): boolean {
  if (point[0] < board.bounds.minX - toleranceMm || point[0] > board.bounds.maxX + toleranceMm
    || point[1] < board.bounds.minY - toleranceMm || point[1] > board.bounds.maxY + toleranceMm) return false;
  if (!net) return true;
  const layers = datumLayers(layer);
  const index = conductorIndex(board);
  const cellX = Math.floor((point[0] - board.bounds.minX) / index.cellSizeMm);
  const cellY = Math.floor((point[1] - board.bounds.minY) / index.cellSizeMm);
  const radius = Math.max(0, Math.ceil(toleranceMm / index.cellSizeMm));
  const candidates = new Set<IndexedFeature>(index.overflowByNet.get(net) ?? []);
  for (let y = cellY - radius; y <= cellY + radius; y += 1) for (let x = cellX - radius; x <= cellX + radius; x += 1) {
    index.buckets.get(`${net}\u0000${cellKey(x, y)}`)?.forEach(feature => candidates.add(feature));
  }
  for (const feature of candidates) {
    if (feature.kind === "track") {
      if ((!layers.length || layers.includes(feature.layer))
        && distanceToSegment(point, feature.value.start, feature.value.end) <= feature.value.width / 2 + toleranceMm) return true;
    } else if (feature.kind === "zone") {
      if ((!layers.length || layers.includes(feature.layer)) && pointInPolygon(point, feature.value.points, toleranceMm)) return true;
    } else if ((!layers.length || layers.some(value => feature.layers.has(value)))) {
      if (feature.kind === "pad" && pointInPad(point, feature.value, toleranceMm)) return true;
      if (feature.kind === "via" && Math.hypot(point[0] - feature.value.at[0], point[1] - feature.value.at[1]) <= feature.value.size / 2 + toleranceMm) return true;
    }
  }
  return false;
}

export function resultDatumFitsConductor(board: ParsedBoard, datum: ResultDatum, toleranceMm = 0.035): boolean {
  const signature = boardSignature(board);
  let cache = datumMaskCaches.get(board);
  if (!cache || cache.signature !== signature) {
    cache = { signature, values: new Map() };
    datumMaskCaches.set(board, cache);
  }
  const geometryKey = [
    toleranceMm, datum.net ?? "", datum.layer ?? "", datum.element_id ?? "",
    datum.x_mm, datum.y_mm,
    ...(datum.vertices_mm ?? []).flatMap(vertex => vertex),
  ].join("\u0000");
  const cached = cache.values.get(geometryKey);
  if (cached !== undefined) return cached;
  const points: Point[] = (datum.vertices_mm ?? []).map(vertex => [vertex[0], vertex[1]]);
  if (!points.length) points.push([datum.x_mm, datum.y_mm]);
  const checks: Point[] = [...points];
  if (points.length > 1) {
    for (let index = 0; index < points.length; index += 1) {
      const start = points[index];
      const end = points[(index + 1) % points.length];
      checks.push(
        [start[0] * 0.75 + end[0] * 0.25, start[1] * 0.75 + end[1] * 0.25],
        [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2],
        [start[0] * 0.25 + end[0] * 0.75, start[1] * 0.25 + end[1] * 0.75],
      );
    }
  }
  const admitted = checks.every(point => pointOnResultConductor(board, point, datum.net, datum.layer, toleranceMm));
  if (cache.values.size >= MAX_DATUM_MASK_CACHE_ENTRIES) cache.values.clear();
  cache.values.set(geometryKey, admitted);
  return admitted;
}

type ProjectedVertex = { index: number; x: number; y: number };

function cross(a: ProjectedVertex, b: ProjectedVertex, c: ProjectedVertex): number {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

function projectedFace(vertices: [number, number, number][]): ProjectedVertex[] {
  let normalX = 0;
  let normalY = 0;
  let normalZ = 0;
  vertices.forEach((current, index) => {
    const next = vertices[(index + 1) % vertices.length];
    normalX += (current[1] - next[1]) * (current[2] + next[2]);
    normalY += (current[2] - next[2]) * (current[0] + next[0]);
    normalZ += (current[0] - next[0]) * (current[1] + next[1]);
  });
  const dropAxis = Math.abs(normalX) >= Math.abs(normalY) && Math.abs(normalX) >= Math.abs(normalZ) ? 0
    : Math.abs(normalY) >= Math.abs(normalZ) ? 1 : 2;
  return vertices.map((vertex, index) => ({
    index,
    x: vertex[dropAxis === 0 ? 1 : 0],
    y: vertex[dropAxis === 2 ? 1 : 2],
  })).filter((vertex, index, all) => {
    const previous = all[(index + all.length - 1) % all.length];
    return Math.hypot(vertex.x - previous.x, vertex.y - previous.y) > EPSILON;
  });
}

function segmentsIntersect(a: ProjectedVertex, b: ProjectedVertex, c: ProjectedVertex, d: ProjectedVertex): boolean {
  const abC = cross(a, b, c);
  const abD = cross(a, b, d);
  const cdA = cross(c, d, a);
  const cdB = cross(c, d, b);
  return abC * abD < -EPSILON && cdA * cdB < -EPSILON;
}

function simplePolygon(vertices: ProjectedVertex[]): boolean {
  for (let left = 0; left < vertices.length; left += 1) {
    const leftNext = (left + 1) % vertices.length;
    for (let right = left + 1; right < vertices.length; right += 1) {
      const rightNext = (right + 1) % vertices.length;
      if (left === right || leftNext === right || rightNext === left) continue;
      if (segmentsIntersect(vertices[left], vertices[leftNext], vertices[right], vertices[rightNext])) return false;
    }
  }
  return true;
}

function pointInTriangle(point: ProjectedVertex, a: ProjectedVertex, b: ProjectedVertex, c: ProjectedVertex, orientation: number): boolean {
  return cross(a, b, point) * orientation >= -EPSILON
    && cross(b, c, point) * orientation >= -EPSILON
    && cross(c, a, point) * orientation >= -EPSILON;
}

export function resultFaceTriangleIndices(vertices: [number, number, number][]): number[] {
  if (vertices.length < 3) return [];
  const projected = projectedFace(vertices);
  if (projected.length < 3 || !simplePolygon(projected)) return [];
  const signedArea = projected.reduce((sum, vertex, index) => {
    const next = projected[(index + 1) % projected.length];
    return sum + vertex.x * next.y - next.x * vertex.y;
  }, 0) / 2;
  if (Math.abs(signedArea) <= EPSILON) return [];
  const orientation = signedArea > 0 ? 1 : -1;
  const remaining = [...projected];
  const triangles: number[] = [];
  while (remaining.length > 3) {
    let clipped = false;
    for (let index = 0; index < remaining.length; index += 1) {
      const previous = remaining[(index + remaining.length - 1) % remaining.length];
      const current = remaining[index];
      const next = remaining[(index + 1) % remaining.length];
      if (cross(previous, current, next) * orientation <= EPSILON) continue;
      if (remaining.some(candidate => candidate !== previous && candidate !== current && candidate !== next
        && pointInTriangle(candidate, previous, current, next, orientation))) continue;
      triangles.push(previous.index, current.index, next.index);
      remaining.splice(index, 1);
      clipped = true;
      break;
    }
    if (!clipped) return [];
  }
  triangles.push(remaining[0].index, remaining[1].index, remaining[2].index);
  return triangles;
}
