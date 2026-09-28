// SPDX-License-Identifier: Apache-2.0
import type { EMergeAngularPattern } from "./emergePatternInterpolation";

export type EmRadiationMeshData = {
  positions: number[];
  indices: number[];
  thetaDeg: number[];
  phiDeg: number[];
  relativeDb: number[];
};

/**
 * Builds a dimensionless, board-anchored far-field surface. Radius is a
 * display encoding of relative E-field amplitude; it is never a spatial field.
 */
export function emRadiationMeshData(pattern: EMergeAngularPattern, floorDb = -40): EmRadiationMeshData {
  const { theta_deg: theta, phi_deg: phi, relative_amplitude_db: db } = pattern;
  if (theta.length < 2 || phi.length < 2 || db.length !== theta.length * phi.length
      || !Number.isFinite(floorDb) || floorDb >= 0
      || theta.some((value, index) => !Number.isFinite(value) || value < 0 || value > 180 || index > 0 && value <= theta[index - 1])
      || phi.some((value, index) => !Number.isFinite(value) || value < 0 || value > 360 || index > 0 && value <= phi[index - 1])
      || db.some(value => !Number.isFinite(value))) {
    throw new Error("EM radiation pattern is not a finite rectangular angular grid.");
  }
  let peak = Number.NEGATIVE_INFINITY;
  for (const value of db) if (value > peak) peak = value;
  const positions: number[] = [];
  const thetaDeg: number[] = [];
  const phiDeg: number[] = [];
  const relativeDb: number[] = [];
  for (let ti = 0; ti < theta.length; ti++) {
    const thetaRad = theta[ti] * Math.PI / 180;
    for (let pi = 0; pi < phi.length; pi++) {
      const phiRad = phi[pi] * Math.PI / 180;
      const relative = db[ti * phi.length + pi] - peak;
      const amplitude = 10 ** (Math.max(relative, floorDb) / 20);
      const radius = 0.18 + 0.82 * amplitude;
      positions.push(
        radius * Math.sin(thetaRad) * Math.cos(phiRad),
        radius * Math.sin(thetaRad) * Math.sin(phiRad),
        radius * Math.cos(thetaRad),
      );
      thetaDeg.push(theta[ti]);
      phiDeg.push(phi[pi]);
      relativeDb.push(relative);
    }
  }
  const indices: number[] = [];
  for (let ti = 0; ti < theta.length - 1; ti++) {
    for (let pi = 0; pi < phi.length - 1; pi++) {
      const a = ti * phi.length + pi;
      const b = a + phi.length;
      indices.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  return { positions, indices, thetaDeg, phiDeg, relativeDb };
}

export type EmRadiationProbe = { thetaDeg: number; phiDeg: number; relativeDb: number; sampleState: "solved-grid" };

export function emRadiationProbeAtVertex(data: EmRadiationMeshData, vertexIndex: number): EmRadiationProbe | null {
  if (!Number.isInteger(vertexIndex) || vertexIndex < 0 || vertexIndex >= data.relativeDb.length) return null;
  return { thetaDeg: data.thetaDeg[vertexIndex], phiDeg: data.phiDeg[vertexIndex], relativeDb: data.relativeDb[vertexIndex], sampleState: "solved-grid" };
}
