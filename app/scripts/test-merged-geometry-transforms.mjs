// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { mergeTransformedGeometries } from '../src/mergedGeometryTransforms.ts';

function geometryBytes(geometry) {
  const attributeBytes = Object.values(geometry.attributes)
    .reduce((sum, attribute) => sum + (attribute.array?.byteLength ?? 0), 0);
  return attributeBytes + (geometry.index?.array?.byteLength ?? 0);
}

function oracleMerge(entries) {
  const clones = [];
  try {
    for (const entry of entries) {
      const clone = entry.geometry.clone();
      clones.push(clone);
      clone.applyMatrix4(entry.matrix);
    }
    return mergeGeometries(clones, false);
  } finally {
    clones.forEach(clone => clone.dispose());
  }
}

function geometryFixture(vertices = 12, indexed = true) {
  const geometry = new THREE.BufferGeometry();
  const position = new Float32Array(vertices * 3);
  const normal = new Float32Array(vertices * 3);
  const tangent = new Float32Array(vertices * 4);
  const uv = new Float32Array(vertices * 2);
  const custom = new Uint16Array(vertices * 2);
  for (let index = 0; index < vertices; index++) {
    position.set([index * .25, (index % 3) * .5, (index % 5) * -.125], index * 3);
    normal.set(new THREE.Vector3(index + 1, 2 - index, 3).normalize().toArray(), index * 3);
    tangent.set([1, 0, 0, index % 2 ? -1 : 1], index * 4);
    uv.set([index / vertices, 1 - index / vertices], index * 2);
    custom.set([index, 65535 - index], index * 2);
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(position, 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(normal, 3));
  geometry.setAttribute('tangent', new THREE.BufferAttribute(tangent, 4));
  geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  geometry.setAttribute('customPair', new THREE.BufferAttribute(custom, 2));
  if (indexed) geometry.setIndex(Array.from({ length: vertices }, (_, index) => index));
  return geometry;
}

const matrices = [
  new THREE.Matrix4().makeTranslation(4, -2, 7),
  new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(.4, -.7, 1.1))
    .scale(new THREE.Vector3(2, .5, 1.25)),
  new THREE.Matrix4().makeScale(-1, 1.5, .75).setPosition(-3, 5, 2),
];

function assertExactGeometry(actual, expected) {
  assert.equal(Boolean(actual?.index), Boolean(expected?.index));
  assert.deepEqual([...actual?.index?.array ?? []], [...expected?.index?.array ?? []]);
  assert.deepEqual(Object.keys(actual.attributes), Object.keys(expected.attributes));
  for (const name of Object.keys(actual.attributes)) {
    const left = actual.getAttribute(name);
    const right = expected.getAttribute(name);
    assert.equal(left.itemSize, right.itemSize);
    assert.equal(left.normalized, right.normalized);
    assert.equal(left.array.constructor, right.array.constructor);
    const leftBytes = Buffer.from(left.array.buffer, left.array.byteOffset, left.array.byteLength);
    const rightBytes = Buffer.from(right.array.buffer, right.array.byteOffset, right.array.byteLength);
    assert.equal(Buffer.compare(leftBytes, rightBytes), 0, `${name} differs`);
  }
  assert.deepEqual(actual.groups, expected.groups);
  assert.deepEqual(actual.drawRange, expected.drawRange);
  assert.equal(actual.boundingBox, expected.boundingBox);
  assert.equal(actual.boundingSphere, expected.boundingSphere);
  assert.deepEqual(actual.userData, expected.userData);
}

// Fast path: exact indexed/nonindexed bytes, transforms, metadata and immutable shared sources.
for (const indexed of [true, false]) {
  const source = geometryFixture(12, indexed);
  source.userData = { future: { nested: true }, identity: { token: 'source' } };
  source.addGroup(0, 3, 2);
  source.setDrawRange(1, 5);
  const savedAttributes = Object.fromEntries(
    Object.entries(source.attributes).map(([name, value]) => [name, [...value.array]]),
  );
  const entries = matrices.map(matrix => ({ geometry: source, matrix }));
  const expected = oracleMerge(entries);
  const actual = mergeTransformedGeometries(entries);
  assertExactGeometry(actual, expected);
  assert.notEqual(actual.userData, source.userData);
  actual.userData.changed = true;
  assert.equal(source.userData.changed, undefined);
  for (const [name, values] of Object.entries(savedAttributes)) {
    assert.deepEqual([...source.getAttribute(name).array], values);
  }
  expected.dispose();
  actual.dispose();
  source.dispose();
}

// Conservative fallback layouts must remain byte-identical to clone/apply/merge.
const unsupportedLayouts = [
  geometry => geometry.setAttribute('position', new THREE.Float16BufferAttribute([...geometry.getAttribute('position').array], 3)),
  geometry => { geometry.getAttribute('uv').normalized = true; },
  geometry => { geometry.morphAttributes.position = [geometry.getAttribute('position').clone()]; },
  geometry => {
    const array = geometry.getAttribute('position').array;
    geometry.setAttribute('position', new THREE.InterleavedBufferAttribute(new THREE.InterleavedBuffer(array, 3), 3, 0));
  },
  geometry => geometry.setAttribute('customPair', new THREE.BufferAttribute(new Uint16Array(4), 2)),
  geometry => geometry.setAttribute('instanceLike', new THREE.InstancedBufferAttribute(
    new Float32Array(geometry.getAttribute('position').count), 1,
  )),
];
for (const configureUnsupportedLayout of unsupportedLayouts) {
  const source = geometryFixture();
  configureUnsupportedLayout(source);
  const entries = matrices.slice(0, 2).map(matrix => ({ geometry: source, matrix }));
  const expected = oracleMerge(entries);
  const actual = mergeTransformedGeometries(entries);
  assertExactGeometry(actual, expected);
  expected.dispose();
  actual.dispose();
  source.dispose();
}

// Malformed missing positions preserve the old exception contract.
{
  const source = geometryFixture();
  source.deleteAttribute('position');
  const entries = matrices.slice(0, 2).map(matrix => ({ geometry: source, matrix }));
  assert.throws(() => oracleMerge(entries), TypeError);
  assert.throws(() => mergeTransformedGeometries(entries), TypeError);
  source.dispose();
}

// Incompatible attribute sets return null without a second fallback attempt.
{
  const left = geometryFixture();
  const right = geometryFixture();
  right.deleteAttribute('customPair');
  const entries = [
    { geometry: left, matrix: matrices[0] },
    { geometry: right, matrix: matrices[1] },
  ];
  const originalError = console.error;
  console.error = () => {};
  try {
    assert.equal(oracleMerge(entries), null);
    assert.equal(mergeTransformedGeometries(entries), null);
  } finally {
    console.error = originalError;
    left.dispose();
    right.dispose();
  }
}

// Synthetic allocation accounting and alternating-order timings; no speed threshold or claim.
const source = geometryFixture(60000, true);
const entries = Array.from({ length: 16 }, (_, index) => ({
  geometry: source,
  matrix: new THREE.Matrix4().makeRotationZ(index * .07).setPosition(index * 3, index % 4, 0),
}));
let sourceClones = 0;
const originalClone = source.clone;
source.clone = function countedClone() {
  sourceClones++;
  return originalClone.call(this);
};
const rounds = 4;
const timing = { oracle: [], fast: [] };
for (let round = 0; round < rounds; round++) {
  const order = round % 2 ? ['fast', 'oracle'] : ['oracle', 'fast'];
  for (const name of order) {
    sourceClones = 0;
    const start = performance.now();
    const geometry = name === 'oracle' ? oracleMerge(entries) : mergeTransformedGeometries(entries);
    timing[name].push(Number((performance.now() - start).toFixed(3)));
    assert.equal(sourceClones, name === 'fast' ? 0 : 16);
    geometry.dispose();
  }
}
const temporaryBytes = geometryBytes(source) * 16;
assert.equal(temporaryBytes, 51840000);
source.dispose();
console.log(JSON.stringify({
  exact: true,
  fast_path_source_clones: 0,
  oracle_source_clones: 16,
  oracle_temporary_buffer_bytes: temporaryBytes,
  alternating_samples_ms: timing,
}));
