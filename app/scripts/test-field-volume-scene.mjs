// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import * as THREE from "three";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { buildFieldVolumeScene } = await importTestTypescript("fieldVolumeScene");
const { disposeScene } = await importTestTypescript("sceneResourceCache");

const base = { contract: "spike/field-volume-view/v1", id: "scene", label: "Scene", lengthUnit: "m",
  cells: { centers: [[.001, .002, .003]], sizes: [[.002, .004, .006]] }, quantities: [{ id: "q", label: "Q", unit: "Pa" }],
  frames: [{ timeS: 0, scalars: { q: [4] }, vectors: [[1, 0, 0]] }] };
const options = { frame: 0, quantity: "q", mode: "voxels", arrows: true, opacity: .7, budget: 20, sliceAxis: "all", slicePercent: 100, celsius: false };
const before = structuredClone(base), scene = buildFieldVolumeScene(base, options, { centerX: 1, centerY: 2, scale: 2 });
assert.deepEqual(base, before, "scene creation must preserve caller arrays");
assert.equal(scene.userData.sourceLengthUnit, "m"); assert.deepEqual(scene.userData.scalarRange, [4, 4]);
assert.equal(scene.userData.scalarLabel, "Q"); assert.equal(scene.userData.scalarUnit, "Pa"); assert.equal(scene.userData.error, "");
const mesh = scene.children.find(object => object instanceof THREE.Mesh);
mesh.geometry.computeBoundingBox();
assert.deepEqual(mesh.geometry.boundingBox.min.toArray(), [-2, -4, 0], "metres become transformed millimetres with one Y inversion");
assert.deepEqual(mesh.geometry.boundingBox.max.toArray(), [2, 4, 12]);
const arrows = scene.children.filter(object => object instanceof THREE.Line);
assert.ok(arrows.length >= 1, "velocity arrows share the scene");
const rangedScene = buildFieldVolumeScene(base, { ...options, arrows: false, colorRange: [4, 8], sampleIndex: 0 });
assert.deepEqual(rangedScene.userData.scalarRange, [4, 8], "Three legend follows manual range");
const rangedColors = rangedScene.children.find(object => object instanceof THREE.Mesh).geometry.attributes.color;
assert.ok(Math.abs(rangedColors.getX(0) - .12) < 1e-6 && Math.abs(rangedColors.getZ(0) - .92) < 1e-6, "Manual endpoint actually changes GPU vertex colors");
const sampleMarker = rangedScene.children.find(object => object instanceof THREE.Points);
assert.ok(sampleMarker, "Exact sample inspection creates an actual renderer marker");
assert.deepEqual(Array.from(sampleMarker.geometry.attributes.position.array), [1, -2, 3]);
disposeScene(rangedScene);
const sizedPoints = buildFieldVolumeScene(base, { ...options, mode: "points", arrows: false, pointSize: 12 });
assert.equal(sizedPoints.children.find(object => object instanceof THREE.Points).material.size, 12, "Sample size reaches the actual Three material");
disposeScene(sizedPoints);

const curves = { ...base, lengthUnit: "mm", cells: { centers: [[0, 0, 0]] }, frames: [{ timeS: 0, scalars: { q: [0] }, streamlines: [
  { points: [[1, 2, 3], [2, 3, 4]], scalars: { q: [0, 1] } }, { points: [[10, 20, 30], [11, 21, 31]], scalars: { q: [1, 2] } }] }] };
const lineScene = buildFieldVolumeScene(curves, { ...options, mode: "streamlines", arrows: false });
assert.equal(lineScene.children.length, 2, "separate source curves remain distinct Three lines");
assert.deepEqual(Array.from(lineScene.children[0].geometry.attributes.position.array.slice(0, 3)), [1, -2, 3]);
const suppliedTubeScene = buildFieldVolumeScene(curves, { ...options, mode: "streamtubes", arrows: false });
const rangedLines = buildFieldVolumeScene(curves, { ...options, mode: "streamlines", arrows: false, colorRange: [0, 4] });
assert.deepEqual(rangedLines.userData.scalarRange, [0, 4]);
const lineColors = rangedLines.children[0].geometry.attributes.color;
assert.ok(lineColors.getZ(1) > .5, "Supplied line colors use the requested common scale");
disposeScene(rangedLines);
const suppliedTubeColors = suppliedTubeScene.children.find(object => object instanceof THREE.Mesh).geometry.attributes.color;
const tubeColors = Array.from({ length: suppliedTubeColors.count }, (_, index) =>
  [suppliedTubeColors.getX(index), suppliedTubeColors.getY(index), suppliedTubeColors.getZ(index)]);
assert.ok(tubeColors.some(color => Math.abs(color[0] - .12) < 1e-6 && Math.abs(color[1] - .35) < 1e-6 && Math.abs(color[2] - .92) < 1e-6),
  "minimum supplied tube scalar uses the legend's blue endpoint");
assert.ok(tubeColors.some(color => Math.abs(color[0] - .94) < 1e-6 && Math.abs(color[1] - .2) < 1e-6 && Math.abs(color[2] - .16) < 1e-6),
  "maximum supplied tube scalar uses the legend's red endpoint");
const gridCenters = []; for (const x of [0, 1]) for (const y of [0, 1]) for (const z of [0, 1]) gridCenters.push([x, y, z]);
const generatedSource = { ...base, lengthUnit: "mm", cells: { centers: gridCenters, flowDomain: "complete-cartesian-fluid" },
  geometryNote: "Retained source solid", geometry: { solids: [] },
  frames: [{ timeS: 0, scalars: { q: gridCenters.map((_, index) => index) }, vectors: gridCenters.map(() => [1, 0, 0]) },
    { timeS: 1, scalars: { q: gridCenters.map((_, index) => index + 1) }, vectors: gridCenters.map(() => [3, 0, 0]) }] };
const generatedBefore = structuredClone(generatedSource);
const tubeScene = buildFieldVolumeScene(generatedSource, { ...options, mode: "streamtubes", arrows: false, budget: 200, seedDensity: 2 });
assert.ok(tubeScene.children.some(object => object instanceof THREE.Mesh), "declared complete grids trace into Three tube meshes");
assert.deepEqual(generatedSource, generatedBefore, "generated rendering uses a synthetic envelope without source mutation");
const tube = tubeScene.children.find(object => object instanceof THREE.Mesh);
assert.equal(tube.geometry.attributes.color.count, tube.geometry.attributes.position.count, "tube speed is retained as per-vertex color");
assert.equal(tubeScene.userData.scalarLabel, "Speed"); assert.equal(tubeScene.userData.scalarUnit, "m/s");
assert.deepEqual(tubeScene.userData.scalarRange, [1, 3], "generated speed scale is fixed over saved vector history");
assert.match(tubeScene.userData.streamNote, /center seed plane/);
const varyingDirection = { ...generatedSource, frames: [1, 2].map((factor, frame) => ({ timeS: frame,
  scalars: { q: gridCenters.map(() => 0) }, vectors: gridCenters.map(point => [factor, point[1] === 0 ? -factor : factor, 0]) })) };
const varyingScenes = [0, 1].map(frame => buildFieldVolumeScene(varyingDirection, { ...options, frame, mode: "streamtubes", arrows: false, seedDensity: 4, budget: 1000 }));
for (const rendered of varyingScenes) {
  assert.ok(rendered.children.length > 0, "The nonuniform field must actually trace curves");
  assert.deepEqual(rendered.userData.scalarRange, [Math.SQRT2, 2 * Math.SQRT2], "Interpolated path speeds must not rescale the saved-vector legend");
  disposeScene(rendered);
}
const unsupported = buildFieldVolumeScene({ ...base, cells: { centers: [[0, 0, 0]] }, frames: [{ timeS: 0, scalars: { q: [1] } }] },
  { ...options, mode: "streamtubes", arrows: false });
assert.equal(unsupported.children.length, 0); assert.equal(unsupported.userData.error, "");
assert.match(unsupported.userData.streamNote, /No renderer-generated curves/);
assert.equal(unsupported.userData.scalarLabel, "Speed"); assert.equal(unsupported.userData.scalarUnit, "m/s");
const unrepresentable = buildFieldVolumeScene({ ...base, cells: { centers: [[1e100, 0, 0]] }, frames: [{ timeS: 0, scalars: { q: [1] } }] }, { ...options, mode: "points", arrows: false });
assert.equal(unrepresentable.children.length, 0); assert.match(unrepresentable.userData.fieldVolumeError, /float32/);

let geometries = 0, materials = 0;
for (const root of [scene, lineScene, suppliedTubeScene, tubeScene]) root.traverse(object => {
  object.geometry?.addEventListener("dispose", () => geometries++);
  const owned = object.material ? (Array.isArray(object.material) ? object.material : [object.material]) : [];
  owned.forEach(material => material.addEventListener("dispose", () => materials++));
});
const owned = scene.children.length + lineScene.children.length + suppliedTubeScene.children.length + tubeScene.children.length;
disposeScene(scene); disposeScene(lineScene); disposeScene(suppliedTubeScene); disposeScene(tubeScene);
assert.equal(geometries, owned); assert.equal(materials, owned);
assert.equal(scene.children.length + lineScene.children.length + suppliedTubeScene.children.length + tubeScene.children.length, 0);
console.log("Field volume Three scene: SI/mm bounds, Y inversion, curve isolation, immutable input and disposal passed");
