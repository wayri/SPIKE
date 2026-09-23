import assert from 'node:assert/strict';
import { analysisFailure } from '../src/analysisFailure.ts';
const warning = { severity: 'warning', code: 'ZONE_MESH_COARSENED', message: 'used cells to respect max_zone_cells' };
const error = { severity: 'error', code: 'DISCONNECTED', message: 'Load is disconnected.', suggestion: 'Check the selected pad.' };
assert.equal(analysisFailure([warning, error], 'Blocked'), '[DISCONNECTED] Load is disconnected. Check the selected pad.');
assert.equal(analysisFailure([warning], 'Solver failed without an error diagnostic.'), 'Solver failed without an error diagnostic.');
assert.equal(analysisFailure(undefined, 'Blocked'), 'Blocked');
assert.equal(analysisFailure([null, {}, error], 'Blocked'), '[DISCONNECTED] Load is disconnected. Check the selected pad.');
console.log('Analysis failure prioritizes actionable errors, never mesh warnings');
