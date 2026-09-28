// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { importTestTypescript } from "../app/scripts/import-test-typescript.mjs";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const imported = JSON.parse(readFileSync(resolve(root, "examples/esp32/pi_request.json"), "utf8"));
const expectedDigest = "3199ce0a25f8987020e716d82a4a35d9b6b04541d33b2f2e46406376713eab33";
assert.equal(imported.design.metadata.source_sha256, expectedDigest, "ESP32 source board changed; review the thermal assumptions.");
const bounds = imported.design.metadata.board_bounds_mm;
assert.ok(Array.isArray(bounds) && bounds.length === 4, "Imported ESP32 design needs finite board bounds.");
const widthMm = Number(bounds[2]) - Number(bounds[0]);
const heightMm = Number(bounds[3]) - Number(bounds[1]);
assert.ok(widthMm > 0 && heightMm > 0);

const { screenThermalEnvironment, thermalEnvironmentProfiles } = await importTestTypescript("thermalEnvironments");
const inputs = { boardWidthMm: widthMm, boardHeightMm: heightMm, ambientC: 25, powerW: 1.35 };
const scenarios = Object.fromEntries(thermalEnvironmentProfiles.map(profile => {
  const result = screenThermalEnvironment(profile.id, inputs);
  return [profile.id, {
    name: profile.name,
    boundary_inputs: { enclosure: profile.enclosure, convection: profile.convection, top_heat_transfer_coefficient_w_m2k: profile.topHeatTransferCoefficientWm2K, bottom_heat_transfer_coefficient_w_m2k: profile.bottomHeatTransferCoefficientWm2K, nominal_airflow_m3_s: profile.nominalAirflowM3s },
    screen: { model_status: result.modelStatus, board_area_m2: result.boardAreaM2, top_resistance_k_w: result.topResistanceKPerW, bottom_resistance_k_w: result.bottomResistanceKPerW, equivalent_resistance_k_w: result.equivalentResistanceKPerW, estimated_board_temperature_c: result.estimatedBoardTemperatureC, ideal_bulk_air_rise_c: result.idealBulkAirRiseC },
    assumptions: profile.assumptions,
  }];
}));
assert.ok(scenarios.closed_box.screen.estimated_board_temperature_c > scenarios.open_air.screen.estimated_board_temperature_c);
assert.ok(scenarios.open_air.screen.estimated_board_temperature_c > scenarios.forced_air.screen.estimated_board_temperature_c);

const evidence = {
  contract: "spike/esp32-thermal-environment-comparison/v1", model_status: "approximate",
  source: { board_path: "examples/esp32/source/iot-esp-eth-ind.kicad_pcb", board_sha256: expectedDigest },
  inputs: { ambient_temperature_c: inputs.ambientC, aggregate_board_power_w: inputs.powerW, board_width_mm: widthMm, board_height_mm: heightMm },
  power_accounting: {
    basis: "The existing ESP32 thermal example totals 1.35 W from illustrative U1 0.60 W, U41 0.50 W, and U61 0.25 W entries.",
    u41_ldo_budget_w: 0.255,
    treatment: "The separately calculated U41 AZ1117 5 V to 3.3 V loss is not added to the 1.35 W aggregate. Add it only after replacing the illustrative per-device loss distribution, otherwise U41 may be counted twice.",
  },
  scenarios,
  limitations: [
    "These are algebraic boundary-condition screens, not board-field, enclosure CFD, or conjugate heat-transfer solves.",
    "Uniform effective coefficients do not resolve package hot spots, copper spreading, enclosure walls, radiation, fan pressure loss, bypass, recirculation, or local air velocity.",
    "The 1.35 W power and all heat-transfer coefficients are assumptions, not measurements of this ESP32 board.",
  ],
};
const output = resolve(root, "examples/esp32/evidence/thermal_environment_comparison.json");
writeFileSync(output, `${JSON.stringify(evidence, null, 2)}\n`);
console.log(JSON.stringify({ output, temperatures_c: Object.fromEntries(Object.entries(scenarios).map(([id, value]) => [id, value.screen.estimated_board_temperature_c])) }, null, 2));
