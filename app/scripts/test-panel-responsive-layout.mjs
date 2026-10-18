// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const read = name => readFile(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const [scriptResults, studies, flex, panels] = await Promise.all([
  read("ScriptResultViewport.css"),
  read("studyManager.css"),
  read("FlexBoardManager.css"),
  read("PanelResponsive.css"),
]);

assert.match(scriptResults, /container:\s*script-result\s*\/\s*inline-size/);
for (const width of [900, 540, 360]) assert.match(scriptResults, new RegExp(`@container script-result \\(max-width: ${width}px\\)`));
assert.match(scriptResults, /\.script-result-body\s*\{[^}]*overflow:\s*auto/s, "stacked results remain vertically reachable");
assert.doesNotMatch(scriptResults, /@media|\b(?:vw|vh|dvh)\b/, "script result layout follows its panel");

assert.match(studies, /container:\s*study-manager\s*\/\s*inline-size/);
for (const width of [1200, 900, 700, 520, 360]) assert.match(studies, new RegExp(`@container study-manager \\(max-width: ${width}px\\)`));
assert.match(studies, /\.study-manager \.study-inspector\s*\{[^}]*position:\s*absolute;[^}]*inset:\s*0/s, "narrow inspector is bounded by the manager body");
assert.match(studies, /content:\s*"Source status"/, "the previously hidden status becomes a labeled card field");
assert.match(studies, /nth-child\(6\)::before\s*\{\s*content:\s*"Move"/, "case reordering remains visible in card mode");
assert.match(studies, /\.study-delete-confirm > div\s*\{[^}]*box-sizing:\s*border-box;[^}]*max-height:\s*calc\(100% - 30px\);[^}]*overflow:\s*auto/s, "delete confirmation stays inside short and narrow panel hosts");
assert.match(studies, /@container study-manager \(max-width: 520px\)\s*\{[^}]*\.study-manager-header\s*\{[^}]*flex-direction:\s*column/s, "study title and actions stack before they collide");
assert.doesNotMatch(studies, /@media|\b(?:vw|vh|dvh)\b|position:\s*fixed/, "study layout and inspector follow the manager pane");

assert.match(flex, /container:\s*flex-board\s*\/\s*inline-size/);
assert.doesNotMatch(flex, /@media|\b(?:vw|vh|dvh)\b/, "flex manager sizing follows its host panel");
for (const width of [900, 540, 360]) assert.match(flex, new RegExp(`@container flex-board \\(max-width: ${width}px\\)`));

assert.match(panels, /container:\s*spice-workbench\s*\/\s*inline-size/);
assert.match(panels, /container:\s*emi-dashboard\s*\/\s*inline-size/);
for (const width of [900, 540, 360]) {
  assert.match(panels, new RegExp(`@container spice-workbench \\(max-width: ${width}px\\)`));
  assert.match(panels, new RegExp(`@container emi-dashboard \\(max-width: ${width}px\\)`));
}
assert.match(panels, /\.spice-pin-table\s*\{\s*min-width:\s*390px/, "pin mapping keeps all columns in a scrollable table");
assert.match(panels, /\.emi-dashboard > footer p\s*\{\s*display:\s*flex/, "the screening and solver validity statement remains visible");
for (const label of ["Priority", "Net", "Score", "Evidence"]) assert.match(panels, new RegExp(`content: "${label}"`));

console.log("container-responsive script, study, flex, SPICE, and EMI layout contracts passed");
