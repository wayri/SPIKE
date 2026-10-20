// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { admitPartLimits, partLimitReportCsv } = await importTestTypescript("partLimitsModel");
const { restoreEngineeringReviewWorkspace } = await importTestTypescript("engineeringReviewWorkspace");
const { withoutSavedResults } = await importTestTypescript("projectSnapshotState");
const fixture = JSON.parse(readFileSync(new URL("../../examples/part_limits/part-limits.json", import.meta.url)));
const rules = admitPartLimits(fixture.rules);
assert.notEqual(rules, fixture.rules);
assert.throws(() => admitPartLimits([rules[0], rules[0]]));
for (const bad of [{...rules[0],value:Infinity},{...rules[0],value:true},{...rules[0],value:"0x10"},{...rules[0],value:"NaN"},{...rules[0],unit:"mV"},{...rules[0],surprise:true}]) assert.throws(()=>admitPartLimits([bad]));
const saved = {contract:"spike/engineering-review-workspace/v1",scope_sha256:"a".repeat(64),overrides:[],part_limits:rules,result:{part_limit_report:{overall_status:"FAIL"}}};
assert.deepEqual(restoreEngineeringReviewWorkspace(saved), saved);
const stripped = withoutSavedResults({analysis:{engineering_review:saved}});
assert.equal(stripped.analysis.engineering_review.result,null);
assert.equal(stripped.analysis.engineering_review.part_limits[0].value,null);
assert.equal(stripped.analysis.engineering_review.part_limits[0].upper,"5");
assert.equal(stripped.analysis.engineering_review.part_limits[0].evidence_status,"unreviewed");
assert.equal(saved.part_limits[0].value,"4", "result-free export cannot change live evidence");
const report = {overall_status:"FAIL",statement:"Captured inputs only",covered_components:1,fitted_components:2,
  rows:[{...rules[0],label:'=HYPERLINK("bad")',status:"FAIL",comparison_status:"FAIL",stress_percent:"120",headroom_percent:"-20",notes:["quoted, evidence"],reference_designator:"U1"}],
  unchecked_components:[{occurrence_id:"board-b",component_id:"u2",reference:"U2"}]};
const csv=partLimitReportCsv(report);
assert.match(csv,/"Overall status","FAIL"/);
assert.ok(csv.includes('"\'=HYPERLINK(""bad"")"'),"formula-looking text is neutralized");
assert.ok(csv.includes('"\'-20"'),"negative text cannot become a spreadsheet formula");
assert.match(csv,/board-b/);
console.log("Part limits: admission, identity, saved rules, result-free privacy and complete safe CSV reports passed");
