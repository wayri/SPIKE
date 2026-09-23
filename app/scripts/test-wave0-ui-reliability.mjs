import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const [reportPreview, workerBridge, styles] = await Promise.all([
  readFile(new URL("../src/ReportPreview.tsx", import.meta.url), "utf8"),
  readFile(new URL("../src/workerBridge.ts", import.meta.url), "utf8"),
  readFile(new URL("../src/styles.css", import.meta.url), "utf8"),
]);

assert.match(reportPreview, /const PRINT_MESSAGE = "spike\/report-preview\/print"/);
assert.match(reportPreview, /contentWindow\?\.postMessage\(PRINT_MESSAGE, "\*"\)/);
assert.match(reportPreview, /sandbox="allow-scripts allow-downloads allow-modals"/);
assert.doesNotMatch(reportPreview, /allow-same-origin/);
assert.match(workerBridge, /"run_converter_study"/);
assert.match(styles, /--z-report-preview:\s*300/);
assert.match(styles, /\.report-preview-shade\s*\{[^}]*z-index:\s*var\(--z-report-preview\)/s);
assert.match(styles, /\.analysis-setup-dock-host\.dock-left,\s*\.analysis-setup-dock-host\.dock-right\s*\{\s*overflow:\s*visible;/s);
assert.match(styles, /dock-left > \.pi-run-dialog > \.pi-panel-resizer\.right/);
assert.match(styles, /dock-right > \.pi-run-dialog > \.pi-panel-resizer\.left/);

console.log("Wave 0 UI reliability checks passed.");
