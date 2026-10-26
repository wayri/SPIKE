// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import * as THREE from "three";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { beginFieldGeometryContext } = await importTestTypescript("fieldGeometryContext");
const root = new THREE.Group(), shared = new THREE.MeshBasicMaterial({ opacity: .8, transparent: false, depthWrite: true });
const geometry = new THREE.BoxGeometry();
root.add(new THREE.Mesh(geometry, shared), new THREE.Mesh(geometry, shared));
const results = new THREE.Group(), thermal = new THREE.MeshBasicMaterial({ opacity: 1 });
results.userData.fieldVolumeOverlay = true;
results.add(new THREE.Mesh(geometry, thermal)); root.add(results);
let disposals = 0; shared.addEventListener("dispose", () => disposals++);
let pass = beginFieldGeometryContext([root], .15);
assert.equal(shared.opacity, .12, "shared material is multiplied exactly once");
assert.equal(shared.transparent, true); assert.equal(shared.depthWrite, false);
assert.equal(thermal.opacity, 1, "result values remain opaque");
pass.restore(); pass.restore();
assert.equal(shared.opacity, .8); assert.equal(shared.transparent, false); assert.equal(shared.depthWrite, true);
shared.opacity = .45; shared.transparent = true; shared.depthWrite = false;
pass = beginFieldGeometryContext([root], 0);
assert.equal(shared.opacity, 0); pass.restore(); assert.equal(shared.opacity, .45, "fresh pass preserves subsequent CAD opacity edits");
try { pass = beginFieldGeometryContext([root], .2); throw new Error("render failure"); } catch {} finally { pass.restore(); }
assert.equal(shared.opacity, .45, "render failure cleanup restores context");
assert.equal(disposals, 0, "temporary review never disposes shared CAD materials");
assert.equal(root.children[0].material, shared, "temporary review never substitutes or leaks material clones");
geometry.dispose(); shared.dispose(); thermal.dispose();
console.log("Field geometry context: shared material deduplication, result exclusion, current state restoration, failure cleanup and no clones passed");
