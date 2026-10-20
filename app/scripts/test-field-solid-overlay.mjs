// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { admitFieldVolume, fieldViewPlot } = await importTestTypescript("fieldVolumeModel");
const { FIELD_SOLID_DISPLAY_LIMIT, FIELD_SOLID_LIMIT } = await importTestTypescript("fieldSolidOverlay");

const base = {
  contract: "spike/field-volume-view/v1", id: "solid-overlay", label: "Coupled circuit and CHT presentation", lengthUnit: "mm",
  cells: { centers: [[0, 0, 0]] }, quantities: [{ id: "temperature_k", label: "Temperature", unit: "K" }],
  frames: [{ timeS: 0, scalars: { temperature_k: [300] }, vectors: [[1, 0, 0]] }],
};
const geometry = { solids: [
  { label: "Package A", min: [-2, -3, 0], max: [4, 5, 6] },
  { label: "Board", min: [-10, -8, -1.6], max: [10, 8, 0] },
] };
const admitted = admitFieldVolume({ ...base, geometry });
geometry.solids[0].min[0] = 900;
assert.equal(admitted.geometry.solids[0].min[0], -2, "admission owns the supplied geometry arrays");
assert.deepEqual(JSON.parse(JSON.stringify(admitted)).geometry.solids[1], { label: "Board", min: [-10, -8, -1.6], max: [10, 8, 0] }, "export round-trip retains exact cuboids");

const options = { frame: 0, quantity: "temperature_k", mode: "points", arrows: false, opacity: .7, budget: 1, sliceAxis: "all", slicePercent: 100, celsius: false, showSolids: true, solidOpacity: .15 };
const withOverlay = fieldViewPlot(admitted, options);
assert.equal(withOverlay.shown, 1);
assert.equal(withOverlay.solidShown, 2);
assert.equal(withOverlay.solidTotal, 2);
assert.equal(withOverlay.traces.length, 2, "solid overlay is separate from the field trace");
const solidTrace = withOverlay.traces[1];
assert.equal(solidTrace.type, "mesh3d");
assert.equal(solidTrace.opacity, .15);
assert.equal(solidTrace.x.length, 16);
assert.equal(solidTrace.i.length, 24);
assert.deepEqual(solidTrace.x.slice(0, 8), [-2, 4, 4, -2, -2, 4, 4, -2], "vertices use exact supplied X bounds");
assert.match(solidTrace.hovertemplate, /x=%\{x\} mm/, "hover coordinates identify the supplied coordinate unit");
const hidden = fieldViewPlot(admitted, { ...options, showSolids: false });
assert.equal(hidden.traces.length, 1);
assert.equal(hidden.solidShown, 0);
assert.deepEqual(hidden.traces[0], withOverlay.traces[0], "overlay visibility does not alter source field presentation");

const many = admitFieldVolume({ ...base, geometry: { solids: Array.from({ length: FIELD_SOLID_DISPLAY_LIMIT + 7 }, (_, index) => ({ label: `Solid ${index}`, min: [index * 2, 0, 0], max: [index * 2 + 1, 1, 1] })) } });
const bounded = fieldViewPlot(many, { ...options, mode: "streamlines" });
assert.equal(bounded.solidShown, FIELD_SOLID_DISPLAY_LIMIT);
assert.equal(bounded.solidTotal, FIELD_SOLID_DISPLAY_LIMIT + 7);
assert.equal(bounded.traces.at(-1).x.length, FIELD_SOLID_DISPLAY_LIMIT * 8, "overlay vertex storage is bounded independently of streamline display");

for (const geometry of [
  { solids: [] },
  { solids: [{ label: "flat", min: [0, 0, 0], max: [1, 0, 1] }] },
  { solids: [{ label: "reversed", min: [2, 0, 0], max: [1, 1, 1] }] },
  { solids: [{ label: "nonfinite", min: [0, 0, 0], max: [1, 1, Infinity] }] },
  { solids: [{ label: "extra", min: [0, 0, 0], max: [1, 1, 1], color: "red" }] },
  { solids: [{ label: "ok", min: [0, 0, 0], max: [1, 1, 1] }], extra: true },
  { solids: Array.from({ length: FIELD_SOLID_LIMIT + 1 }, (_, index) => ({ label: String(index), min: [index * 2, 0, 0], max: [index * 2 + 1, 1, 1] })) },
]) assert.throws(() => admitFieldVolume({ ...base, geometry }));

console.log("Strict solid geometry admission, exact cuboid mesh, bounded independent display, toggle isolation and JSON retention passed");
