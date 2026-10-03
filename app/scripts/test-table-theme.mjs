// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import postcss from "postcss";

const paletteSheet = postcss.parse(readFileSync(new URL("../src/tableTheme.css", import.meta.url), "utf8"));
const tableSheet = postcss.parse(readFileSync(new URL("../src/DataTable.css", import.meta.url), "utf8"));
const palettes = new Map();
paletteSheet.walkRules(rule => {
  for (const name of ["professional-dark", "light", "high-contrast"]) {
    if (!rule.selector.includes(`[data-table-theme="${name}"]`)) continue;
    palettes.set(name, Object.fromEntries(rule.nodes.filter(node => node.type === "decl").map(node => [node.prop, node.value])));
  }
});
const rgb = hex => {
  assert.match(hex, /^#[0-9a-f]{6}([0-9a-f]{2})?$/i);
  return [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
};
const over = (foreground, background) => {
  const alpha = foreground.length === 9 ? parseInt(foreground.slice(7), 16) / 255 : 1;
  return rgb(foreground).map((value, i) => value * alpha + rgb(background)[i] * (1 - alpha));
};
const luminance = color => color.map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4)
  .reduce((sum, c, i) => sum + c * [.2126, .7152, .0722][i], 0);
const contrast = (foreground, background, base = background) => {
  const a = luminance(rgb(foreground)), b = luminance(over(background, base));
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
};
for (const [name, tokens] of palettes) {
  const p = key => tokens[`--spike-table-${key}`];
  const readable = (text, bg, minimum = 4.5, base = p("surface")) => {
    const ratio = contrast(p(text), p(bg), base);
    assert.ok(ratio >= minimum, `${name}: ${text} on ${bg} is ${ratio.toFixed(2)}:1, requires ${minimum}:1`);
  };
  for (const bg of ["surface", "stripe", "hover", "row-focus", "field", "edit-hover", "choice-bg", "choice-hover", "action-bg", "action-hover", "warning-bg"]) readable("text", bg);
  for (const bg of ["surface", "stripe", "toolbar"]) readable("muted", bg);
  readable("text-strong", "header");
  readable("danger-text", "danger-bg"); readable("danger-text", "danger-hover");
  for (const bg of ["surface", "stripe", "toolbar", "field", "choice-bg", "action-bg"]) readable("focus", bg, 3);
  readable("edit", "field", 3); readable("choice", "choice-bg", 3);
  for (const [icon, stroke] of [["edit", "edit"], ["choice", "choice"], ["lock", "muted"]]) {
    const svg = decodeURIComponent(tokens[`--table-${icon}-icon`]);
    assert.ok(svg.includes(`stroke='${p(stroke)}'`), `${name}: ${icon} cue must follow its palette`);
  }
  tableSheet.walkDecls(decl => {
    assert.ok(!/#[\da-f]{6,8}\b/i.test(decl.value), `Hardcoded table color in ${decl.prop}`);
    for (const [, token] of decl.value.matchAll(/var\((--spike-table-[\w-]+)\)/g)) assert.ok(token in tokens, `${name}: missing ${token}`);
  });
}
assert.equal(palettes.size, 3);
const systemRules = [];
paletteSheet.walkRules(rule => { if (rule.selector.includes('[data-table-theme="system"]')) systemRules.push(rule); });
assert.ok(systemRules.some(rule => rule.parent.type === "root" && rule.nodes.some(n => n.prop === "--spike-table-scheme" && n.value === "dark")));
assert.ok(systemRules.some(rule => rule.parent.type === "atrule" && rule.parent.params === "(prefers-color-scheme: light)" && rule.nodes.some(n => n.prop === "--spike-table-scheme" && n.value === "light")));
console.log("Dark, light and high-contrast table palettes passed text/cue contrast, icon colors, token coverage and system preference checks.");
