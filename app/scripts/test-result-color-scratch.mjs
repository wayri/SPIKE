import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { performance } from "node:perf_hooks";
import * as THREE from "three";

const source = await readFile(new URL("../src/BoardViewport.tsx", import.meta.url), "utf8");
assert.equal((source.match(/resultColorScratch\.setHSL/g) ?? []).length, 4,
  "the four audited scalar color sites must use the effect-local scratch color");
assert.match(source, /if \(scalarSamples\.length\) \{\s*const resultColorScratch = new THREE\.Color\(\);/,
  "scratch color must stay inside the scalar overlay effect branch");

const count = 4_000;
const edgeRatios = [-Infinity, -1, -0, 0, .5, 1, 2, Infinity, NaN];
const ratios = Array.from({ length: count }, (_, index) => index < edgeRatios.length
  ? edgeRatios[index] : ((index * 2654435761) >>> 0) / 0xffffffff);

function allocatingColors() {
  let constructions = 0;
  const output = new Float32Array(ratios.length * 3);
  const started = performance.now();
  ratios.forEach((ratio, index) => {
    constructions += 1;
    new THREE.Color().setHSL((1 - ratio) * .62, .92, .54).toArray(output, index * 3);
  });
  return { output, constructions, milliseconds: performance.now() - started };
}

function scratchColors() {
  let constructions = 0;
  const output = new Float32Array(ratios.length * 3);
  constructions += 1;
  const scratch = new THREE.Color();
  const started = performance.now();
  ratios.forEach((ratio, index) => scratch.setHSL((1 - ratio) * .62, .92, .54).toArray(output, index * 3));
  return { output, constructions, milliseconds: performance.now() - started, scratch };
}

const baseline = allocatingColors();
const optimized = scratchColors();
assert.equal(optimized.output.length, baseline.output.length);
for (let index = 0; index < baseline.output.length; index += 1) {
  assert.ok(Object.is(optimized.output[index], baseline.output[index]),
    `color component ${index} changed: ${baseline.output[index]} -> ${optimized.output[index]}`);
}
assert.equal(baseline.constructions, count);
assert.equal(optimized.constructions, 1);

const geometry = new THREE.BufferGeometry();
geometry.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 0], 3));
const material = new THREE.MeshBasicMaterial();
const instances = new THREE.InstancedMesh(geometry, material, 2);
const scratch = optimized.scratch.setHSL(.1, .92, .54);
instances.setColorAt(0, scratch);
const copiedFirst = Array.from(instances.instanceColor.array.slice(0, 3));
scratch.setHSL(.6, .92, .54);
assert.deepEqual(Array.from(instances.instanceColor.array.slice(0, 3)), copiedFirst,
  "setColorAt retained the scratch object instead of copying its components");
instances.setColorAt(1, scratch);
assert.notDeepEqual(Array.from(instances.instanceColor.array.slice(3, 6)), copiedFirst,
  "second copied color should reflect the later scratch value");
geometry.dispose();
material.dispose();

const report = {
  node: process.version,
  colorWritesPerPath: count,
  totalColorWrites: count * 2,
  comparedFloat32Components: baseline.output.length,
  baselineConstructions: baseline.constructions,
  scratchConstructions: optimized.constructions,
  baselineMilliseconds: baseline.milliseconds,
  scratchMilliseconds: optimized.milliseconds,
  ratio: baseline.milliseconds / optimized.milliseconds,
};
const outputPath = process.argv[2];
if (outputPath) {
  const absolute = resolve(outputPath);
  await mkdir(dirname(absolute), { recursive: true });
  await writeFile(absolute, `${JSON.stringify(report, null, 2)}\n`);
}
console.log(`result color scratch: all assertions passed; ${JSON.stringify(report)}`);
