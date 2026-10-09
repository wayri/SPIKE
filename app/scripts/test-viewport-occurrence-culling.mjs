// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as THREE from "three";
import ts from "typescript";

const source = readFileSync(new URL("../src/viewportOccurrenceCulling.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText.replace('from "three"', `from ${JSON.stringify(import.meta.resolve("three"))}`);
const { ViewportOccurrenceCuller } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 200);
camera.position.set(0, 0, 10);
camera.lookAt(0, 0, 0);
camera.updateProjectionMatrix();
camera.updateMatrixWorld();

const material = new THREE.MeshBasicMaterial();
const geometry = new THREE.BoxGeometry(2, 2, 2);
let geometryDisposals = 0, materialDisposals = 0;
geometry.addEventListener("dispose", () => { geometryDisposals += 1; });
material.addEventListener("dispose", () => { materialDisposals += 1; });
const occurrence = (x, visible = true) => {
  const root = new THREE.Group();
  root.position.x = x;
  root.visible = visible;
  root.add(new THREE.Mesh(geometry, material));
  return root;
};

const inside = occurrence(0), outside = occurrence(100), userHidden = occurrence(100, false), empty = new THREE.Group();
const scene = new THREE.Scene();
scene.add(inside, outside, userHidden, empty);
const culler = new ViewportOccurrenceCuller();

const first = culler.begin(camera, [
  { root: inside, geometryRevision: 0 },
  { root: outside, geometryRevision: 0 },
  { root: userHidden, geometryRevision: 0 },
  { root: empty, geometryRevision: 0 },
]);
assert.deepEqual({ tested: first.tested, culled: first.culled, hits: first.cacheHits, misses: first.cacheMisses },
  { tested: 2, culled: 1, hits: 0, misses: 3 }, "only visible occurrences with finite geometry are tested");
assert.equal(inside.visible, true);
assert.equal(outside.visible, false, "offscreen occurrence is hidden for this render pass");
assert.equal(userHidden.visible, false, "user-hidden state stays hidden");
first.restore();
first.restore();
assert.equal(outside.visible, true, "restore is idempotent and returns temporary culling state");
assert.equal(userHidden.visible, false, "restore never overwrites user-hidden state");

outside.position.x = 0;
const moved = culler.begin(camera, [{ root: outside, geometryRevision: 0 }]);
assert.deepEqual({ culled: moved.culled, hits: moved.cacheHits, misses: moved.cacheMisses },
  { culled: 0, hits: 1, misses: 0 }, "placement changes reuse local bounds while applying the current world transform");
moved.restore();

outside.position.x = 100;
const lateChild = new THREE.Mesh(geometry, material);
lateChild.position.x = -100;
outside.add(lateChild);
const stale = culler.begin(camera, [{ root: outside, geometryRevision: 0 }]);
assert.equal(stale.culled, 1, "late children require an explicit geometry revision or invalidation");
stale.restore();
const refreshed = culler.begin(camera, [{ root: outside, geometryRevision: 1 }]);
assert.equal(refreshed.cacheMisses, 1);
assert.equal(refreshed.culled, 0, "a changed revision includes late model children in conservative occurrence bounds");
refreshed.restore();

culler.invalidate(outside);
const invalidated = culler.begin(camera, [{ root: outside, geometryRevision: 1 }]);
assert.equal(invalidated.cacheMisses, 1, "explicit invalidation rebuilds bounds even at the same revision");
invalidated.restore();

const animated = occurrence(100);
animated.clear();
animated.add(new THREE.SkinnedMesh(geometry, material));
scene.add(animated);
const failOpen = culler.begin(camera, [{ root: animated, geometryRevision: 0 }]);
assert.equal(failOpen.tested, 0);
assert.equal(animated.visible, true, "unsupported animated geometry fails open");
failOpen.restore();

assert.equal(geometryDisposals, 0);
assert.equal(materialDisposals, 0);
assert.equal(inside.children[0].geometry, geometry);
assert.equal(inside.children[0].material, material, "culling retains GPU resources and scene identity");

geometry.dispose();
material.dispose();
assert.equal(geometryDisposals, 1);
assert.equal(materialDisposals, 1);
console.log("Occurrence frustum cache, revision invalidation, scoped visibility restore, and resource retention passed.");
