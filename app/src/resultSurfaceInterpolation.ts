// SPDX-License-Identifier: MIT
import type { ScalarSample } from "./analysisResults";

/** Display reconstruction on solver faces only. Never crosses a net/layer or
 * fills a gap between disconnected faces. Authoritative samples stay unchanged. */
export function sharedVertexValues(samples: readonly ScalarSample[]): Map<ScalarSample, number[]> {
  const coordinate = (vertex: number[]) => vertex.map(value => value.toFixed(7)).join(":");
  const domain = (sample: ScalarSample) => `${sample.net ?? ""}\0${sample.layer ?? ""}`;
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
  // A coincident corner alone does not establish face adjacency. Two faces
  // participate in one smoothing patch only when they share a complete edge.
  const edgeOwner = new Map<string, number>();
  samples.forEach((sample, sampleIndex) => {
    const vertices = sample.vertices_mm ?? [];
    for (let index = 0; index < vertices.length; index++) {
      const left = coordinate(vertices[index]);
      const right = coordinate(vertices[(index + 1) % vertices.length]);
      const edge = left < right ? `${left}|${right}` : `${right}|${left}`;
      const key = `${domain(sample)}\0${edge}`;
      const owner = edgeOwner.get(key);
      if (owner === undefined) edgeOwner.set(key, sampleIndex); else union(sampleIndex, owner);
    }
  });
  const accumulators = new Map<string, { weighted: number; weight: number }>();
  const key = (sample: ScalarSample, sampleIndex: number, vertex: number[]) =>
    `${domain(sample)}\0${find(sampleIndex)}\0${coordinate(vertex)}`;
  samples.forEach((sample, sampleIndex) => {
    if (!Number.isFinite(sample.value)) return;
    for (const vertex of sample.vertices_mm ?? []) {
      const weight = 1 / Math.max(Math.hypot(vertex[0] - sample.x_mm, vertex[1] - sample.y_mm), 1e-7);
      const vertexKey = key(sample, sampleIndex, vertex);
      const current = accumulators.get(vertexKey) ?? { weighted: 0, weight: 0 };
      current.weighted += sample.value * weight;
      current.weight += weight;
      accumulators.set(vertexKey, current);
    }
  });
  return new Map(samples.map((sample, sampleIndex) => [sample, (sample.vertices_mm ?? []).map(vertex => {
    const entry = accumulators.get(key(sample, sampleIndex, vertex));
    return entry && entry.weight > 0 ? entry.weighted / entry.weight : sample.value;
  })]));
}

/** Surface hit mapping is independent of how many source faces were batched. */
export function resultSampleForHit(
  samples: readonly ScalarSample[], faceIndex?: number | null,
  triangleSamples?: readonly number[], instanceId?: number,
): ScalarSample | undefined {
  const index = instanceId ?? (faceIndex != null ? triangleSamples?.[faceIndex] : undefined);
  return index != null ? samples[index] : undefined;
}

/** Only actually opaque depth-writing geometry blocks a result cursor. */
export function resultHitOccluded(resultDistance: number, blockerDistance: number,
  opacity: number, depthWrite: boolean, epsilon = 1e-4): boolean {
  return depthWrite && opacity >= 0.999 && blockerDistance + epsilon < resultDistance;
}

export type SmoothDisplayResult = {
  samples: ScalarSample[];
  budget: number;
  emittedTriangles: number;
  fallbackPoints: number;
  omittedGeometry: number;
  omittedFallbacks: number;
};

/** Bounded, unblurred 2D reconstruction of the same vertex field used in 3D. */
export function smoothDisplaySamplesWithBudget(samples: ScalarSample[],
  triangulate: (vertices: [number, number, number][]) => number[], budget = 100_000): SmoothDisplayResult {
  const hardBudget = Math.max(0, Math.floor(Number.isFinite(budget) ? budget : 0));
  const values = sharedVertexValues(samples);
  const faces = samples.map(sample => ({ sample, indices: sample.vertices_mm?.length
    ? triangulate(sample.vertices_mm) : [] }));
  const triangleCount = faces.reduce((count, face) => count + face.indices.length / 3, 0);
  const subdivisions = Math.max(1, Math.min(4, Math.floor(Math.sqrt(hardBudget / Math.max(triangleCount, 1)))));
  const output: ScalarSample[] = [];
  let emittedTriangles = 0; let fallbackPoints = 0; let omittedGeometry = 0; let omittedFallbacks = 0;
  const fallback = (sample: ScalarSample) => {
    if (output.length >= hardBudget) { omittedFallbacks += 1; return; }
    output.push({ ...sample, vertices_mm: undefined });
    fallbackPoints += 1;
  };
  for (let faceIndex = 0; faceIndex < faces.length; faceIndex++) {
    const { sample, indices } = faces[faceIndex];
    if (!indices.length) { fallback(sample); continue; }
    const triangleCost = indices.length / 3 * subdivisions * subdivisions;
    const remainingFallbackReserve = Math.min(faces.length - faceIndex - 1, Math.max(0, hardBudget - output.length));
    if (triangleCost > hardBudget - output.length - remainingFallbackReserve) {
      omittedGeometry += indices.length / 3;
      fallback(sample);
      continue;
    }
    for (let index = 0; index < indices.length; index += 3) {
      const corners = indices.slice(index, index + 3).map(vertex => sample.vertices_mm![vertex]);
      const field = indices.slice(index, index + 3).map(vertex => values.get(sample)![vertex]);
      const at = (i: number, j: number) => {
        const weights = [1 - (i + j) / subdivisions, i / subdivisions, j / subdivisions];
        return { position: [0, 1, 2].map(axis => weights.reduce((sum, weight, corner) =>
          sum + weight * corners[corner][axis], 0)) as [number, number, number],
          value: weights.reduce((sum, weight, corner) => sum + weight * field[corner], 0) };
      };
      const emit = (triangle: ReturnType<typeof at>[]) => {
        output.push({ ...sample,
          x_mm: triangle.reduce((sum, vertex) => sum + vertex.position[0], 0) / 3,
          y_mm: triangle.reduce((sum, vertex) => sum + vertex.position[1], 0) / 3,
          value: triangle.reduce((sum, vertex) => sum + vertex.value, 0) / 3,
          vertices_mm: triangle.map(vertex => vertex.position) });
        emittedTriangles += 1;
      };
      for (let i = 0; i < subdivisions; i++) for (let j = 0; j < subdivisions - i; j++) {
        emit([at(i, j), at(i + 1, j), at(i, j + 1)]);
        if (i + j < subdivisions - 1) emit([at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)]);
      }
    }
  }
  return { samples: output, budget: hardBudget, emittedTriangles, fallbackPoints, omittedGeometry, omittedFallbacks };
}

export function smoothDisplaySamples(samples: ScalarSample[],
  triangulate: (vertices: [number, number, number][]) => number[], budget = 100_000): ScalarSample[] {
  return smoothDisplaySamplesWithBudget(samples, triangulate, budget).samples;
}
