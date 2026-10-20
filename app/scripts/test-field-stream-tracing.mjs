// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { traceFieldGrid, FIELD_STREAM_SEGMENT_LIMIT } = await importTestTypescript("fieldStreamTracing");
const options = { frame: 0, quantity: "q", mode: "streamlines", arrows: false, opacity: 1,
  budget: 16000, sliceAxis: "all", slicePercent: 100, celsius: false, seedAxis: "z", seedDensity: 2 };
function fixture(n, field, scale = 1) {
  const centers = [], vectors = [];
  for (let x = 0; x <= n; x++) for (let y = 0; y <= n; y++) for (let z = 0; z <= n; z++) {
    const p = [x / n * 2 - 1, y / n * 2 - 1, z / n * 2 - 1];
    centers.push(p.map(v => v * scale)); vectors.push(field(p));
  }
  return { contract: "spike/field-volume-view/v1", id: "test", label: "Analytical fixture", lengthUnit: "m",
    cells: { centers, flowDomain: "complete-cartesian-fluid" }, quantities: [{ id: "q", label: "q", unit: "1" }],
    frames: [{ timeS: 0, scalars: { q: centers.map(() => 0) }, vectors }] };
}
const constant = fixture(4, () => [2, 0, 0]);
const before = JSON.stringify(constant);
const lines = traceFieldGrid(constant, options);
assert.equal(lines.length, 4);
for (const line of lines) {
  assert.ok(line.points.at(-1)[0] - line.points[0][0] > 1.7, "Traverse the domain");
  line.points.forEach((p, i) => {
    assert.ok(Math.abs(p[1] - line.points[0][1]) < 1e-13);
    assert.ok(Math.abs(p[2]) < 1e-13);
    assert.ok(p.every(v => v >= -1 && v <= 1), "Do not extrapolate beyond center bounds");
    assert.ok(Math.abs(line.scalars.speed_m_s[i] - 2) < 1e-13);
  });
}
assert.equal(JSON.stringify(constant), before);
assert.deepEqual(traceFieldGrid(constant, options), lines, "Deterministic");
const reordered = structuredClone(constant);
reordered.cells.centers.reverse(); reordered.frames[0].vectors.reverse();
assert.deepEqual(traceFieldGrid(reordered, options), lines, "Grid storage order is irrelevant");
const nonuniform = structuredClone(constant);
nonuniform.cells.centers.forEach(p => { p[0] = p[0] < 0 ? p[0] / 2 : p[0]; });
assert.equal(traceFieldGrid(nonuniform, options).length, 4, "Nonuniform Cartesian axes are supported");
assert.deepEqual(traceFieldGrid(fixture(4, () => [0, 0, 0]), options), []);
const negative = fixture(4, () => [-2, 0, 0]);
assert.ok(traceFieldGrid(negative, options)[0].points[0][0] > traceFieldGrid(negative, options)[0].points.at(-1)[0]);
const transient = structuredClone(constant);
transient.frames.push({ ...transient.frames[0], timeS: 1, vectors: negative.frames[0].vectors });
assert.deepEqual(traceFieldGrid(transient, { ...options, frame: 1 }), traceFieldGrid(negative, options));
const mm = fixture(4, () => [2, 0, 0], 1000); mm.lengthUnit = "mm";
traceFieldGrid(mm, options).forEach((line, j) => line.points.forEach((p, i) =>
  p.forEach((v, d) => assert.ok(Math.abs(v / 1000 - lines[j].points[i][d]) < 1e-12))));
// Rotating linear field interpolates exactly. Exact curve has r=sqrt(1/2).
// Compare the first fixed arc length (0.5), avoiding step count/length changes.
function rotationError(n) {
  const paths = traceFieldGrid(fixture(n, ([x, y]) => [-y, x, 0]), options);
  let error = 0;
  for (const line of paths) {
    const seed = line.points.findIndex(p => Math.abs(p[0] + .5) < 1e-14 && Math.abs(p[1] + .5) < 1e-14);
    if (seed < 0) continue;
    const k = n, p = line.points[seed + k], angle = .5 / Math.sqrt(.5);
    const exact = [-.5 * Math.cos(angle) + .5 * Math.sin(angle), -.5 * Math.sin(angle) - .5 * Math.cos(angle)];
    error = Math.hypot(p[0] - exact[0], p[1] - exact[1]);
    assert.ok(Math.abs(Math.hypot(p[0], p[1]) - Math.sqrt(.5)) < .002);
  }
  assert.ok(error > 0 && error < .003);
  return error;
}
const coarse = rotationError(4), fine = rotationError(8);
assert.ok(coarse / fine > 3.5 && coarse / fine < 4.5, "Second order midpoint refinement");
for (const scale of [1e-100, 1e100]) {
  const paths = traceFieldGrid(fixture(4, () => [1e100, 0, 0], scale), options);
  assert.equal(paths.length, 4); assert.ok(paths.every(p => p.points.flat().every(Number.isFinite)));
}
for (const edit of [
  d => { delete d.cells.flowDomain; },
  d => { d.cells.centers.pop(); d.frames[0].vectors.pop(); },
  d => { d.cells.centers[0] = d.cells.centers[1]; },
  d => { d.cells.centers.forEach(p => { p[2] = 0; }); },
  d => { d.frames[0].vectors[0][0] = Infinity; },
  d => { d.cells.centers.forEach(p => { p[2] *= 1e-14; }); },
]) { const d = structuredClone(constant); edit(d); assert.deepEqual(traceFieldGrid(d, options), []); }
for (const seedDensity of [2, 8, 100, NaN]) {
  const paths = traceFieldGrid(fixture(4, ([x, y]) => [-y, x, 0]), { ...options, seedDensity, budget: Infinity });
  assert.ok(paths.length <= 64);
  assert.ok(paths.reduce((n, p) => n + p.points.length - 1, 0) <= FIELD_STREAM_SEGMENT_LIMIT);
}
assert.deepEqual(traceFieldGrid(constant, { ...options, budget: 1 }), []);
const oversized = fixture(34, () => [1, 0, 0]);
assert.ok(oversized.cells.centers.length > 40000);
assert.deepEqual(traceFieldGrid(oversized, options), [], "Input cap applies before grid construction");
console.log(`Stream presentation checks passed; rotating-field errors ${coarse}, ${fine}; ratio ${coarse / fine}.`);
