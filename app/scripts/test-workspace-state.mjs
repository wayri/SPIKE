import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/workspaceState.ts", import.meta.url), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const workspace = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);

const valid = workspace.normalizeWorkspaceState({
  contract: "spike/workspace-state/v1",
  viewMode: "2D",
  docks: {
    leftOpen: false,
    rightOpen: true,
    bottomOpen: false,
    sidePanelsPinned: false,
    bottomPinned: true,
    leftWidthPx: 310,
    rightWidthPx: 415,
    bottomHeightPx: 240,
    activeBottomDock: "Console",
  },
  viewports: {
    threeD: { contract: "spike/viewport-camera/v1", position: [4, 5, 6], target: [1, 2, 3], up: [0, 0, 1] },
    twoD: { contract: "spike/layout-view/v1", x: 10, y: 20, width: 30, height: 40 },
  },
});
assert.equal(valid.viewMode, "2D");
assert.equal(valid.docks.activeBottomDock, "Console");
assert.equal(valid.docks.leftOpen, false);
assert.deepEqual(valid.viewports.twoD, { contract: "spike/layout-view/v1", x: 10, y: 20, width: 30, height: 40 });

const bounded = workspace.normalizeWorkspaceState({
  contract: "spike/workspace-state/v1",
  docks: { leftWidthPx: -50, rightWidthPx: 10000, bottomHeightPx: Number.NaN, activeBottomDock: "Invalid" },
  viewports: {
    threeD: { contract: "spike/viewport-camera/v1", position: [0, 0, 0], target: [0, 0, 0], up: [0, 0, 0] },
    twoD: { contract: "spike/layout-view/v1", x: 0, y: 0, width: -1, height: 10 },
  },
});
assert.equal(bounded.docks.leftWidthPx, 180);
assert.equal(bounded.docks.rightWidthPx, 620);
assert.equal(bounded.docks.bottomHeightPx, 178);
assert.equal(bounded.docks.activeBottomDock, "Issues");
assert.equal(bounded.viewports.threeD, undefined);
assert.equal(bounded.viewports.twoD, undefined);
assert.equal(workspace.normalizeWorkspaceState({ contract: "spike/workspace-state/v0" }), null);

console.log("SPIKE workspace-state validation and bounds assertions passed");
