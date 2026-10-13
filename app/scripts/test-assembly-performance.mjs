// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import * as THREE from "three";
import { boardSceneComplexity, retainAssemblySceneInputs } from "../src/assemblySceneInputs.ts";
import { componentMountIndex, componentReferenceLookup } from "../src/componentSceneIndex.ts";
import { configureImportedMaterial } from "../src/boardSurfaceMaterials.ts";
import { installWebGLRecovery } from "../src/webGLRecovery.ts";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { batchAssemblyImported } = await importTestTypescript("assemblyImportedBatches");

const board = { id: "A", designId: "retained", active: true, name: "Original", widthMm: 80, heightMm: 50,
  thicknessMm: 1.6, localCenterMm: [40, 25, 0], transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], netIdsByName: { GND: "ground" } };
const source = { components: [], pads: [] };
let inputs = retainAssemblySceneInputs([], [board, { ...board, id: "B", active: false }], { retained: source });
const initial = inputs;
for (let step = 0; step < 500; step++) {
  const moved = { ...board, name: `Renamed ${step}`, transform: [...board.transform], netIdsByName: { ...board.netIdsByName } };
  moved.transform[3] = step; moved.transform[7] = step / 2; moved.transform[0] = Math.cos(step / 100);
  inputs = retainAssemblySceneInputs(inputs, [moved, { ...moved, id: "B", active: false }], { retained: source });
  assert.equal(inputs, initial, "translation, rotation, names and fresh equivalent net maps must reuse scene geometry");
}
assert.notEqual(retainAssemblySceneInputs(inputs, [board, { ...board, id: "B", active: false }], { retained: { ...source } }), inputs, "replaced retained geometry invalidates the scene");
assert.notEqual(retainAssemblySceneInputs(inputs, [board, { ...board, id: "B", active: false, netIdsByName: { GND: "other" } }], { retained: source }), inputs, "canonical net changes update picking");
assert.equal(retainAssemblySceneInputs([], [board], { retained: source }).length, 0, "normal board continues to use the primary scene");
assert.notEqual(retainAssemblySceneInputs(inputs, [board], { retained: source }), inputs, "removed occurrences cannot retain ghost scenes");
const populated = { tracks: Array(7000), vias: [], pads: Array(500), zones: [], components: Array(100) };
assert.equal(boardSceneComplexity(populated, []), 7600, "normal board has one feature budget");
assert.equal(boardSceneComplexity(populated, [{ visual: board, source: populated }, { visual: { ...board, id: 'B' }, source: populated }]), 15200,
  "repeated assembly occurrences are counted and the hidden primary board is excluded");
assert.equal(boardSceneComplexity(populated, [{ visual: { ...board, active: false }, source: populated }]), 15200,
  "a secondary board beside the primary still counts both");

let padVisits = 0;
const pads = Array.from({ length: 100_000 }, (_, i) => ({ get ref() { padVisits++; return `U${i >> 2}`; }, drill: i % 17 === 0 ? .3 : 0, type: "smd" }));
const mounts = componentMountIndex(pads);
assert.ok(padVisits <= pads.length * 2, "mount classification does one bounded pass over pads");
assert.equal(mounts.has("U0"), true); assert.equal(mounts.has("U1"), false);
assert.equal(componentMountIndex([{ ref: "J1", drill: 0, pad_kind: "thru_hole" }]).has("J1"), true);
const reference = componentReferenceLookup(["R1", "R10", "U3", "U3-A"]);
assert.equal(reference("R10_body"), "R10"); assert.equal(reference("R100_body"), undefined);
assert.equal(reference("U3-A.body"), "U3-A"); assert.equal(reference("U3"), "U3");
assert.equal(reference("U3-A.body"), "U3-A", "cached names preserve exact longest reference");

const raw = new THREE.MeshStandardMaterial({ name: "PCB substrate", opacity: .5, transparent: true, depthWrite: false });
const a = raw.clone(), b = raw.clone();
for (const material of [a, b]) {
  assert.equal(configureImportedMaterial(material, "board", "mesh"), "substrate");
  assert.equal(material.opacity, 1); assert.equal(material.transparent, false);
  assert.equal(material.depthWrite, true, "laminate must occlude inner copper in every occurrence");
}
a.opacity = .2; assert.equal(b.opacity, 1, "occurrence material controls remain isolated");
assert.equal(raw.opacity, .5, "cached source materials remain untouched");
const mask = new THREE.MeshStandardMaterial({ name: "soldermask" });
assert.equal(configureImportedMaterial(mask, "board", "mesh"), "soldermask");
assert.equal(mask.depthWrite, false); assert.equal(mask.transparent, true);
const silk = new THREE.MeshStandardMaterial({ name: "viewport", opacity: .5, transparent: true });
silk.userData.spikeSourceMaterialName = "silkscreen";
assert.equal(configureImportedMaterial(silk, "board", "mesh"), "silkscreen", "main-board renamed materials retain source semantics");

const canvas = new EventTarget(); let lost = 0, restored = 0;
const recovery = installWebGLRecovery(canvas, { lost: () => lost++, restored: () => restored++ });
canvas.dispatchEvent(new Event("webglcontextrestored")); assert.equal(restored, 0);
const event = new Event("webglcontextlost", { cancelable: true }); canvas.dispatchEvent(event);
assert.equal(event.defaultPrevented, true, "context restoration must be permitted");
canvas.dispatchEvent(new Event("webglcontextlost")); assert.equal(lost, 1); assert.equal(recovery.lost, true);
canvas.dispatchEvent(new Event("webglcontextrestored")); assert.equal(restored, 1); assert.equal(recovery.lost, false);
recovery.dispose(); canvas.dispatchEvent(new Event("webglcontextlost")); assert.equal(lost, 1, "unmounted viewports remove recovery listeners");
const frame = new THREE.Group(), models = new THREE.Group(), geometry = new THREE.SphereGeometry(.0005, 16, 8);
frame.matrix.set(1000, 0, 0, -40, 0, 0, 1000, -25, 0, 1000, 0, 0, 0, 0, 0, 1); frame.matrixAutoUpdate = false; frame.add(models);
const componentMaterial = new THREE.MeshStandardMaterial({ color: 0x454545, side: THREE.DoubleSide });
for (let i = 0; i < 5000; i++) {
  const mesh = new THREE.Mesh(geometry, componentMaterial); mesh.position.set(i % 100 * .002, .003, Math.floor(i / 100) * .002);
  mesh.userData = { componentRef: `U${i}`, sceneKind: "component-model", componentMount: "smd" }; models.add(mesh);
}
const expectedBounds = new THREE.Box3().setFromObject(frame), original = [...models.children];
const stats = batchAssemblyImported(frame);
assert.deepEqual(stats, { before: 5000, after: 3 }, "repeated parts use bounded shared instance buffers");
assert.equal(original.every(mesh => mesh.material.visible === false && mesh.userData.pickingProxy), true);
assert.equal(new Set(frame.children.filter(mesh => mesh.isInstancedMesh).map(mesh => mesh.geometry)).size, 1, "cached geometry stays shared");
frame.updateMatrixWorld(true);
const visibleBounds = new THREE.Box3();
for (const mesh of frame.children.filter(mesh => mesh.isInstancedMesh)) visibleBounds.union(new THREE.Box3().setFromObject(mesh));
assert.ok(expectedBounds.min.distanceTo(visibleBounds.min) < 1e-4 && expectedBounds.max.distanceTo(visibleBounds.max) < 1e-4, "KiCad axis basis and all component placements survive batching");
const center = new THREE.Vector3().setFromMatrixPosition(original[110].matrixWorld);
const picking = new THREE.Raycaster(center.clone().add(new THREE.Vector3(0, 0, 10)), new THREE.Vector3(0, 0, -1)); picking.layers.enable(31);
const hit = picking.intersectObjects(original, false)[0];
assert.equal(hit.object.userData.componentRef, "U110", "nonrendering source meshes retain exact component picking");
assert.equal(original.every(mesh => !mesh.layers.test(new THREE.Camera().layers)), true, "pick proxies never upload buffers through the render camera");
const transparentFrame = new THREE.Group(), translucent = new THREE.MeshStandardMaterial({ transparent: true, opacity: .5 });
for (let i = 0; i < 8; i++) transparentFrame.add(new THREE.Mesh(geometry, translucent));
assert.deepEqual(batchAssemblyImported(transparentFrame), { before: 8, after: 8 }, "transparent surfaces retain independent sorting");
console.log(`Assembly performance and recovery passed: 500 placements retain scene inputs; ${pads.length} pads use ${padVisits} ref reads; opaque PCB depth and occurrence isolation verified`);
console.log(`Imported assembly batches: ${stats.before} -> ${stats.after}; all source picks and transformed bounds verified`);
