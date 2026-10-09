// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const moduleUrl = source => `data:text/javascript;base64,${Buffer.from(ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText).toString("base64")}`;

async function sourceModule(path, replacements) {
  let source = readFileSync(new URL(path, import.meta.url), "utf8");
  source = source.replace('"./reportPlotInteraction"', JSON.stringify(plotUrl));
  for (const [from, to] of replacements) source = source.replace(from, to);
  return import(moduleUrl(source));
}

const plotUrl = moduleUrl(readFileSync(new URL("../src/reportPlotInteraction.ts", import.meta.url), "utf8"));
const presentationUrl = moduleUrl(readFileSync(new URL("../src/reportPresentation.ts", import.meta.url), "utf8").replace('"./reportPlotInteraction"', JSON.stringify(plotUrl)));
const studyUrl = moduleUrl(readFileSync(new URL("../src/optycalStudy.ts", import.meta.url), "utf8")
  .replace('import { persistedEnginePython } from "./persistedEnginePython";', 'const persistedEnginePython = () => "";'));
const assertNavigableSections = html => {
  const ids = [...html.matchAll(/<section\b[^>]*\bid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(new Set(ids).size, ids.length, "report section IDs must be unique");
  for (const match of html.matchAll(/href="#([^"]+)"/g)) assert.ok(ids.includes(match[1]), `sidebar target #${match[1]} must exist`);
};
const { optycalReportHtml } = await sourceModule("../src/optycalReport.ts", [
  [/from "\.\/optycalStudy";/, `from ${JSON.stringify(studyUrl)};`],
  [/from "\.\/reportPresentation";/, `from ${JSON.stringify(presentationUrl)};`],
]);
const comparison = {
  contract: "spike/optycal-pattern-comparison/v1", frequency_hz: 1e9,
  theta_deg: [0, 90, 180], phi_deg: [0, 180, 360],
  direct_e_xyz: Array.from({ length: 9 }, () => [[1, 0], [0, 0], [0, 0]]),
  scattered_e_xyz: Array.from({ length: 9 }, () => [[1, 0], [0, 0], [0, 0]]),
  total_e_xyz: Array.from({ length: 9 }, () => [[2, 0], [0, 0], [0, 0]]),
  bare_relative_db: Array(9).fill(0), structure_relative_db: Array(9).fill(0),
  delta_db: Array(9).fill(0), interference_cross_term: Array(9).fill(2),
};
const optycal = optycalReportHtml({ analysis_id: "optycal-fixture", status: "completed", model_status: "unvalidated",
  summary: { setup: { frequency_hz: 1e9, mesh_size_mm: 25 } }, fields: { comparison },
  provenance: { project_name: "antenna.spike", generated_at: "2026-10-03T00:00:00Z", solver: "Optycal/fixture" }, issues: [] });
assert.match(optycal, /href=["']#optycal-setup["']/);
assert.match(optycal, /id=["']optycal-setup["'][^>]*><h2>Study setup/);
assert.match(optycal, /mesh_size_mm/);
assert.match(optycal, /same bare-field peak reference/);
assert.match(optycal, /id=["']optycal-provenance["']/);
assertNavigableSections(optycal);

const { buildSiChannelHtmlReport } = await sourceModule("../src/siChannelResults.ts", [
  [/from "\.\/reportPresentation";/, `from ${JSON.stringify(presentationUrl)};`],
]);
const siResult = { contract: "spike/si-channel-result/v1", analysis_id: "si-fixture", project_name: "channel.spike",
  generated_at: "2026-10-03T00:00:00Z", status: "completed", production_qualified: false, compliance_status: "not_evaluated",
  setup: { source_port: 1, receiver_port: 2, bit_rate_hz: 1e9 },
  network: { port_order: ["source", "receiver"], traces: { S21: [{ frequency_hz: 1e9, magnitude_db: -2, phase_deg: -12 }] } },
  time_domain: { tdr: [], tdt: [] }, eye: { traces: [] }, provenance: { solver: "fixture" }, issues: [{ message: "Fixture warning" }] };
const si = buildSiChannelHtmlReport(siResult);
assert.match(si, /href=["']#si-setup["']/);
assert.match(si, /id=["']si-setup["'][^>]*><h2>Analysis setup/);
assert.match(si, /bit_rate_hz/);
assert.match(si, /id=["']si-s-magnitude["']/);
assert.match(si, /Fixture warning/);
assert.match(si, /not production\/signoff qualified/);
assert.match(si, /does not add de-embedding/);
assertNavigableSections(si);

const unavailable = buildSiChannelHtmlReport({ ...siResult, setup: undefined, summary: undefined, provenance: undefined, issues: undefined });
assert.match(unavailable, /Analysis setup[\s\S]*Unavailable in returned result/);
assert.doesNotMatch(unavailable, />50(?:\.0+)?<|default setup/i);

console.log("Secondary reports share navigable presentation, truthful setup evidence and qualification boundaries.");
