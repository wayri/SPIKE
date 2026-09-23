import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
assert.equal((app.match(/<nav className="ribbon-tabs"/g) ?? []).length, 1);
assert.ok(!app.includes("{appSettings.ribbonVisible && <>"));
assert.ok(app.includes('{appSettings.ribbonVisible && <div id="workspace-ribbon-tools"'));
assert.ok(app.includes('aria-expanded={appSettings.ribbonVisible}'));
assert.ok(app.includes('aria-controls="workspace-ribbon-tools"'));
for (const rows of ["52px 28px 40px", "44px 25px 36px", "42px 24px 34px"]) {
  assert.ok(css.includes(`grid-template-rows: ${rows} minmax(0, 1fr)`));
}
assert.ok(!css.includes(".ribbon-tabs { overflow: hidden; }"));
console.log("Ribbon minimization retains navigation and responsive grid rows.");
