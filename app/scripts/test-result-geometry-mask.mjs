import assert from "node:assert/strict";
import { pointOnResultConductor, resultConductorIndexStats, resultDatumFitsConductor, resultFaceTriangleIndices } from "../src/resultGeometryMask.ts";

const board = {
  width: 30,
  height: 20,
  bounds: { minX: 0, minY: 0, maxX: 30, maxY: 20 },
  outlineLoops: [],
  tracks: [{ id: "track", start: [1, 2], end: [10, 2], width: 1, layer: "F.Cu", net: "VCC" }],
  vias: [{ id: "via", at: [10, 2], size: 1.2, drill: 0.5, layers: ["F.Cu", "B.Cu"], net: "VCC" }],
  pads: [{ id: "pad", name: "1", at: [1, 2], width: 2, height: 2, rotation: 0, shape: "circle", drill: 0, layers: ["F.Cu"], layer: "F.Cu", net: "VCC" }],
  zones: [{ id: "zone", points: [[12, 1], [20, 1], [20, 8], [12, 8]], layer: "F.Cu", net: "VCC" }],
  components: [], drawings: [], layers: ["F.Cu", "In1.Cu", "B.Cu"], layerDefinitions: [], stackup: [], nets: {},
};

assert.equal(pointOnResultConductor(board, [5, 2], "VCC", "F.Cu"), true);
assert.equal(pointOnResultConductor(board, [5, 4], "VCC", "F.Cu"), false);
assert.equal(pointOnResultConductor(board, [10, 2], "VCC", "In1.Cu"), true);
assert.equal(resultDatumFitsConductor(board, { x_mm: 5, y_mm: 2, net: "VCC", layer: "F.Cu", vertices_mm: [[4, 1.55, 0], [6, 1.55, 0], [6, 2.45, 0], [4, 2.45, 0]] }), true);
assert.equal(resultDatumFitsConductor(board, { x_mm: 10, y_mm: 2, net: "VCC", layer: "F.Cu", vertices_mm: [[5, 2, 0], [15, 2, 0], [15, 3, 0], [5, 3, 0]] }), false);

const concave = [[0, 0, 0], [4, 0, 0], [4, 4, 0], [2, 2, 0], [0, 4, 0]];
assert.equal(resultFaceTriangleIndices(concave).length, 9);
const vertical = [[0, 0, 0], [2, 0, 0], [2, 0, 1], [0, 0, 1]];
assert.equal(resultFaceTriangleIndices(vertical).length, 6);
const crossed = [[0, 0, 0], [4, 4, 0], [0, 4, 0], [4, 0, 0]];
assert.deepEqual(resultFaceTriangleIndices(crossed), []);

const largeBoard = {
  ...board,
  width: 500,
  height: 100,
  bounds: { minX: 0, minY: 0, maxX: 500, maxY: 100 },
  tracks: Array.from({ length: 5000 }, (_, index) => ({
    id: `track-${index}`,
    start: [index * 0.1, 10 + index % 20],
    end: [index * 0.1 + 0.08, 10 + index % 20],
    width: 0.05,
    layer: index % 2 ? "B.Cu" : "F.Cu",
    net: `N${index % 100}`,
  })),
  zones: [], pads: [], vias: [],
};
assert.equal(pointOnResultConductor(largeBoard, [10.04, 10], "N0", "F.Cu"), true);
assert.equal(pointOnResultConductor(largeBoard, [10.04, 10], "N1", "F.Cu"), false);
const stats = resultConductorIndexStats(largeBoard);
assert.equal(stats.featureCount, 5000);
assert.ok(stats.bucketCount > 100);
assert.ok(stats.maximumBucketSize < 50, `spatial bucket unexpectedly contains ${stats.maximumBucketSize} features`);

console.log("result geometry mask: all assertions passed");
