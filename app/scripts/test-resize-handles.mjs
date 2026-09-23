import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");

assert.match(css, /\.dock-resizer::after\s*\{[^}]*background:\s*transparent;/s);
assert.match(css, /\.dock-resizer\.is-resizing::after\s*\{[^}]*background:\s*#d9a13f;/s);
assert.doesNotMatch(css, /\.dock-resizer:hover::after/);
assert.match(css, /\.pi-panel-resizer\.is-resizing::after\s*\{[^}]*background:\s*#d9a13f;/s);
assert.doesNotMatch(css, /\.pi-panel-resizer:hover::after/);

assert.match(app, /window\.addEventListener\("pointercancel", stop/);
assert.match(app, /window\.addEventListener\("blur", stop/);
assert.match(app, /handle\.addEventListener\("lostpointercapture", stop/);
assert.match(app, /window\.addEventListener\("pointercancel", onUp/);
assert.match(app, /handle\.addEventListener\("lostpointercapture", onUp/);

console.log("resize handle lifecycle assertions passed");
