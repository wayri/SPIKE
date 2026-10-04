// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { importTestTypescript } from './import-test-typescript.mjs';
const { boundFloatingRect, initialFloatingRect } = await importTestTypescript('pythonFloatingWindow');
for (const [width,height] of [[1920,1080],[900,620],[700,500],[320,240]]) {
  for (const candidate of [initialFloatingRect(width,height), {x:-400,y:3000,width:10000,height:1}, {x:2000,y:-500,width:1,height:5000}]) {
    const rect = boundFloatingRect(candidate,width,height);
    assert.ok(rect.x >= 8 && rect.y >= 8);
    assert.ok(rect.width > 0 && rect.height > 0);
    assert.ok(rect.x + rect.width <= width - 8);
    assert.ok(rect.y + rect.height <= height - 8);
  }
}
const original = initialFloatingRect(1920,1080);
assert.deepEqual(boundFloatingRect({...original,x:100,y:150},1920,1080), {...original,x:100,y:150});
assert.equal(boundFloatingRect({...original,width:720,height:500},1920,1080).width,720);
console.log('Floating Python movement and resizing stay within wide and narrow viewports.');
