import { readFileSync } from "node:fs";
import { resolve } from "node:path";

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
