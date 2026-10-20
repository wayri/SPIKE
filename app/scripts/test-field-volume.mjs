// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { admitFieldVolume, fieldViewPlot } = await importTestTypescript("fieldVolumeModel");
const raw = JSON.parse(fs.readFileSync(new URL("../../examples/field_visualization/illustrative-volume.json", import.meta.url)));
const data = admitFieldVolume(raw);
const options = { frame: 0, quantity: "temperature_k", mode: "voxels", arrows: true, opacity: .7, budget: 2500, sliceAxis: "all", slicePercent: 100, celsius: true };
const plot = fieldViewPlot(data, options);
assert.equal(plot.shown, 72);
assert.equal(plot.traces[0].x.length, 72 * 8);
assert.equal(plot.traces[0].i.length, 72 * 12);
assert.equal(plot.traces[0].intensity.length, plot.traces[0].i.length);
assert.equal(plot.arrowCount, 72);
assert.equal(plot.unit, "°C");
assert.equal(plot.minimum, Math.min(...raw.frames.flatMap(f => f.scalars.temperature_k)) - 273.15);
const later = fieldViewPlot(data, { ...options, frame: 3 });
assert.equal(later.minimum, plot.minimum); assert.equal(later.maximum, plot.maximum, "Playback must not change the legend range");
assert.notDeepEqual(later.traces[0].intensity, plot.traces[0].intensity);
const cut = fieldViewPlot(data, { ...options, sliceAxis: "x", slicePercent: 50, budget: 10 });
assert.equal(cut.eligible, 36); assert.ok(cut.shown <= 10);
assert.ok(cut.traces[0].x.every(x => x <= 3), "Cut must exclude high-X cells");
const noSizes = admitFieldVolume({ ...raw, cells: { centers: raw.cells.centers } });
assert.equal(fieldViewPlot(noSizes, options).traces[0].type, "scatter3d", "Unknown cells must remain points, not inferred voxels");
raw.frames[0].scalars.temperature_k[0] = 999;
assert.notEqual(data.frames[0].scalars.temperature_k[0], 999, "Admitted data must own its arrays");
for (const invalid of [
  { ...raw, lengthUnit: "cm" },
  { ...raw, quantities: [...raw.quantities, raw.quantities[0]] },
  { ...raw, frames: [raw.frames[0], raw.frames[0]] },
  { ...raw, cells: { centers: [[NaN, 0, 0]] } },
  { ...raw, cells: { ...raw.cells, sizes: [[0, 1, 1]] } },
  { ...raw, frames: [{ ...raw.frames[0], vectors: [[1, 2, Infinity]] }] },
]) assert.throws(() => admitFieldVolume(invalid));
assert.deepEqual(data.cells.centers[0], [.5, .5, .5]);
console.log("Field volume admission, voxel topology, clipping, bounded display, vectors, immutable source and stable transient scales passed");
