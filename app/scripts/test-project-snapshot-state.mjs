import assert from 'node:assert/strict';
import { mergeProjectSnapshot, createResultPackage, readResultPackage, retainOpaqueResultState, isSupportedSavedResult, withoutSavedResults } from '../src/projectSnapshotState.ts';
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
    { id: 'case-pi', type: 'pi', settings: { mode: 'DC IR Drop' }, resultSnapshot: { voltage: [1, 2] } },
    { id: 'case-thermal', type: 'thermal', settings: { ambient_c: 25 } },
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
assert.deepEqual(resultFree.studies[0].cases[0].settings, linked.studies[0].cases[0].settings);
assert.deepEqual(linked.studies[0].cases[0].resultSnapshot, { voltage: [1, 2] }, 'result-free copy must not modify active study');
assert.deepEqual(readResultPackage(JSON.stringify(createResultPackage({ design: linked.design, analysis: {}, studies: linked.studies }))).snapshot.studies, linked.studies);
assert.deepEqual(linked.thermal.scenario.field_result, { grid: [55] }, 'export must not clear live results');
assert.deepEqual(readResultPackage(JSON.stringify(createResultPackage({ ...linked, analysis: {}, emi: {}, thermal: linked.thermal }))).snapshot.thermal, linked.thermal);
const old = readResultPackage(JSON.stringify({ contract: 'spike/result-package/v1', active_result: results[0].bundle, results }));
assert.equal(old.results.result_history.length, 25);
assert.equal(old.snapshot, null, 'legacy result files must not pretend to contain design geometry');
assert.throws(() => createResultPackage({ analysis: {} }), /Run a simulation/);
assert.throws(() => readResultPackage('{"contract":"unrelated"}'), /not a SPIKE/);
console.log('future project fields, stable identities and portable 25-result package round trips passed');
