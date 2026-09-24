// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/SiWorkflowPlots.tsx", import.meta.url), "utf8");
const helperMatch = source.match(/export function nearestPointIndex[\s\S]*?\n}\n/);
assert.ok(helperMatch, "nearest-point helper remains available for cursor selection");
const output = ts.transpileModule(helperMatch[0], {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { nearestPointIndex } = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);

const nonUniform = [
  { x: 0, y: 1 },
  { x: 1, y: 2 },
  { x: 100, y: 3 },
];
assert.equal(nearestPointIndex(nonUniform, 40), 1, "cursor uses x distance instead of array fraction");
assert.equal(nearestPointIndex(nonUniform, 80), 2);
assert.equal(nearestPointIndex([{ x: Number.NaN, y: 1 }, { x: 4, y: 2 }], 3), 1);
assert.equal(nearestPointIndex([], 10), -1);

const geometryMatch = source.match(/export function svgViewBoxX[\s\S]*?\n}\n/);
assert.ok(geometryMatch, "SVG pointer conversion remains independently testable");
const geometryOutput = ts.transpileModule(geometryMatch[0], {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { svgViewBoxX } = await import(`data:text/javascript;base64,${Buffer.from(geometryOutput).toString("base64")}`);
assert.equal(svgViewBoxX(395, 0, 790, 270), 395, "native aspect ratio has no inset");
assert.equal(svgViewBoxX(395, 0, 790, 540), 395, "vertical letterboxing does not shift x");
assert.equal(svgViewBoxX(790, 0, 1580, 270), 395, "horizontal letterboxing is removed before scaling");
assert.equal(svgViewBoxX(890, 100, 1580, 540), 395, "scaled viewBox coordinates account for element offset");
assert.match(source, /role="dialog"/);
assert.match(source, /event\.key === "Escape"/);
assert.match(source, /event\.key !== "Tab"/);
assert.match(source, /expandButton\.current\?\.focus\(\)/);
assert.match(source, /aria-label={`Close expanded \$\{title\}`}/);
assert.match(source, /className="si-parameter-options"/, "trace menu uses an in-panel list instead of an unbounded native popup");
assert.match(source, /setSelected\(key\)/, "choosing an S-parameter changes the plotted trace");
assert.match(source, /parameterPicker\.current\?\.removeAttribute\("open"\)/, "selection and Escape dismiss the trace menu");
const css = readFileSync(new URL("../src/siWorkflow.css", import.meta.url), "utf8");
assert.match(css, /\.si-parameter-options\s*\{[^}]*max-height:[^;]+;[^}]*overflow-y: auto/s, "trace menu height is bounded and scrollable");

console.log("SI workflow plot cursor and expanded-window assertions passed");
