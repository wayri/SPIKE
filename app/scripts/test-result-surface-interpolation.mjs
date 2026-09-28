// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/resultSurfaceInterpolation.ts", import.meta.url), "utf8")
  .replace('import type { ScalarSample } from "./analysisResults";', "");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const surface = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);
const sample = (value, vertices, options = {}) => ({ x_mm: options.x ?? vertices[0][0], y_mm: options.y ?? vertices[0][1], value, vertices_mm: vertices, net: options.net ?? "VCC", layer: options.layer ?? "F.Cu" });
const a = sample(0, [[0, 0, 0], [1, 0, 0], [0, 1, 0]], { x: 0, y: 0 });
const cornerOnly = sample(10, [[0, 0, 0], [-1, 0, 0], [0, -1, 0]], { x: -1, y: -1 });
let values = surface.sharedVertexValues([a, cornerOnly]);
assert.equal(values.get(a)[0], 0, "a corner-only contact must not join smoothing patches");
assert.equal(values.get(cornerOnly)[0], 10);

const edgeNeighbor = sample(10, [[1, 0, 0], [0, 0, 0], [1, -1, 0]], { x: 1, y: -1 });
values = surface.sharedVertexValues([a, edgeNeighbor]);
assert.ok(values.get(a)[0] > 0 && values.get(a)[0] < 10);
assert.equal(values.get(a)[0], values.get(edgeNeighbor)[1], "both sides of a shared edge must receive one value");
assert.equal(values.get(a)[1], values.get(edgeNeighbor)[0]);
const otherNet = { ...edgeNeighbor, net: "GND" };
const otherLayer = { ...edgeNeighbor, layer: "B.Cu" };
assert.equal(surface.sharedVertexValues([a, otherNet]).get(a)[0], 0);
assert.equal(surface.sharedVertexValues([a, otherLayer]).get(a)[0], 0);

const fan = vertices => Array.from({ length: Math.max(0, vertices.length - 2) }, (_, index) => [0, index + 1, index + 2]).flat();
const hugeVertices = Array.from({ length: 1002 }, (_, index) => [Math.cos(index / 1002 * Math.PI * 2), Math.sin(index / 1002 * Math.PI * 2), 0]);
const huge = sample(4, hugeVertices);
const before = structuredClone(huge);
let bounded = surface.smoothDisplaySamplesWithBudget([huge], fan, 12);
assert.ok(bounded.samples.length <= 12); assert.equal(bounded.fallbackPoints, 1); assert.equal(bounded.samples[0].vertices_mm, undefined);
assert.equal(bounded.omittedGeometry, 1000); assert.deepEqual(huge, before, "reconstruction must not mutate solver samples");
const many = Array.from({ length: 50 }, (_, index) => sample(index, [[index, 0, 0], [index + .8, 0, 0], [index, .8, 0]]));
bounded = surface.smoothDisplaySamplesWithBudget(many, fan, 10);
assert.equal(bounded.samples.length, 10); assert.equal(bounded.omittedFallbacks, 40); assert.ok(bounded.samples.every(item => item.vertices_mm === undefined));
assert.equal(surface.smoothDisplaySamples(many, fan, 10).length, 10, "compatibility wrapper must keep the hard budget");

assert.equal(surface.resultSampleForHit(many, 1, [4, 7, 9]), many[7]);
assert.equal(surface.resultSampleForHit(many, 1, [4, 7, 9], 3), many[3]);
assert.equal(surface.resultSampleForHit(many, 99, [4]), undefined);
assert.equal(surface.resultHitOccluded(10, 9, 1, true), true);
assert.equal(surface.resultHitOccluded(10, 9, .5, true), false);
assert.equal(surface.resultHitOccluded(10, 9, 1, false), false);
assert.equal(surface.resultHitOccluded(10, 10, 1, true), false);
console.log("Result surface topology, hard budget, fallbacks, immutability, hit mapping and occlusion passed.");
