// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const transpile = source => ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const playbackSource = readFileSync(new URL("../src/transientPlayback.ts", import.meta.url), "utf8");
const playbackUrl = `data:text/javascript;base64,${Buffer.from(transpile(playbackSource)).toString("base64")}`;
const captureSource = readFileSync(new URL("../src/plotAnimationCapture.ts", import.meta.url), "utf8");
const captureCode = transpile(captureSource).replace('from "./transientPlayback"', `from "${playbackUrl}"`);
const capture = await import(`data:text/javascript;base64,${Buffer.from(captureCode).toString("base64")}`);
globalThis.window = globalThis;

const callbacks = new Map();
const graph = {
  once(event, callback) { callbacks.set(event, callback); },
  removeListener(event, callback) { if (callbacks.get(event) === callback) callbacks.delete(event); },
};
const root = { querySelector(selector) { assert.equal(selector, ".trace-plot-canvas"); return graph; } };
const rendered = capture.waitForPlotlyRender(root, undefined, 100);
assert.equal(typeof callbacks.get("plotly_afterplot"), "function", `registered events: ${[...callbacks.keys()].join(",")}`);
callbacks.get("plotly_afterplot")();
await rendered;
assert.equal(callbacks.size, 0, "render listener is removed after the dedicated plot completes");

const controller = new AbortController();
const cancelled = capture.waitForPlotlyRender(root, controller.signal, 100);
controller.abort();
await assert.rejects(cancelled, error => error?.name === "AbortError");
assert.equal(callbacks.size, 0, "cancellation removes the pending Plotly listener");
await assert.rejects(capture.waitForPlotlyRender({ querySelector: () => null }), /not available/);
let nextFrame = 0, cancelledFrame = 0;
globalThis.requestAnimationFrame = () => ++nextFrame;
globalThis.cancelAnimationFrame = frame => { cancelledFrame = Math.max(cancelledFrame, frame); };
await assert.rejects(capture.waitForPlotlyRender({ querySelector: () => ({}) }, undefined, 5), /did not paint within/);
assert.ok(cancelledFrame > 0, "fallback timeout cancels its pending animation frame");
assert.match(captureSource, /plotly\.toImage\(graph/, "capture must target the graph found inside the supplied viewer root");

console.log("dedicated Plotly render wait, cancellation, cleanup, and scoped capture target passed");
