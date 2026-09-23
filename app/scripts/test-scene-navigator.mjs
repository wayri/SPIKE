import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const navigator = readFileSync(new URL("../src/SceneNavigator.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

for (const command of ["2D layout", "3D board", "Layer manager", "Fit active scene", "Top view", "Bottom view", "Isometric view"]) {
  assert.ok(app.includes(command), `persistent board-view command is missing: ${command}`);
}
assert.ok(app.includes("<BoardViewRibbon"), "persistent board-view ribbon is not mounted");
assert.ok(app.includes("<SceneNavigator"), "scene navigator is not mounted");

for (const category of ["Boards & Assembly", "Electrical", "Mechanical & MCAD", "Analysis"]) {
  assert.ok(navigator.includes(category), `scene navigator category is missing: ${category}`);
}
for (const objectKind of ["board.components", "board.pads", "board.vias", "board.tracks", "board.zones", "board.layerDefinitions", "board.regions", "board.bendLines", "thermalElements", "probes"]) {
  assert.ok(navigator.includes(objectKind), `scene object source is not indexed: ${objectKind}`);
}
assert.ok(navigator.includes("open board/harness structure editing"), "multi-board navigator must expose the implemented structure editor");
assert.ok(app.includes("Assembly board-instance and harness editor opened; coupled analysis remains capability-gated."), "assembly action must open editing without implying coupled physics");
assert.ok(navigator.includes("Attached MCAD"), "attached AssemblyIR parts must have a dedicated navigator tree");
assert.ok(navigator.includes("Assembly hierarchy"), "AssemblyIR frames must be presented as a tree-oriented hierarchy");
assert.ok(navigator.includes("assemblyHierarchyRows"), "scene hierarchy must use the bounded canonical frame projection");
assert.ok(navigator.includes("onAssemblyPart"), "MCAD hierarchy rows must focus the existing editor by stable part identity");
assert.ok(navigator.includes("partDisplayStatus"), "MCAD rows must disclose format-specific visualization and frame-parent limits");
assert.ok(styles.includes(".persistent-board-view"), "persistent board-view ribbon styling is missing");
assert.ok(styles.includes(".scene-navigator-content"), "scene navigator scrolling/layout styling is missing");

console.log("Scene navigator and persistent board-view ribbon contract passed.");
