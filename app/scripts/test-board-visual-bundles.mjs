import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { configureKnownVisuals } from "../src/boardVisualBundles.ts";

const board = () => ({
  layerDefinitions: [{ name: "F.Cu" }, { name: "B.Cu" }],
});

const ebrake = board();
assert.equal(await configureKnownVisuals(ebrake, "C:\\projects\\ebrake1.kicad_pcb", readFileSync(new URL('../public/demo/ebrake1.kicad_pcb', import.meta.url), 'utf8')), true);
assert.equal(ebrake.boardModelUrl, "/demo/models/ebrake1_board.glb");
assert.equal(ebrake.componentModelUrl, "/demo/models/ebrake1_components.glb");
assert.equal(ebrake.modelManifestUrl, "/demo/models/ebrake1_scene.json");

assert.equal(await configureKnownVisuals(board(), "unbundled.kicad_pcb"), false);
const edited = board();
assert.equal(await configureKnownVisuals(edited, "ebrake1.kicad_pcb", "(kicad_pcb (version 20260101))"), false);
assert.equal(edited.boardModelUrl, undefined, "an edited board must not receive stale demo geometry");
console.log("board visual bundles: all assertions passed");
