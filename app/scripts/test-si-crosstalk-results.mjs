// SPDX-License-Identifier: MIT
// Copyright (c) 2026 SigHarmonic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const source = readFileSync(new URL("../src/siChannelResults.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const api = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);
const trace = [{ frequency_hz: 0, transfer_db: -6000, magnitude: 0 }, { frequency_hz: 1e9, transfer_db: -20, magnitude: .1 }];
const result = { contract: "spike/si-channel-result/v1", status: "completed", production_qualified: false,
  crosstalk: { contract: "spike/si-crosstalk-result/v1", mapping: { next: "S(victim.near, aggressor.near)", fext: "S(victim.far, aggressor.near)" },
    next: { trace }, fext: { trace }, loaded: { contract: "spike/si-loaded-crosstalk-result/v1", status: "completed",
      port_map: { aggressor_near: 2, aggressor_far: 0, victim_near: 1, victim_far: 3 },
      frequency_response: { next: { trace }, fext: { trace } },
      time_domain: { status: "completed", time_s: [0, 1e-9, 2e-9], source_v: [0, 1, 0], next_v: [0, -.2, .1], fext_v: [0, .3, -.1] } } } };
const charts = api.normalizeSiChannelResult(result);
assert.match(charts.nextDb.label, /victim.near/);
assert.match(charts.loadedCrosstalkDb[0].label, /port 3.*port 2/);
assert.deepEqual(charts.crosstalkVoltage[1].points.map(p => p.y), [0, -.2, .1]);
assert.equal(api.floorSiDb([charts.nextDb])[0].points[0].y, -160);
assert.equal(charts.nextDb.points[0].y, -6000);
const csv = api.buildSiCrosstalkCsv(result);
assert.match(csv, /-6000/);
assert.match(csv, /V_per_source_V/);
assert.match(csv, /NEXT victim voltage/);
assert.match(api.buildSiChannelHtmlReport(result), /Loaded victim\/source voltage transfer/);
const malformed = structuredClone(result);
malformed.crosstalk.loaded.time_domain.next_v = [0, NaN, 1];
assert.equal(api.normalizeSiChannelResult(malformed).crosstalkVoltage.some(s => s.id === "next_v"), false);
malformed.crosstalk.loaded.time_domain.source_v = [1];
assert.equal(api.normalizeSiChannelResult(malformed).crosstalkVoltage.some(s => s.id === "source_v"), false);
console.log("Crosstalk mapping, voltage alignment, display floor and original CSV assertions passed");
const impedanceResult = structuredClone(result);
impedanceResult.network = { impedance_response: { contract: "spike/si-driving-point-impedance/v1", status: "completed", termination_mode: "matched", ports: [{ port: 0,
  trace: [
    { frequency_hz: 1, status: "finite", real_ohm: 50, imag_ohm: -2, magnitude_ohm: 50.04 },
    { frequency_hz: 2, status: "finite", real_ohm: 50, imag_ohm: -1, magnitude_ohm: 50.01 },
    { frequency_hz: 4, status: "finite", real_ohm: 50, imag_ohm: 1, magnitude_ohm: 50.01 },
    { frequency_hz: 5, status: "finite", gap_before: true, real_ohm: 50, imag_ohm: 2, magnitude_ohm: 50.04 },
  ], invalid_samples: [{ frequency_hz: 3, status: "open_or_pole" }],
  sampled_candidates: [{ kind: "reactance_sign_change", bracket_hz: [2,4] }], candidate_output_truncated: true }] } };
const impedance = api.normalizeSiChannelResult(impedanceResult);
assert.equal(impedance.impedanceReal.length, 3);
assert.deepEqual(impedance.impedanceReal.map(s => s.points.map(p => p.x)), [[1,2], [4], [5]]);
assert.equal(impedance.impedanceCandidates[0].frequencyHz, null);
assert.equal(impedance.impedanceCandidateTruncated, true);
assert.match(api.buildSiChannelHtmlReport(impedanceResult), /Masked poles are gaps/);
assert.match(api.buildSiImpedanceCsv(impedanceResult), /1,5,finite,50,2,50.04,true/);
console.log("Driving impedance masked-gap and bounded candidate display assertions passed");
assert.deepEqual(api.siPlotExtent([{ id: "test", label: "test", points: [{ x: 0, y: -2 }, { x: 8e9, y: 5 }] }]), { xMin: 0, xMax: 8e9, yMin: -2, yMax: 5 });
assert.equal(api.siTickLabel(8e9), "8.00e+9");
assert.equal(api.siTickLabel(-.001), "-0.001");
assert.match(api.buildSiChannelHtmlReport(result), /1.00e\+9/);
console.log("Quantitative plot extent and engineering tick assertions passed");
