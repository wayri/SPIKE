import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { materializeVisualBundle } from '../src/boardVisualBundles.ts';

// Verify a captured worker response through the same byte/hash/Blob boundary
// and Three.js loader used by the desktop, without requiring a GPU.
globalThis.ProgressEvent ??= class ProgressEvent extends Event {
  constructor(type, init = {}) { super(type); Object.assign(this, init); }
};
let board = {};
let bundle;
let bytes = 0;
const disposers = [];
try {
  for (const path of process.argv.slice(2)) {
    const response = JSON.parse(readFileSync(path, 'utf8'));
    assert.equal(response.ok, true, response.error);
    bundle = await materializeVisualBundle(board, response.result);
    board = bundle.board;
    disposers.push(bundle.dispose);
    bytes += response.result.artifact_bytes;
  }
  const meshCounts = {};
  for (const [kind, url] of Object.entries({ board: bundle.board.boardModelUrl, components: bundle.board.componentModelUrl })) {
    const loaded = await new GLTFLoader().loadAsync(url);
    let meshes = 0;
    loaded.scene.traverse(object => { if (object.isMesh) meshes++; });
    assert.ok(meshes > 0, `${kind} scene is empty`);
    meshCounts[kind] = meshes;
  }
  const layers = Object.keys(bundle.board.layoutLayerUrls);
  for (const [layer, url] of Object.entries(bundle.board.layoutLayerUrls)) {
    const svg = await (await fetch(url)).text();
    assert.match(svg, /<svg\b/, `${layer} is not SVG`);
    const viewBox = svg.match(/viewBox="([^"]+)"/)[1].trim().split(/\s+/).map(Number);
    assert.deepEqual(viewBox, bundle.board.layoutViewBox, `${layer} uses a different coordinate frame`);
  }
  console.log(JSON.stringify({ meshCounts, layers: layers.length, bytes, missing: bundle.missingReferences, nativeCopper: board.boardModelIncludesCopper === false }));
} finally {
  disposers.forEach(dispose => dispose());
}
