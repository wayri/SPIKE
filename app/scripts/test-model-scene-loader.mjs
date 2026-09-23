import assert from "node:assert/strict";
import { boardSceneFormat, loadSceneWithRetry, retryableSceneLoadError, sceneLoadErrorMessage } from "../src/modelSceneLoader.ts";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLLoader } from "three/examples/jsm/loaders/VRMLLoader.js";

for (const url of ["blob:http://localhost/1234", "blob:nodedata:1234", "/models/board.GLB?v=2", "/board.gltf#scene", "data:model/gltf-binary;base64,AA=="]) {
  assert.equal(boardSceneFormat(url), "gltf", url);
}
assert.equal(boardSceneFormat("/legacy/board.wrl?v=2"), "vrml");
assert.equal(boardSceneFormat("/legacy/board.VRML"), "vrml");

// Exercise the same real Three loader dispatch with an extensionless GLB Blob,
// not just filename policy. No browser, network, or GPU is required for parsing.
globalThis.ProgressEvent ??= class ProgressEvent extends Event {
  constructor(type, init = {}) { super(type); Object.assign(this, init); }
};
const json = Buffer.from(JSON.stringify({ asset: { version: "2.0" }, scene: 0, scenes: [{ nodes: [0] }], nodes: [{ name: "imported-board" }] }));
const padded = Buffer.alloc(Math.ceil(json.length / 4) * 4, 0x20);
json.copy(padded);
const glb = Buffer.alloc(20 + padded.length);
glb.writeUInt32LE(0x46546c67, 0);
glb.writeUInt32LE(2, 4);
glb.writeUInt32LE(glb.length, 8);
glb.writeUInt32LE(padded.length, 12);
glb.writeUInt32LE(0x4e4f534a, 16);
padded.copy(glb, 20);
const blobUrl = URL.createObjectURL(new Blob([glb], { type: "model/gltf-binary" }));
try {
  const loaded = boardSceneFormat(blobUrl) === "gltf"
    ? (await new GLTFLoader().loadAsync(blobUrl)).scene
    : await new VRMLLoader().loadAsync(blobUrl);
  assert.equal(loaded.children[0].name, "imported-board");
} finally {
  URL.revokeObjectURL(blobUrl);
}

assert.equal(retryableSceneLoadError(new TypeError("Failed to fetch")), true);
assert.equal(retryableSceneLoadError({ target: { status: 0, responseURL: "http://127.0.0.1/model.glb" } }), true);
assert.equal(retryableSceneLoadError({ target: { status: 503 } }), true);
assert.equal(retryableSceneLoadError({ target: { status: 404 } }), false);
assert.match(sceneLoadErrorMessage({ target: { status: 404, responseURL: "/missing.glb" } }), /404.*missing\.glb/);

let transientAttempts = 0;
const scene = await loadSceneWithRetry(async () => {
  transientAttempts += 1;
  if (transientAttempts < 3) throw new TypeError("Failed to fetch");
  return { name: "scene" };
}, { attempts: 3, delayMs: 0, wait: async () => undefined });
assert.deepEqual(scene, { name: "scene" });
assert.equal(transientAttempts, 3);

let permanentAttempts = 0;
await assert.rejects(
  loadSceneWithRetry(async () => {
    permanentAttempts += 1;
    throw { target: { status: 404, responseURL: "/missing.glb" } };
  }, { attempts: 3, delayMs: 0, wait: async () => undefined }),
);
assert.equal(permanentAttempts, 1, "permanent HTTP failures must not waste retries");

console.log("model scene loader retry policy: all assertions passed");
