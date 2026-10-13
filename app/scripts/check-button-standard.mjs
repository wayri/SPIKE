// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import postcss from "postcss";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const appDir = resolve(scriptDir, "..");
const read = path => readFileSync(resolve(appDir, path), "utf8");
const standardSource = read("src/buttonStandard.css");
const standard = postcss.parse(standardSource);

assert.match(read("src/main.tsx"), /import\s+["']\.\/buttonStandard\.css["'];/, "main.tsx must import the shared control standard");

const previewsWithButtons = readdirSync(scriptDir)
  .filter(name => name.endsWith("-preview.tsx"))
  .filter(name => /<button\b|role=["']button["']/.test(read(`scripts/${name}`)));
assert.ok(previewsWithButtons.length > 0, "expected first party interactive previews");
for (const name of previewsWithButtons) {
  const source = read(`scripts/${name}`);
  assert.match(source, /import\s+["']\.\.\/src\/buttonStandard\.css["'];/, `${name} must import buttonStandard.css`);
  assert.doesNotMatch(source, /<button\b[^>]*\bstyle=\{/, `${name} must not bypass the standard with an inline button style`);
}

const selectors = [];
standard.walkRules(rule => selectors.push(rule.selector));
const hasSelector = fragment => selectors.some(selector => selector.includes(fragment));
assert.ok(selectors.some(selector => selector.includes("button") && selector.includes('[role="button"]') && !selector.includes(":where")), "Typography reset must beat the legacy inherited-font rule");
for (const [fragment, description] of [
  [":where(button, [role=\"button\"]", "native and ARIA button baseline"],
  [":hover:not(:disabled", "enabled hover state"],
  [":active:not(:disabled", "enabled active state"],
  ["[aria-pressed=\"true\"]", "pressed state"],
  [":focus-visible", "keyboard focus state"],
  [":disabled", "native disabled state"],
  ["[aria-disabled=\"true\"]", "ARIA disabled state"],
  ["::file-selector-button", "file input button"],
]) assert.ok(hasSelector(fragment), `Missing ${description}`);

const declarations = new Map();
standard.walkDecls(decl => {
  const values = declarations.get(decl.prop) ?? [];
  values.push(decl.value);
  declarations.set(decl.prop, values);
  if (!decl.parent.selector || decl.parent.selector === ":root") return;
  assert.doesNotMatch(decl.value, /#[0-9a-f]{3,8}\b|\brgba?\s*\(/i, `Raw color in shared rule ${decl.parent.selector}; use a SPIKE token`);
});
for (const property of ["appearance", "min-height", "padding", "border", "border-radius", "color", "background", "font", "outline", "cursor"]) {
  assert.ok(declarations.has(property), `Missing required ${property} declaration`);
}
assert.ok(declarations.get("appearance").every(value => value === "none"), "Clickable controls must not use browser-native button appearance");
assert.ok(standardSource.includes('@import "./tableTheme.css";'), "Control palette must come from tableTheme.css");

console.log(`SPIKE button/control standard passed for the desktop entrypoint and ${previewsWithButtons.length} interactive previews.`);
