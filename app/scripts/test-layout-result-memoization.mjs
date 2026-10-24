// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import ts from "typescript";

const helperSource = readFileSync(new URL("../src/viewportResultFields.ts", import.meta.url), "utf8");
const helperJs = ts.transpileModule(helperSource, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const helper = await import(`data:text/javascript;base64,${Buffer.from(helperJs).toString("base64")}`);
const layoutSource = readFileSync(new URL("../src/LayoutViewport.tsx", import.meta.url), "utf8");

assert.equal(helper.resultFieldLayerSelectionKey(undefined), "[]");
assert.equal(helper.resultFieldLayerSelectionKey(["F.Cu", "In1.Cu"]), '["F.Cu","In1.Cu"]');
assert.notEqual(helper.resultFieldLayerSelectionKey(["F.Cu", "In1.Cu"]), helper.resultFieldLayerSelectionKey(["In1.Cu", "F.Cu"]),
  "selection order remains part of the exact visualization state");

const dependencyLists = [...layoutSource.matchAll(/\}, \[analysisResult, board, resultAnalysisOnly, analysisNetsKey, activeCopperLayer, isolatedNet, visibleLayersKey, ([^\]]+)\]\);/g)]
  .map(match => match[1]);
assert.equal(dependencyLists.length, 2, "field and vector pipelines expose reviewable memo dependencies");
for (const dependencies of dependencyLists) {
  assert.match(dependencies, /selectedResultLayersKey/);
  assert.doesNotMatch(dependencies, /\bresultVisualization\b/,
    "unrelated visualization controls must not invalidate dense result pipelines");
}

const visualization = { visibleResultLayers: ["F.Cu"], animationPlaying: false, animationFrame: 0, boardOpacity: 0.18, fusingAmbientC: 25 };
const samples = Array.from({ length: 50_000 }, (_, index) => ({ layer: index % 3 ? "F.Cu" : "B.Cu", value: index }));
let previousObject = visualization;
let previousLayerKey = helper.resultFieldLayerSelectionKey(visualization.visibleResultLayers);
let legacyScans = 0, narrowedScans = 0;
const scan = () => samples.filter(sample => sample.layer === "F.Cu").reduce((sum, sample) => sum + sample.value, 0);
const started = performance.now();
let checksum = 0;
for (let frame = 1; frame <= 40; frame += 1) {
  const next = { ...visualization, animationFrame: frame, animationPlaying: frame % 2 === 0 };
  if (next !== previousObject) { checksum += scan(); legacyScans += 1; }
  const nextLayerKey = helper.resultFieldLayerSelectionKey(next.visibleResultLayers);
  if (nextLayerKey !== previousLayerKey) { checksum += scan(); narrowedScans += 1; }
  previousObject = next; previousLayerKey = nextLayerKey;
}
const elapsedMs = performance.now() - started;
assert.equal(legacyScans, 40, "whole-object dependency reproduces one dense scan per playback update");
assert.equal(narrowedScans, 0, "unchanged layer selection skips dense field work during playback updates");
assert.ok(checksum > 0);
console.log(JSON.stringify({ samples: samples.length, playbackUpdates: 40, legacyScans, narrowedScans, legacyScanWorkMs: elapsedMs }));
