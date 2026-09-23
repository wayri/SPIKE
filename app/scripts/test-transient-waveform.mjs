import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/transientWaveform.ts", import.meta.url), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const waveform = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);

const closeTo = (actual, expected, tolerance = 1e-12) => {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} is not within ${tolerance} of ${expected}`);
};

closeTo(waveform.parseSpiceNumber("100ns"), 100e-9);
closeTo(waveform.parseSpiceNumber("2.5us"), 2.5e-6);
closeTo(waveform.parseSpiceNumber("1ms"), 1e-3);
closeTo(waveform.parseSpiceNumber("4.7m"), 4.7e-3);
closeTo(waveform.parseSpiceNumber("10meg"), 10e6, 1e-6);
assert.throws(() => waveform.parseSpiceNumber("1x"), /must be numeric/);

const step = {
  kind: "step", highValue: "5", initialValue: "0", delayS: "10us", riseS: "2us",
};
closeTo(waveform.waveformValue(step, 9e-6), 0);
closeTo(waveform.waveformValue(step, 11e-6), 2.5, 1e-9);
closeTo(waveform.waveformValue(step, 15e-6), 5);

const pulse = {
  kind: "pulse", highValue: "2", initialValue: "0", delayS: "10us", riseS: "2us",
  widthS: "5us", fallS: "1us", periodS: "20us",
};
closeTo(waveform.waveformValue(pulse, 11e-6), 1, 1e-9);
closeTo(waveform.waveformValue(pulse, 13e-6), 2);
closeTo(waveform.waveformValue(pulse, 17.5e-6), 1, 1e-9);
closeTo(waveform.waveformValue(pulse, 19e-6), 0);
assert.deepEqual(waveform.validateWaveform({ ...pulse, periodS: "5us" }), ["Pulse period must contain rise, on-time, and fall intervals."]);

const pwl = { kind: "piecewise_linear", highValue: "0", points: "0:0, 10us:0, 20us:2, 30us:1" };
closeTo(waveform.waveformValue(pwl, 15e-6), 1, 1e-9);
assert.equal(waveform.parsePwlPoints(pwl.points).length, 4);
assert.equal(waveform.sampleWaveform(step, 20e-6, 24).length, 24);

console.log("SPIKE SPICE-number, step, pulse, PWL, and waveform sampling assertions passed");
