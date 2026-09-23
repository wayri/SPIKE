import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/viewportContext.ts", import.meta.url), "utf8")
  .replace('import type { ResultViewMode, SolverResultBundle } from "./analysisResults";\n', "");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const context = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);

const result = {
  scalar_fields: {
    voltage_v: [{ value: 12 }], voltage_drop_v: [{ value: 0.01 }], current_a: [],
    current_density_a_mm2: [{ value: 4 }], power_loss_w: [], via_current_density_a_mm2: [],
    operating_point_impedance_ohm: [],
  },
  vector_fields: { current_density: [], electric_field: [], magnetic_field: [] },
  mesh: [{ id: "cell-1" }], parasitics: [{ impedance: [{ frequency_hz: 1e6 }] }],
  loop_parasitics: [], pdn_multiports: [],
};
assert.deepEqual(context.availableViewportResultModes(result), ["voltage", "voltage_drop", "current_density", "mesh"]);
assert.equal(context.resultHasExtractedNetworks(result), true);
assert.equal(context.viewportContextLabel({ tab: "PI", analysisMode: "AC Impedance Sweep", hasBoard: true, hasSelection: false, hasSelectedNet: true, hasStoredResults: false, hasActiveResult: false }), "AC SETUP");
assert.equal(context.viewportContextLabel({ tab: "PI", analysisMode: "DC IR Drop", hasBoard: true, hasSelection: false, hasSelectedNet: true, hasStoredResults: true, hasActiveResult: false }), "RESULTS HIDDEN");
assert.equal(context.viewportContextLabel({ tab: "PI", analysisMode: "Bulk Net Analysis", hasBoard: true, hasSelection: false, hasSelectedNet: true, hasStoredResults: true, hasActiveResult: true }), "BATCH RESULT");
assert.equal(context.viewportContextLabel({ tab: "Thermal", analysisMode: "DC IR Drop", hasBoard: true, hasSelection: false, hasSelectedNet: false, hasStoredResults: false, hasActiveResult: false }), "THERMAL SETUP");

console.log("viewport context command assertions passed");
