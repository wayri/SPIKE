// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { build } from "esbuild";
const load = async path => {
  const result = await build({ entryPoints: [path], bundle: true, write: false, format: "esm", platform: "node" });
  return import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
};
const { createProjectPackage, parseProjectPackage } = await load("src/projectPackage.ts");
const { mergeProjectSnapshot, withoutSavedResults, createResultPackage } = await load("src/projectSnapshotState.ts");
const { coerceIbisDeploymentWorkspace, coerceSpatialDeploymentWorkspace } = await load("src/siDeploymentWorkspace.ts");
const { parseNormalizedBoard } = await load("src/normalizedBoard.ts");
const json = async path => JSON.parse(await readFile(path, "utf8"));
const request = await json("../examples/si/ibis_driver_receiver/request.json");
const candidate = await json("../examples/si/spatial_crosstalk/samples.json");
const normalized = await readFile("../examples/si/spatial_crosstalk/board.spike-design.json", "utf8");
assert.equal(parseNormalizedBoard(normalized).tracks.length, 2, "bundled board opens through the actual normalized viewport importer");
const ibis = coerceIbisDeploymentWorkspace({ contract: "spike/ibis-deployment-workspace/v1", request, result: null, resultRequest: null, draft: "" });
const spatial = coerceSpatialDeploymentWorkspace({ contract: "spike/si-spatial-workspace/v1", candidate, fileName: "samples.json", aggressor: candidate.binding.aggressorNetId,
  victim: candidate.binding.victimNetId, requestId: candidate.binding.requestId, pairDraft: await readFile("../examples/si/spatial_crosstalk/solver.json", "utf8"), settings: {} });
assert.ok(ibis); assert.ok(spatial);
const snapshot = createProjectPackage({ project: { name: "SI deployment" }, design: { source_file: "pair.spike-design.json", source_format: "spike-normalized", source_board: normalized,
  canonical_design: JSON.parse(normalized).canonical_design }, analysis: { si: { deployment_workspaces: { ibis, spatial } } } });
const reopened = parseProjectPackage(JSON.stringify(snapshot)).project;
assert.deepEqual(coerceIbisDeploymentWorkspace(reopened.analysis.si.deployment_workspaces.ibis), ibis);
assert.deepEqual(coerceSpatialDeploymentWorkspace(reopened.analysis.si.deployment_workspaces.spatial), spatial);
assert.equal(reopened.analysis.si.deployment_workspaces.spatial.capture, undefined, "no admitted display authority is persisted");
assert.equal(reopened.analysis.si.deployment_workspaces.ibis.trusted, undefined, "no native execution trust is persisted");
const previous = structuredClone(snapshot);
previous.analysis.si.deployment_workspaces.ibis.request.driver.removed_electrical_option = "old";
const merged = mergeProjectSnapshot(previous, snapshot);
assert.equal(merged.analysis.si.deployment_workspaces.ibis.request.driver.removed_electrical_option, undefined, "removed request data cannot return from opaque prior save state");
const withEvidence = structuredClone(snapshot);
withEvidence.analysis.si.deployment_workspaces.ibis.result = { contract: "spike/ibis-behavioral-result/v1", status: "failed", diagnostics: [] };
withEvidence.analysis.si.deployment_workspaces.ibis.resultRequest = request;
assert.ok(createResultPackage(withEvidence).project_snapshot, "standalone SI evidence is eligible for result export");
const without = withoutSavedResults(withEvidence);
assert.equal(without.analysis.si.deployment_workspaces.ibis.result, null);
assert.equal(without.analysis.si.deployment_workspaces.ibis.resultRequest, null);
assert.equal(without.analysis.si.deployment_workspaces.spatial.candidate, null);
assert.deepEqual(without.analysis.si.deployment_workspaces.ibis.request, request, "save without results retains the solver setup");
assert.equal(withEvidence.analysis.si.deployment_workspaces.spatial.candidate.contract, "spike/si-spatial-noise/v1", "stripping does not mutate retained evidence");
console.log("SI deployment integration: actual example importer, project save/reopen, authoritative source replacement and save-without-results passed.");
