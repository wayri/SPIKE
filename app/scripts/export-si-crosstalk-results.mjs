// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
/** Export actual worker JSON through the application's renderer; no solver runs. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { resolve, join } from "node:path";
import ts from "typescript";

const args = process.argv.slice(2);
if (args.length !== 4 || args[0] !== "--input" || args[2] !== "--output") {
  console.error("Usage: node scripts/export-si-crosstalk-results.mjs --input actual-result.json --output new-directory");
  process.exit(2);
}
const input = resolve(args[1]);
const outputDirectory = resolve(args[3]);
if (statSync(input).size > 64 * 1024**2) throw new Error("Result exceeds the 64 MiB local export budget.");
const bytes = readFileSync(input);
const original = JSON.parse(bytes.toString("utf8"));
const standalone = original.contract === "spike/si-loaded-crosstalk-result/v1";
if (standalone && original.status !== "completed") throw new Error("Loaded result is not completed.");
// Display adaptation only: no frequency/time samples or physical claims added.
const result = standalone ? {
  contract: "spike/si-channel-result/v1", status: "completed", production_qualified: false,
  compliance_status: "not_evaluated", crosstalk: { loaded: original },
} : original;
const rendererPath = new URL("../src/siChannelResults.ts", import.meta.url);
const renderer = readFileSync(rendererPath, "utf8");
const javascript = ts.transpileModule(renderer, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const api = await import(`data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`);
const charts = api.normalizeSiChannelResult(result);
let html = api.buildSiChannelHtmlReport(result);
if (standalone) html = html.replaceAll("Geometry-derived SI channel", "Loaded network crosstalk");
if (original.measurement_only === true) html = html.replaceAll("Geometry-derived SI channel", "Measured fixture SI response");
const attribution = original.measurement_only === true ? [original.provenance?.title,
  original.provenance?.authors?.join(", "), original.provenance?.dataset_doi,
  original.provenance?.license, original.provenance?.license_url,
  "SPIKE derived visualization; retained data may be display-decimated. No geometric correlation qualification."].filter(Boolean).join("\n") : "";
if (attribution) {
  const escape = text => text.replace(/[&<>"']/g, value => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[value]));
  html = html.replace("</header>", `<h2>Measured-data attribution</h2><pre>${escape(attribution)}</pre></header>`);
}
html = html.replace("<h2>Qualification boundary</h2>", "<h2>Qualification boundary</h2><p>Charts may be display-decimated. CSV contains the worker-retained samples, which may themselves be decimated; it is not a full solver-history export.</p>");
const csv = api.buildSiCrosstalkCsv(result);
const impedanceCsv = api.buildSiImpedanceCsv(result);
const series = [charts.nextDb, charts.fextDb, ...charts.crosstalkLinear,
  ...charts.loadedCrosstalkDb, ...charts.loadedCrosstalkLinear, ...charts.crosstalkVoltage].filter(Boolean);
assert.ok(series.some(item => item.points.length), "No actual crosstalk samples to export.");
const expectedRows = series.reduce((sum, item) => sum + item.points.length, 0);
// Labels can contain newlines, so count parsed CSV records rather than lines.
let quoted = false;
let records = 0;
for (let i = 0; i < csv.length; i += 1) {
  if (csv[i] === '"') {
    if (quoted && csv[i + 1] === '"') i += 1;
    else quoted = !quoted;
  } else if (csv[i] === "\n" && !quoted) records += 1;
}
assert.equal(records, expectedRows + 1);
assert.equal(quoted, false);
for (const item of series) for (const point of item.points) {
  assert.ok(csv.includes(`,${String(point.x)},${String(point.y)}\r\n`), "A retained value changed during CSV export.");
}
assert.match(html, /Loaded victim\/source voltage transfer|NEXT \/ FEXT/);
const sha = value => createHash("sha256").update(value).digest("hex");
assert.equal(sha(readFileSync(input)), sha(bytes), "Source result changed during export.");
assert.equal(readFileSync(rendererPath, "utf8"), renderer, "Renderer changed during export.");
mkdirSync(outputDirectory); // Do not overwrite earlier immutable evidence.
writeFileSync(join(outputDirectory, "crosstalk.html"), html, { flag: "wx" });
writeFileSync(join(outputDirectory, "crosstalk.csv"), csv, { flag: "wx" });
writeFileSync(join(outputDirectory, "impedance.csv"), impedanceCsv, { flag: "wx" });
if (attribution) writeFileSync(join(outputDirectory, "ATTRIBUTION.txt"), attribution, { flag: "wx" });
const manifest = {
  contract: "spike/si-crosstalk-export/v1", source_path: input,
  source_contract: original.contract, source_sha256: sha(bytes), renderer_sha256: sha(renderer),
  display_only_wrapper: standalone, production_qualified: false,
  measured_data_attribution: attribution || null,
  fidelity: "exact worker-retained values; worker and chart decimation may apply",
  csv_sample_rows: expectedRows,
  series: series.map(item => ({ id: item.id, label: item.label, samples: item.points.length,
    first: item.points[0] ?? null, last: item.points.at(-1) ?? null })),
  files: { "crosstalk.html": sha(html), "crosstalk.csv": sha(csv), "impedance.csv": sha(impedanceCsv) },
};
writeFileSync(join(outputDirectory, "manifest.json"), JSON.stringify(manifest, null, 2), { flag: "wx" });
console.log(JSON.stringify({ status: "completed", outputDirectory, retained_sample_rows: expectedRows,
  exported_series: series.length, source_sha256: manifest.source_sha256 }));
