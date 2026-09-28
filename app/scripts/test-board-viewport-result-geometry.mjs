// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const sourceText = readFileSync(new URL("../src/BoardViewport.tsx", import.meta.url), "utf8");
const source = ts.createSourceFile("BoardViewport.tsx", sourceText, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
const names = new Set([
  "resultHeightDisplayRange",
  "resultHeightRatio",
  "resultHeightAmplitude",
  "resultSampleMatchesVia",
]);
const helpers = source.statements
  .filter(statement => ts.isFunctionDeclaration(statement) && statement.name && names.has(statement.name.text))
  .map(statement => statement.getText(source))
  .join("\n");
assert.equal((helpers.match(/function /g) ?? []).length, names.size, "all result geometry helpers are testable");
const compiled = ts.transpileModule(`${helpers}\nexport { ${[...names].join(", ")} };`, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const geometry = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

const distribution = [...Array.from({ length: 100 }, (_, index) => index), 10_000];
const range = geometry.resultHeightDisplayRange(distribution);
assert.equal(range.minimum, 0);
assert.equal(range.maximum, 98, "height ceiling ignores an isolated outlier without changing source values");
assert.equal(geometry.resultHeightRatio(10_000, range), 1, "outliers clamp to the bounded display height");
assert.ok(geometry.resultHeightRatio(49, range) > 0.49 && geometry.resultHeightRatio(49, range) < 0.51);
assert.ok(Math.abs(geometry.resultHeightAmplitude(150, 0.5, 1.6, 8) - 5.25) < 1e-12,
  "height remains a small fraction of board span");

const via = { id: "via-415", at: [12, 8], size: 0.8, drill: 0.4, layers: ["F.Cu", "B.Cu"], net: "VCC" };
assert.equal(geometry.resultSampleMatchesVia({ element_id: "via-415:barrel:1:face:7", x_mm: 99, y_mm: 99, value: 4 }, via), true);
assert.equal(geometry.resultSampleMatchesVia({ x_mm: 12.2, y_mm: 8, value: 4, net: "VCC" }, via), true);
assert.equal(geometry.resultSampleMatchesVia({ x_mm: 12.2, y_mm: 8, value: 4, net: "GND" }, via), false);

console.log("3D result height bounds and via sample binding passed.");
