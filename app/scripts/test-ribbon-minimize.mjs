// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
assert.ok(app.includes('const legacyRibbonVisible = appSettings.interfaceMode === "classic" && appSettings.ribbonVisible;'));
assert.ok(app.includes('{legacyRibbonVisible && <CommandStrip id="workspace-ribbon-tools"'));
assert.ok(app.includes('${legacyRibbonVisible ? "ribbon-visible" : "ribbon-hidden"}'));
assert.ok(app.includes('setAppSettings(toggleLegacyRibbon)'));
assert.ok(app.includes('label="Viewport">{viewportEssentials}'), "compact navigation remains independent of the legacy ribbon");
assert.ok(app.includes('className="classic-workspace-tabs"'));
console.log("Clean excludes the legacy ribbon and retains compact navigation; Classic remains optional.");
