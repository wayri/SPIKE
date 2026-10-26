// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { admitFieldVolume, fieldViewPlot, fieldInspectionPresets, fieldSampleInspection, fieldSavedRange } = await importTestTypescript("fieldVolumeModel");
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
const manual = fieldViewPlot(data, { ...options, colorRange: [25, 75] });
assert.deepEqual([manual.minimum, manual.maximum], [25, 75]);
assert.deepEqual(manual.traces[0].intensity, plot.traces[0].intensity, "Manual coloring never modifies stored values");
assert.equal(manual.traces[0].cmin, 25); assert.equal(manual.traces[0].cmax, 75);
for (const colorRange of [[5, 5], [10, -10], [NaN, 1], [0, Infinity]]) {
  const recovered = fieldViewPlot(data, { ...options, colorRange });
  assert.deepEqual([recovered.minimum, recovered.maximum], [plot.minimum, plot.maximum], "Invalid display limits recover to data range");
}
assert.deepEqual(fieldSavedRange(data, options), [plot.minimum, plot.maximum]);
const presets = fieldInspectionPresets(data, 0);
assert.equal(fieldViewPlot(data, { ...options, ...presets[0].patch }).eligible, data.cells.centers.length);
assert.equal(fieldViewPlot(data, { ...options, ...presets[1].patch }).eligible, 36);
assert.equal(presets[2].available, false, "Scalar values cannot establish field-line availability");
assert.equal(fieldInspectionPresets(noSizes, 0)[0].patch.mode, "points");
const withCurve = admitFieldVolume({ ...data, frames: data.frames.map((frame, index) => ({ ...frame, ...(index === 0 ? { streamlines: [{ points: [[0,0,0], [1,0,0]], scalars: Object.fromEntries(data.quantities.map(q => [q.id, [1,2]])) }] } : {}) })) });
assert.equal(fieldInspectionPresets(withCurve, 0)[2].available, true);
assert.equal(fieldInspectionPresets(withCurve, 1)[2].available, false, "Supplied-line preset admission follows the saved frame");
assert.equal(fieldViewPlot(withCurve, { ...options, ...fieldInspectionPresets(withCurve, 0)[2].patch }).streamCount, 1);
const tiny = admitFieldVolume({ contract: data.contract, id: "samples", label: "Samples", lengthUnit: "mm", cells: { centers: [[10,20,30], [40,50,60], [70,80,90]] },
  quantities: [{ id: "t", label: "Temperature", unit: "K" }], frames: [{ timeS: 0, scalars: { t: [300, 290, 310] } }, { timeS: 1, scalars: { t: [320, 330, 310] } }] });
const sampleOptions = { ...options, quantity: "t", sampleIndex: 2, budget: 1, sliceAxis: "x", slicePercent: 0 };
const inspection = fieldSampleInspection(tiny, sampleOptions);
assert.deepEqual(inspection.minimum, { index: 1, value: 290 - 273.15, point: [40,50,60] });
assert.deepEqual(inspection.maximum, { index: 2, value: 310 - 273.15, point: [70,80,90] });
assert.equal(fieldSampleInspection(tiny, { ...sampleOptions, frame: 1 }).maximum.index, 1, "Readout follows the selected saved frame");
const marked = fieldViewPlot(tiny, sampleOptions);
assert.equal(marked.shown, 1);
assert.deepEqual(marked.traces.find(trace => trace.name === "Inspected stored sample").x, [70], "Inspected location remains visible beyond the cut and display budget");
assert.equal(fieldSampleInspection(tiny, { ...sampleOptions, sampleIndex: NaN }).selected.index, 0);
for (const [requested, expected] of [[12, 12], [999, 18], [-10, 2], [NaN, 4]]) {
  const resized = fieldViewPlot(tiny, { ...sampleOptions, mode: "points", pointSize: requested });
  assert.equal(resized.traces[0].marker.size, expected, "Point size stays bounded and uses an honest marker path");
  assert.deepEqual(resized.traces[0].marker.color, [300 - 273.15], "Point size does not invent or interpolate thermal values");
}
console.log("Field volume admission, voxel topology, clipping, bounded display, vectors, immutable source and stable transient scales passed");
