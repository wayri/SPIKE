// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";

function compile(relativePath, requireFn = () => { throw new Error("Unexpected import"); }) {
  const source = readFileSync(resolve(import.meta.dirname, relativePath), "utf8"), module = { exports: {} };
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  new Function("module", "exports", "require", output)(module, module.exports, requireFn);
  return module.exports;
}

const studies = compile("../src/simulationStudies.ts");
const {
  MAX_STUDY_ATTACHMENT_BYTES, prepareStudyDataset, exportStudyDataset, parseStudyCsv,
  MAX_STUDY_DOCUMENT_BYTES, preflightStudyDocument, preflightStudyRunCapture, preflightStudyDatasetUpdate,
  comparisonCompatibility, studyMatchesQuery, cloneImportedStudies,
} = compile("../src/studyWorkspaceModel.ts", specifier => {
  if (specifier === "./simulationStudies") return studies;
  throw new Error(`Unexpected import ${specifier}`);
});

const csv = 'frequency_hz,label,value\r\n1000,"port, one",-12\r\n2000,"quoted ""port""",-9';
assert.deepEqual(parseStudyCsv(csv), { columns: ["frequency_hz", "label", "value"], rows: [
  ["1000", "port, one", "-12"], ["2000", 'quoted "port"', "-9"],
] });
assert.throws(() => parseStudyCsv('a,b\n"unterminated'), /unterminated/);
assert.throws(() => parseStudyCsv("a,b\n1"), /same number/);

const csvDataset = prepareStudyDataset(csv, { name: "S parameters", format: "csv", provenance: "bench A",
  units: { frequency_hz: "Hz", value: "dB" }, createdAt: "2026-10-03T10:30:00Z" });
assert.equal(csvDataset.kind, "csv");
assert.equal(csvDataset.rawText, csv, "CSV import retains exact source text");
assert.deepEqual(csvDataset.units, { frequency_hz: "Hz", value: "dB" });
assert.equal(exportStudyDataset(csvDataset).contents, csv);

const jsonDataset = prepareStudyDataset('{"contract":"lab/fixture/v1","values":[1,2]}', {
  name: "Fixture / A", format: "json", provenance: "lab", resultDerived: true,
});
assert.equal(jsonDataset.payload.contract, "lab/fixture/v1");
assert.equal(jsonDataset.resultDerived, true);
assert.equal(exportStudyDataset(jsonDataset).fileName, "Fixture-A.json");
const reportedUnits = prepareStudyDataset('{"contract":"spike/data-view/v1","units":["Hz","dB"],"x_unit":"GHz","y_unit":"dB"}', {
  name: "Reported units", format: "json", provenance: "script",
});
assert.deepEqual(reportedUnits.units, { reported: ["Hz", "dB"], x_unit: "GHz", y_unit: "dB" });
const provenanceUnits = prepareStudyDataset('{"contract":"spike/v1","provenance":{"units":{"voltage":"V"}}}', {
  name: "Provenance units", format: "json", provenance: "solver",
});
assert.deepEqual(provenanceUnits.units, { voltage: "V" });
const overriddenUnits = prepareStudyDataset('{"units":{"voltage":"mV"}}', {
  name: "Reviewed units", format: "json", provenance: "review", units: { voltage: "V" },
});
assert.deepEqual(overriddenUnits.units, { voltage: "V" }, "explicit attachment units take precedence over payload metadata");
assert.throws(() => prepareStudyDataset("{".repeat(2), { name: "bad", format: "json", provenance: "" }), /not valid JSON/);
assert.throws(() => prepareStudyDataset("x".repeat(MAX_STUDY_ATTACHMENT_BYTES + 1), { name: "large", format: "csv", provenance: "" }), /2 MiB/);
assert.equal(preflightStudyDatasetUpdate([csvDataset, jsonDataset]).ok, true);

assert.deepEqual(preflightStudyRunCapture({ contract: "spike/v1", values: [1, 2] }).ok, true);
const cyclic = {}; cyclic.self = cyclic;
assert.deepEqual(preflightStudyRunCapture(cyclic).ok, false);
const fullCase = { id: "case", type: "pi", mode: "dc", name: "full", notes: "", scenario: {}, settings: {}, resultSnapshot: {}, datasetIds: [],
  runs: Array.from({ length: 100 }, (_, index) => ({ id: String(index), capturedAt: "2026-10-03T00:00:00Z", association: "workspace-capture", caseType: "pi", mode: "dc", scenario: {}, settings: {}, facts: {}, resultRef: String(index) })) };
assert.match(preflightStudyRunCapture({ value: 1 }, undefined, fullCase).error, /100 recorded snapshots/);

const baseRun = { id: "a", capturedAt: "2026-10-03T00:00:00Z", association: "workspace-capture", caseType: "em", mode: "far-field", scenario: {}, settings: {}, resultSnapshot: {}, facts: {
  contract: "spike/v1", designId: "d1", designDigestSha256: "abc", units: { voltage: "V", current: "A" },
} };
assert.deepEqual(comparisonCompatibility([baseRun, { ...baseRun, id: "b", facts: { ...baseRun.facts, units: { current: "A", voltage: "V" } } }]), { compatible: true, reasons: [] });
const incompatible = comparisonCompatibility([baseRun, { ...baseRun, id: "c", facts: { contract: "other/v1", designId: "d2", designDigestSha256: "def", units: { voltage: "mV" } } }]);
assert.equal(incompatible.compatible, false);
assert.deepEqual(incompatible.reasons, ["Result contracts differ.", "Source design bindings differ.", "Result units differ."]);
assert.equal(comparisonCompatibility([baseRun]).compatible, false);
const unknown = comparisonCompatibility([{ ...baseRun, id: "u1", facts: {} }, { ...baseRun, id: "u2", facts: {} }]);
assert.equal(unknown.compatible, false);
assert.deepEqual(unknown.reasons, ["Compatibility not established: a result contract is not reported.", "Compatibility not established: result units are not reported."]);

const study = { version: 1, id: "s", name: "Antenna sweep", notes: "match review", tags: ["RF"], archived: false,
  datasets: [csvDataset], cases: [{ id: "c", type: "em", mode: "far field", name: "Open enclosure", notes: "", scenario: {}, settings: {}, runs: [], datasetIds: [] }] };
assert.equal(studyMatchesQuery(study, "bench a"), true);
assert.equal(studyMatchesQuery(study, "OPEN enclosure"), true);
assert.equal(studyMatchesQuery(study, "thermal"), false);

const importedSource = studies.normalizeStudies([{ version: 1, id: "study-source", name: "Imported", datasets: [{
  ...csvDataset, id: "dataset-source",
}], cases: [{ id: "case-source", type: "em", mode: "far-field", name: "Case", notes: "", scenario: {}, settings: {}, datasetIds: ["dataset-source"], runs: [{
  ...baseRun, id: "run-source",
}] }] }]);
const firstImport = cloneImportedStudies(importedSource), secondImport = cloneImportedStudies(importedSource);
for (const imported of [firstImport[0], secondImport[0]]) {
  assert.notEqual(imported.id, "study-source");
  assert.notEqual(imported.cases[0].id, "case-source");
  assert.notEqual(imported.datasets[0].id, "dataset-source");
  assert.notEqual(imported.cases[0].runs[0].id, "run-source");
  assert.deepEqual(imported.cases[0].datasetIds, [imported.datasets[0].id], "fresh dataset identity is remapped in the case link");
  assert.equal(imported.cases[0].runs.length, 1, "recorded snapshot history survives import cloning");
}
assert.notEqual(firstImport[0].id, secondImport[0].id);
assert.notEqual(firstImport[0].cases[0].id, secondImport[0].cases[0].id);
assert.notEqual(firstImport[0].datasets[0].id, secondImport[0].datasets[0].id);
assert.notEqual(firstImport[0].cases[0].runs[0].id, secondImport[0].cases[0].runs[0].id);
assert.equal(MAX_STUDY_DOCUMENT_BYTES, 256 * 1024 * 1024);
assert.equal(preflightStudyDocument(firstImport[0]).ok, true);

console.log("study datasets, CSV fidelity, capture preflight, search and comparison compatibility passed");
