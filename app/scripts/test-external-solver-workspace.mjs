// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { restoreExternalSolverWorkflows, isExternalSolverId } from '../src/externalSolverWorkspace.ts';
import { withoutSavedResults, mergeProjectSnapshot } from '../src/projectSnapshotState.ts';
const input = { 'spike.xyce-suite': { parameters: { netlist: 'owned fixture', libraries: [] }, result: { contract: 'spike/extension-result/v1', data: { solved: true, waveforms: [{ rows: [[0,1],[1,2]] }] } } }, 'unknown': { result: { solved: true } } };
const restored = restoreExternalSolverWorkflows(input);
assert.deepEqual(Object.keys(restored), ['spike.xyce-suite']);
assert.notEqual(restored['spike.xyce-suite'].parameters, input['spike.xyce-suite'].parameters);
assert.deepEqual(restoreExternalSolverWorkflows(null), {});
assert.equal(isExternalSolverId('spike.palace-suite'), true);
assert.equal(isExternalSolverId('palace'), false);
const snapshot = { analysis: { extension_workflows: { native_solvers: restored } } };
const saved = mergeProjectSnapshot({}, snapshot);
assert.equal(restoreExternalSolverWorkflows(saved.analysis.extension_workflows.native_solvers)['spike.xyce-suite'].result.data.solved, true);
const setupOnly = withoutSavedResults(saved);
assert.equal(setupOnly.analysis.extension_workflows.native_solvers['spike.xyce-suite'].result, null);
assert.equal(setupOnly.analysis.extension_workflows.native_solvers['spike.xyce-suite'].parameters.netlist, 'owned fixture');
assert.equal(saved.analysis.extension_workflows.native_solvers['spike.xyce-suite'].result.data.solved, true);
console.log('External solver setup/result persistence and setup-only export passed.');
