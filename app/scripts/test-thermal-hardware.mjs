import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const app = readFileSync(resolve(root, "src", "App.tsx"), "utf8");
const editor = readFileSync(resolve(root, "src", "ThermalHardwareEditor.tsx"), "utf8");
const model = readFileSync(resolve(root, "src", "thermalHardware.ts"), "utf8");
const scene = readFileSync(resolve(root, "src", "thermalScene.ts"), "utf8");
const viewport = readFileSync(resolve(root, "src", "BoardViewport.tsx"), "utf8");

for (const fragment of ["<ThermalHardwareEditor", "fans,", "virtual_heatsinks: heatsinks", "totalFanFlow"]) {
  if (!app.includes(fragment)) throw new Error(`Thermal hardware handoff missing: ${fragment}`);
}
for (const fragment of ["FANS", "INTEGRATED HEATSINKS", "Pressure Pa", "Fin height", "Interface Rth", "onSpreadsheetKeyDown"]) {
  if (!editor.includes(fragment)) throw new Error(`Thermal hardware spreadsheet missing: ${fragment}`);
}
for (const fragment of ["normalizeThermalFans", "normalizeThermalHeatsinks", "static_pressure_pa", "interface_resistance_c_per_w"]) {
  if (!model.includes(fragment)) throw new Error(`Thermal hardware normalization missing: ${fragment}`);
}
for (const fragment of ["export type ThermalFan", "export type ThermalHeatsink", "fin_count", "depth_mm"]) {
  if (!scene.includes(fragment)) throw new Error(`Thermal hardware schema missing: ${fragment}`);
}
for (const fragment of ["fan.enabled !== false", "heatsink.enabled !== false", 'type: "fan"', 'type: "heatsink"']) {
  if (!viewport.includes(fragment)) throw new Error(`Thermal hardware viewport missing: ${fragment}`);
}

console.log("thermal hardware workflow contract passed");
