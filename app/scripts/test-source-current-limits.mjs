// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import loadDataTable from './load-data-table.mjs';
import { importTestTypescript } from './import-test-typescript.mjs';

const { piSourceCurrentLimitPayload: payload } = await importTestTypescript('piSourceCurrentLimit');
assert.deepEqual(payload({ name: 'Supply' }), {});
assert.deepEqual(payload({ name: 'Supply', currentLimit: '   ' }), {});
assert.deepEqual(payload({ name: 'Supply', currentLimit: '500m' }), { current_limit_a: 0.5 });
for (const value of ['0', '-1', 'NaN', 'Infinity', 'invalid']) {
  assert.throws(() => payload({ name: 'Supply', currentLimit: value }));
}
const rows = [
  { id: 's1', forward_current_a: 1.2, current_limit_a: 1, headroom_a: -0.2, status: 'exceeded' },
  { id: 's2', forward_current_a: 0, current_limit_a: 1, headroom_a: 1, status: 'within_limit' },
  { id: 's3', forward_current_a: null, current_limit_a: null, headroom_a: null, status: 'unlimited' },
];
const { normalizeSolverResult } = await importTestTypescript('analysisResults');
const saved = normalizeSolverResult({ analysis_id: 'capacity', mode: 'dc', status: 'failed', model_status: 'approximate',
  summary: { source_capacity_status: 'infeasible' }, fields: { source_current_results: rows }, issues: [] });
assert.deepEqual(saved.source_current_results, rows);
assert.deepEqual(normalizeSolverResult(JSON.parse(JSON.stringify(saved))).source_current_results, rows,
  'diagnostic rows survive a saved-result JSON round trip');
assert.deepEqual(saved.scalar_fields.voltage_v, [], 'infeasible results do not acquire fabricated fields');

const require = createRequire(import.meta.url), module = { exports: {} };
const code = ts.transpileModule(readFileSync(new URL('../src/SourceCapacityResults.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;
new Function('require', 'module', 'exports', code)(name => name === './DataTable' ? { default: loadDataTable(), __esModule: true } : require(name), module, module.exports);
const View = module.exports.default;
const html = renderToStaticMarkup(React.createElement(View, { status: 'infeasible', rows }));
for (const expected of ['infeasible', 'exceeded', '-0.20000 A', '0.0000 A', 'Unlimited', 'Not determined']) assert.ok(html.includes(expected), expected);
assert.equal(View({ status: 'not_requested', rows }), null);
assert.equal(View({ status: 'unsupported', rows: [] }), null);
console.log('Optional source limits, invalid input, retained results and capacity presentation passed.');
