import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { normalizeThermalFieldResult, thermalFieldResultPreview, thinThermalFieldSamples, thermalFieldColor } = await importTestTypescript("thermalResultFields");

const result = normalizeThermalFieldResult({
  contract: "spike/thermal-field-result/v1", status: "completed", model_status: "engineering",
  fields: {
    temperature_c: [
      { position_mm: [0, 0, 0], value: 25, coordinate_frame: "board_local" },
      { position_mm: [20, 10, 1], value: 90, coordinate_frame: "board_local" },
      { position_mm: ["bad", 0, 0], value: 100 },
    ],
    heat_flux_w_m2: [{ x_mm: 1, y_mm: 2, z_mm: 3, value: 4 }],
  },
});
assert.equal(result.fields.temperature_c.length, 2, "only explicit finite samples are drawable");
assert.equal(result.fields.heat_flux_w_m2[0].coordinate_frame, "domain_local");
assert.equal(normalizeThermalFieldResult({ summary: { maximum_temperature_c: 99 } }), null, "a summary cannot fabricate a field");

const canonical = normalizeThermalFieldResult({
  contract: "spike/thermal-field-result/v1",
  fields: {
    temperature_k: { unit: "K", samples: [{ point_mm: [1, 2, 3], value: 300 }] },
    heat_flux_w_m2: { unit: "W/m2", samples: [{ point_mm: [1, 2, 3], value: [3, 4, 0] }] },
  },
});
assert.ok(Math.abs(canonical.fields.temperature_c[0].value - 26.85) < 1e-9, "canonical Kelvin fields convert explicitly to Celsius");
assert.equal(canonical.fields.heat_flux_w_m2[0].value, 5, "vector heat flux is rendered by magnitude");

const dense = Array.from({ length: 25000 }, (_, index) => ({ position_mm: [index % 100, Math.floor(index / 100) % 100, Math.floor(index / 10000)] , value: index }));
const reduced = thinThermalFieldSamples(dense, 9000);
assert.ok(reduced.length <= 9000, "viewport LOD has a hard instance budget");
assert.ok(reduced.some(item => item.value === 0) && reduced.some(item => item.value === 24999), "global extrema remain visible");
const preview = thermalFieldResultPreview({ contract: "spike/thermal-field-result/v1", fields: { temperature_c: dense } }, 100);
assert.ok(preview.fields.temperature_c.length <= 100 && preview.visualization.decimated, "React/project payloads retain only bounded LOD samples");
assert.deepEqual(Array.from(thermalFieldColor(0, 0, 1)), [0.12, 0.35, 0.92]);
console.log("thermal field rendering contract passed");
