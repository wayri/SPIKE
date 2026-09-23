import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import * as progressModule from '../src/boardImportProgress.ts';
import { materializeVisualBundle } from '../src/boardVisualBundles.ts';

// Drive the production hook with deterministic worker responses. React state is
// captured synchronously so cancellation and late replies can be tested directly.
const source = readFileSync(new URL('../src/useBoardVisualImport.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
  .replace(/^import \{([^}]+)\} from "([^"]+)";/gm, (_, names, path) =>
    `const {${names}} = deps[${JSON.stringify(path)}];`)
  .replace('export function useBoardVisualImport', 'function useBoardVisualImport');
const makeHook = new Function('deps', `${js}\nreturn useBoardVisualImport;`);
const artifact = (name, text) => ({ file_name: name, media_type: name.endsWith('.svg') ? 'image/svg+xml' : 'model/gltf-binary',
  bytes: Buffer.byteLength(text), sha256: createHash('sha256').update(text).digest('hex'), artifact_base64: Buffer.from(text).toString('base64') });
function response(request, quality = {}) {
  const { stage, lightweight_board } = request.params;
  const data = artifact(stage === 'layout' ? 'F_Cu.svg' : `${stage}.glb`,
    stage === 'layout' ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 20"/>' : stage);
  return { ok: true, result: { contract: 'spike/visual-bundle-payload/v1', status: 'ready',
    scenes: stage === 'layout' ? {} : { [stage]: data },
    layout: { layers: stage === 'layout' ? { 'F.Cu': data } : {}, view_box: stage === 'layout' ? [0, 0, 40, 20] : [] },
    quality: { board_includes_copper: !lightweight_board, ...quality }, artifact_bytes: data.bytes, artifact_limit_bytes: 4096,
    security: { self_contained_glb_required: true, external_resource_uris_allowed: false } } };
}
const missing = '${KIPRJMOD}/packages3D/missing.stp';
const board = () => ({ tracks: [], pads: [], vias: [], components: Array.from({ length: 8 }, (_, i) => ({ ref: `F${i + 1}`, modelPaths: [missing] })) });
function harness(worker = async request => response(request), cancellation = async () => {}) {
  const states = [], calls = [], applied = [], revoked = [], created = [];
  const deps = {
    react: {
      useState(initial) { const index = states.push(initial) - 1; return [initial, next => { states[index] = typeof next === 'function' ? next(states[index]) : next; }]; },
      useRef: current => ({ current }), useCallback: fn => fn, useEffect: () => {},
    },
    './boardImportProgress': progressModule,
    './boardVisualBundles': { materializeVisualBundle: (board, raw) => materializeVisualBundle(board, raw,
      () => { const url = `blob:import-${created.length}`; created.push(url); return url; }, url => revoked.push(url)) },
    './workerBridge': {
      isDesktopShell: () => true, cancelLocalWorker: cancellation,
      runNativeProjectWorker: async request => { calls.push(structuredClone(request)); return worker(request); },
      runLocalWorker: async request => { calls.push(structuredClone(request)); return worker(request); },
      selectNativeMcadFile: async () => ({ path: 'C:/models/replacement.step' }),
    },
  };
  return { hook: makeHook(deps)(value => applied.push(value), () => {}), states, calls, applied, revoked, created };
}
const success = harness();
await success.hook.prepare(board(), 'large.kicad_pcb', ' '.repeat(8 * 1024 * 1024), 'C:/boards/large.kicad_pcb');
assert.deepEqual(success.calls.map(call => call.params.stage), ['layout', 'board', 'components']);
assert.equal(success.calls[1].params.lightweight_board, true);
assert.equal(success.applied.length, 3, 'each stage must become available immediately');
assert.ok(success.applied[2].boardModelUrl && success.applied[2].componentModelUrl && success.applied[2].layoutLayerUrls['F.Cu']);
assert.deepEqual(success.applied[2].layoutViewBox, [0, 0, 40, 20]);
assert.equal(success.applied[2].boardModelIncludesCopper, false, 'component stage must preserve native copper mode');
assert.equal(success.states[0].percent, 100);
assert.equal(success.states[1], false, 'clean imports finish without requiring a wizard');
success.hook.reset();
assert.deepEqual(success.revoked.sort(), success.created.sort());

const recovery = harness(async request => request.params.stage === 'board' && !request.params.lightweight_board
  ? { ok: false, error: 'Artifact budget exceeded' } : response(request));
await recovery.hook.prepare(board(), 'small.kicad_pcb', '(kicad_pcb)', 'C:/boards/small.kicad_pcb');
assert.deepEqual(recovery.calls.map(call => call.params.stage), ['layout', 'board', 'board', 'components']);
assert.equal(recovery.applied.at(-1).boardModelIncludesCopper, false);
assert.equal(recovery.states[0].warnings.length, 0, 'automatic recovery needs no user intervention');

const partial = harness(async request => request.params.stage === 'layout' ? { ok: false, error: 'Layer export failed' }
  : response(request, request.params.stage === 'components' && !request.params.model_overrides[missing]
    ? { missing_references: ['F1', 'F2'], unresolved_model_paths: [missing, missing] } : {}));
await partial.hook.prepare(board(), 'partial.kicad_pcb', '(kicad_pcb)', 'C:/boards/partial.kicad_pcb');
assert.equal(partial.applied.length, 2, 'layer failure must not block the 3D stages');
assert.equal(partial.states[0].problems.length, 1);
assert.equal(partial.states[0].problems[0].references.length, 8);
await partial.hook.locate(missing);
assert.equal(partial.calls.length, 4, 'a model selection must rerun only the component stage');
assert.equal(partial.calls.at(-1).params.model_overrides[missing], 'C:/models/replacement.step');
assert.equal(partial.states[0].problems.length, 0);
assert.equal(partial.states[0].warnings.length, 1, 'model recovery must retain unrelated layer failures');
assert.equal(partial.revoked.length, 2, 'replaced component and manifest URLs must be released');

let release;
const cancelledIds = [];
const cancelled = harness(request => new Promise(resolve => { release = () => resolve(response(request)); }), async id => { cancelledIds.push(id); });
const pending = cancelled.hook.prepare(board(), 'cancel.kicad_pcb', '(kicad_pcb)', 'C:/boards/cancel.kicad_pcb');
await cancelled.hook.cancel();
release(); await pending;
assert.equal(cancelledIds.length, 1);
assert.equal(cancelled.applied.length, 0, 'a late cancelled response must never replace the board');
assert.equal(cancelled.states[0].stage, 'cancelled');

const releaseCancellations = [];
// Hold a worker response so cancellation can overlap a fresh import.
let releaseOld;
const race = harness(request => request.params.board_path.endsWith('old.kicad_pcb')
  ? new Promise(resolve => { releaseOld = () => resolve(response(request)); }) : Promise.resolve(response(request)),
  () => new Promise(resolve => { releaseCancellations.push(resolve); }));
const old = race.hook.prepare(board(), 'old.kicad_pcb', '', 'C:/boards/old.kicad_pcb');
const stopping = race.hook.cancel();
race.hook.reset();
await race.hook.prepare(board(), 'new.kicad_pcb', '', 'C:/boards/new.kicad_pcb');
releaseCancellations.forEach(resolve => resolve()); await stopping; releaseOld(); await old;
assert.equal(race.states[0].fileName, 'new.kicad_pcb');
assert.equal(race.states[0].stage, 'ready', 'old cancellation must not stop a new import');
assert.equal(race.applied.length, 3);
console.log('staged import, native-copper recovery, grouped model repair, partial failure and cancellation checks passed');
