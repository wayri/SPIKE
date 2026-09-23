export type SpatialPoint = { x_mm: number; y_mm: number };

export type PointSpatialIndex<T extends SpatialPoint> = {
  samples: readonly T[];
  cellSize: number;
  buckets: Map<string, T[]>;
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minCellX: number;
  maxCellX: number;
  minCellY: number;
  maxCellY: number;
};

export type NearestPointQuery<T> = {
  sample?: T;
  inspected: number;
  rings: number;
  bucketCount: number;
};

const pointIndexCache = new WeakMap<readonly object[], PointSpatialIndex<SpatialPoint>>();
const cellKey = (x: number, y: number) => `${x}:${y}`;

export function pointSpatialIndex<T extends SpatialPoint>(samples: readonly T[]): PointSpatialIndex<T> {
  const cached = pointIndexCache.get(samples as readonly object[]);
  if (cached) return cached as PointSpatialIndex<T>;
  let minX = Infinity; let maxX = -Infinity; let minY = Infinity; let maxY = -Infinity;
  for (const sample of samples) {
    minX = Math.min(minX, sample.x_mm); maxX = Math.max(maxX, sample.x_mm);
    minY = Math.min(minY, sample.y_mm); maxY = Math.max(maxY, sample.y_mm);
  }
  if (!samples.length) minX = maxX = minY = maxY = 0;
  const area = Math.max((maxX - minX) * (maxY - minY), 0.0004);
  const cellSize = Math.min(5, Math.max(0.02, Math.sqrt(area / Math.max(samples.length, 1)) * 1.75));
  const buckets = new Map<string, T[]>();
  for (const sample of samples) {
    const x = Math.floor(sample.x_mm / cellSize);
    const y = Math.floor(sample.y_mm / cellSize);
    const key = cellKey(x, y);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(sample);
    else buckets.set(key, [sample]);
  }
  const index: PointSpatialIndex<T> = {
    samples, cellSize, buckets, minX, maxX, minY, maxY,
    minCellX: Math.floor(minX / cellSize), maxCellX: Math.floor(maxX / cellSize),
    minCellY: Math.floor(minY / cellSize), maxCellY: Math.floor(maxY / cellSize),
  };
  pointIndexCache.set(samples as readonly object[], index as PointSpatialIndex<SpatialPoint>);
  return index;
}

export function nearbyPointCandidates<T extends SpatialPoint>(
  samples: readonly T[], x: number, y: number, minimum = 12, maximumRings = 3,
): T[] {
  const index = pointSpatialIndex(samples);
  const cellX = Math.floor(x / index.cellSize);
  const cellY = Math.floor(y / index.cellSize);
  const nearby: T[] = [];
  for (let ring = 0; ring <= maximumRings && nearby.length < minimum; ring += 1) {
    for (let bucketX = cellX - ring; bucketX <= cellX + ring; bucketX += 1) {
      for (let bucketY = cellY - ring; bucketY <= cellY + ring; bucketY += 1) {
        if (ring > 0 && bucketX > cellX - ring && bucketX < cellX + ring
          && bucketY > cellY - ring && bucketY < cellY + ring) continue;
        const bucket = index.buckets.get(cellKey(bucketX, bucketY));
        if (bucket) for (const sample of bucket) nearby.push(sample);
      }
    }
  }
  return nearby;
}

export function nearestPointSample<T extends SpatialPoint>(
  samples: readonly T[], x: number, y: number,
): NearestPointQuery<T> {
  const index = pointSpatialIndex(samples);
  if (!samples.length) return { inspected: 0, rings: 0, bucketCount: 0 };
  // Hover coordinates normally lie within the solved board. An external query
  // is rare and uses an exact bounded fallback rather than iterating empty grid rings.
  if (x < index.minX || x > index.maxX || y < index.minY || y > index.maxY) {
    let sample: T | undefined;
    let bestDistance = Infinity;
    for (const candidate of samples) {
      const distance = (candidate.x_mm - x) ** 2 + (candidate.y_mm - y) ** 2;
      if (distance < bestDistance) { sample = candidate; bestDistance = distance; }
    }
    return { sample, inspected: samples.length, rings: 0, bucketCount: index.buckets.size };
  }
  const cellX = Math.floor(x / index.cellSize);
  const cellY = Math.floor(y / index.cellSize);
  // Sparse multi-board and collinear fields can contain millions of empty
  // cells. Visit a small local neighborhood, then prune occupied buckets by
  // their exact lower distance bound. Work is bounded by data, not world area.
  const maximumRing = Math.min(3, Math.max(
    cellX - index.minCellX, index.maxCellX - cellX,
    cellY - index.minCellY, index.maxCellY - cellY,
  ));
  let sample: T | undefined;
  let bestDistanceSquared = Infinity;
  let inspected = 0;
  let rings = 0;
  for (let ring = 0; ring <= maximumRing; ring += 1) {
    rings = ring + 1;
    for (let bucketX = cellX - ring; bucketX <= cellX + ring; bucketX += 1) {
      for (let bucketY = cellY - ring; bucketY <= cellY + ring; bucketY += 1) {
        if (ring > 0 && bucketX > cellX - ring && bucketX < cellX + ring
          && bucketY > cellY - ring && bucketY < cellY + ring) continue;
        for (const candidate of index.buckets.get(cellKey(bucketX, bucketY)) ?? []) {
          inspected += 1;
          const distanceSquared = (candidate.x_mm - x) ** 2 + (candidate.y_mm - y) ** 2;
          if (distanceSquared < bestDistanceSquared) {
            sample = candidate;
            bestDistanceSquared = distanceSquared;
          }
        }
      }
    }
    if (sample) {
      const lowX = (cellX - ring) * index.cellSize;
      const highX = (cellX + ring + 1) * index.cellSize;
      const lowY = (cellY - ring) * index.cellSize;
      const highY = (cellY + ring + 1) * index.cellSize;
      const minimumOutsideDistance = Math.min(x - lowX, highX - x, y - lowY, highY - y);
      if (bestDistanceSquared <= minimumOutsideDistance * minimumOutsideDistance) {
        return { sample, inspected, rings, bucketCount: index.buckets.size };
      }
    }
  }
  for (const [key, bucket] of index.buckets) {
    const [bucketX, bucketY] = key.split(":").map(Number);
    if (Math.abs(bucketX - cellX) <= maximumRing && Math.abs(bucketY - cellY) <= maximumRing) continue;
    const dx = Math.max(bucketX * index.cellSize - x, 0, x - (bucketX + 1) * index.cellSize);
    const dy = Math.max(bucketY * index.cellSize - y, 0, y - (bucketY + 1) * index.cellSize);
    if (dx * dx + dy * dy > bestDistanceSquared) continue;
    for (const candidate of bucket) {
      inspected += 1;
      const distanceSquared = (candidate.x_mm - x) ** 2 + (candidate.y_mm - y) ** 2;
      if (distanceSquared < bestDistanceSquared) { sample = candidate; bestDistanceSquared = distanceSquared; }
    }
  }
  return { sample, inspected, rings, bucketCount: index.buckets.size };
}

export type SpatialBounds<T> = {
  value: T;
  minX: number; maxX: number; minY: number; maxY: number; minZ: number; maxZ: number;
};

export type BoundsSpatialIndex<T> = {
  cellSize: number;
  buckets: Map<string, SpatialBounds<T>[]>;
  global: SpatialBounds<T>[];
  all: SpatialBounds<T>[];
  minZ: number;
  maxZ: number;
  memberships: number;
};

export function buildBoundsSpatialIndex<T>(
  records: readonly SpatialBounds<T>[],
  maximumMemberships = 1_000_000,
): BoundsSpatialIndex<T> {
  if (!records.length) return { cellSize: 1, buckets: new Map(), global: [], all: [], minZ: 0, maxZ: 0, memberships: 0 };
  let minX = Infinity; let maxX = -Infinity; let minY = Infinity; let maxY = -Infinity;
  let minZ = Infinity; let maxZ = -Infinity;
  for (const record of records) {
    minX = Math.min(minX, record.minX); maxX = Math.max(maxX, record.maxX);
    minY = Math.min(minY, record.minY); maxY = Math.max(maxY, record.maxY);
    minZ = Math.min(minZ, record.minZ); maxZ = Math.max(maxZ, record.maxZ);
  }
  const area = Math.max((maxX - minX) * (maxY - minY), 1);
  const cellSize = Math.min(20, Math.max(0.5, Math.sqrt(area / records.length) * 2));
  const buckets = new Map<string, SpatialBounds<T>[]>();
  const global: SpatialBounds<T>[] = [];
  let memberships = 0;
  for (const record of records) {
    const lowX = Math.floor(record.minX / cellSize); const highX = Math.floor(record.maxX / cellSize);
    const lowY = Math.floor(record.minY / cellSize); const highY = Math.floor(record.maxY / cellSize);
    const count = (highX - lowX + 1) * (highY - lowY + 1);
    if (count > 4096 || memberships + count > maximumMemberships) {
      global.push(record);
      continue;
    }
    for (let x = lowX; x <= highX; x += 1) for (let y = lowY; y <= highY; y += 1) {
      const key = cellKey(x, y);
      const bucket = buckets.get(key);
      if (bucket) bucket.push(record);
      else buckets.set(key, [record]);
      memberships += 1;
    }
  }
  return { cellSize, buckets, global, all: [...records], minZ, maxZ, memberships };
}

export function pointBoundsCandidates<T>(
  index: BoundsSpatialIndex<T>,
  x: number,
  y: number,
  radius = 0,
): { values: T[]; inspected: number; global: number } {
  if (!index.all.length) return { values: [], inspected: 0, global: 0 };
  const safeRadius = Math.max(0, radius);
  const lowX = Math.floor((x - safeRadius) / index.cellSize);
  const highX = Math.floor((x + safeRadius) / index.cellSize);
  const lowY = Math.floor((y - safeRadius) / index.cellSize);
  const highY = Math.floor((y + safeRadius) / index.cellSize);
  const candidates = new Set<SpatialBounds<T>>(index.global);
  for (let cellX = lowX; cellX <= highX; cellX += 1) {
    for (let cellY = lowY; cellY <= highY; cellY += 1) {
      for (const record of index.buckets.get(cellKey(cellX, cellY)) ?? []) candidates.add(record);
    }
  }
  const values: T[] = [];
  for (const record of candidates) {
    if (x + safeRadius < record.minX || x - safeRadius > record.maxX
      || y + safeRadius < record.minY || y - safeRadius > record.maxY) continue;
    values.push(record.value);
  }
  return { values, inspected: candidates.size, global: index.global.length };
}

export function rayBoundsCandidates<T>(
  index: BoundsSpatialIndex<T>,
  origin: readonly [number, number, number],
  direction: readonly [number, number, number],
): { values: T[]; cells: number; global: number } {
  if (!index.all.length) return { values: [], cells: 0, global: 0 };
  if (Math.abs(direction[2]) < 1e-12) {
    return { values: index.all.map(record => record.value), cells: index.buckets.size, global: index.global.length };
  }
  const firstT = (index.minZ - origin[2]) / direction[2];
  const secondT = (index.maxZ - origin[2]) / direction[2];
  const nearT = Math.max(0, Math.min(firstT, secondT));
  const farT = Math.max(firstT, secondT);
  if (farT < 0) return { values: [], cells: 0, global: index.global.length };
  const firstX = origin[0] + direction[0] * nearT; const secondX = origin[0] + direction[0] * farT;
  const firstY = origin[1] + direction[1] * nearT; const secondY = origin[1] + direction[1] * farT;
  const lowX = Math.floor(Math.min(firstX, secondX) / index.cellSize) - 1;
  const highX = Math.floor(Math.max(firstX, secondX) / index.cellSize) + 1;
  const lowY = Math.floor(Math.min(firstY, secondY) / index.cellSize) - 1;
  const highY = Math.floor(Math.max(firstY, secondY) / index.cellSize) + 1;
  const candidates = new Set<SpatialBounds<T>>(index.global);
  let cells = 0;
  for (let x = lowX; x <= highX; x += 1) for (let y = lowY; y <= highY; y += 1) {
    cells += 1;
    for (const record of index.buckets.get(cellKey(x, y)) ?? []) candidates.add(record);
  }
  return { values: [...candidates].map(record => record.value), cells, global: index.global.length };
}
