// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import ts from 'typescript';
import { materializeVisualBundle } from '../src/boardVisualBundles.ts';

const source = readFileSync(new URL('../src/projectPersistenceArtifacts.ts', import.meta.url), 'utf8');
function persistence(text, byteType = Uint8Array) {
  const code = ts.transpileModule(text, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
    .replace(/^import .*?;$/gm, '').replace(/export /g, '');
  return new Function('Uint8Array', 'materializeVisualBundle',
    `${code}; return { check: assertSelfContainedArtifact, restore: restoreBoardVisuals };`)(byteType, materializeVisualBundle);
}
const validator = (text, byteType = Uint8Array) => persistence(text, byteType).check;
function artifact(uri) {
  const body = Buffer.from(JSON.stringify({ asset: { version: '2.0' }, buffers: [{ byteLength: 131072, ...(uri ? { uri } : {}) }] }));
  const json = Buffer.alloc(Math.ceil(body.length / 4) * 4, 32); body.copy(json);
  const glb = Buffer.alloc(20 + json.length + 8 + 131072);
  glb.writeUInt32LE(0x46546c67); glb.writeUInt32LE(2, 4); glb.writeUInt32LE(glb.length, 8);
  glb.writeUInt32LE(json.length, 12); glb.writeUInt32LE(0x4e4f534a, 16); json.copy(glb, 20);
  glb.writeUInt32LE(131072, 20 + json.length); glb.writeUInt32LE(0x004e4942, 24 + json.length);
  for (let index = 28 + json.length; index < glb.length; index++) glb[index] = index % 256;
  return { raw: glb, record: { role: 'board', media_type: 'model/gltf-binary', bytes: glb.length,
    sha256: createHash('sha256').update(glb).digest('hex'), artifact_base64: glb.toString('base64') } };
}
const fixture = artifact();
const captured = [];
class ObservedBytes extends Uint8Array {
  constructor(...args) { super(...args); if (args.length === 1 && typeof args[0] === 'number') captured.push(this); }
}
validator(source, ObservedBytes)(fixture.record);
assert.equal(captured.length, 2);
assert.deepEqual(Buffer.from(captured[0]), fixture.raw.subarray(0, 20), 'Preflight retains exact header bytes');
assert.deepEqual(Buffer.from(captured[1]), fixture.raw.subarray(20, 20 + fixture.raw.readUInt32LE(12)),
  'Preflight retains the complete UTF-8 JSON chunk');
assert.ok(captured.reduce((sum, bytes) => sum + bytes.length, 0) < fixture.raw.length / 100,
  'Binary payload is not copied into unused preflight storage');
const check = validator(source);
assert.throws(() => check(artifact('https://example.invalid/model.bin').record), /external resource/);
assert.throws(() => check({ ...fixture.record, sha256: 'invalid' }), /metadata/);
const badVersion = Buffer.from(fixture.raw); badVersion.writeUInt32LE(1, 4);
assert.throws(() => check({ ...fixture.record, artifact_base64: badVersion.toString('base64') }), /valid GLB/);
for (const [offset, value, error] of [[0, 0, /valid GLB/], [8, 20, /valid GLB/],
  [12, fixture.raw.length, /JSON chunk/], [16, 0, /JSON chunk/]]) {
  const bytes = Buffer.from(fixture.raw); bytes.writeUInt32LE(value, offset);
  assert.throws(() => check({ ...fixture.record, artifact_base64: bytes.toString('base64') }), error);
}
assert.throws(() => check({ ...fixture.record, artifact_base64: Buffer.alloc(19).toString('base64') }), /valid GLB/);
assert.throws(() => check({ ...fixture.record, artifact_base64: '!' }), /character/i);
const saved = record => ({ contract: 'spike/saved-board-visuals/v1', artifacts: [record],
  view_box: [0, 0, 10, 10], quality: {}, board_includes_copper: false });
const restored = await persistence(source).restore({}, saved(fixture.record));
assert.deepEqual(Buffer.from(await (await fetch(restored.board.boardModelUrl)).arrayBuffer()), fixture.raw,
  'Full materialization preserves all 256 byte values in the model payload');
assert.equal(restored.board.boardModelIncludesCopper, false);
restored.dispose();
const corruptPayload = Buffer.from(fixture.raw); corruptPayload[corruptPayload.length - 1] ^= 1;
await assert.rejects(() => persistence(source).restore({}, saved({ ...fixture.record,
  artifact_base64: corruptPayload.toString('base64') })), /integrity|digest|SHA/i,
  'A payload change outside preflight slices must still fail full integrity validation');

const [referencePath, outputPath] = process.argv.slice(2);
if (referencePath) {
  const reference = validator(readFileSync(referencePath, 'utf8'));
  reference(fixture.record); check(fixture.record);
  const before = [], after = [];
  for (let pair = 0; pair < 7; pair++) {
    for (const current of pair % 2 ? [true, false] : [false, true]) {
      const call = current ? check : reference, start = performance.now();
      for (let repeat = 0; repeat < 3; repeat++) call(fixture.record);
      (current ? after : before).push((performance.now() - start) / 3);
    }
  }
  const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
  const report = { scope: 'bounded synthetic portable GLB preflight; no native board-load or responsiveness stress',
    node: process.version, platform: process.platform, arch: process.arch, bytes: fixture.raw.length,
    sha256: fixture.record.sha256, before_ms: before, after_ms: after,
    before_median_ms: median(before), after_median_ms: median(after),
    source_sha256: createHash('sha256').update(source).digest('hex') };
  if (outputPath) writeFileSync(outputPath, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report));
}
console.log('Portable GLB header/JSON slices, complete payload bytes, integrity, URI, metadata and version gates passed');
