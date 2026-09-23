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
};

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
  let step = Math.max(spacing, Math.max(width, height) / 72);
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
      const nearest = candidates.slice(0, 8);
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
      if (!topLeft || !topRight || !bottomLeft || !bottomRight) continue;
      indices.push(topLeftIndex, bottomLeftIndex, topRightIndex, topRightIndex, bottomLeftIndex, bottomRightIndex);
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
