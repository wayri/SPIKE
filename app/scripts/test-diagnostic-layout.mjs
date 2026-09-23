import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
assert.doesNotMatch(css, /\.preflight-summary\s*>\s*div\s*\{/, "summary header flex layout must not turn the diagnostic list into narrow columns");
assert.match(css, /\.diagnostic-list\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
assert.match(css, /\.diagnostic-item > div > span\s*\{[^}]*grid-column:\s*1\s*\/\s*-1/,
  "message text must span the card width instead of competing with code and Help");
assert.match(css, /\.diagnostic-item > div > button\s*\{[^}]*grid-row:\s*1/);
console.log("diagnostic card layout regression: all assertions passed");
