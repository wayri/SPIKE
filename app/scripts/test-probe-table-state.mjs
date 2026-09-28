// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { assignProbeReferenceIds, normalizeProbeTableState } from '../src/probeTableState.ts';
import { mergeProjectSnapshot } from '../src/projectSnapshotState.ts';
const aliases=assignProbeReferenceIds(['pad/first','pad/second'],{},[]);
assert.deepEqual(Object.values(aliases),['P1','P2']);
const after=assignProbeReferenceIds(['pad/second','new'],aliases,[{id:'P3',name:'reserved',formula:'1'}]);
assert.equal(after['pad/second'],'P2'); assert.equal(after.new,'P4');
const formulas=[{id:'C1',name:'Drop',formula:'P1.voltage-P2.voltage'}];
const packageState=mergeProjectSnapshot({probe_table:{future:{keep:true}}},{probe_table:{calculated_rows:formulas,reference_ids:after}});
const reopened=normalizeProbeTableState(JSON.parse(JSON.stringify(packageState)).probe_table);
assert.deepEqual(reopened,{calculatedRows:formulas,referenceIds:after});
assert.ok(packageState.probe_table.future.keep);
assert.deepEqual(normalizeProbeTableState(null),{calculatedRows:[],referenceIds:{}});
assert.equal(normalizeProbeTableState({calculated_rows:[null,{}]}).calculatedRows.length,0);
console.log('Probe table state: stable IDs, deletion, collision and save/reopen passed');
