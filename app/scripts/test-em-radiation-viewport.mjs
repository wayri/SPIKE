// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(specifier, context, nextResolve) {
  if (specifier.startsWith(".") && !specifier.endsWith(".ts")) return nextResolve(`${specifier}.ts`, context);
  return nextResolve(specifier, context);
} });
const { emRadiationMeshData, emRadiationProbeAtVertex } = await import("../src/emRadiationViewport.ts");

const pattern = {
  frequency_hz: 2.45e9,
  theta_deg: [0, 90, 180],
  phi_deg: [0, 180, 360],
  relative_amplitude_db: [0, 0, 0, -6, -12, -6, -30, -30, -30],
};
const mesh = emRadiationMeshData(pattern);
assert.equal(mesh.positions.length, 27);
assert.equal(mesh.indices.length, 24);
assert.deepEqual(emRadiationProbeAtVertex(mesh, 4), { thetaDeg: 90, phiDeg: 180, relativeDb: -12, sampleState: "solved-grid" });
assert.equal(emRadiationProbeAtVertex(mesh, 99), null);
assert.ok(Math.abs(mesh.positions[2] - 1) < 1e-12, "theta zero points along board +Z");
assert.ok(mesh.positions[3 * 4] < 0, "theta 90, phi 180 points along board -X");
assert.throws(() => emRadiationMeshData({ ...pattern, relative_amplitude_db: [0] }), /rectangular angular grid/);
console.log("EM board viewport: directional mesh, board axes, and solved-grid probe passed");
