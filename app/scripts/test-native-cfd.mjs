// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const js = ts.transpileModule(readFileSync(new URL('../src/nativeCfdPresentation.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const module = { exports: {} };
new Function('module', 'exports', js)(module, module.exports);
const { admitCavityResult, cavityHeatmap } = module.exports;
const request = { n: 16, reynolds: 100 }, n = request.n;
const fields = { x_m: [], y_m: [], u_m_s: [], v_m_s: [], pressure_pa: [] };
for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { fields.x_m.push((i+.5)/n); fields.y_m.push((j+.5)/n); fields.u_m_s.push(3); fields.v_m_s.push(4); fields.pressure_pa.push(i-j); }
const payload = { schema: 'spike-native-cavity-v1', model_status: 'experimental', production_qualified: false, status: 'converged', settings: request,
 diagnostics: { steps: 4240, time: 26.5, dt: .00625, divergence_linf: 3.4e-12, steady_rate_linf: 9.6e-8, poisson_residual_linf: 5.4e-10 }, fields };
const admitted = admitCavityResult(payload, request);
const speed = cavityHeatmap(admitted, 'speed')[0], pressure = cavityHeatmap(admitted, 'pressure')[0];
assert.equal(speed.z.length, n); assert.equal(speed.z[0].length, n); assert.equal(speed.z[4][7], 5);
assert.equal(pressure.z[4][7], 3); assert.equal(speed.x[7], fields.x_m[7]); assert.equal(speed.y[4], fields.y_m[4*n]);
for (const change of [{ schema: 'wrong' }, { production_qualified: true }, { settings: { n:32, reynolds:100 } }, { fields: { ...fields, u_m_s:[NaN] } }, { fields: { ...fields, pressure_pa: Array(n*n).fill(Infinity) } }, { diagnostics: { ...payload.diagnostics, divergence_linf: 1e-2 } }, { fields: { ...fields, x_m: Array(n*n).fill(0) } }, { status: 'failed_to_converge' }]) assert.throws(() => admitCavityResult({ ...payload, ...change }, request));
const failed = admitCavityResult({ ...payload, status: 'failed_to_converge', fields: null }, request);
assert.equal(failed.fields, null); assert.throws(() => cavityHeatmap(failed, 'speed'));
console.log('Native CFD payload, failed-convergence and heatmap admission passed.');
