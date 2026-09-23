import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/trackGeometry.ts", import.meta.url), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const geometry = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);

const capCenterOffset = dimensions => dimensions.shapeLength / 2 - dimensions.width / 2;
const closeTo = (actual, expected, tolerance = 1e-12) => {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} is not within ${tolerance} of ${expected}`);
};

const straight = geometry.trackCapsuleDimensions(10, 1);
assert.equal(straight.shapeLength, 11);
assert.equal(capCenterOffset(straight), 5, "cap centers must lie on the imported endpoints");

const narrow = geometry.trackCapsuleDimensions(Math.hypot(5, 5), 0.4);
const wide = geometry.trackCapsuleDimensions(Math.hypot(5, 5), 1.2);
closeTo(capCenterOffset(narrow), narrow.centerlineLength / 2);
closeTo(capCenterOffset(wide), wide.centerlineLength / 2);
closeTo(
  capCenterOffset(narrow),
  capCenterOffset(wide),
);

const zeroLength = geometry.trackCapsuleDimensions(0, 0.6);
assert.equal(zeroLength.shapeLength, 0.6);
assert.equal(capCenterOffset(zeroLength), 0);

const invalid = geometry.trackCapsuleDimensions(Number.NaN, Number.POSITIVE_INFINITY);
assert.deepEqual(invalid, { centerlineLength: 0, shapeLength: 0, width: 0 });

console.log("Track capsule endpoint and joint geometry assertions passed.");
