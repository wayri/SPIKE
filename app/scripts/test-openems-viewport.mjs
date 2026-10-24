// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { writeFileSync, unlinkSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const compile = async entry => { const b = await build({ entryPoints: [entry], bundle: true, write: false, format: "esm", platform: "node" }); return import(`data:text/javascript;base64,${Buffer.from(b.outputFiles[0].text).toString("base64")}`); };
const fieldApi = await compile("src/openEMSFarfield.ts"), viewport = await compile("src/emViewportResults.ts"), networks = await compile("src/openEMSNetworkSamples.ts"), results = await compile("src/analysisResults.ts"), optycal = await compile("src/optycalStudy.ts");
// Independent synthetic complex-field fixture; this test is not a solver run.
const field = { contract: "spike/openems-far-field-result/v1", status: "computed", validation_status: "not_validated", validation: { status: "not_validated" }, normalization: { kind: "incident_power", incident_power_w: 1, incident_voltage_phase_deg: 0, phasor: "peak", reference_impedance_ohm: 50, source_spectrum: "single_sided_pulse_fourier_integral", frequency_sampling: "exact_port_reevaluation" }, shape: [2, 2, 2], frequencies_hz: [1e9, 3e9], theta_deg: [90, 180], phi_deg: [0, 90], radius_m: 5, center_mm: [10, 20, 30], e_field_v_m: { theta: { real: [1,1,1,1,2,2,2,2], imag: [2,2,2,2,4,4,4,4] }, phi: { real: [3,3,3,3,6,6,6,6], imag: [4,4,4,4,8,8,8,8] }, magnitude: [...Array(4).fill(Math.sqrt(30)), ...Array(4).fill(2 * Math.sqrt(30))] } };
const admitted = fieldApi.admitOpenEMSFarfield(field); assert.ok(admitted);
const vectors = fieldApi.openEMSFarfieldVectors(admitted, 0);
assert.ok(Math.abs(vectors[0][0][0]) < 1e-12); assert.deepEqual(vectors[0][1], [3,4]); assert.deepEqual(vectors[0][2], [-1,-2]);
assert.deepEqual(fieldApi.openEMSFarfieldCut(admitted, 1).magnitudeVm, [2 * Math.sqrt(30), 2 * Math.sqrt(30)]);
for (const change of [v => v.shape[2] = 3, v => v.e_field_v_m.theta.imag.pop(), v => v.e_field_v_m.phi.real[0] = Infinity, v => v.e_field_v_m.magnitude[0] = 0, v => v.normalization.phasor = "rms", v => v.normalization.incident_power_w = 2, v => v.validation_status = "validated", v => v.frequencies_hz.reverse(), v => v.theta_deg[0] = -1, v => v.center_mm.pop(), v => v.radius_m = 0]) { const invalid = structuredClone(field); change(invalid); assert.equal(fieldApi.admitOpenEMSFarfield(invalid), null); }
const network = { frequencies_hz: [1e9,2e9,3e9], ports: ["P1","P2"], reference_impedance_ohm: 50, column_scope: "single actual excited port; other columns are null and invalid", missing_columns: ["P2"], values: Array.from({length:3}, () => [[[.5,0],null], [[.25,.1],null]]), valid_mask: Array.from({length:3}, () => [[true,false],[true,false]]) };
assert.ok(networks.admitOpenEMSNetworkSamples(network));
assert.throws(() => networks.exportOpenEMSNetworkTouchstone(networks.admitOpenEMSNetworkSamples(network)), /every excitation/);
for (const change of [v => v.valid_mask[0][0][1] = true, v => v.values[0][1][1] = [0,0], v => v.missing_columns = [2], v => v.values[1][0][0] = null, v => v.column_scope = "complete"]) { const invalid = structuredClone(network); change(invalid); assert.equal(networks.admitOpenEMSNetworkSamples(invalid), null); }
const onePort = { ...network, ports: ["P1"], missing_columns: [], values: network.values.map(matrix => [[matrix[0][0]]]), valid_mask: network.values.map(() => [[true]]) };
assert.match(networks.exportOpenEMSNetworkTouchstone(networks.admitOpenEMSNetworkSamples(onePort)).text, /# Hz S RI R 50/);
const result = { contract: "spike/v1", analysis_id: "fixture", status: "completed", model_status: "unvalidated", mode: "em", fields: { openems_far_field: field }, networks: { s_parameters: network }, summary: {}, issues: [], provenance: { solver: "OpenEMS/fixture" } };
const record = { id: "fixture", label: "fixture", result };
assert.deepEqual(viewport.emResultFrequencies(record), [1e9,2e9,3e9]);
const settings = { ...viewport.defaultEMViewportSettings, quantity: "far_e" };
let data = viewport.buildEMViewportData(record, settings); assert.equal(data.values.length,4); assert.equal(data.unit, "V/m peak at 5 m · 1 W incident"); assert.ok(Math.abs(data.values[0]-Math.sqrt(30))<1e-12); assert.ok(Math.abs(data.positionsMm[0][0]-50)<1e-12); assert.equal(data.positionsMm[0][1],20);
assert.equal(viewport.buildEMViewportData(record, {...settings,frequencyIndex:1}), null);
data = viewport.buildEMViewportData(record, {...settings,frequencyIndex:2,component:"z",projection:"phase"}); assert.ok(Math.abs(data.values[0] - (-116.565051177078)) < 1e-9);
const normalized = results.normalizeSolverResult(result); assert.deepEqual(normalized.em_fields.openems_far_field,field); assert.deepEqual(results.normalizeSolverResult(JSON.parse(JSON.stringify(normalized))).em_fields.openems_far_field,field);
assert.equal(optycal.admitOptycalSource(result), null);
const bundle = await build({entryPoints:["src/EMViewportResultManager.tsx"],bundle:true,write:false,format:"esm",platform:"node",external:["react","react-dom","lucide-react","plotly.js-dist-min"],loader:{".css":"empty"}}), file = new URL("../.openems-manager-test.mjs", import.meta.url);
writeFileSync(file,bundle.outputFiles[0].contents);
try { const {default:Manager}=await import(file.href); const html=renderToStaticMarkup(React.createElement(Manager,{records:[record],activeRecordId:"fixture",settings,data:viewport.buildEMViewportData(record,settings),onSelectRecord(){},onSettingsChange(){},onClose(){}})); assert.match(html,/peak V\/m at 5 m/); assert.match(html,/1 W incident/); assert.match(html,/not validated/); const exportButton=(html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g)??[]).find(button=>button.includes("Export Touchstone")); assert.ok(exportButton,"Touchstone export control is present"); assert.match(exportButton,/<button[^>]*disabled=""/,"incomplete networks keep their actual export control disabled, including icon controls"); assert.match(html,/Uncomputed excitation columns: P2/); } finally {unlinkSync(file);}
console.log("OpenEMS display: complex spherical projection, strict shape/normalization admission, frequency subsets, actual network gaps, blocked incomplete Touchstone and history retention passed.");
