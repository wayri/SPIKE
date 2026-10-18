// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { viewportFrameDue, viewportDampingFactor, ViewportFrameClock } from '../src/viewportFrameCadence.ts';

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

for(const [refresh,limit] of [[60,60],[144,60],[144,120],[60,30]]){
 const clock=new ViewportFrameClock();let frames=0;
 for(let i=0;i<refresh*4;i++)if(clock.due(i*(1000/refresh-.01),true,limit))frames++;
 assert.ok(Math.abs(frames-limit*4)<=2,`${refresh}Hz / ${limit}FPS retained phase: ${frames}`);
}
const resume=new ViewportFrameClock();
assert.equal(resume.due(0,false,60),true);
assert.equal(resume.due(10,false,60),false);
assert.equal(resume.due(20,true,60),true,'interaction wakes immediately from idle');
assert.equal(resume.due(100000,true,60),true,'long suspension resumes');
assert.equal(resume.due(100000,true,60),false,'no burst of duplicate resume frames');
