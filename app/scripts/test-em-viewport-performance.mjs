// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import { buildEMViewportScene } from "../src/emViewportScene.ts";
import { disposeScene } from "../src/sceneResourceCache.ts";

const width = 180;
const positionsMm = Array.from({ length: width*width }, (_, index) =>
  [index%width, Math.floor(index/width), 0]);
const values = positionsMm.map(([x, y]) => Math.sin(x/12)+Math.cos(y/17));
const indices = [];
for (let y = 0; y < width-1; y++) for (let x = 0; x < width-1; x++) {
  const a = y*width+x;
  indices.push(a,a+width,a+1,a+1,a+width,a+width+1);
}
const data = { domain: "spatial", frequencyHz: 1e9, label: "Dense field", unit: "V/m",
  positionsMm, indices, values, directions: Array(values.length).fill(null),
  highlights: Array(values.length).fill(null), range: [-2,2], notices: [] };
const settings = { visible: true, style: "surface", opacity: .7, nodes: false, antinodes: false,
  showStructure: false, selectedSample: -1 };
const transform = { centerX: 0, centerY: 0, scale: 1 };

const surfaceStarted = performance.now();
const surfaceScene = buildEMViewportScene(data, settings, transform);
const surfaceMs = performance.now()-surfaceStarted;
const surface = surfaceScene.getObjectByName("EM scalar surface");
assert.equal(surface.geometry.index.count, indices.length, "dense surface retains every admitted triangle index");
assert.deepEqual(Array.from(surface.geometry.index.array), indices, "dense surface retains the exact triangle index stream");
assert.deepEqual(surface.userData.emSampleIndices, Array.from({length: values.length}, (_, index) => index),
  "dense surface preserves exact probe identity");
const densePositions = surface.geometry.attributes.position;
for (const index of [0, width-1, width, values.length-1]) assert.deepEqual(
  [densePositions.getX(index), densePositions.getY(index), densePositions.getZ(index)],
  [positionsMm[index][0], positionsMm[index][1] ? -positionsMm[index][1] : 0, positionsMm[index][2]],
  `dense surface coordinate ${index} keeps the supplied sample location and display transform`);
assert.ok(surfaceMs < 1000, `32k-sample dense surface built in ${surfaceMs.toFixed(1)} ms`);

const contourStarted = performance.now();
const contourScene = buildEMViewportScene(data, { ...settings, style: "contours" }, transform);
const contourMs = performance.now()-contourStarted;
const contours = contourScene.getObjectByName("EM display contours");
assert.ok(contours.geometry.attributes.position.count > 0, "dense contours retain interpolated display segments");
assert.equal(contours.geometry.attributes.position.count, contours.userData.emSampleIndices.length,
  "every contour vertex keeps its nearest solved-sample mapping");
assert.ok(contourMs < 3000, `32k-sample dense contours built in ${contourMs.toFixed(1)} ms`);

const maskedData = { ...data, positionsMm: [[0,0,0],[2,0,0],[0,2,0],[2,2,0]],
  values: [-1,0,1,null], indices: [0,1,2,1,3,2,0,0,2,0,2,9],
  directions: [null,null,null,null], highlights: [null,null,null,null] };
const maskedScene = buildEMViewportScene(maskedData, settings, { centerX: 1, centerY: 1, scale: 2, zOffsetMm: .5 });
const maskedSurface = maskedScene.getObjectByName("EM scalar surface");
assert.deepEqual(Array.from(maskedSurface.geometry.index.array), [0,1,2],
  "null samples, duplicate vertices and out-of-range indices cannot admit a cell");
assert.deepEqual(maskedSurface.userData.emSampleIndices, [0,1,2,3],
  "the position-to-source mapping remains exact even when cells are masked");
assert.deepEqual(Array.from(maskedSurface.geometry.attributes.position.array.slice(0,9)),
  [-2,2,1,2,2,1,-2,-2,1], "admitted sample coordinates retain the exact board transform");

disposeScene(surfaceScene); disposeScene(contourScene); disposeScene(maskedScene);
console.log(`EM viewport performance: samples=${values.length}; triangles=${indices.length/3}; surface=${surfaceMs.toFixed(1)}ms; contours=${contourMs.toFixed(1)}ms`);
