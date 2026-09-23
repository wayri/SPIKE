import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { materializeVisualBundle } from '../src/boardVisualBundles.ts';

const source = readFileSync(new URL('../src/projectPersistenceArtifacts.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
  .replace(/^import .*?;$/gm, '').replace(/export /g, '');
const { hydrateProjectArtifacts, serializeBoardVisuals, restoreBoardVisuals } = new Function('materializeVisualBundle',
  `${code}; return { hydrateProjectArtifacts, serializeBoardVisuals, restoreBoardVisuals };`)(materializeVisualBundle);

const reference = { contract: 'spike/state-artifact-reference/v1', path: `state/artifacts/${'a'.repeat(64)}.json`, sha256: 'a'.repeat(64), bytes: 200 };
let reads = 0;
const waveform = { analysis_id: 'run', time_series: { values: [1, 2, 3] }, future: { units: 'V' } };
const restored = await hydrateProjectArtifacts({ analysis: { latest_result: reference, result_history: Array.from({ length: 25 }, (_, i) => ({ id: String(i), bundle: reference })) } }, async () => { reads++; return waveform; });
assert.equal(reads, 1);
assert.equal(restored.analysis.result_history.length, 25);
assert.deepEqual(restored.analysis.result_history[0].bundle, waveform);
await assert.rejects(() => hydrateProjectArtifacts({ a: reference, b: { ...reference, bytes: 300 } }, async () => waveform), /Conflicting/);

function glb() {
  const json = Buffer.from(JSON.stringify({ asset: { version: '2.0' }, scenes: [{ nodes: [] }], scene: 0 }));
  const padded = Buffer.alloc(Math.ceil(json.length / 4) * 4, 32); json.copy(padded);
  const result = Buffer.alloc(20 + padded.length);
  result.writeUInt32LE(0x46546c67, 0); result.writeUInt32LE(2, 4); result.writeUInt32LE(result.length, 8);
  result.writeUInt32LE(padded.length, 12); result.writeUInt32LE(0x4e4f534a, 16); padded.copy(result, 20);
  return result;
}
const artifact = (role, bytes) => ({ role, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex'),
  media_type: role.startsWith('layer:') ? 'image/svg+xml' : 'model/gltf-binary', artifact_base64: bytes.toString('base64') });
const saved = { contract: 'spike/saved-board-visuals/v1', artifacts: [artifact('board', glb()), artifact('components', glb()),
  artifact('layer:In2.Cu', Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 20"/>'))],
  view_box: [0, 0, 40, 20], board_includes_copper: false, quality: { missing_references: ['F1'] } };
const scene = await restoreBoardVisuals({ tracks: [], components: [] }, saved);
assert.ok(scene.board.boardModelUrl && scene.board.componentModelUrl && scene.board.layoutLayerUrls['In2.Cu']);
assert.equal(scene.board.boardModelIncludesCopper, false);
const reserialized = await serializeBoardVisuals(scene.board);
assert.deepEqual(reserialized.artifacts.map(item => [item.role, item.sha256]), saved.artifacts.map(item => [item.role, item.sha256]));
assert.deepEqual(reserialized.view_box, saved.view_box);
assert.equal(reserialized.board_includes_copper, false);
scene.dispose(); scene.dispose();
await assert.rejects(() => fetch(scene.board.boardModelUrl), /fetch failed/);
const bad = { ...saved, artifacts: [artifact('layer:F.Cu', Buffer.from('<svg><script>alert(1)</script></svg>'))] };
await assert.rejects(() => restoreBoardVisuals({}, bad), /active or external/);
console.log('deferred result hydration, 25 records, real GLB/SVG save/restore, copper policy and disposal passed');
