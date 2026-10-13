// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import ts from 'typescript';
import { piTerminalPosition, removePiTerminal } from '../src/piTerminalState.ts';
assert.equal(piTerminalPosition({ x: '', y: '' }), null);
assert.equal(piTerminalPosition({ x: ' ', y: '10' }), null);
assert.equal(piTerminalPosition({ x: 'NaN', y: '10' }), null);
assert.deepEqual(piTerminalPosition({ x: '0', y: '0' }), [0, 0]);
assert.deepEqual(piTerminalPosition({ x: '-12.5', y: ' 10 ' }), [-12.5, 10]);
const setup = { sources: [{ id: 'same' }], loads: [{ id: 'same' }],
  returnPath: { sources: [{ id: 'same' }], loads: [{ id: 'same' }] }, batchJobs: [{ id: 'batch' }] };
for (const role of ['source', 'load', 'source_return', 'load_return']) {
  const next = removePiTerminal(setup, role, 'same');
  const values = [next.sources, next.loads, next.returnPath.sources, next.returnPath.loads];
  assert.equal(values.filter(items => !items.length).length, 1, 'only the clicked role is deleted');
  assert.equal(next.batchJobs, setup.batchJobs);
  assert.equal(setup.sources.length, 1, 'original snapshot remains usable for undo');
}
assert.equal(removePiTerminal(setup, 'source', 'missing').sources.length, 1);
const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
assert.match(app, /clickedObject\?\.type==="terminal"&&clickedObject\.terminalRole/,
  'every terminal role is offered a removal action outside the PI tab');
assert.match(app, /label:"Remove this configured terminal"/);
assert.match(app, /removePiTerminal\(current,clickedObject\.terminalRole!,clickedObject\.id\.replace\(\/\^analysis-terminal:\/,""\)\)/,
  'the viewport action removes only the clicked terminal role and id');
console.log('PI terminal coordinates and role-scoped deletion passed.');
