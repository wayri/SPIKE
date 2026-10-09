// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { basename } from "node:path";
import { pathToFileURL } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const source = (await readFile(new URL("../src/icons/index.tsx", import.meta.url), "utf8"))
  .replace('export * from "lucide-react";', "");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const moduleRecord = { exports: {} };
new Function("require", "exports", "module", compiled)(createRequire(import.meta.url), moduleRecord.exports, moduleRecord);
const icons = moduleRecord.exports;

assert.equal(icons.workbenchIconInventory.length, 60, "native inventory should stay broad and reviewable");
assert.equal(new Set(icons.workbenchIconInventory.map(item => item.name)).size, icons.workbenchIconInventory.length, "icon names must be unique");
assert.ok(new Set(icons.workbenchIconInventory.map(item => item.category)).size >= 6, "inventory should cover every workbench category");

for (const name of ["CircuitBoard", "Grid3X3", "RadioTower", "ThermometerSun", "SquareTerminal", "Search"]) {
  const decorative = renderToStaticMarkup(React.createElement(icons[name], { size: 18, className: "fixture-icon", style: { opacity: .8 } }));
  assert.match(decorative, /viewBox="0 0 24 24"/);
  assert.match(decorative, /xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
  assert.ok(!decorative.includes("href="), `${name} must be self-contained SVG geometry`);
  assert.match(decorative, /stroke="currentColor"/);
  assert.match(decorative, /stroke-width="1\.8"/);
  assert.match(decorative, /stroke-linecap="round"/);
  assert.match(decorative, /stroke-linejoin="round"/);
  assert.match(decorative, /aria-hidden="true"/);
  assert.match(decorative, /class="fixture-icon"/);
  assert.match(decorative, /style="opacity:0\.8"/);
  assert.match(decorative, /<(path|circle|rect|line|polyline|polygon|ellipse)[ >]/, `${name} needs visible geometry`);
}

const labeled = renderToStaticMarkup(React.createElement(icons.RadioTower, { size: 48, absoluteStrokeWidth: true, "aria-label": "RF radiation source" }));
assert.match(labeled, /role="img"/);
assert.ok(!labeled.includes("aria-hidden"));
assert.match(labeled, /<title>RF radiation source<\/title>/);
assert.match(labeled, /stroke-width="0\.9"/, "absolute stroke width scales against a 24-unit viewBox");
const referencedLabel = renderToStaticMarkup(React.createElement(icons.RadioTower, { "aria-labelledby": "rf-title" }));
assert.match(referencedLabel, /role="img"/);
assert.ok(!referencedLabel.includes("aria-hidden"), "externally labelled icons must remain accessible");

const sourceRoot = new URL("../src/", import.meta.url);
const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
assert.match(appSource, /<Tool icon=\{GalleryVertical\} label="Icon gallery"/);
assert.match(appSource, /iconGalleryOpen && <IconGallery/);
const sourceFiles = (await readdir(sourceRoot, { recursive: true, withFileTypes: true }))
  .filter(entry => entry.isFile() && /\.(?:ts|tsx)$/.test(entry.name) && basename(entry.parentPath) !== "icons");
for (const entry of sourceFiles) {
  const text = await readFile(pathToFileURL(`${entry.parentPath}/${entry.name}`), "utf8");
  assert.ok(!text.includes('from "lucide-react"'), `${entry.name} bypasses the local icon barrel`);
}

console.log(`Workbench icon pack: ${icons.workbenchIconInventory.length} native icons rendered and verified`);
