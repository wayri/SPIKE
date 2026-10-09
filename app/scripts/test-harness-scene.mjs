// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import * as THREE from "three";
import { buildHarnessScene, disposeHarnessScene, updateHarnessSceneSelection,
  HARNESS_TUBE_RADIAL_SEGMENTS } from "../src/harnessScene.ts";

const ROLE_COLORS = {
  unspecified: 0x78b7c5, power: 0xe36f4f, return: 0x8090aa,
  signal: 0x55c7dc, shield: 0xb2aaa0, other: 0xc18ad6,
};
const SELECTION_COLOR = 0x123456;

const route = [[0, 0, 0], [8, 0, 5], [20, 10, 5], [30, 10, 0]];
const visual = {
  id: "loom", name: "Main loom", lengthMm: 45,
  endpointA: { boardId: "a", connectorId: "J1", positionMm: route[0] },
  endpointB: { boardId: "b", connectorId: "J2", positionMm: route.at(-1) },
  routeMm: route, routedPolyline: true,
  conductors: [
    { id: "PWR", fromPin: "1", toPin: "A", role: "power", twisted: false },
    { id: "SIG", fromPin: "2", toPin: "B", role: "signal", twisted: false },
  ],
};
const path = (wireId, role, offset = 0) => ({
  harness: visual,
  conductor: { harnessId: visual.id, wireId, role, presentation: "schematic", samplingCapped: false,
    pointsMm: route.map(([x, y, z]) => [x, y + offset, z]) },
});
const originalRoute = structuredClone(route);
const built = buildHarnessScene([path("PWR", "power"), path("SIG", "signal", 0.6)],
  { roleColors: ROLE_COLORS, tubularSegmentBudget: 16 });
assert.equal(built.pickables.length, 2);
assert.equal(built.stats.tubularSegments, 16, "scene-wide tessellation is bounded before allocating geometry");
assert.equal(built.stats.triangles, 16 * HARNESS_TUBE_RADIAL_SEGMENTS * 2);
assert.equal(built.stats.geometryBudgetCapped, true);
assert.deepEqual(route, originalRoute, "scene smoothing must not rewrite authored route anchors");
for (const mesh of built.pickables) {
  assert.ok(mesh instanceof THREE.Mesh && mesh.geometry instanceof THREE.TubeGeometry,
    "conductors are view-scaled solid tubes rather than one-pixel lines");
  assert.equal(mesh.material.depthTest, true, "board solids occlude cables behind them");
  assert.equal(mesh.material.depthWrite, true);
  assert.equal(mesh.material.transparent, false, "opaque cable surfaces avoid transparent depth sorting artifacts");
  assert.equal(mesh.userData.presentationOnly, true, "display curves cannot be mistaken for solver geometry");
  assert.equal(mesh.userData.harnessRouteMm, route, "picks retain the exact displayed route anchor record");
  assert.equal(mesh.userData.harnessRouteIsSaved, true);
}
assert.equal(built.pickables[0].userData.harnessFromPin, "1");
assert.equal(built.pickables[0].userData.harnessToPin, "A", "pick metadata retains both saved endpoint pin IDs");
assert.equal(built.pickables[0].userData.virtualHarness.selectedConductorId, "PWR");

updateHarnessSceneSelection(built.group, "loom", "PWR", SELECTION_COLOR);
assert.equal(built.pickables[0].material.color.getHex(), SELECTION_COLOR);
assert.equal(built.pickables[1].material.color.getHex(), 0x55c7dc, "wire selection does not highlight its neighbor");
updateHarnessSceneSelection(built.group, "loom", null, SELECTION_COLOR);
assert.ok(built.pickables.every(mesh => mesh.material.color.getHex() === SELECTION_COLOR), "bundle selection highlights every admitted wire");

const fallback = buildHarnessScene([{
  harness: { ...visual, conductors: [] },
  conductor: { harnessId: "loom", wireId: null, role: "unspecified", presentation: "bundle-fallback",
    samplingCapped: false, pointsMm: route },
}], { roleColors: ROLE_COLORS });
assert.equal(fallback.pickables[0].userData.harnessRadiusMm, 0.72, "legacy bundles remain visibly cable-sized");
assert.equal(fallback.pickables[0].userData.harnessWireId, null);

const bounded = buildHarnessScene([path("PWR", "power"), path("SIG", "signal"), path("AUX", "other")],
  { roleColors: ROLE_COLORS, maxMeshes: 2, tubularSegmentBudget: 16 });
assert.equal(bounded.pickables.length, 2);
assert.equal(bounded.stats.truncatedMeshes, 1);
assert.ok(bounded.stats.triangles <= 16 * HARNESS_TUBE_RADIAL_SEGMENTS * 2);

const tinyBudget = buildHarnessScene([path("PWR", "power")],
  { roleColors: ROLE_COLORS, tubularSegmentBudget: 7 });
assert.equal(tinyBudget.pickables.length, 0, "a budget below the minimum tube cost allocates no geometry");
assert.equal(tinyBudget.stats.tubularSegments, 0, "the requested segment budget is a strict upper bound");
assert.equal(tinyBudget.stats.truncatedMeshes, 1);
const invalid = buildHarnessScene([{ ...path("BAD", "other"), conductor: {
  ...path("BAD", "other").conductor, pointsMm: [[0, 0, 0], [Number.NaN, 1, 2]],
} }], { roleColors: ROLE_COLORS });
assert.equal(invalid.stats.invalidPaths, 1, "malformed paths are reported separately from resource truncation");

const raycaster = new THREE.Raycaster(new THREE.Vector3(0, 0, 4), new THREE.Vector3(0, 0, -1));
built.group.updateMatrixWorld(true);
assert.ok(raycaster.intersectObjects(built.pickables, false).some(hit => hit.object.userData.harnessWireId === "PWR"),
  "solid cable geometry provides depth-aware picking without a line threshold");

let geometryDisposals = 0, materialDisposals = 0;
for (const mesh of built.pickables) {
  mesh.geometry.addEventListener("dispose", () => geometryDisposals++);
  mesh.material.addEventListener("dispose", () => materialDisposals++);
}
disposeHarnessScene(built.group);
assert.equal(built.group.children.length, 0);
assert.equal(geometryDisposals, 2);
assert.equal(materialDisposals, 2, "owned cable GPU resources are released exactly once");
disposeHarnessScene(fallback.group);
disposeHarnessScene(bounded.group);
disposeHarnessScene(tinyBudget.group);
disposeHarnessScene(invalid.group);
console.log("Harness scene tubes, depth, identity, bounds, picking, selection, and disposal passed.");
