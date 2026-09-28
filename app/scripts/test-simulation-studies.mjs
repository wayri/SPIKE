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
  name: "Cold start", scenario: { ambientC: -20 }, resultSnapshot: { scalar_fields: { voltage_v: [1, 2] } },
});
assert.equal(study.cases[1].scenario.ambientC, -20);
assert.equal(study.cases[0].scenario.ambientC, 25);
assert.equal(study.cases[1].resultSnapshot.scalar_fields.voltage_v[1], 2);
study = updateStudyCase(study, study.cases[1].id, { settings: { tolerance: 1e-6 } });
assert.equal(study.cases[1].resultSnapshot, undefined);
study = updateStudyCase(study, study.cases[1].id, { resultRef: "saved-result-1" });
assert.equal(study.cases[1].resultRef, "saved-result-1");
study = updateStudyCase(study, study.cases[1].id, { scenario: { ambientC: -30 } });
assert.equal(study.cases[1].resultRef, undefined);
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

const collection = updateStudy([study], study.id, { name: "Renamed", notes: "For review" });
assert.equal(collection[0].name, "Renamed");
assert.equal(collection[0].notes, "For review");
assert.equal(study.name, "Converter sweep");
assert.deepEqual(removeStudy(collection, study.id), []);
console.log("simulation study lifecycle, mixed cases, snapshots, and persisted-data admission passed");
