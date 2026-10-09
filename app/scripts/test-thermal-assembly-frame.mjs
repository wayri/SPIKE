// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { thermalResultOccurrence, thermalOccurrenceMatchesDesign, thermalAssemblyPoint, thermalOverlayTransform, fitThermalAssemblyVolume } = await importTestTypescript("thermalAssemblyFrame");
const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const base = { id: "base", designId: "base-design", active: true, localCenterMm: [50, 35, 0], widthMm: 100, heightMm: 70, thicknessMm: 1.6, transform: identity };
// Rotate native Y into upright Z, with source coordinates away from the origin.
const blade = { ...base, id: "blade", designId: "blade-design", active: false, heightMm: 115, localCenterMm: [50, 257.5, 0], transform: [1, 0, 0, 10, 0, 0, -1, 35, 0, 1, 0, -200, 0, 0, 0, 1] };
const repeated = { ...blade, id: "blade-2" };
assert.equal(thermalResultOccurrence([base, blade], "blade-design"), blade);
assert.equal(thermalResultOccurrence([base, blade, repeated], "blade-design"), null);
assert.equal(thermalResultOccurrence([base, blade, repeated], "blade-design", "blade-2"), repeated);
assert.equal(thermalResultOccurrence([base, blade], "base-design", "blade"), null);
assert.equal(thermalResultOccurrence([base, blade], "missing"), null);
assert.equal(thermalResultOccurrence([base, { ...base, id: "base-2" }]), null);
const aliased = { ...blade, sourceNativeId: "native-blade-source" };
const repeatedAlias = { ...repeated, sourceNativeId: "native-blade-source" };
assert.equal(thermalOccurrenceMatchesDesign(aliased, "native-blade-source"), true);
assert.equal(thermalOccurrenceMatchesDesign(aliased, "blade-design"), true);
assert.equal(thermalOccurrenceMatchesDesign(base, "native-blade-source"), false);
assert.equal(thermalOccurrenceMatchesDesign(base, undefined), false);
assert.equal(thermalResultOccurrence([base, aliased], "native-blade-source"), aliased);
assert.equal(thermalResultOccurrence([base, aliased, repeatedAlias], "native-blade-source"), null);
assert.equal(thermalResultOccurrence([base, aliased, repeatedAlias], "native-blade-source", "blade-2"), repeatedAlias);
assert.equal(thermalResultOccurrence([base, aliased], "native-blade-source", "base"), null);
assert.deepEqual(thermalAssemblyPoint([50, 315, 1.6], blade.transform), [60, 33.4, 115]);
const frame = thermalOverlayTransform(blade, [50, 35], 2, 0.8, 7);
// Cell source (50, 250) and saved native top 1.6 map to the same upright
// occurrence; layer display offsets must advance along its normal, not world Z.
const point = thermalAssemblyPoint([0, (35 - 250) * 2, 1.6], frame);
const expected = [20, 3.2, 114];
point.forEach((value, i) => assert.ok(Math.abs(value - expected[i]) < 1e-10));
const above = thermalAssemblyPoint([0, (35 - 250) * 2, 3.6], frame);
assert.ok(Math.abs(above[1] - point[1] - 2) < 1e-10);
assert.ok(Math.abs(above[2] - point[2]) < 1e-10);
const fit = fitThermalAssemblyVolume([base, blade], [50, 35]);
assert.deepEqual(fit.volume, { x: 130, y: 80, z: 120 });
assert.equal(fit.extendsBelowDomain, false);
assert.ok(fit.maximum[2] >= 115, "upright blade must not be clipped at the old 40 mm volume");
assert.equal(fitThermalAssemblyVolume([], [0, 0]), null);
assert.equal(fitThermalAssemblyVolume([{ ...base, transform: [] }], [0, 0]), null);
assert.equal(fitThermalAssemblyVolume([{ ...base, transform: identity.map((x, i) => i === 11 ? -10 : x) }], [50, 35]).extendsBelowDomain, true);
console.log("thermal assembly ownership, source frame, normal and domain bounds passed");
