import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { cachedResultFaceTriangleIndices, resultFaceTriangleIndices } from "../src/resultGeometryMask.ts";

const fixtures = {
  concave: [[0, 0, 0], [4, 0, 0], [4, 4, 0], [2, 2, 0], [0, 4, 0]],
  vertical: [[0, 0, 0], [2, 0, 0], [2, 0, 1], [0, 0, 1]],
  crossed: [[0, 0, 0], [4, 4, 0], [0, 4, 0], [4, 0, 0]],
  repeated: [[0, 0, 0], [2, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]],
};

for (const [name, vertices] of Object.entries(fixtures)) {
  const expected = resultFaceTriangleIndices(vertices);
  const first = cachedResultFaceTriangleIndices(vertices);
  const second = cachedResultFaceTriangleIndices(vertices);
  assert.deepEqual(first, expected, `${name}: cold mapping changed`);
  assert.deepEqual(second, expected, `${name}: warm mapping changed`);
  assert.equal(second, first, `${name}: unchanged topology was not reused`);
  for (let index = 0; index < expected.length; index += 1) {
    assert.equal(second[index], expected[index], `${name}: triangle index ${index} changed`);
  }
}

const mutable = fixtures.concave.map(vertex => [...vertex]);
const beforeMutation = cachedResultFaceTriangleIndices(mutable);
const beforeMutationReference = [...beforeMutation];
assert.throws(() => { beforeMutation[0] = 99; }, TypeError, "cached index assignment must be rejected");
assert.throws(() => { delete beforeMutation[0]; }, TypeError, "cached index deletion must be rejected");
assert.deepEqual(cachedResultFaceTriangleIndices(mutable), beforeMutationReference,
  "attempted index mutation poisoned the cached mapping");
mutable[3][0] = 3;
const expectedAfterMutation = resultFaceTriangleIndices(mutable);
const afterMutation = cachedResultFaceTriangleIndices(mutable);
assert.deepEqual(afterMutation, expectedAfterMutation, "in-place coordinate change returned stale triangles");
assert.notEqual(afterMutation, beforeMutation, "in-place coordinate change did not invalidate cache entry");

mutable[3] = [2.5, 1.5, 0];
const expectedAfterReplacement = resultFaceTriangleIndices(mutable);
const afterReplacement = cachedResultFaceTriangleIndices(mutable);
assert.deepEqual(afterReplacement, expectedAfterReplacement, "vertex replacement returned stale triangles");
assert.notEqual(afterReplacement, afterMutation, "vertex replacement did not invalidate cache entry");

mutable.push([0, 2, 0]);
const expectedAfterAppend = resultFaceTriangleIndices(mutable);
const afterAppend = cachedResultFaceTriangleIndices(mutable);
assert.deepEqual(afterAppend, expectedAfterAppend, "vertex-count change returned stale triangles");
assert.notEqual(afterAppend, afterReplacement, "vertex-count change did not invalidate cache entry");

const faceCount = 2_000;
const passes = 16;
const faces = Array.from({ length: faceCount }, (_, index) => {
  const x = index % 100;
  const y = Math.floor(index / 100);
  return [[x, y, 0], [x + 4, y, 0], [x + 4, y + 4, 0], [x + 3, y + 2, 0],
    [x + 2, y + 3, 0], [x + 1, y + 2, 0], [x, y + 4, 0]];
});

function measure(triangulate) {
  let checksum = 0;
  const started = performance.now();
  for (let pass = 0; pass < passes; pass += 1) {
    for (const face of faces) {
      const triangles = triangulate(face);
      checksum += triangles.length;
      for (const triangleIndex of triangles) checksum += triangleIndex;
    }
  }
  return { milliseconds: performance.now() - started, checksum };
}

// Populate the topology cache as the first displayed saved frame would.
for (const face of faces) cachedResultFaceTriangleIndices(face);
const baseline = measure(resultFaceTriangleIndices);
const warm = measure(cachedResultFaceTriangleIndices);
assert.equal(warm.checksum, baseline.checksum, "cached playback changed the complete triangle-index checksum");

const report = {
  node: process.version,
  faceCount,
  passes,
  calls: faceCount * passes,
  baselineMilliseconds: baseline.milliseconds,
  warmMilliseconds: warm.milliseconds,
  speedup: baseline.milliseconds / warm.milliseconds,
  checksum: baseline.checksum,
};
const output = process.argv[2];
if (output) {
  const path = resolve(output);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(report, null, 2)}\n`);
}
console.log(`result face topology cache: all assertions passed; ${JSON.stringify(report)}`);
