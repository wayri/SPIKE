import assert from 'node:assert/strict';
import { solverReadinessLabel } from '../src/solverReadinessLabel.ts';
const candidate = { eligible: false, state: 'available', missing: ['far_field'] };
assert.equal(solverReadinessLabel(candidate), 'capability missing');
assert.equal(solverReadinessLabel({ ...candidate, state: 'runtime_verified_adapter_pending' }), 'adapter incomplete');
assert.equal(solverReadinessLabel({ ...candidate, state: 'unavailable' }), 'unavailable');
assert.equal(solverReadinessLabel({ ...candidate, state: 'not_catalogued' }), 'not integrated');
assert.equal(solverReadinessLabel({ ...candidate, state: 'experimental', eligible: true, missing: [] }), 'eligible');
console.log('solver runtime/adapter/capability labels passed');
