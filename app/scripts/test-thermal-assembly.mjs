import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import assert from "node:assert/strict";
import ts from "typescript";

const root = resolve(import.meta.dirname, "..");
const app = readFileSync(resolve(root, "src", "App.tsx"), "utf8");
const editor = readFileSync(resolve(root, "src", "ThermalAssemblyEditor.tsx"), "utf8");
const model = readFileSync(resolve(root, "src", "thermalAssembly.ts"), "utf8");
const scene = readFileSync(resolve(root, "src", "thermalScene.ts"), "utf8");
const viewport = readFileSync(resolve(root, "src", "BoardViewport.tsx"), "utf8");

for (const fragment of ["thermal_elements: thermalElements", "thermal_links: thermalLinks", "material_library: thermalMaterials", "thermal_screening: thermalScreening", "<ThermalAssemblyEditor"]) {
  if (!app.includes(fragment)) throw new Error(`Thermal scenario handoff missing: ${fragment}`);
}
for (const fragment of ["PARTS, BOARDS, AND MECHANICAL OBJECTS", "THERMAL LINKS AND CONTACTS", "MATERIAL PROPERTY LIBRARY", "Rth top", "Tj max", "Sync board parts"]) {
  if (!editor.includes(fragment)) throw new Error(`Thermal table workflow missing: ${fragment}`);
}
for (const fragment of ["export const thermalMaterials", "glass_transition_c", "black-anodized", "screenThermalElements", "thermalAssemblyIssues", "componentThermalElements"]) {
  if (!model.includes(fragment)) throw new Error(`Thermal model missing: ${fragment}`);
}
for (const fragment of ["thermal_elements?:", "thermal_links?:", "material_library?:", "thermal_screening?:"]) {
  if (!scene.includes(fragment)) throw new Error(`Thermal scene contract missing: ${fragment}`);
}
for (const fragment of ['type: "thermal-element"', 'type: "thermal-link"', '`elements=${thermalScenario.thermal_elements?.length ?? 0}`']) {
  if (!viewport.includes(fragment)) throw new Error(`Thermal viewport missing: ${fragment}`);
}

console.log("thermal assembly workflow contract passed");

// Exercise the editor's actual sync callback against a large board: an imported
// powered reference beyond the first 256 source objects must keep its inputs.
const syncSource = editor.slice(editor.indexOf("  const syncParts ="), editor.indexOf("  const addMechanical ="));
const syncCompiled = ts.transpileModule(syncSource, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
const sourceParts = Array.from({ length: 300 }, (_, index) => ({ object_id: `part-${index}`, reference: `U${index}`, kind: "pcb_component", coordinate_frame: "board_local", power_w: 0, position: [index, 0, 0], dimensions_mm: { x: 1, y: 1, z: 1 } }));
const powered = { ...sourceParts[299], power_w: 7, theta_top_c_per_w: 12, position: [0, 0, 0] };
const mechanical = { object_id: "sink", kind: "heatsink", reference: "HS1" };
const sync = elements => {
  let result;
  new Function("elements", "board", "componentThermalElements", "onElements", `${syncCompiled}\nsyncParts();`)(elements, {}, () => sourceParts, rows => { result = rows; });
  return result;
};
const synced = sync([powered, mechanical]);
assert.equal(synced.length, 256);
assert.equal(synced[0].reference, "U299");
assert.equal(synced[0].power_w, 7);
assert.equal(synced[0].theta_top_c_per_w, 12);
assert.deepEqual(synced[0].position, [299, 0, 0]);
assert.equal(synced[1], mechanical);
assert.equal(new Set(synced.map(row => row.object_id)).size, 256);
assert.deepEqual(sync(synced), synced, "repeated sync must preserve all entered rows at capacity");
console.log("Thermal sync preserves powered references and hardware at the 256-row limit.");
