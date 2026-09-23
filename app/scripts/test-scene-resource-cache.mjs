import assert from 'node:assert/strict';
import * as THREE from 'three';
import { SceneResourceCache, disposeScene } from '../src/sceneResourceCache.ts';
import { loadScenesBounded } from '../src/modelSceneLoader.ts';

let loads = 0;
let geometryDisposals = 0;
let textureDisposals = 0;
const makeScene = () => {
  const root = new THREE.Group();
  const geometry = new THREE.BoxGeometry();
  const texture = new THREE.DataTexture(new Uint8Array(16), 2, 2);
  geometry.addEventListener('dispose', () => geometryDisposals++);
  texture.addEventListener('dispose', () => textureDisposals++);
  const material = new THREE.MeshStandardMaterial({ map: texture });
  root.add(new THREE.Mesh(geometry, material), new THREE.Mesh(geometry, material));
  return root;
};
const cache = new SceneResourceCache(async () => { loads++; return makeScene(); }, 1, 1);
const started = performance.now();
const occurrences = await Promise.all(Array.from({ length: 10_000 }, () => cache.clone('same.glb')));
assert.equal(loads, 1, 'simultaneous occurrences must decode once');
const geometry = occurrences[0].children[0].geometry;
const texture = occurrences[0].children[0].material.map;
for (const occurrence of occurrences) {
  assert.equal(occurrence.children[0].geometry, geometry);
  assert.equal(occurrence.children[0].material.map, texture);
  assert.equal(occurrence.children[0].material, occurrence.children[1].material);
}
assert.notEqual(occurrences[0].children[0].material, occurrences[1].children[0].material);
occurrences[0].children[0].material.opacity = .25;
assert.equal(occurrences[1].children[0].material.opacity, 1);
assert.equal(cache.stats.users, 10_000);
const retainedBytes = cache.stats.bytes;
const assembly = new THREE.Group();
assembly.add(...occurrences.slice(0, 5000));
disposeScene(assembly);
assert.equal(cache.stats.users, 5000);
assert.equal(geometryDisposals, 0, 'removing a sibling cannot dispose live geometry');
assert.equal(textureDisposals, 0, 'removing a sibling cannot dispose live textures');
occurrences.slice(5000).forEach(disposeScene);
assert.deepEqual(cache.stats, { entries: 0, users: 0, bytes: 0 });
assert.equal(geometryDisposals, 1, 'over-budget idle source must be evicted exactly once');
assert.equal(textureDisposals, 1);
disposeScene(assembly);
assert.equal(cache.stats.users, 0);

let attempts = 0;
const retry = new SceneResourceCache(async () => {
  if (++attempts === 1) throw new Error('decode failure');
  return makeScene();
}, 0, 0);
await assert.rejects(retry.clone('retry.glb'), /decode failure/);
const recovered = await retry.clone('retry.glb');
disposeScene(recovered);
assert.equal(attempts, 2);
assert.equal(retry.stats.entries, 0);

const uniqueLoads = new Map();
const lru = new SceneResourceCache(async url => {
  uniqueLoads.set(url, (uniqueLoads.get(url) ?? 0) + 1);
  return makeScene();
}, 1024 ** 2, 2);
const a = await lru.clone('a');
const b = await lru.clone('b');
const c = await lru.clone('c');
assert.equal(lru.stats.entries, 3, 'live unique sources are pinned even above retention limit');
disposeScene(a);
assert.equal(lru.stats.entries, 2, 'last release makes an over-budget source evictable');
const bAgain = await lru.clone('b');
assert.equal(uniqueLoads.get('b'), 1);
disposeScene(b); disposeScene(bAgain);
const d = await lru.clone('d');
assert.equal(lru.stats.entries, 2, 'loading another source evicts idle entries without scanning pinned models');
disposeScene(c); disposeScene(d);
assert.equal(lru.stats.users, 0);

let active = 0; let peak = 0;
const jobs = await loadScenesBounded(Array.from({ length: 40 }, (_, i) => i), async value => {
  active++; peak = Math.max(peak, active);
  await new Promise(resolve => setTimeout(resolve, value % 3));
  active--;
  if (value === 5) throw new Error('one failed model');
  return value;
}, { concurrency: 3 });
assert.equal(peak, 3);
assert.equal(jobs[5].status, 'rejected');
assert.equal(jobs[39].value, 39);
assert.equal(jobs.filter(item => item.status === 'fulfilled').length, 39);
let dispatched = 0; let cancelled = false;
const stale = await loadScenesBounded(Array.from({ length: 100 }, (_, i) => i), async value => {
  dispatched++;
  cancelled = true;
  return value;
}, { cancelled: () => cancelled });
assert.equal(dispatched, 1, 'cancelled generations must stop dispatching queued models');
assert.equal(stale.filter(item => item.status === 'rejected').length, 99);
console.log(JSON.stringify({ occurrences: 10_000, geometryAllocations: 1, retainedBytes,
  elapsedMs: Math.round(performance.now() - started), maximumConcurrentLoads: peak,
  disposal: 'verified', cancellation: 'verified' }));
