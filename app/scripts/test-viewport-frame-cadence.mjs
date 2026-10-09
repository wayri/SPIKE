// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { viewportFrameDue, viewportDampingFactor } from '../src/viewportFrameCadence.ts';

// A common slightly early RAF stream must not collapse to 30 FPS while dragging.
for (const refresh of [60, 90, 120, 144]) {
  let last = 0, rendered = 0;
  for (let frame = 1; frame <= refresh; frame++) {
    const now = frame * (1000 / refresh - 0.05);
    if (viewportFrameDue(now, last, true)) { rendered++; last = now; }
  }
  assert.equal(rendered, refresh);
  const nominal = 0.075;
  const factor = viewportDampingFactor(nominal, 1 / refresh);
  assert.ok(Math.abs((1 - factor) ** refresh - (1 - nominal) ** 60) < 1e-12,
    'damping decay after one second is independent of display refresh');
}
assert.equal(viewportFrameDue(199, 0, false), false);
assert.equal(viewportFrameDue(200, 0, false), true);
assert.equal(viewportDampingFactor(.075, 0), 0);
assert.equal(viewportDampingFactor(.075, 20), viewportDampingFactor(.075, .1), 'resume cannot jump through a long damping interval');
console.log('Viewport refresh cadence and time-based damping checks passed.');
