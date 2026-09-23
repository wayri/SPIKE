import assert from "node:assert/strict";
import { meshCellEdgeIndexes, meshCellFaceVertices } from "../src/meshTopology.ts";

const surface = {
  id: "surface-polygon8",
  kind: "surface",
  topology: "polygon8",
  vertices_mm: Array.from({ length: 8 }, (_, index) => [index, index % 2, 0]),
};
assert.equal(meshCellEdgeIndexes(surface).length, 8);
assert.deepEqual(meshCellEdgeIndexes(surface).at(-1), [7, 0]);
assert.equal(meshCellFaceVertices(surface).length, 8);

const volume = {
  ...surface,
  id: "volume-hex8",
  kind: "volume",
  topology: "hex8",
};
assert.equal(meshCellEdgeIndexes(volume).length, 12);
assert.equal(meshCellFaceVertices(volume).length, 4);

const prism = {
  ...surface,
  id: "volume-prism10",
  kind: "volume",
  topology: "prism5",
  vertices_mm: Array.from({ length: 10 }, (_, index) => [index, index % 2, index < 5 ? 0 : 1]),
};
assert.equal(meshCellEdgeIndexes(prism).length, 15);
assert.equal(meshCellFaceVertices(prism).length, 5);

console.log("mesh topology: all assertions passed");
