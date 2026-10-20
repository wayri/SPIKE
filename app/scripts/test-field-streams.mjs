// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { admitFieldVolume, fieldViewPlot } = await importTestTypescript("fieldVolumeModel");
const { cartesianFluidGrid, fieldStreamAvailability } = await importTestTypescript("fieldStreamPresentation");
const curves = JSON.parse(fs.readFileSync(new URL("../../examples/field_visualization/illustrative-curves.json", import.meta.url)));
const grid = JSON.parse(fs.readFileSync(new URL("../../examples/field_visualization/illustrative-volume.json", import.meta.url)));
const options = { frame: 0, quantity: "temperature_k", mode: "streamlines", arrows: false, opacity: 1, budget: 2500, sliceAxis: "all", slicePercent: 100, celsius: true };
const data = admitFieldVolume(curves), plot = fieldViewPlot(data, options);
assert.equal(plot.streamCount, 8); assert.equal(plot.traces[0].type, "scatter3d");
assert.equal(plot.traces[0].connectgaps, false);
assert.equal(plot.traces[0].x.filter(x => x === null).length, 8, "Every path boundary needs a gap");
assert.deepEqual(plot.traces[0].x.slice(0, 64), curves.frames[0].streamlines[0].points.map(p => p[0]));
assert.equal(plot.traces[0].line.color[0], curves.frames[0].streamlines[0].scalars.temperature_k[0] - 273.15);
const tubes = fieldViewPlot(data, { ...options, mode: "streamtubes" });
assert.equal(tubes.traces[0].type, "mesh3d");
assert.equal(tubes.traces[0].x.length, 8 * 64 * 8);
assert.equal(tubes.traces[0].i.length, 8 * 63 * 16);
assert.ok(tubes.traces[0].x.every(Number.isFinite));
// Tubes must not connect the last ring of one path to the first ring of another.
for (let f = 0; f < tubes.traces[0].i.length; f++) {
  const paths = [tubes.traces[0].i[f], tubes.traces[0].j[f], tubes.traces[0].k[f]].map(v => Math.floor(v / (64 * 8)));
  assert.equal(new Set(paths).size, 1);
}
const declared = admitFieldVolume(grid), generated = fieldViewPlot(declared, { ...options, mode: "streamtubes", seedAxis: "x", seedDensity: 4 });
assert.ok(cartesianFluidGrid(declared, 0)); assert.equal(generated.traces[0].type, "streamtube"); assert.equal(generated.streamCount, 16);
assert.ok(generated.traces[0].starts.x.every(x => x === .5));
assert.equal(generated.traces[0].cmin, 0); assert.match(generated.streamNote, /not the selected scalar/);
assert.equal(fieldViewPlot(declared, { ...options, mode: "streamtubes", frame: 3 }).traces[0].cmax, generated.traces[0].cmax);
const noDeclaration = structuredClone(declared); delete noDeclaration.cells.flowDomain;
assert.equal(cartesianFluidGrid(noDeclaration, 0), null, "Do not silently assume samples form an obstacle-free fluid domain");
const duplicate = structuredClone(declared); duplicate.cells.centers[0] = duplicate.cells.centers[1];
assert.equal(cartesianFluidGrid(duplicate, 0), null);
const planar = structuredClone(declared); planar.cells.centers = planar.cells.centers.map(p => [p[0], p[1], 0]);
assert.equal(fieldStreamAvailability(planar, 0).grid, false, "A 2D sheet is not a 3D flow grid");
const broken = structuredClone(curves); broken.frames[0].streamlines[0].scalars.temperature_k.pop();
assert.throws(() => admitFieldVolume(broken), /match each path point/);
const repeated = structuredClone(curves); repeated.frames[0].streamlines[0].points[1] = repeated.frames[0].streamlines[0].points[0];
assert.throws(() => admitFieldVolume(repeated), /distinct/);
console.log("Supplied curve topology, scalar coloring, tube isolation, bounded seeded grid admission and temporal scale checks passed");
