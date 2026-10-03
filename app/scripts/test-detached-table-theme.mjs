// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import React from "react";

const require = createRequire(import.meta.url);
const values = new Map(), listeners = new Map(), effects = [];
const localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
const document = { documentElement: { dataset: {} } };
const window = { location: { search: "?spikeTool=probes" }, addEventListener: (key, fn) => listeners.set(key, fn), removeEventListener: (key, fn) => { if (listeners.get(key) === fn) listeners.delete(key); } };
const compile = path => ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const settingsModule = { exports: {} };
new Function("module", "exports", "localStorage", compile("../src/appSettings.ts"))(settingsModule, settingsModule.exports, localStorage);
const settings = settingsModule.exports;
const module = { exports: {} };
new Function("require", "module", "exports", "window", "document", compile("../src/detachedToolWindows.tsx"))(name => {
  if (name === "react") return { ...React, lazy: () => () => null, useState: initial => [initial, () => {}], useMemo: fn => fn(), useEffect: fn => effects.push(fn) };
  if (name === "./appSettings") return settings;
  if (name === "./DataTable" || name === "./detachedToolWindowModel" || name.endsWith(".css")) return {};
  return require(name);
}, module, module.exports, window, document);
settings.saveAppSettings({ ...settings.DEFAULT_SETTINGS, theme: "high-contrast" });
module.exports.DetachedToolWindowRoot({ kind: "probes" });
const cleanup = effects[0]();
assert.equal(document.documentElement.dataset.theme, "high-contrast", "detached tables read saved preferences when opened");
settings.saveAppSettings({ ...settings.DEFAULT_SETTINGS, theme: "system" });
listeners.get("storage")({ key: "unrelated" });
assert.equal(document.documentElement.dataset.theme, "high-contrast");
listeners.get("storage")({ key: settings.APP_SETTINGS_STORAGE_KEY });
assert.equal(document.documentElement.dataset.theme, "system", "an open detached table updates when preferences change");
values.clear(); listeners.get("storage")({ key: null });
assert.equal(document.documentElement.dataset.theme, "professional-dark", "cleared preferences recover the default theme");
values.set(settings.APP_SETTINGS_STORAGE_KEY, "invalid JSON"); listeners.get("storage")({ key: settings.APP_SETTINGS_STORAGE_KEY });
assert.equal(document.documentElement.dataset.theme, "professional-dark", "malformed settings do not break a detached table");
cleanup(); assert.ok(!listeners.has("storage"), "unmounted windows stop observing settings");
console.log("Detached table theme initialization, live settings updates, recovery and listener cleanup passed.");
