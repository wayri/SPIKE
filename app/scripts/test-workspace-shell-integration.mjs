// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const file = ts.createSourceFile("App.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const visit = (node, predicate) => {
  if (predicate(node)) return node;
  let match;
  ts.forEachChild(node, child => { if (!match) match = visit(child, predicate); });
  return match;
};
const name = node => node?.name && ts.isIdentifier(node.name) ? node.name.text
  : node?.name && ts.isStringLiteral(node.name) ? node.name.text : "";
const property = (object, key) => object.properties.find(item => name(item) === key);
const arrowFrom = node => {
  assert.ok(node && ts.isArrowFunction(node), "expected an App arrow callback");
  const expression = node.getText(file);
  const output = ts.transpileModule(`const extracted = ${expression};`, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return dependencies => {
    const keys = Object.keys(dependencies);
    return new Function(...keys, `${output}; return extracted;`)(...keys.map(key => dependencies[key]));
  };
};

const selectWorkspaceDeclaration = visit(file, node => ts.isVariableDeclaration(node)
  && ts.isIdentifier(node.name) && node.name.text === "selectWorkspace");
assert.ok(selectWorkspaceDeclaration?.initializer);
const makeSelectWorkspace = arrowFrom(selectWorkspaceDeclaration.initializer);
const transitions = [];
const selectWorkspace = makeSelectWorkspace({
  setTab: value => transitions.push(["tab", value]),
  setMenu: value => transitions.push(["menu", value]),
  setLeftOpen: value => transitions.push(["left", value]),
  setRightOpen: value => transitions.push(["right", value]),
  setResultVisualizerOpen: value => transitions.push(["results", value]),
  setStatus: value => transitions.push(["status", value]),
});
selectWorkspace("PI");
assert.deepEqual(transitions, [
  ["tab", "PI"], ["menu", null], ["left", false], ["right", true], ["status", "PI workspace selected"],
], "the extracted shared transition applies the analysis-sidebar contract");
transitions.length = 0;
selectWorkspace("Results");
assert.deepEqual(transitions, [
  ["tab", "Results"], ["menu", null], ["left", false], ["right", false], ["results", true], ["status", "Results workspace selected"],
], "the Results transition retains its result-manager capability");

const universalWorkspaceObject = visit(file, node => ts.isObjectLiteralExpression(node)
  && property(node, "id")?.initializer && ts.isTemplateExpression(property(node, "id").initializer)
  && property(node, "id").initializer.head.text === "workspace:");
const universalRun = property(universalWorkspaceObject, "run")?.initializer;
assert.ok(universalRun);
const universalCalls = [];
arrowFrom(universalRun)({ selectWorkspace: value => universalCalls.push(value), name: "Thermal" })();
assert.deepEqual(universalCalls, ["Thermal"], "Universal Search delegates workspace entry to the shared transition");

const focusWorkspaceObject = visit(file, node => ts.isObjectLiteralExpression(node)
  && property(node, "id")?.initializer?.getText(file) === '"workspace:" + item.name'
  && name(property(node, "onEnter")) === "onEnter");
const focusOnEnter = property(focusWorkspaceObject, "onEnter")?.initializer;
assert.ok(focusOnEnter);
const focusCalls = [];
arrowFrom(focusOnEnter)({ selectWorkspace: value => focusCalls.push(value), item: { name: "HF / SI" } })();
assert.deepEqual(focusCalls, ["HF / SI"], "command-menu workspace entry delegates to the shared transition");

const headerElement = visit(file, node => ts.isJsxSelfClosingElement(node) && node.tagName.getText(file) === "WorkspaceHeader");
const headerWorkspaceAttribute = headerElement?.attributes.properties.find(item => ts.isJsxAttribute(item) && item.name.text === "onWorkspace");
assert.ok(headerWorkspaceAttribute && ts.isJsxExpression(headerWorkspaceAttribute.initializer));
const headerWorkspaceCallback = headerWorkspaceAttribute.initializer.expression;
const headerCalls = [];
arrowFrom(headerWorkspaceCallback)({ selectWorkspace: value => headerCalls.push(value) })("EM");
assert.deepEqual(headerCalls, ["EM"], "the rendered header route delegates to the shared transition");

const workspaceViewsCall = visit(file, node => ts.isCallExpression(node)
  && node.expression.getText(file) === "useWorkspaceViews");
assert.ok(workspaceViewsCall && ts.isObjectLiteralExpression(workspaceViewsCall.arguments[0]));
const onActionNode = property(workspaceViewsCall.arguments[0], "onAction")?.initializer;
assert.ok(onActionNode);

const visualA = { id: "board-A", designId: "design-A", name: "Board A" };
const visualB = { id: "board-B", designId: "design-B", name: "Board B" };
const context = { selected: { id: "R1" }, harness: "harness-A", highlight: { kind: "net", boardId: "board-A" }, occurrence: "board-A" };
const actionLog = [];
const onAction = arrowFrom(onActionNode)({
  assemblyToolAction: () => { throw new Error("unrelated assembly action"); },
  handleAssemblyNetSelect: () => {},
  handleAssemblyComponentSelect: () => {},
  handleSelect: object => {
    context.selected = object;
    context.harness = null;
    context.highlight = null;
    context.occurrence = null;
    actionLog.push(["object", object.id]);
  },
  virtualBoardProjection: { visuals: [visualA, visualB] },
  handleBoardInstanceSelect: board => {
    context.selected = null;
    context.harness = null;
    context.highlight = null;
    context.occurrence = board.id;
    actionLog.push(["board", board.id]);
  },
  setIsolatedAssemblyPartId: value => actionLog.push(["part", value]),
  selectWorkspace: value => actionLog.push(["workspace", value]),
  setRightOpen: value => actionLog.push(["right", value]),
  setStatus: () => {},
});
await onAction(
  { type: "open-analysis", domain: "pi", occurrenceId: "board-B" },
  { title: "Board B", scope: { kind: "board-occurrence", occurrenceId: "board-B", designId: "design-B" } },
);
assert.deepEqual(context, { selected: null, harness: null, highlight: null, occurrence: "board-B" },
  "opening scoped board analysis uses the production selection path and clears stale source context");
assert.deepEqual(actionLog, [["board", "board-B"], ["part", null], ["workspace", "PI"], ["right", true]],
  "board analysis also retires any stale isolated assembly part");

context.selected = { id: "U2" };
context.harness = "harness-B";
context.highlight = { kind: "component", boardId: "board-B" };
actionLog.length = 0;
await onAction(
  { type: "open-analysis", domain: "thermal", partId: "enclosure" },
  { title: "Enclosure", scope: { kind: "assembly-part", partId: "enclosure" } },
);
assert.equal(context.occurrence, null, "part-scoped analysis clears the previous board occurrence instead of retargeting another board");
assert.deepEqual(context.selected, { id: "enclosure", type: "component", name: "Enclosure", assemblyPartId: "enclosure" });
assert.equal(context.harness, null);
assert.equal(context.highlight, null);
assert.deepEqual(actionLog, [["object", "enclosure"], ["part", "enclosure"], ["workspace", "Thermal"], ["right", true]]);

await assert.rejects(() => onAction(
  { type: "open-analysis", domain: "em", occurrenceId: "removed" },
  { title: "Removed", scope: { kind: "board-occurrence", occurrenceId: "removed", designId: "missing" } },
), /no longer available/, "a stale scoped view cannot silently retarget analysis");

const scopedViewportEffectCall = visit(file, node => ts.isCallExpression(node)
  && node.expression.getText(file) === "useEffect"
  && node.arguments[1]?.getText(file) === "[scopedViewportActive]");
assert.ok(scopedViewportEffectCall && ts.isArrowFunction(scopedViewportEffectCall.arguments[0]));
const makeScopedViewportEffect = arrowFrom(scopedViewportEffectCall.arguments[0]);
const previousScopedViewport = { current: false };
const camera3DRef = { current: { contract: "spike/viewport-camera/v1", position: [4, 5, 6] } };
const layout2DRef = { current: { contract: "spike/layout-view/v1", x: 12, y: 18, width: 84, height: 62 } };
let viewportRestore = { token: 7, threeD: { old: "camera" }, twoD: { old: "layout" } };
let restoreUpdates = 0;
const setViewportRestore = update => {
  restoreUpdates++;
  viewportRestore = typeof update === "function" ? update(viewportRestore) : update;
};
const runScopedViewportEffect = active => makeScopedViewportEffect({
  scopedViewportActive: active,
  previousScopedViewport,
  camera3DRef,
  layout2DRef,
  setViewportRestore,
})();

runScopedViewportEffect(false);
assert.equal(restoreUpdates, 0, "an inactive scoped viewport does not alter the main pose");
runScopedViewportEffect(true);
assert.equal(restoreUpdates, 1);
assert.deepEqual(viewportRestore, { token: 8, threeD: camera3DRef.current, twoD: layout2DRef.current },
  "entering a scoped view captures the current main 3D camera and 2D layout exactly once");
const capturedRestore = viewportRestore;
camera3DRef.current = { contract: "spike/viewport-camera/v1", position: [9, 9, 9] };
layout2DRef.current = { contract: "spike/layout-view/v1", x: 99, y: 99, width: 10, height: 10 };
runScopedViewportEffect(true);
assert.equal(restoreUpdates, 1, "rerenders while scoped do not overwrite the captured main pose");
assert.equal(viewportRestore, capturedRestore);
runScopedViewportEffect(false);
assert.equal(restoreUpdates, 1, "returning to main leaves the captured restore command intact for remount");
assert.equal(viewportRestore, capturedRestore);

const mainViewportFallback = visit(file, node => ts.isBinaryExpression(node)
  && node.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken
  && node.left.getText(file) === "workspaceViews.activeRenderer"
  && node.right.getText(file).includes("<BoardViewport"));
assert.ok(mainViewportFallback, "the scoped renderer retains the production main-viewport fallback");

console.log("Workspace shell routes, scoped analysis isolation, main camera restoration, and viewport fallback passed.");
