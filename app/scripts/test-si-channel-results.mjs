import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/siChannelResults.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const module = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);
const result = { contract: "spike/si-channel-result/v1", status: "completed", production_qualified: false, compliance_status: "not_evaluated", network: { port_order: ["near", "far"], traces: { S21: [{ frequency_hz: 0, magnitude_db: -1, phase_deg: 0 }, { frequency_hz: 1e9, magnitude_db: -2, phase_deg: -12 }] } }, time_domain: { tdr: [{ time_s: 0, reflection: 0, impedance_ohm: 50 }], tdt: [{ time_s: 0, normalized_step: 1 }] }, eye: { samples_per_ui: 4, traces: [{ source_bit_index: 0, values: [0, 1, 0] }] }, mixed_mode: { conversion_db: -40 } };
const normalized = module.normalizeSiChannelResult(result);
assert.equal(normalized.productionQualified, false);
assert.equal(normalized.complianceStatus, "not_evaluated");
assert.equal(normalized.sMagnitudeDb[0].points.length, 2);
assert.equal(normalized.mixedModeMetrics.conversion_db, -40);
assert.match(module.buildSiChannelHtmlReport(result), /not production\/signoff qualified/);
const differential = { ...result, mixed_mode: undefined, differential: { transform: { single_ended_reference_impedance_ohm: 50, differential_reference_impedance_ohm: 100 } } };
const normalizedDifferential = module.normalizeSiChannelResult(differential);
assert.equal(normalizedDifferential.mixedModeMetrics.single_ended_reference_impedance_ohm, 50);
assert.equal(normalizedDifferential.mixedModeMetrics.differential_reference_impedance_ohm, 100);
const pam4 = { ...result, eye: { contract: "spike/si-eye-collection/v1", pam4: { contract: "spike/si-pam4-eye/v1", bathtub: [
  { phase_ui: 0, eye_heights_normalized: [0.1, 0.2, 0.3], ber_proxies: [0.4, 0.3, 0.2] },
  { phase_ui: 0.5, eye_heights_normalized: [0.5, 0.6, 0.7], ber_proxies: [1e-4, 1e-5, 1e-6] },
] } } };
const normalizedPam4 = module.normalizeSiChannelResult(pam4);
assert.equal(normalizedPam4.pam4EyeHeights.length, 3);
assert.equal(normalizedPam4.pam4BerProxies[2].points[1].y, 1e-6);
assert.match(module.buildSiChannelHtmlReport(pam4), /PAM4 eye height/);
const panel = readFileSync(new URL("../src/SiChannelResultPanel.tsx", import.meta.url), "utf8");
assert.match(panel, /const displayed = showAll \? available : selected \? available\.filter/, "trace selector must control the plotted series");
assert.match(panel, /defaultShowAll \/>/, "NEXT and FEXT are shown together for direct comparison");
assert.match(panel, /No matched NEXT\/FEXT samples were returned/, "absent crosstalk stays explicit");
console.log("SI channel native result assertions passed");
