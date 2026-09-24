import type { ScalarSample } from "./analysisResults";
import { numericExtent } from "./numericRange";

export type ContourVertex = {
  xMm: number;
  yMm: number;
  value: number;
};

export type ContourSegment = {
  level: number;
  start: [number, number];
  end: [number, number];
};

export type ContourGrid = {
  columns: number;
  rows: number;
  minimum: number;
  maximum: number;
  vertices: Array<ContourVertex | null>;
  indices: number[];
  contours: ContourSegment[];
  sourceSamples: ScalarSample[];
};

type ContourOptions = {
  levels?: number;
  maximumSourceSamples?: number;
  maximumGridVertices?: number;
  /** Presentation mask. Interpolated vertices outside the admitted conductor
   * geometry are omitted rather than allowed to bridge a clearance or void. */
  supportsPoint?: (xMm: number, yMm: number) => boolean;
};

export type ViaStressGeometry = {
  id: string;
  at: [number, number];
  size: number;
  drill: number;
  net?: string;
  layers?: string[];
};

export type ViaStressGlyph = {
  via: ViaStressGeometry;
  value: number;
  sampleCount: number;
};

export function viaStressAnnulusPath(
  via: ViaStressGeometry,
  project: (point: [number, number]) => [number, number] = point => point,
): string {
  const point = project(via.at);
  const outer = Math.max(via.size / 2, 0);
  if (!(outer > 0) || !point.every(Number.isFinite)) return "";
  const inner = Math.min(Math.max(via.drill / 2, 0), outer * 0.96);
  return `M${point[0] - outer},${point[1]}a${outer},${outer} 0 1,0 ${outer * 2},0a${outer},${outer} 0 1,0 ${-outer * 2},0Z`
    + (inner > 0 ? ` M${point[0] - inner},${point[1]}a${inner},${inner} 0 1,1 ${inner * 2},0a${inner},${inner} 0 1,1 ${-inner * 2},0Z` : "");
}

const coordinateKey = (vertex: [number, number, number]) => vertex.map(value => value.toFixed(7)).join(":");

function projectedPolygon(sample: ScalarSample): [number, number][] {
  return (sample.vertices_mm ?? []).map(vertex => [vertex[0], vertex[1]]);
}

function polygonArea(points: [number, number][]) {
  return Math.abs(points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length];
    return sum + point[0] * next[1] - next[0] * point[1];
  }, 0)) / 2;
}

/** Split planar solver faces by complete shared edges. A coincident corner or
 * same-net copper nearby is not enough to permit interpolation between faces. */
export function connectedContourSampleGroups(rawSamples: readonly ScalarSample[]): ScalarSample[][] {
  const samples = rawSamples.filter(sample => finiteSample(sample)
    && (sample.vertices_mm?.length ?? 0) >= 3 && polygonArea(projectedPolygon(sample)) > 1e-12);
  const parents = samples.map((_, index) => index);
  const find = (index: number): number => {
    let root = index;
    while (parents[root] !== root) root = parents[root];
    while (parents[index] !== index) { const next = parents[index]; parents[index] = root; index = next; }
    return root;
  };
  const union = (left: number, right: number) => {
    const leftRoot = find(left); const rightRoot = find(right);
    if (leftRoot !== rightRoot) parents[rightRoot] = leftRoot;
  };
  const owners = new Map<string, number>();
  samples.forEach((sample, sampleIndex) => {
    const vertices = sample.vertices_mm!;
    const domain = `${sample.net ?? ""}\u0000${sample.layer ?? ""}\u0000`;
    for (let index = 0; index < vertices.length; index += 1) {
      const left = coordinateKey(vertices[index]);
      const right = coordinateKey(vertices[(index + 1) % vertices.length]);
      const edge = left < right ? `${left}|${right}` : `${right}|${left}`;
      const key = domain + edge;
      const owner = owners.get(key);
      if (owner === undefined) owners.set(key, sampleIndex); else union(sampleIndex, owner);
    }
  });
  const groups = new Map<number, ScalarSample[]>();
  samples.forEach((sample, index) => {
    const root = find(index);
    const group = groups.get(root) ?? [];
    group.push(sample);
    groups.set(root, group);
  });
  return [...groups.values()];
}

function pointInFace(point: [number, number], polygon: [number, number][]) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index++) {
    const left = polygon[previous]; const right = polygon[index];
    const dx = right[0] - left[0]; const dy = right[1] - left[1];
    const lengthSquared = dx * dx + dy * dy;
    const ratio = lengthSquared ? Math.max(0, Math.min(1,
      ((point[0] - left[0]) * dx + (point[1] - left[1]) * dy) / lengthSquared)) : 0;
    if (Math.hypot(point[0] - left[0] - ratio * dx, point[1] - left[1] - ratio * dy) <= 1e-8) return true;
    if ((right[1] > point[1]) !== (left[1] > point[1])
      && point[0] < (left[0] - right[0]) * (point[1] - right[1]) / ((left[1] - right[1]) || Number.EPSILON) + right[0]) inside = !inside;
  }
  return inside;
}

/** Spatially indexed exact-face support for a contour component. */
export function sampleFaceSupport(rawSamples: readonly ScalarSample[]): (xMm: number, yMm: number) => boolean {
  const faces = rawSamples.map(sample => projectedPolygon(sample)).filter(points => points.length >= 3 && polygonArea(points) > 1e-12);
  if (!faces.length) return () => false;
  const allX = faces.flatMap(face => face.map(point => point[0]));
  const allY = faces.flatMap(face => face.map(point => point[1]));
  const xExtent = numericExtent(allX); const yExtent = numericExtent(allY);
  const minX = xExtent.minimum; const maxX = xExtent.maximum;
  const minY = yExtent.minimum; const maxY = yExtent.maximum;
  const cellSize = Math.max(Math.max(maxX - minX, maxY - minY) / Math.max(Math.sqrt(faces.length), 1), 1e-5);
  const buckets = new Map<string, number[]>();
  const overflow: number[] = [];
  faces.forEach((face, faceIndex) => {
    const x = face.map(point => point[0]); const y = face.map(point => point[1]);
    const faceX = numericExtent(x); const faceY = numericExtent(y);
    const left = Math.floor((faceX.minimum - minX) / cellSize); const right = Math.floor((faceX.maximum - minX) / cellSize);
    const top = Math.floor((faceY.minimum - minY) / cellSize); const bottom = Math.floor((faceY.maximum - minY) / cellSize);
    if ((right - left + 1) * (bottom - top + 1) > 256) { overflow.push(faceIndex); return; }
    for (let row = top; row <= bottom; row += 1) for (let column = left; column <= right; column += 1) {
      const key = `${column}:${row}`; const entries = buckets.get(key) ?? [];
      entries.push(faceIndex); buckets.set(key, entries);
    }
  });
  return (xMm, yMm) => {
    if (xMm < minX - 1e-8 || xMm > maxX + 1e-8 || yMm < minY - 1e-8 || yMm > maxY + 1e-8) return false;
    const key = `${Math.floor((xMm - minX) / cellSize)}:${Math.floor((yMm - minY) / cellSize)}`;
    return [...(buckets.get(key) ?? []), ...overflow].some(index => pointInFace([xMm, yMm], faces[index]));
  };
}

const finiteSample = (sample: ScalarSample) => Number.isFinite(sample.x_mm)
  && Number.isFinite(sample.y_mm)
  && Number.isFinite(sample.value);

const median = (values: number[]) => {
  if (!values.length) return 0;
  const ordered = [...values].sort((left, right) => left - right);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
};

function deterministicDownsample(samples: ScalarSample[], limit: number) {
  limit = Math.max(3, Math.floor(limit));
  if (samples.length <= limit) return samples;
  const minimum = samples.reduce((best, sample) => sample.value < best.value ? sample : best);
  const maximum = samples.reduce((best, sample) => sample.value > best.value ? sample : best);
  const output: ScalarSample[] = [minimum, maximum];
  const step = (samples.length - 1) / Math.max(limit - 1, 1);
  for (let index = 0; output.length < limit && index < limit; index += 1) output.push(samples[Math.round(index * step)]);
  return output;
}

/** Local least-squares display reconstruction. Fit v=a+b*dx+c*dy using
 * weighted normal equations; fall back to IDW when samples are collinear. */
export function interpolateDisplayValue(samples: ScalarSample[], x: number, y: number): number | undefined {
  if (!samples.length) return undefined;
  const exact = samples.find(sample => Math.hypot(sample.x_mm - x, sample.y_mm - y) < 1e-9);
  if (exact) return exact.value;
  const radius = Math.max(numericExtent(samples.map(sample => Math.hypot(sample.x_mm - x, sample.y_mm - y))).maximum, 1e-9);
  const matrix = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]];
  let weighted = 0; let weightSum = 0;
  for (const sample of samples) {
    const basis = [1, (sample.x_mm - x) / radius, (sample.y_mm - y) / radius];
    const weight = 1 / Math.max(basis[1] ** 2 + basis[2] ** 2, 1e-8);
    weighted += sample.value * weight; weightSum += weight;
    for (let row = 0; row < 3; row++) {
      for (let column = 0; column < 3; column++) matrix[row][column] += weight * basis[row] * basis[column];
      matrix[row][3] += weight * basis[row] * sample.value;
    }
  }
  const fallback = weighted / weightSum;
  const tolerance = matrix[0][0] * 1e-10;
  for (let column = 0; column < 3; column++) {
    let pivot = column;
    for (let row = column + 1; row < 3; row++) if (Math.abs(matrix[row][column]) > Math.abs(matrix[pivot][column])) pivot = row;
    if (Math.abs(matrix[pivot][column]) < tolerance) return fallback;
    [matrix[column], matrix[pivot]] = [matrix[pivot], matrix[column]];
    const divisor = matrix[column][column];
    for (let index = column; index < 4; index++) matrix[column][index] /= divisor;
    for (let row = 0; row < 3; row++) if (row !== column) {
      const factor = matrix[row][column];
      for (let index = column; index < 4; index++) matrix[row][index] -= factor * matrix[column][index];
    }
  }
  const extent = numericExtent(samples.map(sample => sample.value));
  return Math.max(extent.minimum, Math.min(extent.maximum, matrix[0][3]));
}

function characteristicSpacing(samples: ScalarSample[], span: number) {
  const probes = deterministicDownsample(samples, 160);
  const search = deterministicDownsample(samples, 1800);
  const nearest: number[] = [];
  probes.forEach(probe => {
    let distanceSquared = Number.POSITIVE_INFINITY;
    search.forEach(candidate => {
      if (candidate === probe) return;
      const dx = candidate.x_mm - probe.x_mm;
      const dy = candidate.y_mm - probe.y_mm;
      const next = dx * dx + dy * dy;
      if (next > 1e-16 && next < distanceSquared) distanceSquared = next;
    });
    if (Number.isFinite(distanceSquared)) nearest.push(Math.sqrt(distanceSquared));
  });
  const measured = median(nearest.filter(value => value > 1e-8));
  const widths = median(samples.map(sample => Number(sample.width_mm)).filter(value => Number.isFinite(value) && value > 0));
  if (measured > 0 && widths > 0) return Math.min(measured, widths);
  if (measured > 0) return measured;
  if (widths > 0) return widths;
  return Math.max(span / Math.max(Math.sqrt(samples.length), 8), 0.01);
}

function crossing(
  left: ContourVertex,
  right: ContourVertex,
  level: number,
): [number, number] | null {
  const deltaLeft = left.value - level;
  const deltaRight = right.value - level;
  if (deltaLeft === 0 && deltaRight === 0) return null;
  if (deltaLeft * deltaRight > 0) return null;
  const ratio = right.value === left.value ? 0.5 : (level - left.value) / (right.value - left.value);
  if (ratio < 0 || ratio > 1) return null;
  return [
    left.xMm + (right.xMm - left.xMm) * ratio,
    left.yMm + (right.yMm - left.yMm) * ratio,
  ];
}

/**
 * Builds a display-only scalar surface. Unsupported grid vertices remain null,
 * so triangles and contour lines cannot bridge large conductor or net voids.
 */
export function buildContourGrid(rawSamples: ScalarSample[], options: ContourOptions = {}): ContourGrid | null {
  const finite = rawSamples.filter(finiteSample);
  if (finite.length < 3) return null;
  const sourceSamples = deterministicDownsample(finite, options.maximumSourceSamples ?? 3000);
  const xExtent = numericExtent(sourceSamples.map(sample => sample.x_mm));
  const yExtent = numericExtent(sourceSamples.map(sample => sample.y_mm));
  let minX = xExtent.minimum;
  let maxX = xExtent.maximum;
  let minY = yExtent.minimum;
  let maxY = yExtent.maximum;
  const originalSpan = Math.max(maxX - minX, maxY - minY, 0.01);
  const spacing = Math.max(characteristicSpacing(sourceSamples, originalSpan), 1e-4);
  // Solver samples usually describe face centres. Extend by half a sample
  // pitch so the display reconstruction can reach the conductor boundary;
  // supportsPoint below remains authoritative for the visible geometry.
  minX -= spacing * 0.55;
  maxX += spacing * 0.55;
  minY -= spacing * 0.55;
  maxY += spacing * 0.55;
  if (maxX - minX < spacing * 0.8) {
    const center = (minX + maxX) / 2;
    minX = center - spacing * 0.65;
    maxX = center + spacing * 0.65;
  }
  if (maxY - minY < spacing * 0.8) {
    const center = (minY + maxY) / 2;
    minY = center - spacing * 0.65;
    maxY = center + spacing * 0.65;
  }
  const width = Math.max(maxX - minX, spacing);
  const height = Math.max(maxY - minY, spacing);
  const maximumGridVertices = Math.max(options.maximumGridVertices ?? 4200, 64);
  // A grid at the solver sample pitch merely redraws the original blocks.
  // Three presentation vertices per pitch is enough to make interpolation
  // continuous without pretending that the solver itself was refined.
  let step = Math.max(spacing / 3, Math.max(width, height) / 144);
  let columns = Math.max(2, Math.ceil(width / step) + 1);
  let rows = Math.max(2, Math.ceil(height / step) + 1);
  while (columns * rows > maximumGridVertices) {
    step *= Math.max(1.05, Math.sqrt(columns * rows / maximumGridVertices));
    columns = Math.max(2, Math.ceil(width / step) + 1);
    rows = Math.max(2, Math.ceil(height / step) + 1);
  }
  const stepX = width / Math.max(columns - 1, 1);
  const stepY = height / Math.max(rows - 1, 1);
  const bucketSize = Math.max(spacing * 1.6, step * 1.45);
  const buckets = new Map<string, ScalarSample[]>();
  const bucketKey = (x: number, y: number) => `${Math.floor((x - minX) / bucketSize)}:${Math.floor((y - minY) / bucketSize)}`;
  sourceSamples.forEach(sample => {
    const key = bucketKey(sample.x_mm, sample.y_mm);
    const bucket = buckets.get(key) ?? [];
    bucket.push(sample);
    buckets.set(key, bucket);
  });
  const vertices: Array<ContourVertex | null> = Array(columns * rows).fill(null);
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const xMm = minX + column * stepX;
      const yMm = minY + row * stepY;
      if (options.supportsPoint && !options.supportsPoint(xMm, yMm)) continue;
      const bucketX = Math.floor((xMm - minX) / bucketSize);
      const bucketY = Math.floor((yMm - minY) / bucketSize);
      const candidates: Array<{ sample: ScalarSample; distanceSquared: number }> = [];
      for (let offsetY = -1; offsetY <= 1; offsetY += 1) {
        for (let offsetX = -1; offsetX <= 1; offsetX += 1) {
          (buckets.get(`${bucketX + offsetX}:${bucketY + offsetY}`) ?? []).forEach(sample => {
            const dx = sample.x_mm - xMm;
            const dy = sample.y_mm - yMm;
            const distanceSquared = dx * dx + dy * dy;
            const sampleWidth = Number.isFinite(sample.width_mm) && Number(sample.width_mm) > 0 ? Number(sample.width_mm) : spacing;
            const localSupport = Math.min(Math.max(spacing * 1.35, sampleWidth * 0.85, step * 1.2), spacing * 3.2);
            if (distanceSquared <= localSupport * localSupport) candidates.push({ sample, distanceSquared });
          });
        }
      }
      candidates.sort((left, right) => left.distanceSquared - right.distanceSquared);
      const nearest = candidates.slice(0, 12);
      if (!nearest.length) continue;
      const value = interpolateDisplayValue(nearest.map(candidate => candidate.sample), xMm, yMm)!;
      vertices[row * columns + column] = { xMm, yMm, value };
    }
  }
  const indices: number[] = [];
  const contours: ContourSegment[] = [];
  const valueExtent = numericExtent(sourceSamples.map(sample => sample.value));
  const minimum = valueExtent.minimum;
  const maximum = valueExtent.maximum;
  const levelCount = Math.max(2, Math.min(24, Math.round(options.levels ?? 10)));
  const levels = maximum > minimum
    ? Array.from({ length: levelCount }, (_, index) => minimum + (maximum - minimum) * (index + 1) / (levelCount + 1))
    : [];
  for (let row = 0; row < rows - 1; row += 1) {
    for (let column = 0; column < columns - 1; column += 1) {
      const topLeftIndex = row * columns + column;
      const topRightIndex = topLeftIndex + 1;
      const bottomLeftIndex = (row + 1) * columns + column;
      const bottomRightIndex = bottomLeftIndex + 1;
      const topLeft = vertices[topLeftIndex];
      const topRight = vertices[topRightIndex];
      const bottomLeft = vertices[bottomLeftIndex];
      const bottomRight = vertices[bottomRightIndex];
      const admitTriangle = (entries: Array<[number, ContourVertex | null]>) => {
        if (entries.some(([, vertex]) => !vertex)) return;
        const admitted = entries.map(([, vertex]) => vertex!) as ContourVertex[];
        if (options.supportsPoint) {
          const checks = [
            ...admitted.map((vertex, index) => {
              const next = admitted[(index + 1) % admitted.length];
              return [(vertex.xMm + next.xMm) / 2, (vertex.yMm + next.yMm) / 2] as [number, number];
            }),
            [admitted.reduce((sum, vertex) => sum + vertex.xMm, 0) / 3,
              admitted.reduce((sum, vertex) => sum + vertex.yMm, 0) / 3] as [number, number],
          ];
          if (checks.some(point => !options.supportsPoint!(point[0], point[1]))) return;
        }
        indices.push(...entries.map(([vertexIndex]) => vertexIndex));
      };
      admitTriangle([[topLeftIndex, topLeft], [bottomLeftIndex, bottomLeft], [topRightIndex, topRight]]);
      admitTriangle([[topRightIndex, topRight], [bottomLeftIndex, bottomLeft], [bottomRightIndex, bottomRight]]);
      if (!topLeft || !topRight || !bottomLeft || !bottomRight) continue;
      levels.forEach(level => {
        const points = [
          crossing(topLeft, topRight, level),
          crossing(topRight, bottomRight, level),
          crossing(bottomRight, bottomLeft, level),
          crossing(bottomLeft, topLeft, level),
        ].filter((point): point is [number, number] => Boolean(point));
        if (points.length === 2) contours.push({ level, start: points[0], end: points[1] });
        if (points.length === 4) {
          const center = (topLeft.value + topRight.value + bottomLeft.value + bottomRight.value) / 4;
          const pairs = center >= level ? [[0, 3], [1, 2]] : [[0, 1], [2, 3]];
          pairs.forEach(([start, end]) => contours.push({ level, start: points[start], end: points[end] }));
        }
      });
    }
  }
  if (!indices.length) return null;
  return { columns, rows, minimum, maximum, vertices, indices, contours, sourceSamples: finite };
}

/** Convert the display grid to triangle samples accepted by both 2D result
 * batch renderers. Values are interpolated only inside the admitted support;
 * the solver samples and extrema remain untouched. */
export function contourGridTriangleSamples(grid: ContourGrid, template: ScalarSample): ScalarSample[] {
  const output: ScalarSample[] = [];
  for (let index = 0; index < grid.indices.length; index += 3) {
    const vertices = grid.indices.slice(index, index + 3).map(vertex => grid.vertices[vertex]);
    if (vertices.some(vertex => !vertex)) continue;
    const admitted = vertices as ContourVertex[];
    output.push({
      ...template,
      x_mm: admitted.reduce((sum, vertex) => sum + vertex.xMm, 0) / 3,
      y_mm: admitted.reduce((sum, vertex) => sum + vertex.yMm, 0) / 3,
      value: admitted.reduce((sum, vertex) => sum + vertex.value, 0) / 3,
      vertices_mm: admitted.map(vertex => [vertex.xMm, vertex.yMm, template.z_mm ?? 0]),
    });
  }
  return output;
}

/** Associate vertical barrel-face samples with their source via. The exact
 * source prefix is preferred; a tightly bounded geometric match supports old
 * result envelopes that did not retain source identifiers. Each via displays
 * the peak returned stress while retaining the original samples elsewhere. */
export function matchViaStressSamples(
  rawSamples: readonly ScalarSample[], rawVias: readonly ViaStressGeometry[],
): ViaStressGlyph[] {
  const samples = rawSamples.filter(finiteSample);
  const vias = rawVias.filter(via => Number.isFinite(via.at[0]) && Number.isFinite(via.at[1])
    && Number.isFinite(via.size) && via.size > 0);
  const viasById = new Map(vias.map(via => [via.id, via]));
  const matches = new Map<string, { via: ViaStressGeometry; value: number; sampleCount: number }>();
  for (const sample of samples) {
    const source = sample.source_id ?? sample.element_id ?? "";
    let via = source ? viasById.get(source) : undefined;
    if (!via && source) {
      let separator = source.length;
      while (!via && (separator = source.lastIndexOf(":", separator - 1)) >= 0) via = viasById.get(source.slice(0, separator));
    }
    if (!via) {
      let nearestDistance = Number.POSITIVE_INFINITY;
      for (const candidate of vias) {
        if (sample.net && candidate.net && sample.net !== candidate.net) continue;
        const distance = Math.hypot(sample.x_mm - candidate.at[0], sample.y_mm - candidate.at[1]);
        if (distance <= candidate.size * 0.7 && distance < nearestDistance) {
          via = candidate;
          nearestDistance = distance;
        }
      }
    }
    if (!via) continue;
    const current = matches.get(via.id);
    if (!current) matches.set(via.id, { via, value: sample.value, sampleCount: 1 });
    else {
      current.sampleCount += 1;
      if (Math.abs(sample.value) > Math.abs(current.value)) current.value = sample.value;
    }
  }
  return [...matches.values()];
}
