// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { createRequire } from 'node:module';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const panelSource = readFileSync(new URL('../src/ProjectLoadPanel.tsx', import.meta.url), 'utf8');
assert.ok(panelSource.includes('view.etaNote'));
assert.ok(panelSource.includes("view.etaScope === 'stage'"));
assert.ok(panelSource.includes('loadEstimate(view.etaMs)'));
assert.ok(panelSource.includes('Project identity is still being verified'));
const source = readFileSync(new URL('../src/projectLoadProgress.ts', import.meta.url), 'utf8');
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const progress = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const { beginProjectLoad, advanceProjectLoad, measuredLoadFraction, finishProjectLoad, projectLoadView,
  validLoadCalibration, readLoadTimings, loadEstimate } = progress;
const durations = { package: 10000, trust: 0, results: 2000, design: 3000, visuals: 2000, workspace: 0, scene: 3000 };
let state = beginProjectLoad('open-1', 'board.spike', 0);
assert.equal(projectLoadView(state, 5000).percent, 0, 'elapsed time cannot invent progress');
assert.equal(projectLoadView(state, 5000).etaMs, null, 'cold startup has no measured ETA');
assert.match(projectLoadView(state, 5000).etaNote, /startup/);
assert.ok(validLoadCalibration(durations), 'zero-duration fast stages are valid');
assert.equal(validLoadCalibration({ ...durations, scene: NaN }), false);
assert.equal(validLoadCalibration({ ...durations, trust: -1 }), false);
assert.equal(validLoadCalibration({ ...durations, package: 1e300 }), false);
assert.equal(validLoadCalibration({ package: 1 }), false);
assert.equal(validLoadCalibration(Object.fromEntries(Object.keys(durations).map(key => [key, 0]))), false);
state = { ...state, calibration: durations };
assert.equal(projectLoadView(state, 5000).etaMs, 15000);
assert.equal(projectLoadView(state, 10000).etaMs, null, 'an overrun must not count down fictitious remaining work');
assert.match(projectLoadView(state, 10000).etaNote, /taking longer/);
state = advanceProjectLoad(state, 'results', 10000);
state = measuredLoadFraction(state, 50, 100, 'half the artifact bytes verified');
const currentRate = projectLoadView(state, 14000);
assert.equal(currentRate.etaMs, 12000, 'live measured rate replaces an overrun, with later calibrated stages');
assert.equal(currentRate.etaScope, 'project');
const firstOpen = projectLoadView({ ...state, calibration: undefined }, 14000);
assert.equal(firstOpen.etaMs, 4000);
assert.equal(firstOpen.etaScope, 'stage', 'artifact throughput cannot forecast unrelated stages');
assert.match(firstOpen.etaNote, /later stages/);
assert.equal(projectLoadView({ ...state, calibration: undefined }, 10500).etaMs, null, 'sample under one second is too early');
assert.equal(measuredLoadFraction(state, -1, 100), state);
assert.equal(measuredLoadFraction(state, 101, 100), state);
assert.equal(measuredLoadFraction(state, 10, 100).fraction, 0.5, 'work progress cannot move backwards');
assert.throws(() => advanceProjectLoad(state, 'package', 15000), /backwards/);
assert.throws(() => finishProjectLoad(state, 'ready', 15000), /usable/);
const cancelled = finishProjectLoad(state, 'cancelled', 15000);
assert.equal(projectLoadView(cancelled, 99999).etaMs, null);
assert.equal(projectLoadView(cancelled, 99999).elapsedMs, 15000);
assert.equal(advanceProjectLoad(cancelled, 'scene', 99999), cancelled);
assert.equal(measuredLoadFraction(cancelled, 100, 100), cancelled);
const ready = finishProjectLoad(advanceProjectLoad(state, 'scene', 17000), 'ready', 20000);
assert.equal(projectLoadView(ready, 99999).percent, 100);
assert.equal(projectLoadView(ready, 99999).etaMs, 0);
const now = 2000000000;
const record = { digest: 'a'.repeat(64), fileName: 'board.spike', savedAt: now, durations };
assert.deepEqual(readLoadTimings(JSON.stringify([record]), now), [record], 'completed durations survive a new app session');
for (const raw of ['broken', '{}', JSON.stringify([null, { ...record, digest: 'wrong' },
  { ...record, savedAt: now + 1 }, { ...record, durations: { package: 10 } },
  { ...record, savedAt: now - 31 * 86400000 }]), ' '.repeat(32769)]) {
  assert.deepEqual(readLoadTimings(raw, now), []);
}
assert.equal(readLoadTimings(JSON.stringify(Array(20).fill(record)), now).length, 8);
assert.deepEqual(readLoadTimings(JSON.stringify([{ ...record, durations: { ...durations, extra: 'ignored' } }]), now), [record]);
assert.equal(loadEstimate(1200), 'less than 5 s');
assert.equal(loadEstimate(12001), 'about 15 s');
assert.equal(loadEstimate(124000), 'about 2 min');
// Render the actual panel with stable time and check its cold/rate/terminal states.
const require = createRequire(import.meta.url);
const panelCompiled = ts.transpileModule(panelSource, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
let renderNow = 14000;
const panelModule = { exports: {} };
new Function('require', 'module', 'exports', panelCompiled)(name => {
  if (name === 'react') return { ...React, useEffect() {}, useRef: initial => ({ current: initial }),
    useState: () => [renderNow, () => {}] };
  if (name === './projectLoadProgress') return progress;
  if (name.endsWith('.css')) return {};
  return require(name);
}, panelModule, panelModule.exports);
const Panel = panelModule.exports.default;
let cancellations = 0;
let dismissals = 0;
const props = { onCancel: () => { cancellations++; }, onDismiss: () => { dismissals++; } };
const renderPanel = state => renderToStaticMarkup(React.createElement(Panel, { ...props, state }));
const cold = { ...beginProjectLoad('cold', 'a-very-long-project-name.spike', 0), previousDurationMs: 7000 };
assert.match(renderPanel(cold), /Measuring/);
assert.match(renderPanel(cold), /Project identity is still being verified/);
assert.match(renderPanel(cold), /Cancel loading/);
assert.match(renderPanel({ ...state, calibration: undefined }), /Estimated remaining in this stage/);
assert.match(renderPanel({ ...state, calibration: undefined }), /less than 5 s/);
assert.match(renderPanel(cancelled), /Loading cancelled/);
assert.match(renderPanel(cancelled), /Stopped/);
assert.match(renderPanel(cancelled), />Close<\/button>/);
assert.match(renderPanel({ ...cancelled, status: 'failed', error: 'fixture error' }), /role="alert"/);
assert.equal(renderPanel(ready), '');
Panel({ ...props, state: cold }).props.children.props.onKeyDown({ key: 'Escape', preventDefault() {} });
Panel({ ...props, state: cancelled }).props.children.props.onKeyDown({ key: 'Escape', preventDefault() {} });
assert.equal(cancellations, 1);
assert.equal(dismissals, 1);

// Exercise the real hook's lifecycle with deterministic React state primitives.
// This does not render React; it verifies timing admission and cancellation paths.
const progressUrl = `data:text/javascript;base64,${Buffer.from(output).toString('base64')}`;
const hookSource = readFileSync(new URL('../src/useProjectLoad.ts', import.meta.url), 'utf8')
  .replace("import { useCallback, useRef, useState } from 'react';",
    'const { useCallback, useRef, useState } = globalThis.__loadHooks;')
  .replace("from './projectLoadProgress'", `from '${progressUrl}'`);
const hookOutput = ts.transpileModule(hookSource, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const originalPerformance = globalThis.performance;
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
let clockMs = 0;
let latest = null;
let stored = null;
let saves = 0;
const cancelledWorkers = [];
globalThis.__loadHooks = { useCallback: fn => fn, useRef: value => ({ current: value }),
  useState: value => [value, next => { latest = next; }] };
Object.defineProperty(globalThis, 'performance', { configurable: true, value: { now: () => clockMs } });
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: () => stored, setItem: (_key, value) => { stored = value; saves++; },
} });
try {
  const { useProjectLoad } = await import(`data:text/javascript;base64,${Buffer.from(hookOutput).toString('base64')}`);
  let hook = useProjectLoad(async id => { cancelledWorkers.push(id); return true; });
  let load = hook.start('board.spike');
  load.identity(record.digest);
  for (const stage of ['trust', 'results', 'design', 'visuals', 'workspace', 'scene']) {
    clockMs += 1000; load.stage(stage);
  }
  clockMs += 1000;
  hook.ready(load.id);
  assert.equal(latest.status, 'ready');
  assert.equal(saves, 1);
  hook = useProjectLoad(async id => { cancelledWorkers.push(id); return true; });
  load = hook.start('board.spike');
  assert.equal(latest.previousDurationMs, 7000, 'timing reference survives a fresh hook');
  assert.equal(latest.calibration, undefined, 'file name must not authorize a project ETA');
  load.identity('b'.repeat(64));
  assert.equal(latest.calibration, undefined, 'a changed manifest rejects prior timings');
  load.identity(record.digest);
  assert.ok(latest.calibration, 'verified exact manifest admits prior stage timings');
  load.workerId = 'worker-1';
  await hook.cancel();
  assert.equal(load.signal.aborted, true);
  assert.equal(latest.status, 'cancelled');
  assert.deepEqual(cancelledWorkers, ['worker-1']);
  assert.throws(() => load.units(1, 2), /cancelled/);
  hook.ready(load.id);
  assert.equal(saves, 1, 'cancellation cannot overwrite successful timing history');
  load = hook.start('failed.spike');
  hook.fail(load, new Error('fixture failure'));
  assert.equal(latest.status, 'failed');
  assert.equal(saves, 1);
} finally {
  Object.defineProperty(globalThis, 'performance', { configurable: true, value: originalPerformance });
  if (originalStorage) Object.defineProperty(globalThis, 'localStorage', originalStorage);
  else delete globalThis.localStorage;
  delete globalThis.__loadHooks;
}
console.log('Project load timing: cold start, measured work, calibration, overrun, cancellation and bounded cache passed');
