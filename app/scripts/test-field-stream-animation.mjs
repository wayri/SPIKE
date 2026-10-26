// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import * as THREE from "three";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { FIELD_STREAM_MARKER_LIMIT, attachFieldStreamAnimation, sampleFieldStreamMarkers, updateFieldStreamAnimation } =
  await importTestTypescript("fieldStreamAnimation");
const { buildFieldVolumeScene } = await importTestTypescript("fieldVolumeScene");

const elbow = [[[0, 0, 0], [1, 0, 0], [1, 3, 0]]];
assert.deepEqual(Array.from(sampleFieldStreamMarkers(elbow, 0, { speed: 1, markerCount: 2 })), [1, 0, 0, 1, 2, 0],
  "markers use polyline arc length rather than vertex index spacing");
assert.deepEqual(Array.from(sampleFieldStreamMarkers(elbow, .25, { speed: 1, markerCount: 2 })), [1, 1, 0, 0, 0, 0],
  "elapsed presentation time advances and wraps markers along the same geometry");
assert.equal(sampleFieldStreamMarkers([[[0, 0, 0], [0, 0, 0]], [[0, 0, 0], [Infinity, 0, 0]]], 0).length, 0,
  "degenerate and nonfinite paths do not create markers");
assert.equal(sampleFieldStreamMarkers(Array.from({ length: 300 }, (_, n) => [[0, n, 0], [1, n, 0]]), 0).length / 3,
  FIELD_STREAM_MARKER_LIMIT, "the GPU marker buffer has a fixed upper bound");

const root = new THREE.Group();
const controller = attachFieldStreamAnimation(root, elbow, "supplied-point-order", { markerCount: 2 });
assert.ok(controller); assert.equal(root.children.length, 1); assert.equal(controller.points.visible, false);
assert.equal(controller.pathCount, 1); assert.equal(controller.markerCount, 2);
assert.equal(controller.sourceCurveDirection, "supplied-point-order");
const initial = Array.from(controller.points.geometry.attributes.position.array);
assert.equal(updateFieldStreamAnimation(root, .1, false), false); assert.equal(controller.points.visible, false);
assert.deepEqual(Array.from(controller.points.geometry.attributes.position.array), initial, "paused markers do not advance");
assert.equal(updateFieldStreamAnimation(root, .1, true), true); assert.equal(controller.points.visible, true);
assert.notDeepEqual(Array.from(controller.points.geometry.attributes.position.array), initial);
assert.equal(updateFieldStreamAnimation(root, Number.NaN, true), false, "nonfinite deltas are ignored");
let geometryDisposals = 0, materialDisposals = 0;
controller.points.geometry.addEventListener("dispose", () => geometryDisposals++);
controller.points.material.addEventListener("dispose", () => materialDisposals++);
controller.dispose(); controller.dispose();
assert.equal(root.children.length, 0); assert.equal(root.userData.fieldStreamAnimation, undefined);
assert.equal(geometryDisposals, 1); assert.equal(materialDisposals, 1, "explicit animation disposal is idempotent");

const options = { frame: 0, quantity: "temperature_k", mode: "streamlines", arrows: false, opacity: .7,
  budget: 100, sliceAxis: "all", slicePercent: 100, celsius: true };
const flow = { contract: "spike/field-volume-view/v1", id: "flow", label: "Flow", lengthUnit: "mm",
  cells: { centers: [[0, 0, 0], [1, 0, 0]] }, quantities: [{ id: "temperature_k", label: "Temperature", unit: "K" },
    { id: "speed_m_s", label: "Speed", unit: "m/s" }], frames: [{ timeS: 0,
      scalars: { temperature_k: [300, 301], speed_m_s: [1, 1] }, vectors: [[1, 0, 0], [1, 0, 0]],
      streamlines: [{ points: [[0, 0, 0], [1, 0, 0]], scalars: { temperature_k: [300, 301], speed_m_s: [1, 1] } }] }] };
const flowScene = buildFieldVolumeScene(flow, options);
assert.equal(flowScene.userData.flowAnimationAvailable, true);
assert.equal(flowScene.userData.flowAnimationPathCount, 1); assert.equal(flowScene.userData.flowAnimationMarkerCount, 2);
assert.equal(flowScene.userData.sourceCurveDirection, "supplied-point-order");
assert.equal(flowScene.userData.fieldStreamAnimation.points.visible, false, "motion waits for the explicit play control");
assert.match(flowScene.userData.flowAnimationNote, /not solver time or a transient particle path/);

const em = { ...flow, id: "em", quantities: [{ id: "relative_field", label: "Relative field", unit: "relative" }],
  frames: [{ timeS: 0, scalars: { relative_field: [0, 1] },
    streamlines: [{ points: [[0, 0, 0], [1, 0, 0]], scalars: { relative_field: [0, 1] } }] }] };
const emScene = buildFieldVolumeScene(em, { ...options, quantity: "relative_field", celsius: false });
assert.equal(emScene.userData.flowAnimationAvailable, false); assert.equal(emScene.userData.fieldStreamAnimation, undefined);
assert.equal(emScene.children.filter(object => object.name === "field-flow-motion-markers").length, 0,
  "supplied EM curves remain static because they have no admitted velocity field");

const gridCenters = []; for (const x of [0, 1]) for (const y of [0, 1]) for (const z of [0, 1]) gridCenters.push([x, y, z]);
const generated = { ...flow, id: "generated", cells: { centers: gridCenters, flowDomain: "complete-cartesian-fluid" },
  quantities: [{ id: "speed_m_s", label: "Speed", unit: "m/s" }], frames: [{ timeS: 0,
    scalars: { speed_m_s: gridCenters.map(() => 1) }, vectors: gridCenters.map(() => [1, 0, 0]) }] };
const generatedScene = buildFieldVolumeScene(generated, { ...options, mode: "streamtubes", quantity: "speed_m_s", celsius: false, seedDensity: 2 });
assert.equal(generatedScene.userData.flowAnimationAvailable, true);
assert.equal(generatedScene.userData.sourceCurveDirection, "generated-velocity-trace-order");
const generatedPositions = generatedScene.userData.fieldStreamAnimation.points.geometry.attributes.position.array;
assert.ok(Array.from(generatedPositions).every(Number.isFinite));
for (let index = 0; index < generatedPositions.length; index += 3) {
  assert.ok(generatedPositions[index] >= 0 && generatedPositions[index] <= 1);
  assert.ok(generatedPositions[index + 1] >= -1 && generatedPositions[index + 1] <= 0, "BoardViewport Y inversion stays bounded");
  assert.ok(generatedPositions[index + 2] >= 0 && generatedPositions[index + 2] <= 1);
}

console.log("Field stream motion: arc-length sampling, pause/play, bounded buffers, disposal and supplied/generated velocity admission passed");
