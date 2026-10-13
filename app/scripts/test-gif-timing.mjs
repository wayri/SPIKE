// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/gifExport.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const gif = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const frame = { width: 1, height: 1, data: new Uint8ClampedArray([255, 0, 0, 255]) };
const blob = gif.encodeGif([frame, frame, frame], [2, 19, 250]);
const bytes = new Uint8Array(await blob.arrayBuffer());
const delays = [];
for (let index = 0; index < bytes.length - 7; index += 1) {
  if (bytes[index] === 0x21 && bytes[index + 1] === 0xf9 && bytes[index + 2] === 0x04) {
    delays.push(bytes[index + 4] | bytes[index + 5] << 8);
  }
}
assert.deepEqual(delays, [2, 19, 250], "GIF encoder must retain each source-derived frame hold");
assert.throws(() => gif.encodeGif([frame, frame], [5]), /must match/);
assert.equal(gif.encodeGif([frame], 7).type, "image/gif", "fixed-delay callers remain compatible");
assert.throws(() => gif.encodeGif([{ ...frame, width: 10_000, height: 10_000 }], 7), /256 MiB raw-frame limit/);
assert.doesNotMatch(source, /const output: number\[\]/, "GIF output must use bounded typed chunks rather than boxed byte arrays");
console.log("per-frame GIF timing and fixed-delay compatibility passed");
