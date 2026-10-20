// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { importTestTypescript } from './import-test-typescript.mjs';
const { engineeringReviewScope, restoreEngineeringReviewWorkspace } = await importTestTypescript('engineeringReviewWorkspace');
import { mergeProjectSnapshot, withoutSavedResults } from '../src/projectSnapshotState.ts';

const boards = [{ id: 'a', design: { components: [{id:'r1',reference:'R1'}], metadata: {x:1,y:2} } }];
const scope = await engineeringReviewScope(boards);
assert.equal(scope, await engineeringReviewScope([{id:'a',design:{metadata:{y:2,x:1},components:[{reference:'R1',id:'r1'}]}}]));
assert.notEqual(scope, await engineeringReviewScope([{...boards[0],id:'b'}]));
assert.notEqual(scope, await engineeringReviewScope([{...boards[0],design:{...boards[0].design,metadata:{x:2,y:2}}}]));
const value = {contract:'spike/engineering-review-workspace/v1',scope_sha256:scope,
  overrides:[{occurrence_id:'a',component_id:'r1',unit_cost:'2.10',currency:'USD',dnp:false}],
  result:{contract:'spike/engineering-review-result/v1',summary:{cost:{subtotals_by_currency:{USD:'2.10'}}}}};
const restored = restoreEngineeringReviewWorkspace(JSON.parse(JSON.stringify(value)));
assert.deepEqual(restored,value);
restored.overrides[0].unit_cost='5';
assert.equal(value.overrides[0].unit_cost,'2.10');
assert.equal(restoreEngineeringReviewWorkspace(undefined),null);
for (const bad of [{...value,scope_sha256:'wrong'},{...value,contract:'future/v9'},{...value,result:'not evidence'},
  {...value,overrides:[{component_id:'r1'}]},{...value,overrides:Array(20001).fill(value.overrides[0])}]) {
  assert.throws(()=>restoreEngineeringReviewWorkspace(bad));
}
const saved = mergeProjectSnapshot({analysis:{future:{keep:true}}},{analysis:{engineering_review:value}});
assert.deepEqual(saved.analysis.future,{keep:true});
const noResults = withoutSavedResults(saved);
assert.equal(noResults.analysis.engineering_review.result,null);
assert.deepEqual(noResults.analysis.engineering_review.overrides,value.overrides);
assert.ok(saved.analysis.engineering_review.result,'result-free export leaves live evidence intact');
const cleared = mergeProjectSnapshot(saved,{analysis:{engineering_review:null}});
assert.equal(cleared.analysis.engineering_review,null,'explicit clearing does not resurrect old saved review');
console.log('Engineering review scope, admission, staging and result-free persistence checks passed.');
