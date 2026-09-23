// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const bundle = await build({ entryPoints: [fileURLToPath(new URL("../src/detachedToolWindowModel.ts", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node" });
const model = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].contents).toString("base64")}`);
const lifecycleBundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/detachedToolWindows.tsx", import.meta.url))], bundle: true, write: false,
  format: "esm", platform: "node", external: ["./TraceResultsWorkbench", "@tauri-apps/api/*"],
  plugins: [{ name: "ignore-css", setup(builder) {
    builder.onResolve({ filter: /\.css$/ }, args => ({ path: args.path, namespace: "empty-css" }));
    builder.onLoad({ filter: /.*/, namespace: "empty-css" }, () => ({ contents: "", loader: "js" }));
  } }],
});
const lifecycle = await import(`data:text/javascript;base64,${Buffer.from(lifecycleBundle.outputFiles[0].contents).toString("base64")}`);

const oversized = Array.from({ length: model.MAX_DETACHED_ROWS + 5 }, (_, index) => ({
  id: model.encodeDetachedRowId(index === 0 ? "probe/unsafe id" : `probe-${index}`),
  cells: [index, "x".repeat(model.MAX_DETACHED_TEXT + 20), Infinity, "ignored"], editActions: { 1: "edit-formula", 99: "invalid" },
}));
const snapshot = model.normalizeDetachedToolSnapshot({
  kind: "probes", title: "Probe table", revision: -2, columns: ["ID", "Formula", "Value"], rows: oversized,
  controls: [{ id: "field-select", label: "Field", kind: "select", value: "voltage", options: [{ value: "voltage", label: "Voltage" }] }],
  rowActions: [{ id: "delete", label: "Delete", destructive: true }],
});
assert.equal(snapshot.rows.length, model.MAX_DETACHED_ROWS);
assert.equal(model.decodeDetachedRowId(snapshot.rows[0].id), "probe/unsafe id");
assert.equal(snapshot.rows[0].cells[1].length, model.MAX_DETACHED_TEXT);
assert.equal(snapshot.rows[0].cells[2], "Infinity");
assert.equal(snapshot.rows[0].cells.length, 3);
assert.deepEqual(snapshot.rows[0].editActions, { 1: "edit-formula" });
assert.equal(snapshot.revision, 0);
assert.equal(snapshot.controls[0].id, "field-select");

assert.deepEqual(model.normalizeDetachedToolAction({ kind: "results", type: "control-change", controlId: "field", value: "current-density" }), {
  kind: "results", type: "control-change", controlId: "field", value: "current-density",
});
assert.equal(model.normalizeDetachedToolAction({ kind: "probes", type: "row-action", rowId: "a" }), null);
assert.equal(model.normalizeDetachedToolAction({ kind: "unknown", type: "ready" }), null);
assert.equal(model.normalizeDetachedToolAction({ kind: "results", type: "ready" }, "probes"), null);
assert.equal(model.normalizeDetachedToolAction({ kind: "probes", type: "row-action", rowId: "unsafe/id", actionId: "delete-probe" }), null);
assert.equal(model.normalizeDetachedToolSnapshot({ kind: "probes", title: "x", revision: 0, columns: ["x"], rows: [{ id: "unsafe/id", cells: ["x"] }] }).rows.length, 0);

const nativeHandle = () => {
  const handlers = new Map();
  const stopped = [];
  return {
    handlers, stopped,
    async once(event, handler) { handlers.set(event, handler); return () => { stopped.push(event); handlers.delete(event); }; },
  };
};
{
  const handle = nativeHandle();
  let settled = false;
  const pending = lifecycle.awaitNativeWindowCreated(handle).then(() => { settled = true; });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(settled, false, "registering once listeners must not count as native window creation");
  handle.handlers.get("tauri://created")({ payload: null });
  await pending;
  assert.deepEqual(new Set(handle.stopped), new Set(["tauri://created", "tauri://error", "tauri://destroyed"]));
}
{
  const handle = nativeHandle();
  const pending = lifecycle.awaitNativeWindowCreated(handle);
  await new Promise(resolve => setImmediate(resolve));
  handle.handlers.get("tauri://error")({ payload: "label already exists" });
  await assert.rejects(pending, /label already exists/);
  assert.equal(handle.handlers.size, 0, "creation failure must remove all temporary listeners");
}
console.log("detached tool windows: bounded snapshots and validated interactive actions passed");
