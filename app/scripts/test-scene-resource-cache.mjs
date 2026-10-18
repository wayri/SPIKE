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

// Closing a viewport must release even under-budget sources, including sources
// whose requests finish after teardown, without invalidating a sibling viewport.
const lifecycleDisposals = new Map();
const lifecycleLoads = new Map();
const lifecycleScene = key => {
  const source = makeScene();
  const counts = { geometry: 0, texture: 0, material: 0 };
  lifecycleDisposals.set(key, counts);
  const mesh = source.children[0];
  mesh.geometry.addEventListener('dispose', () => counts.geometry++);
  mesh.material.map.addEventListener('dispose', () => counts.texture++);
  mesh.material.addEventListener('dispose', () => counts.material++);
  return source;
};
let resolvePending, rejectPending;
const lateSource = new Promise(resolve => { resolvePending = resolve; });
const failedSource = new Promise((_resolve, reject) => { rejectPending = reject; });
const lifecycle = new SceneResourceCache(async key => {
  lifecycleLoads.set(key, (lifecycleLoads.get(key) ?? 0) + 1);
  return key === 'pending' ? lateSource : key === 'failed' ? failedSource : lifecycleScene(key);
});
const retained = await lifecycle.clone('idle');
disposeScene(retained);
assert.ok(lifecycle.stats.bytes > 0, 'ordinary changes retain a bounded cache while mounted');
const siblingA = await lifecycle.clone('shared');
const siblingB = await lifecycle.clone('shared');
const pendingClone = lifecycle.clone('pending');
const pendingFailure = lifecycle.clone('failed');
const failureCheck = assert.rejects(pendingFailure, /late failure/);
lifecycle.releaseIdle();
lifecycle.releaseIdle();
assert.deepEqual(lifecycleDisposals.get('idle'), { geometry: 1, texture: 1, material: 1 });
assert.deepEqual(lifecycleDisposals.get('shared'), { geometry: 0, texture: 0, material: 0 });
assert.equal(lifecycle.stats.users, 4, 'live clones and pending requests remain pinned during teardown');
resolvePending(lifecycleScene('pending'));
rejectPending(new Error('late failure'));
const loadedAfterClose = await pendingClone;
await failureCheck;
assert.deepEqual(lifecycleDisposals.get('pending'), { geometry: 0, texture: 0, material: 0 });
let cloneMaterialDisposals = 0;
loadedAfterClose.children[0].material.addEventListener('dispose', () => cloneMaterialDisposals++);
disposeScene(loadedAfterClose);
disposeScene(loadedAfterClose);
assert.equal(cloneMaterialDisposals, 1, 'cancelled late clone owns one material instance shared by its children');
assert.deepEqual(lifecycleDisposals.get('pending'), { geometry: 1, texture: 1, material: 1 });
disposeScene(siblingA);
assert.deepEqual(lifecycleDisposals.get('shared'), { geometry: 0, texture: 0, material: 0 });
assert.ok(siblingB.children[0].geometry.getAttribute('position').count > 0);
disposeScene(siblingB);
assert.deepEqual(lifecycleDisposals.get('shared'), { geometry: 1, texture: 1, material: 1 });
assert.deepEqual(lifecycle.stats, { entries: 0, bytes: 0, users: 0 });
const reopened = await lifecycle.clone('shared');
assert.equal(lifecycleLoads.get('shared'), 2, 'a later viewport reloads a released source');
disposeScene(reopened);
assert.equal(lifecycle.stats.entries, 1, 'future loads recover normal bounded retention');
lifecycle.releaseIdle();
assert.deepEqual(lifecycle.stats, { entries: 0, bytes: 0, users: 0 });
assert.deepEqual(lifecycleDisposals.get('shared'), { geometry: 1, texture: 1, material: 1 });
console.log('Viewport teardown releases retained and late sources exactly once; shared clones and future cache reuse remain safe.');

// Shader uniforms and Scene-level image slots are owned resources too. Missing
// them from the walk leaves decoded images alive across repeated open/close.
let nestedTextureDisposals = 0;
const nestedTexture = new THREE.DataTexture(new Uint8Array(4 * 4 * 4), 4, 4);
nestedTexture.addEventListener('dispose', () => nestedTextureDisposals++);
const environmentTexture = new THREE.DataTexture(new Uint8Array(2 * 2 * 4), 2, 2);
environmentTexture.addEventListener('dispose', () => nestedTextureDisposals++);
const nestedSceneTexture = new THREE.DataTexture(new Uint8Array(3 * 2 * 4), 3, 2);
nestedSceneTexture.addEventListener('dispose', () => nestedTextureDisposals++);
const aliasedUniformArray = [nestedTexture];
const nestedSource = new THREE.Scene();
nestedSource.environment = environmentTexture;
nestedSource.add(new THREE.Mesh(
  new THREE.BoxGeometry(),
  new THREE.ShaderMaterial({ uniforms: {
    direct: { value: nestedTexture },
    nested: { value: { layers: [nestedTexture] } },
    aliasA: { value: aliasedUniformArray },
    aliasB: { value: aliasedUniformArray },
  } }),
));
nestedSource.add(Object.assign(new THREE.Scene(), { background: nestedSceneTexture }));
const nestedCache = new SceneResourceCache(async () => nestedSource, 1024 ** 2, 1);
const nestedClones = await Promise.all(Array.from({ length: 64 }, () => nestedCache.clone('shader.glb')));
const nestedClone = nestedClones[0];
assert.equal(nestedClone.children[0].material.uniforms.direct.value, nestedTexture,
  'occurrence material clones retain the exact shared shader texture');
assert.equal(nestedClone.environment, environmentTexture,
  'scene-level environment texture remains exact across the occurrence clone');
assert.equal(nestedClone.children[1].background, nestedSceneTexture,
  'a nested Scene shares its exact source texture and participates in ownership');
assert.equal(nestedClone.children[0].material.uniforms.aliasA.value[0], nestedTexture,
  'the first clone of an aliased uniform container restores the shared source texture');
assert.equal(nestedClone.children[0].material.uniforms.aliasB.value[0], nestedTexture,
  'a second clone of the same source uniform container also restores the shared texture');
assert.equal(new Set(nestedClones.map(item => item.children[0].material.uniforms.direct.value)).size, 1,
  'repeated occurrences share one shader texture object rather than cloning one per material');
assert.equal(new Set(nestedClones.map(item => item.children[0].material)).size, 64,
  'shader materials remain independent per occurrence');
const nestedDecodedBytes = Math.ceil(nestedTexture.image.data.byteLength * 4 / 3)
  + Math.ceil(environmentTexture.image.data.byteLength * 4 / 3)
  + Math.ceil(nestedSceneTexture.image.data.byteLength * 4 / 3);
assert.ok(nestedCache.stats.bytes >= nestedDecodedBytes,
  'retention accounting includes nested shader and scene-level decoded textures');
for (const clone of nestedClones) disposeScene(clone);
assert.equal(nestedTextureDisposals, 0, 'idle retained sources continue owning shared nested textures');
nestedCache.releaseIdle();
assert.equal(nestedTextureDisposals, 3, 'viewport close disposes each nested and scene-level texture exactly once');
assert.deepEqual(nestedCache.stats, { entries: 0, bytes: 0, users: 0 });
console.log(JSON.stringify({ shaderOccurrences: nestedClones.length, retainedShaderTextureObjects: 1,
  sharedOccurrenceTextureReferences: nestedClones.length, nestedDecodedBytes, nestedTextureDisposals }));
