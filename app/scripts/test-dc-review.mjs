import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const admission = ts.transpileModule(readFileSync(new URL("../src/resultAdmission.ts", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const reviewSource = readFileSync(new URL("../src/dcReview.ts", import.meta.url), "utf8")
  .replace('import { resultSolvedForPresentation } from "./resultAdmission";', "");
const reviewJs = ts.transpileModule(reviewSource, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { buildDcReview } = await import(`data:text/javascript;base64,${Buffer.from(`${admission}\n${reviewJs}`).toString("base64")}`);
const sample = (value, net, layer, id) => ({ value, net, layer, element_id: id, source_id: `board-${id}`, source_kind: "track", x_mm: 1, y_mm: 2 });
const result = {
  status: "completed", mode: "dc", model_status: "approximate", summary: { source_voltage_v: 3.3 }, provenance: {},
  scalar_fields: {
    voltage_v: [sample(3.2, "PWR", "F.Cu", "source-near"), sample(3.0, "PWR", "F.Cu", "load-near"), sample(2.5, "OTHER", "F.Cu", "other")],
    voltage_drop_v: [sample(0.1, "PWR", "F.Cu", "source-near"), sample(0.3, "PWR", "F.Cu", "load-near"), sample(0.8, "OTHER", "F.Cu", "other")],
    current_density_a_mm2: [sample(12, "PWR", "F.Cu", "neck"), sample(20, "OTHER", "F.Cu", "other")],
    via_current_density_a_mm2: [sample(18, "PWR", "F.Cu", "via")],
  },
};
const review = buildDcReview(result, "PWR", ["F.Cu"], 250, 15);
assert.equal(review.sourceVoltageV, 3.3);
assert.equal(review.lowestVoltage.element_id, "load-near");
assert.equal(review.highestDrop.value, 0.3);
assert.equal(review.drop.state, "violated");
assert.equal(review.density.state, "within");
assert.equal(review.highestViaDensity.source_id, "board-via");
assert.equal(buildDcReview(result, "PWR", ["B.Cu"], 250, 15).drop.state, "unavailable");
assert.equal(buildDcReview(result, "PWR", [], null, null).drop.state, "unset");
assert.equal(buildDcReview({ ...result, status: "failed" }, "PWR", [], 250, 15), null);
assert.equal(buildDcReview({ ...result, summary: { ...result.summary, solved: false } }, "PWR", [], 250, 15), null);
console.log("DC review: 10 checks passed");
