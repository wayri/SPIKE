// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";

const source = readFileSync(resolve(import.meta.dirname, "../src/simulationStudies.ts"), "utf8");
const module = { exports: {} };
new Function("module", "exports", ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText)(module, module.exports);
const {
  STUDY_SCHEMA_VERSION, normalizeStudies, createStudy, updateStudy, removeStudy,
  addStudyCase, duplicateStudyCase, updateStudyCase, removeStudyCase, moveStudyCase,
} = module.exports;

let study = createStudy("  Converter sweep  ");
assert.equal(study.version, STUDY_SCHEMA_VERSION);
assert.equal(study.name, "Converter sweep");
const sourceScenario = { ambientC: 25, load: { amps: 3 } };
const sourceSettings = { solver: "native", limit: 10 };
study = addStudyCase(study, "pi", "Nominal", sourceScenario, sourceSettings, "dc");
sourceScenario.load.amps = 99;
sourceSettings.limit = 99;
assert.equal(study.cases[0].scenario.load.amps, 3);
assert.equal(study.cases[0].settings.limit, 10);
assert.deepEqual(study.tags, []);
assert.equal(study.archived, false);
assert.deepEqual(study.datasets, []);
assert.deepEqual(study.cases[0].runs, []);
assert.deepEqual(study.cases[0].datasetIds, []);
study = addStudyCase(study, "thermal", "Hot enclosure", { ambientC: 60 }, {}, "steady");
study = addStudyCase(study, "pi", "High load", { load: { amps: 8 } }, {}, "transient");
assert.deepEqual(study.cases.map(item => item.type), ["pi", "thermal", "pi"]);
assert.deepEqual(study.cases.map(item => item.mode), ["dc", "steady", "transient"]);
assert.equal(new Set(study.cases.map(item => item.id)).size, 3);

const originalId = study.cases[0].id;
const original = study;
study = duplicateStudyCase(study, originalId);
assert.equal(study.cases[1].name, "Nominal copy");
assert.notEqual(study.cases[1].id, originalId);
assert.notEqual(study.cases[1].scenario, study.cases[0].scenario);
assert.equal(original.cases.length, 3);
study = updateStudyCase(study, study.cases[1].id, {
  name: "Cold start", scenario: { ambientC: -20 }, settings: { designId: "design-a", tolerance: 1e-5 },
  resultSnapshot: { contract: "spike/v1", status: "completed", model_status: "experimental", units: { voltage: "V" }, scalar_fields: { voltage_v: [1, 2] } },
});
assert.equal(study.cases[1].scenario.ambientC, -20);
assert.equal(study.cases[0].scenario.ambientC, 25);
assert.equal(study.cases[1].resultSnapshot.scalar_fields.voltage_v[1], 2);
assert.equal(study.cases[1].runs.length, 1);
assert.equal(study.cases[1].runs[0].facts.contract, "spike/v1");
assert.equal(study.cases[1].runs[0].facts.status, "completed");
assert.equal(study.cases[1].runs[0].facts.modelStatus, "experimental");
assert.equal(study.cases[1].runs[0].facts.designId, undefined, "workspace settings do not become claimed result provenance");
assert.deepEqual(study.cases[1].runs[0].scenario, { ambientC: -20 });
assert.deepEqual(study.cases[1].runs[0].settings, { designId: "design-a", tolerance: 1e-5 });
study = updateStudyCase(study, study.cases[1].id, { settings: { tolerance: 1e-6 } });
assert.equal(study.cases[1].resultSnapshot, undefined);
assert.equal(study.cases[1].runs.length, 1, "setup edits retain immutable recorded runs");
assert.equal(study.cases[1].runs[0].settings.tolerance, 1e-5);
study = updateStudyCase(study, study.cases[1].id, { resultRef: "saved-result-1" });
assert.equal(study.cases[1].resultRef, "saved-result-1");
study = updateStudyCase(study, study.cases[1].id, { scenario: { ambientC: -30 } });
assert.equal(study.cases[1].resultRef, undefined);
study = updateStudy([study], study.id, { tags: [" converter ", "review", "review"], archived: true })[0];
assert.deepEqual(study.tags, ["converter", "review"]);
assert.equal(study.archived, true);
const movedId = study.cases[1].id;
study = moveStudyCase(study, movedId, 99);
assert.equal(study.cases.at(-1).id, movedId);
study = removeStudyCase(study, originalId);
assert.equal(study.cases.length, 3);
assert.ok(!study.cases.some(item => item.id === originalId));
assert.throws(() => addStudyCase(study, "  "), /Simulation type/);

const rows = normalizeStudies({ version: 1, studies: [
  { version: 1, id: "repeat", name: "First", cases: [
    { id: "case", type: "si", mode: "eye", scenario: { voltage: 1 }, settings: {} },
    { id: "case", type: "future-solver", name: "Preserved descriptor", resultRef: "result-1", resultSnapshot: { value: 2 } },
    { type: "" }, null,
  ] },
  { id: "repeat", name: "Second", cases: [] },
] });
assert.equal(rows.length, 2);
assert.equal(new Set([rows[0].id, rows[1].id, ...rows[0].cases.map(item => item.id)]).size, 4);
assert.equal(rows[0].cases.length, 2);
assert.equal(rows[0].cases[1].type, "future-solver");
assert.equal(rows[0].cases[1].resultRef, "result-1");
assert.deepEqual(rows[0].cases[0].settings, {});
assert.deepEqual(normalizeStudies(JSON.parse(JSON.stringify(rows))), rows);
assert.throws(() => normalizeStudies({ version: 2, studies: [] }), /Unsupported/);
assert.throws(() => normalizeStudies([{ version: 2, cases: [] }]), /Unsupported/);

const malformed = JSON.parse('{"studies":[{"cases":[{"type":"pi","scenario":{"__proto__":{"polluted":true},"good":2},"settings":{"bad":null},"resultSnapshot":{"value":7}}]}]}');
const safe = normalizeStudies(malformed)[0].cases[0];
assert.equal(safe.scenario.good, 2);
assert.ok(!Object.hasOwn(safe.scenario, "__proto__"));
assert.equal({}.polluted, undefined);
const cycle = {}; cycle.self = cycle;
assert.deepEqual(normalizeStudies([{ cases: [{ type: "pi", scenario: cycle, resultSnapshot: Number.POSITIVE_INFINITY }] }])[0].cases[0].scenario, {});

const datasetStudy = normalizeStudies([{ id: "datasets", name: "Attached", tags: ["rf"], archived: true, datasets: [
  { id: "source-data", name: "Measured", kind: "csv", mediaType: "text/csv", provenance: "bench", units: { frequency: "Hz" }, createdAt: "2026-01-02T03:04:05Z", resultDerived: false, rawText: "f,s11\n1,-10" },
], cases: [{ id: "linked", type: "si", scenario: {}, settings: {}, datasetIds: ["source-data", "missing"], runs: [
  { id: "run-a", capturedAt: "2026-01-02T03:04:05Z", scenario: { load: 1 }, settings: { solver: "emerge" }, facts: { contract: "spike/v1", status: "completed" }, resultSnapshot: { contract: "spike/v1" } },
] }] }])[0];
assert.equal(datasetStudy.datasets.length, 1);
assert.deepEqual(datasetStudy.cases[0].datasetIds, ["source-data"], "dangling dataset links are removed");
assert.equal(datasetStudy.cases[0].runs[0].facts.status, "completed");
assert.equal(datasetStudy.cases[0].runs[0].association, "workspace-capture");
const withoutDataset = updateStudy([datasetStudy], datasetStudy.id, { datasets: [] })[0];
assert.deepEqual(withoutDataset.cases[0].datasetIds, [], "dataset deletion clears case links");
const duplicatedLinked = duplicateStudyCase(datasetStudy, "linked").cases[1];
assert.deepEqual(duplicatedLinked.datasetIds, ["source-data"], "duplication retains dataset links");
assert.deepEqual(duplicatedLinked.runs, [], "duplication clears recorded run history");
assert.equal(duplicatedLinked.resultSnapshot, undefined);
const definitionsOnly = normalizeStudies([{ ...datasetStudy,
  datasets: datasetStudy.datasets.map(({ payload, rawText, artifactRef, ...definition }) => definition),
  cases: datasetStudy.cases.map(item => ({ ...item, runs: item.runs.map(({ resultSnapshot, resultRef, ...definition }) => definition) })),
}])[0];
assert.equal(definitionsOnly.datasets.length, 1, "result-free dataset definitions survive normalization");
assert.equal(definitionsOnly.cases[0].runs.length, 1, "result-free run definitions survive normalization");
const excessiveRuns = Array.from({ length: 101 }, (_, index) => ({ id: `run-${index}`, capturedAt: "2026-01-02T03:04:05Z", scenario: {}, settings: {}, facts: {}, resultRef: `r-${index}` }));
assert.throws(() => normalizeStudies([{ cases: [{ type: "pi", runs: excessiveRuns }] }]), /exceeds 100 recorded snapshots/);

let nestedFacts = createStudy("Nested result facts");
nestedFacts = addStudyCase(nestedFacts, "em", "EMerge", {}, { designId: "board-a" }, "far-field");
nestedFacts = updateStudyCase(nestedFacts, nestedFacts.cases[0].id, { resultSnapshot: { provider: "emerge", extensionResult: { data: { analysis_result: {
  contract: "spike/v1", status: "completed", model_status: "unvalidated", units: { electric_field: "V/m" }, provenance: { design_id: "board-a", design_digest_sha256: "abc" },
} } } } });
assert.deepEqual(nestedFacts.cases[0].runs[0].facts, { provider: "emerge", contract: "spike/v1", status: "completed", modelStatus: "unvalidated", designId: "board-a", designDigestSha256: "abc", units: { electric_field: "V/m" } });

const repeatedDatasetIds = normalizeStudies([
  { id: "study-a", datasets: [{ id: "d", name: "A", kind: "json", payload: { value: 1 } }], cases: [{ id: "case-a", type: "pi", datasetIds: ["d"] }] },
  { id: "study-b", datasets: [{ id: "d", name: "B", kind: "json", payload: { value: 2 } }], cases: [{ id: "case-b", type: "si", datasetIds: ["d"] }] },
]);
assert.equal(repeatedDatasetIds[0].datasets[0].id, "d");
assert.equal(repeatedDatasetIds[1].datasets[0].id, "d", "dataset identities are scoped to their study");
assert.deepEqual(repeatedDatasetIds.map(row => row.cases[0].datasetIds), [["d"], ["d"]], "same-named dataset links survive in separate studies");
assert.equal(new Set(repeatedDatasetIds.flatMap(row => row.cases.map(item => item.id))).size, 2, "case identities remain global");

const largeDatasetText = "x".repeat(1_100_000);
const multiDatasetStudy = normalizeStudies([{ id: "multi-data", datasets: [
  { id: "one", name: "One", kind: "csv", rawText: largeDatasetText },
  { id: "two", name: "Two", kind: "csv", rawText: largeDatasetText },
], cases: [{ id: "multi-data-case", type: "em", datasetIds: ["one", "two"] }] }])[0];
const multiDatasetRoundTrip = normalizeStudies(JSON.parse(JSON.stringify([multiDatasetStudy])))[0];
assert.equal(multiDatasetRoundTrip.datasets.length, 2, "multiple sub-2 MiB datasets survive a complete study round trip");
assert.deepEqual(multiDatasetRoundTrip.cases[0].datasetIds, ["one", "two"]);

const collection = updateStudy([study], study.id, { name: "Renamed", notes: "For review" });
assert.equal(collection[0].name, "Renamed");
assert.equal(collection[0].notes, "For review");
assert.equal(study.name, "Converter sweep");
assert.deepEqual(removeStudy(collection, study.id), []);
console.log("simulation study lifecycle, mixed cases, snapshots, and persisted-data admission passed");
