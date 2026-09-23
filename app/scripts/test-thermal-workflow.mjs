import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const appRoot = resolve(import.meta.dirname, "..");
const app = readFileSync(resolve(appRoot, "src", "App.tsx"), "utf8");
const scene = readFileSync(resolve(appRoot, "src", "thermalScene.ts"), "utf8");

const requiredAppFragments = [
  'method: "validate_thermal"',
  'method: "prepare_thermal_case"',
  'method: "run_thermal_case"',
  'method: "estimate_thermal"',
  'engine_id: "external.openfoam"',
  "OPENFOAM CASE CONTROLS",
  "<ThermalHardwareEditor",
  "Potted block",
  "Vacuum disables convection",
  "Prepare a runnable OpenFOAM case before execution",
  "No result is marked validated here.",
  "Approximate independent RC sources only",
];

for (const fragment of requiredAppFragments) {
  if (!app.includes(fragment)) throw new Error(`Thermal workflow is missing: ${fragment}`);
}

if (!app.includes('disabled={busy !== null || !preparedCase?.can_run}')) {
  throw new Error("OpenFOAM execution must remain gated by a prepared runnable case");
}

for (const fragment of ["solver?:", "mesh?:", "run?:", "flow_rate_m3_s", "diameter_mm"]) {
  if (!scene.includes(fragment)) throw new Error(`Thermal viewport contract is missing: ${fragment}`);
}

console.log("thermal workflow UI contract passed");
