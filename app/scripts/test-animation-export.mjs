// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const transpile = source => ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const playbackSource = readFileSync(new URL("../src/transientPlayback.ts", import.meta.url), "utf8");
const playbackUrl = `data:text/javascript;base64,${Buffer.from(transpile(playbackSource)).toString("base64")}`;
const exportSource = readFileSync(new URL("../src/animationExport.ts", import.meta.url), "utf8");
const exportCode = transpile(exportSource).replace('from "./transientPlayback"', `from "${playbackUrl}"`);

globalThis.window = globalThis;
let activeTrack;
class FakeCanvas {
  constructor() { this.width = 0; this.height = 0; }
  getContext() { return { putImageData() {} }; }
  captureStream() {
    activeTrack = { stopped: false, stop() { this.stopped = true; }, requestFrame() {} };
    return { getVideoTracks: () => [activeTrack], getTracks: () => [activeTrack] };
  }
}
globalThis.HTMLCanvasElement = FakeCanvas;
globalThis.document = { createElement: kind => { assert.equal(kind, "canvas"); return new FakeCanvas(); } };

class FakeRecorder {
  static failOnStop = false;
  static isTypeSupported = type => type.includes("webm");
  constructor() { this.state = "inactive"; this.listeners = new Map(); }
  addEventListener(event, callback) { this.listeners.set(event, callback); }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    if (FakeRecorder.failOnStop) this.listeners.get("error")?.({ error: new Error("encoder stop failed") });
    else {
      this.listeners.get("dataavailable")?.({ data: new Blob([new Uint8Array([1, 2, 3])]) });
      this.listeners.get("stop")?.();
    }
  }
}
globalThis.MediaRecorder = FakeRecorder;
const animation = await import(`data:text/javascript;base64,${Buffer.from(exportCode).toString("base64")}`);
const plan = { frames: [{ frameIndex: 0, timeS: 0, durationMs: 10 }], playbackSpeed: 1, durationMs: 10, sourceFrameCount: 2 };
const options = { plan, width: 2, height: 2, presentFrame() {}, captureFrame: async () => ({ width: 2, height: 2, data: new Uint8ClampedArray(16) }) };

const blob = await animation.captureWebM(options);
assert.equal(blob.type.startsWith("video/webm"), true);
assert.equal(activeTrack.stopped, true, "successful WebM export releases its canvas stream track");

FakeRecorder.failOnStop = true;
await assert.rejects(animation.captureWebM(options), /encoder stop failed/);
assert.equal(activeTrack.stopped, true, "encoder-stop failure still releases its canvas stream track");

console.log("WebM capability, encoded output, stop-error propagation, and stream cleanup passed");
