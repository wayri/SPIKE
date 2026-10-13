// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { restoreAssemblyBoardVisual } = await importTestTypescript("assemblyBoardVisualRestoration");
const retained = {
  width: 68, height: 54, bounds: { minX: 0, minY: 0, maxX: 68, maxY: 54 },
  outlineLoops: [[[0, 0], [68, 0], [68, 54], [0, 54], [0, 0]]],
  tracks: [{ id: "uno-track" }], vias: [{ id: "uno-via" }], pads: [{ id: "uno-pad" }],
  components: [{ id: "uno-component" }], zones: [{ id: "uno-zone" }], drawings: [{ id: "uno-silkscreen" }],
  layers: ["F.Cu", "B.Cu"], layerDefinitions: [], stackup: [], nets: { "1": "+5V" },
};
const outlineOnly = {
  ...retained,
  tracks: [], vias: [], pads: [], components: [], zones: [], drawings: [{ id: "outline-only" }],
  boardModelUrl: "blob:active-board", layoutLayerUrls: { "F.Cu": "blob:active-layer" }, layoutViewBox: [0, 0, 68, 54],
};
const restored = restoreAssemblyBoardVisual(retained, outlineOnly);
assert.equal(restored.tracks, retained.tracks, "outline-only active board recovers retained UNO tracks");
assert.equal(restored.pads, retained.pads, "outline-only active board recovers retained UNO pads");
assert.equal(restored.components, retained.components, "outline-only active board recovers retained UNO components");
assert.equal(restored.drawings, retained.drawings, "outline-only active board cannot replace retained artwork with its rectangle");
assert.equal(restored.boardModelUrl, outlineOnly.boardModelUrl, "progressively prepared active 3D board asset remains attached");
assert.equal(restored.layoutLayerUrls, outlineOnly.layoutLayerUrls, "progressively prepared active 2D layers remain attached");

const complete = { ...outlineOnly, tracks: [{ id: "active-track" }] };
assert.equal(restoreAssemblyBoardVisual(retained, complete), complete, "a populated active board remains authoritative");
assert.equal(restoreAssemblyBoardVisual({ ...retained, tracks: [], vias: [], pads: [], components: [], zones: [] }, outlineOnly), outlineOnly,
  "a genuinely geometry-free retained design does not fabricate content");

console.log("Assembly active-board retained geometry restoration passed");

const prepared = { ...retained, boardModelUrl: "blob:prepared-board", componentModelUrl: "blob:prepared-parts", layoutLayerUrls: {"F.Cu":"blob:prepared-layer"}, boardModelIncludesCopper: true };
const pending = {...outlineOnly, boardModelUrl: undefined, componentModelUrl: undefined, layoutLayerUrls: undefined, boardModelIncludesCopper: false};
const preserved = restoreAssemblyBoardVisual(prepared,pending);
assert.equal(preserved.boardModelUrl,prepared.boardModelUrl);
assert.equal(preserved.componentModelUrl,prepared.componentModelUrl);
assert.equal(preserved.layoutLayerUrls,prepared.layoutLayerUrls);
assert.equal(preserved.boardModelIncludesCopper,false,"an explicit active flag remains authoritative");

const assembled = restoreAssemblyBoardVisual(restoreAssemblyBoardVisual(retained,prepared),pending);
assert.equal(assembled.tracks,retained.tracks);
assert.equal(assembled.boardModelUrl,prepared.boardModelUrl,"active outline cannot drop asynchronously prepared board assets");
