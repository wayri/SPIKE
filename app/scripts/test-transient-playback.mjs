// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/transientPlayback.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const playback = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

assert.deepEqual(playback.playbackFrameAtElapsed([0, 0.1, 0.9, 1], 0, 500, 1), { frameIndex: 1, ended: false },
  "playback must use saved timestamps rather than an equal frame cadence");
assert.deepEqual(playback.playbackFrameAtElapsed([0, 0.1, 0.9, 1], 1, 450, 2), { frameIndex: 3, ended: true },
  "speed scales simulated time and ends on the final saved sample");
const sourceTimes = [0, 0.1, 0.9, 1];
const timeline = playback.createPlaybackTimeline(sourceTimes);
sourceTimes[1] = 0.8;
assert.deepEqual(timeline.frameAtElapsed(0, 500, 1), { frameIndex: 1, ended: false },
  "validated timeline keeps one immutable timestamp copy for repeated animation ticks");
assert.equal(timeline.frameAtElapsed(0, 500, 1).frameIndex, 1);
assert.equal(playback.savedFrameIndexAtTime([0, 0.25, 0.25, 1], 0.25), 2, "duplicate timestamps resolve to their last saved sample");

const plan = playback.buildAnimationExportPlan([0, 0.01, 0.2, 0.6, 1], 2, { maximumFrames: 3 });
assert.deepEqual(plan.frames.map(frame => frame.frameIndex), [0, 2, 4], "bounded export retains the first and last solved samples");
assert.deepEqual(plan.frames.map(frame => frame.durationMs), [100, 400, 10], "retained frame holds follow source-time deltas at selected speed with a bounded final hold");
assert.deepEqual(playback.gifDelayCentiseconds(plan), [10, 40, 1]);
assert.throws(() => playback.buildAnimationExportPlan([0, 120], 1), /increase playback speed/);
assert.throws(() => playback.validatedFrameTimes([0, Number.NaN]), /finite simulated time/);
assert.throws(() => playback.validatedFrameTimes([0, 2, 1]), /nondecreasing/);
assert.throws(() => playback.assertCaptureBounds(1920, 1080, 180), /GIF capture requires/);
playback.assertCaptureBounds(800, 500, 100);

console.log("timestamp playback, bounded frame selection, GIF delays, and resource guards passed");
