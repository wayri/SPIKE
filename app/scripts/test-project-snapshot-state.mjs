import assert from 'node:assert/strict';
import { mergeProjectSnapshot, createResultPackage, readResultPackage, retainOpaqueResultState, isSupportedSavedResult, withoutSavedResults } from '../src/projectSnapshotState.ts';
import { normalizeStudies, updateStudyCase } from '../src/simulationStudies.ts';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const normalizerSource = ts.transpileModule(readFileSync(new URL('../src/analysisResults.ts', import.meta.url), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  .replace('"./numericRange"', JSON.stringify(new URL('../src/numericRange.ts', import.meta.url).href));
const { normalizeSolverResult } = await import(`data:text/javascript;base64,${Buffer.from(normalizerSource).toString('base64')}`);

const previous = { project: { id: 'stable-id', name: 'before' }, future_domain: { opaque: [1, 2, 3] },
  design: { metadata: { vendor: 'ODB++', future: { tolerance: .001 } }, models: [{ id: 'm1', enabled: true, vendor_data: { future: 42 } }, { id: 'm2' }] },
  analysis: { future_solver_setup: { formulation: 'future' } } };
const merged = mergeProjectSnapshot(previous, { project: { name: 'after' }, design: { models: [{ id: 'm1', enabled: false }] }, analysis: { latest_result: null } });
assert.equal(merged.project.id, 'stable-id');
assert.equal(merged.project.name, 'after');
assert.deepEqual(merged.future_domain, previous.future_domain);
assert.deepEqual(merged.design.metadata, previous.design.metadata);
assert.deepEqual(merged.design.models, [{ id: 'm1', enabled: false, vendor_data: { future: 42 } }]);
assert.equal(merged.analysis.latest_result, null, 'explicit clearing must remain possible');
assert.deepEqual(merged.analysis.future_solver_setup, previous.analysis.future_solver_setup);

const retainedStudyBase = normalizeStudies([{ id: 'saved-study', name: 'Saved', cases: [{ id: 'saved-case', type: 'pi', mode: 'dc',
  scenario: {}, settings: { load: 1 }, resultSnapshot: { contract: 'spike/v1', values: [1] }, resultRef: 'old-result', runs: [{
    id: 'saved-run', capturedAt: '2026-10-03T00:00:00Z', caseType: 'pi', mode: 'dc', scenario: {}, settings: { load: 1 }, facts: { contract: 'spike/v1' }, resultSnapshot: { contract: 'spike/v1', values: [1] }, resultRef: 'old-run-result',
  }] }] }])[0];
const retainedStudy = { ...retainedStudyBase, cases: retainedStudyBase.cases.map(item => ({ ...item, future_case_field: { keep: true } })) };
const editedStudy = updateStudyCase(retainedStudy, 'saved-case', { settings: { load: 2 } });
assert.equal(editedStudy.cases[0].resultSnapshot, undefined);
const savedAfterInvalidation = JSON.parse(JSON.stringify(mergeProjectSnapshot({ studies: [retainedStudy] }, { studies: [editedStudy] })));
const reloadedAfterInvalidation = normalizeStudies(savedAfterInvalidation.studies)[0];
assert.equal(reloadedAfterInvalidation.cases[0].resultSnapshot, undefined, 'save/reload must not resurrect an invalidated current result');
assert.equal(reloadedAfterInvalidation.cases[0].resultRef, undefined, 'save/reload must not resurrect an invalidated current result reference');
assert.deepEqual(savedAfterInvalidation.studies[0].cases[0].future_case_field, { keep: true }, 'unknown case fields remain preserved');
const strippedRetainedStudy = withoutSavedResults({ studies: [retainedStudy] });
const savedResultFreeStudy = JSON.parse(JSON.stringify(mergeProjectSnapshot({ studies: [retainedStudy] }, strippedRetainedStudy)));
assert.equal(savedResultFreeStudy.studies[0].cases[0].runs[0].resultSnapshot, undefined, 'merge must not resurrect stripped run payloads');
assert.equal(savedResultFreeStudy.studies[0].cases[0].runs[0].resultRef, undefined, 'merge must not resurrect stripped run references');

const results = Array.from({ length: 25 }, (_, i) => ({ id: `result-${i}`, label: `Run ${i}`, bundle: {
  analysis_id: `result-${i}`, scalar_fields: {}, time_series: { times_s: [0, 1], frames: [{ value: i }] }, future_field: { exact: true },
} }));
const supported = { analysis_id: 'supported', mode: 'dc', scalar_fields: { voltage_v: [], voltage_drop_v: [], current_density_a_mm2: [] }, vector_fields: {} };
const opaque = { contract: 'spike/future-engine-result/v9', analysis_id: 'future', opaque_fields: [1, 2, 3] };
const canRender = isSupportedSavedResult;
assert.ok(normalizeSolverResult(opaque), 'generic normalization alone is too permissive to classify future engine results');
assert.equal(canRender(opaque), false);
assert.equal(canRender(supported), true);
const retained = { latest_result: opaque, result_history: [{ id: 'future', bundle: opaque }, { id: 'supported', bundle: supported }] };
const kept = retainOpaqueResultState(retained, { latest_result: null, result_history: [] }, canRender);
assert.deepEqual(kept.latest_result, opaque);
assert.deepEqual(kept.result_history, [{ id: 'future', bundle: opaque }], 'deleted supported rows must not be resurrected');
const cleared = retainOpaqueResultState(retained, { latest_result: null, result_history: [] }, canRender, { clearAll: true });
assert.deepEqual(cleared, { latest_result: null, result_history: [] });
assert.equal(retainOpaqueResultState(retained, { latest_result: null, result_history: [] }, canRender, { clearLatest: true }).latest_result, null);
const replaced = retainOpaqueResultState({ latest_result: opaque }, { latest_result: supported, result_history: [] }, canRender);
assert.deepEqual(replaced.result_history[0].bundle, opaque, 'new runs archive an opaque previous active result');
assert.deepEqual(replaced.latest_result, supported);
const snapshot = { project: { name: 'board' }, design: { source_format: 'spike-normalized', source_board: '{"canonical_design":{}}' },
  analysis: { latest_result: results.at(-1).bundle, result_history: results, result_visualization: { mode: 'voltage', visible: true } },
  thermal: { scenario: { heat_sources: [1] } }, emi: { field_result: { values: [3] } } };
const packed = createResultPackage(snapshot, { board_includes_copper: false });
const reopened = readResultPackage(JSON.stringify(packed));
assert.deepEqual(reopened.snapshot, snapshot);
assert.equal(reopened.results.result_history.length, 25);
assert.deepEqual(reopened.visuals, packed.visuals);
const linked = { ...snapshot, assembly_ir: { boards: ['a', 'b'], connector_mappings: [{ kind: 'connector-mate' }], harnesses: [{ id: 'cable' }] },
  studies: [{ version: 1, id: 'study-1', name: 'Mixed conditions', cases: [
    { id: 'case-pi', type: 'pi', settings: { mode: 'DC IR Drop', coreOptycalSetup: { enabled: true }, optycalSource: { solved_pattern: [1] } }, resultSnapshot: { voltage: [1, 2] }, runs: [
      { id: 'run-1', capturedAt: '2026-10-03T00:00:00Z', scenario: { load: 2 }, settings: { mode: 'DC IR Drop', coreOptycalSetup: { enabled: true }, optycalSource: { solved_pattern: [1] } }, facts: { contract: 'spike/v1', status: 'completed' }, resultSnapshot: { voltage: [1, 2] }, resultRef: 'state/artifacts/result.json' },
    ] },
    { id: 'case-thermal', type: 'thermal', settings: { ambient_c: 25 } },
  ], datasets: [
    { id: 'source-data', name: 'Measured', kind: 'csv', resultDerived: false, rawText: 'f,v\n1,2', provenance: 'lab' },
    { id: 'result-data', name: 'Solved', kind: 'json', resultDerived: true, payload: { values: [3] }, artifactRef: 'state/artifacts/result-data.json', provenance: 'run' },
  ] }],
  thermal: { scenario: { ambient_c: 25, result: { peak_c: 55 }, field_result: { grid: [55] } } },
  emi: { setup: { band: 'test' }, screening: { value: 1 }, field_result: { values: [3] } },
  analysis: { ...snapshot.analysis, si: { suite: { name: 'test' }, latest_channel_result: { eye: [1] } }, pdn_review: { value: 2 } } };
const resultFree = withoutSavedResults(linked);
assert.deepEqual(resultFree.assembly_ir, linked.assembly_ir);
assert.deepEqual(resultFree.analysis.si.suite, linked.analysis.si.suite);
assert.equal(resultFree.analysis.latest_result, null);
assert.deepEqual(resultFree.analysis.result_history, []);
assert.equal(resultFree.analysis.si.latest_channel_result, null);
assert.equal(resultFree.emi.screening, null);
assert.equal(resultFree.thermal.scenario.field_result, null);
assert.equal(resultFree.studies[0].cases[0].resultSnapshot, undefined);
assert.equal(resultFree.studies[0].cases[0].runs[0].resultSnapshot, undefined);
assert.equal(resultFree.studies[0].cases[0].runs[0].resultRef, undefined);
assert.equal(resultFree.studies[0].cases[0].settings.optycalSource, undefined);
assert.deepEqual(resultFree.studies[0].cases[0].settings.coreOptycalSetup, { enabled: true });
assert.equal(resultFree.studies[0].cases[0].runs[0].settings.optycalSource, undefined);
assert.deepEqual(resultFree.studies[0].cases[0].runs[0].settings.coreOptycalSetup, { enabled: true });
assert.equal(resultFree.studies[0].datasets[1].payload, undefined);
assert.equal(resultFree.studies[0].datasets[1].artifactRef, undefined);
assert.deepEqual(resultFree.studies[0].datasets[0], linked.studies[0].datasets[0], 'source datasets stay attached');
assert.equal(resultFree.studies[0].datasets[1].name, 'Solved', 'result-derived dataset definition stays attached');
assert.equal(linked.studies[0].cases[0].settings.optycalSource.solved_pattern[0], 1, 'result-free copy must not modify live Optycal source data');
assert.deepEqual(linked.studies[0].cases[0].resultSnapshot, { voltage: [1, 2] }, 'result-free copy must not modify active study');
assert.deepEqual(linked.studies[0].cases[0].runs[0].resultSnapshot, { voltage: [1, 2] }, 'result-free copy must not modify active run history');
assert.deepEqual(readResultPackage(JSON.stringify(createResultPackage({ design: linked.design, analysis: {}, studies: linked.studies }))).snapshot.studies, linked.studies);
const datasetOnlyPackage = createResultPackage({ design: linked.design, analysis: {}, studies: [{ cases: [], datasets: [
  { id: 'derived', resultDerived: true, kind: 'json', payload: { samples: [1, 2] } },
] }] });
assert.deepEqual(datasetOnlyPackage.project_snapshot.studies[0].datasets[0].payload, { samples: [1, 2] });
assert.deepEqual(linked.thermal.scenario.field_result, { grid: [55] }, 'export must not clear live results');
assert.deepEqual(readResultPackage(JSON.stringify(createResultPackage({ ...linked, analysis: {}, emi: {}, thermal: linked.thermal }))).snapshot.thermal, linked.thermal);
const old = readResultPackage(JSON.stringify({ contract: 'spike/result-package/v1', active_result: results[0].bundle, results }));
assert.equal(old.results.result_history.length, 25);
assert.equal(old.snapshot, null, 'legacy result files must not pretend to contain design geometry');
assert.throws(() => createResultPackage({ analysis: {} }), /Run a simulation/);
assert.throws(() => readResultPackage('{"contract":"unrelated"}'), /not a SPIKE/);
console.log('future project fields, stable identities and portable 25-result package round trips passed');
const assemblyStudy = { assembly_ir: { extensions: { 'spike.multiboard-studies': { pi: { request: { source: 12 }, result: { status: 'completed' } } } } } };
const strippedStudy = withoutSavedResults(assemblyStudy);
assert.deepEqual(strippedStudy.assembly_ir.extensions['spike.multiboard-studies'].pi.request, { source: 12 });
assert.equal(strippedStudy.assembly_ir.extensions['spike.multiboard-studies'].pi.result, undefined);
assert.equal(assemblyStudy.assembly_ir.extensions['spike.multiboard-studies'].pi.result.status, 'completed');
