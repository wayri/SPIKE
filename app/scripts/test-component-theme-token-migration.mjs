// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import postcss from "postcss";

const files = [
  "PwmElectrothermalPanel.css", "emiChamber.css", "AssemblyHandlingBar.css",
  "EMViewportResultManager.css", "EMergeExtension.css", "assemblyWorkspace.css",
  "pythonWorkspace.css", "mcpBridgePanel.css", "traceResultsWorkbench.css",
  "SavedFramePlaybackControls.css", "assemblyToolWindows.css", "KicadSchematicViewer.css",
  "AssistantChatPanel.css", "OpenEMSExtension.css", "reportPreview.css",
  "importSourceDialog.css", "pythonCompletions.css", "studyNavigator.css",
  "ThermalHistoryPopup.css",
];
const rawColor = /#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)/gi;
const source = new Map(await Promise.all(files.map(async file => [
  file,
  await readFile(fileURLToPath(new URL(`../src/${file}`, import.meta.url)), "utf8"),
])));
const tokenDefinitions = ["tableTheme.css", "buttonStandard.css"]
  .map(file => readFile(fileURLToPath(new URL(`../src/${file}`, import.meta.url)), "utf8"));
const definedTokens = new Set((await Promise.all(tokenDefinitions)).flatMap(css => [...css.matchAll(/(--spike-[\w-]+)\s*:/g)].map(match => match[1])));

for (const [file, css] of source) postcss.parse(css, { from: file });
for (const [file, css] of source) {
  for (const match of css.matchAll(/var\(\s*(--spike-[\w-]+)/g)) assert.ok(definedTokens.has(match[1]), `${file} references undefined theme token ${match[1]}`);
}

const literalFree = files.filter(file => ![
  "PwmElectrothermalPanel.css", "pythonWorkspace.css", "KicadSchematicViewer.css",
].includes(file));
for (const file of literalFree) {
  assert.deepEqual(source.get(file).match(rawColor) ?? [], [], `${file} must use shared theme/status tokens for UI chrome`);
}

const pwmColors = source.get("PwmElectrothermalPanel.css").match(rawColor) ?? [];
assert.equal(pwmColors.length, 5);
assert.deepEqual(new Set(pwmColors), new Set(["#76529f", "#c094fb", "#f8c66a", "#ffe0a6", "#5d4316"]), "PWM literals are limited to distinct plot band, trace, cursor, and point encodings");
const pwmWithoutPlotEncoding = source.get("PwmElectrothermalPanel.css").split(/\r?\n/).filter(line => !/pwm-electrothermal-(?:band|trace|cursor|point)/.test(line)).join("\n");
assert.deepEqual(pwmWithoutPlotEncoding.match(rawColor) ?? [], []);

const pythonNonSyntax = source.get("pythonWorkspace.css").split(/\r?\n/).filter(line => !/--py-code-(?:keyword|builtin|definition|class|parameter|decorator|module|number|string|comment|operator)/.test(line)).join("\n");
assert.deepEqual(pythonNonSyntax.match(rawColor) ?? [], [], "Python literals are limited to lexical syntax categories and their contrast variants");
const pythonSyntaxColors = source.get("pythonWorkspace.css").match(rawColor) ?? [];
const expectedPythonSyntaxColors = [
  "#d9a8ff", "#71d2dc", "#f1d178", "#79dcc2", "#e5c0a7", "#f4a6c8", "#91c4ff", "#f3aa79", "#a8d58c", "#94a590", "#c8bbd2",
  "#7b2da6", "#006b75", "#855900", "#08705e", "#7a4931", "#a12f67", "#285da8", "#9a431e", "#3f7027", "#60705a", "#554b5d",
  "#ffdc72", "#a7fff0", "#fff2a3", "#9bffe5", "#ffd6bd", "#ffb8dd", "#b6deff", "#ffc09a", "#c7f5a8", "#d1dfeb", "#fff",
];
assert.equal(pythonSyntaxColors.length, expectedPythonSyntaxColors.length);
assert.deepEqual(new Set(pythonSyntaxColors), new Set(expectedPythonSyntaxColors));

const schematicColors = source.get("KicadSchematicViewer.css").match(rawColor) ?? [];
assert.equal(schematicColors.length, 5);
assert.deepEqual(new Set(schematicColors), new Set(["#fff", "#e9ba4a22", "#b97600", "#f1bd5533"]), "schematic literals are limited to the document canvas and interactive pick overlay");

for (const [file, css] of source) {
  assert.doesNotMatch(css, /var\(\s*--spike-(?:table|surface|border|text|accent|popup|status)[^,)]*,\s*(?:#|rgba?\()/i, `${file} must not retain raw fallback chrome colors`);
}

console.log("component chrome uses shared graphite, teal, and semantic status tokens; data encodings remain explicit");
