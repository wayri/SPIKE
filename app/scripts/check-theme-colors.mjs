// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import postcss from "postcss";

const sheets = [
  "ViewportQuickTools.css",
  "ViewportActionMenu.css",
  "FocusWorkspace.css",
  "WorkbenchChrome.css",
  "ActionContextMenu.css",
  "IconGallery.css",
  "ParallelWorkerPanel.css",
  "ProbeResultsTable.css",
  "TerminalTable.css",
  "assemblyBoardManagers.css",
  "assemblyConnectorLinks.css",
  "assemblyGizmoNumericInput.css",
  "boardImportPanel.css",
  "detachedToolWindows.css",
  "modelResolverPanel.css",
  "multiboardStudyEditor.css",
  "siWorkflow.css",
  "toolRestoreShelf.css",
  "viewportNetViewer.css",
  "viewportNotifications.css",
];
const domainExceptions = new Map([
  ["AnalysisGuide.css", /analysis-guide-pulse|analysis-guide-highlight/],
  ["InternalAirflowPanel.css", /internal-airflow-(?:figure|channel|wall|axis-label|boundary-label|velocity-arrow|swatch|gradient)|#internal-airflow-arrow/],
  ["TraceValuePopup.css", /trace-value-popup-graph polyline/],
  ["connectorGraphEditor.css", /connector-graph-(?:board|board-title|board-id|empty|edge|pending|node)/],
  ["workflowSchematic.css", /workflow-schematic-sheet|workflow-symbol/],
]);
const rawColor = /#[\da-f]{3,8}\b|\brgba?\(|\bhsla?\(/i;
const colorProperty = /^(?:color|background(?:-color|-image)?|border(?:-(?:top|right|bottom|left|inline|block))?(?:-color)?|outline(?:-color)?|box-shadow|accent-color|caret-color)$/;

const stylesRawColor = /#[\da-f]{3,8}\b|\brgba?\(|\bhsla?\(|\b(?:white|black)\b/i;
const stylesColorProperty = /^(?:color|background(?:-color|-image)?|border(?:-(?:top|right|bottom|left|inline|block))?(?:-color)?|outline(?:-color)?|box-shadow|text-shadow|accent-color|caret-color|scrollbar-color|fill|stroke|filter|--layer-color)$/;
const stylesDomainColors = new Set([
  ".board-canvas|background-image|linear-gradient(#18262e 1px, transparent 1px), linear-gradient(90deg, #18262e 1px, transparent 1px)",
  ".legend-copper|background|#d6a84f",
  ".legend-current|background|#5bc2ac",
  ".legend-hot|background|#df5e55",
  ".net-swatch.red|background|#df675e",
  ".net-swatch.blue|background|#599fca",
  ".net-role-dot.source|background|#df675e",
  ".net-role-dot.return|background|#599fca",
  ".net-role-dot.series|background|#d9a84d",
  ".layer-color|background|#d9a64d",
  ".layer-1|background|#5bb9ab",
  ".layer-2|background|#5590c7",
  ".layer-3|background|#9f6ab5",
  ".layer-4|background|#d68145",
  ".waveform-plot .wave-grid|stroke|#233841",
  ".waveform-plot .wave-line|stroke|#57d1bf",
  ".waveform-plot.invalid .wave-grid|stroke|#4c302e",
  ".board-thermal-figure text|fill|#dce8ed",
  ".board-thermal-cut text|fill|#c3d9e4",
  ".board-thermal-section svg[aria-label=\"Maximum board temperature versus transient time\"] text|fill|#c3d9e4",
  ".hover-probe-reticle|border|1px solid #65e2d1",
  ".hover-probe-reticle|box-shadow|0 0 0 2px #071217c7, 0 0 10px #55dfcf66",
  ".hover-probe-reticle::before, .hover-probe-reticle::after|background|#65e2d1",
  ".layout-layer-tabs button|--layer-color|#7d929b",
  ".layout-layer-tabs button.aggregate i|background|conic-gradient(#e55757, #c965e6, #55c98b, #4f7fe8, #e55757)",
  ".layout-layer-tabs button.overview i|background|linear-gradient(135deg, #e55757 0 25%, #55c98b 25% 50%, #c965e6 50% 75%, #4f7fe8 75%)",
  ".layout-measurement-axes line|stroke|#89a9b4",
  ".layout-measurement-axes text|fill|#9db6bf",
  ".layout-measurement-axes text|stroke|#081116",
  ".impedance-plot .grid|stroke|#263b44",
  ".impedance-plot .trace|stroke|#54d5c8",
  ".topology-canvas|background-image|linear-gradient(#17252c 1px, transparent 1px), linear-gradient(90deg, #17252c 1px, transparent 1px)",
  ".topology-edge path|stroke|#d5a34d",
  ".topology-edge.return path|stroke|#65818c",
  ".topology-edge.signal path|stroke|#58c9ba",
  ".topology-edge.control path|stroke|#8b7ac4",
  ".topology-pending-wire|stroke|#65ddca",
  ".topology-pending-wire|filter|drop-shadow(0 0 3px rgba(101, 221, 202, .5))",
  ".sparam-chart line|stroke|#39505a",
  ".sparam-chart polyline|stroke|#e2a436",
  ".emi-polar-result .polar-grid|stroke|#2b4651",
  ".emi-polar-result .polar-trace|fill|rgba(82, 202, 198, .16)",
  ".emi-polar-result .polar-trace|stroke|#59cec8",
  ".si-channel-chart > svg line|stroke|#49606a",
  ".si-channel-chart .si-cursor circle|fill|#08141b",
  ".si-channel-chart .cursor-a line, .si-channel-chart .cursor-a circle|stroke|#fbbf24",
  ".si-channel-chart .cursor-b line, .si-channel-chart .cursor-b circle|stroke|#67e8f9",
  ".si-channel-chart > svg text|fill|#78919a",
  ".si-channel-chart .series-0, .si-channel-legend .series-0|stroke|#67e8f9",
  ".si-channel-chart .series-0, .si-channel-legend .series-0|color|#67e8f9",
  ".si-channel-chart .series-1, .si-channel-legend .series-1|stroke|#fbbf24",
  ".si-channel-chart .series-1, .si-channel-legend .series-1|color|#fbbf24",
  ".si-channel-chart .series-2, .si-channel-legend .series-2|stroke|#a78bfa",
  ".si-channel-chart .series-2, .si-channel-legend .series-2|color|#a78bfa",
  ".si-channel-chart .series-3, .si-channel-legend .series-3|stroke|#4ade80",
  ".si-channel-chart .series-3, .si-channel-legend .series-3|color|#4ade80",
  ".si-channel-chart .series-4, .si-channel-legend .series-4|stroke|#fb7185",
  ".si-channel-chart .series-4, .si-channel-legend .series-4|color|#fb7185",
  ".si-channel-chart .series-5, .si-channel-legend .series-5|stroke|#60a5fa",
  ".si-channel-chart .series-5, .si-channel-legend .series-5|color|#60a5fa",
]);

for (const file of sheets) {
  const sheet = postcss.parse(readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8"), { from: file });
  sheet.walkDecls(decl => {
    if (!colorProperty.test(decl.prop) || !rawColor.test(decl.value)) return;
    // A SPIKE token with a literal fallback remains portable in isolated previews.
    assert.match(decl.value, /var\(--spike-/, `${file}: raw UI color in ${decl.parent.selector} ${decl.prop}: ${decl.value}`);
  });
}

for (const [file, allowedSelector] of domainExceptions) {
  const sheet = postcss.parse(readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8"), { from: file });
  sheet.walkDecls(decl => {
    if (!colorProperty.test(decl.prop) || !rawColor.test(decl.value) || /var\(--spike-/.test(decl.value)) return;
    const context = `${decl.parent.selector ?? ""} ${decl.parent.parent?.params ?? ""}`;
    assert.match(context, allowedSelector, `${file}: undocumented raw color in ${context.trim()} ${decl.prop}: ${decl.value}`);
  });
}

const styles = postcss.parse(readFileSync(new URL("../src/styles.css", import.meta.url), "utf8"), { from: "styles.css" });
const seenStylesDomainColors = new Set();
styles.walkDecls(decl => {
  if (!stylesColorProperty.test(decl.prop) || !stylesRawColor.test(decl.value) || /var\(--spike-/.test(decl.value)) return;
  const key = `${decl.parent.selector}|${decl.prop}|${decl.value}`;
  assert.ok(stylesDomainColors.has(key), `styles.css: undocumented raw UI color in ${decl.parent.selector} ${decl.prop}: ${decl.value}`);
  seenStylesDomainColors.add(key);
});
assert.deepEqual(
  [...seenStylesDomainColors].sort(),
  [...stylesDomainColors].sort(),
  "styles.css: documented engineering color exceptions must stay exact and in use",
);

console.log(`Theme color guard passed for ${sheets.length} migrated UI stylesheets, styles.css chrome, ${domainExceptions.size} domain-color exception sheets and ${stylesDomainColors.size} exact styles.css engineering colors.`);
