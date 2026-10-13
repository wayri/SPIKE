// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { encodeResultScreenshot } from "../src/resultScreenshot.ts";
const frame = { width: 2, height: 3, data: new Uint8ClampedArray(24) };
function encoder(type, fail = false) {
  const canvas = { width: 0, height: 0, getContext: () => ({ putImageData: value => assert.equal(value, frame) }),
    toBlob(callback, requested, quality) {
      assert.equal(quality, 0.9);
      assert.equal(this.width, 2); assert.equal(this.height, 3);
      callback(fail ? null : new Blob(["encoded"], { type: type ?? requested }));
    } };
  return canvas;
}
for (const [format, mime] of [["webp", "image/webp"], ["jpeg", "image/jpeg"], ["png", "image/png"]]) {
  const canvas = encoder();
  assert.equal((await encodeResultScreenshot(frame, format, () => canvas)).type, mime);
  assert.equal(canvas.width, 0); assert.equal(canvas.height, 0);
}
const fallback = encoder("image/png");
await assert.rejects(encodeResultScreenshot(frame, "webp", () => fallback), /Choose PNG/);
assert.equal(fallback.width, 0);
await assert.rejects(encodeResultScreenshot(frame, "jpeg", () => encoder(undefined, true)), /encoding failed/);
await assert.rejects(encodeResultScreenshot({ ...frame, width: 4001, height: 1000 }, "png"), /megapixel/);
await assert.rejects(encodeResultScreenshot(frame, "gif"), /Unsupported/);
console.log("Screenshot format, codec fallback, failure, memory cleanup and size limits passed.");
