// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { Matrix4, Vector3 } from "three";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { assemblyNetLabels } = await importTestTypescript("assemblyNetLabels");
const { validAssemblyToolAction } = await importTestTypescript("assemblyToolWindowModel");
const board={bounds:{minX:0,minY:0,maxX:100,maxY:50},width:100,height:50,nets:{1:"VCC"},tracks:[{id:"t",net:"1",layer:"F.Cu",start:[5,10],end:[95,10],width:1}],zones:[]};
const a={id:"a",netIdsByName:{VCC:"net-a"},netNamesById:{"net-a":"VCC"}};
const b={...a,id:"b",netIdsByName:{VCC:"net-b"},netNamesById:{"net-b":"VCC"}};
const first=assemblyNetLabels(board,a,{}, {},.1);
assert.equal(first[0].net,"VCC"); assert.equal(first[0].occurrenceId,"a"); assert.equal(first[0].canonicalNetId,"net-a");
assert.equal(assemblyNetLabels(board,b,{}, {},.1)[0].canonicalNetId,"net-b");
assert.equal(assemblyNetLabels(board,a,{"F.Cu":false},{},.1).length,0);
assert.equal(assemblyNetLabels(board,a,{}, {"F.Cu":0},.1).length,0);
assert(assemblyNetLabels(board,a,{}, {},.1,1).length<=1);
assert(validAssemblyToolAction({type:"net-names",value:true}));
assert(!validAssemblyToolAction({type:"net-names",value:"true"}));
console.log("Assembly net label names, occurrence identities, hidden layers, budgets and toggle admission passed");

// Execute the actual label-only effect with bounded scene stubs. This checks
// placement against the primary scene frame without allocating WebGL resources.
const viewportSource = readFileSync(new URL("../src/BoardViewport.tsx", import.meta.url), "utf8");
const ast = ts.createSourceFile("BoardViewport.tsx", viewportSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const helperNames = ["boardThicknessMm", "copperZ", "primaryNetLabelPosition", "rowMajorMatrix"];
const helpers = ast.statements.filter(node => ts.isFunctionDeclaration(node) && helperNames.includes(node.name?.text)).map(node => node.getText(ast)).join("\n");
let labelEffect;
function visit(node) {
  if (ts.isCallExpression(node) && node.expression.getText(ast) === "useEffect" && node.arguments[0]?.getText(ast).includes('labels.name = "assembly-net-labels"')) labelEffect = node.arguments[0].getText(ast);
  ts.forEachChild(node, visit);
}
visit(ast);
assert(labelEffect);
const { copperNetLabels } = await importTestTypescript("viewportPerformance");
const { assemblyLayerIsRendered } = await importTestTypescript("assemblyLayout2d");
class Sprite {
  get point() { return this.position.toArray(); }
  constructor() { this.position = new Vector3(); this.material = { map: { dispose() {} }, dispose() {} }; }
}
class Group {
  children = [];
  add(child) { this.children.push(child); }
  traverse(callback) { this.children.forEach(callback); }
}
const execute = ts.transpileModule(`${helpers}\nreturn (${labelEffect})();`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
const renderLabels = (overrides = {}) => {
  const scene = { children: [], add(group) { this.children.push(group); }, remove(group) { this.children = this.children.filter(item => item !== group); } };
  const environment = {
    sceneRef: { current: scene }, viewMode: "3D", virtualBoards: [], activeBoard: { ...board, stackup: [], layers: ["F.Cu", "B.Cu"] },
    singleBoardNetNames: true, showNetNames: true, assemblyBoardVisibility: {}, assemblyLayerVisibility: {}, assemblyLayerOpacity: {},
    assemblyNetNameVisibility: {}, visibleLayers: {}, layerOpacity: {}, isolatedNet: null, layerSeparation: 0,
    boardTransformRef: { current: { centerX: 50, centerY: 25, scale: 2 } },
    THREE: { Group, Sprite, Matrix4 }, assemblyNetLabels, assemblyBoardDesigns: {}, assemblyExplodeOffsets: {},
    kiCadLaminateMidplaneMm: source => (source.stackup.filter(row => !["F.Cu", "B.Cu", "F.Mask", "B.Mask"].includes(row.name)).reduce((sum, row) => sum + (row.thickness ?? 0), 0) || 1.6) / 2,
    overlayLabel: () => new Sprite(), copperNetLabels, assemblyLayerIsRendered,
    requestInteractiveFrameRef: { current() {} }, ...overrides,
  };
  const cleanup = new Function(...Object.keys(environment), execute)(...Object.values(environment));
  return { scene, cleanup, labels: scene.children.flatMap(group => group.children) };
};
const frontLabels = renderLabels();
assert(frontLabels.labels.length > 0, "standalone 3D has actual net label sprites");
const point = frontLabels.labels[0].point;
assert(Math.abs(point[0]) < 1e-9, "board center maps to scene X origin");
assert.equal(point[1], 30, "source Y is inverted around the primary board center");
assert(Math.abs(point[2] - 1.76) < 1e-9, "front label follows scaled 1.6mm laminate and surface clearance");
frontLabels.cleanup(); assert.equal(frontLabels.scene.children.length, 0, "toggling labels disposes only its overlay group");
assert.equal(renderLabels({ singleBoardNetNames: false }).labels.length, 0);
assert.equal(renderLabels({ visibleLayers: { "F.Cu": false } }).labels.length, 0);
assert.equal(renderLabels({ layerOpacity: { "F.Cu": 0 } }).labels.length, 0);
assert.equal(renderLabels({ activeBoard: null }).labels.length, 0, "no source board creates no labels");
const separated = renderLabels({ layerSeparation: 3 }).labels[0].point;
assert(Math.abs(separated[2] - 4.76) < 1e-9, "front labels follow the existing half-stack layer separation");
const backBoard = { ...board, stackup: [], layers: ["F.Cu", "B.Cu"], tracks: board.tracks.map(row => ({ ...row, layer: "B.Cu" })) };
const backLabels = renderLabels({ activeBoard: backBoard, layerSeparation: 3 });
assert(Math.abs(backLabels.labels[0].point[2] + 4.76) < 1e-9, "back labels follow the back copper plane and separation");
console.log("Standalone 3D net label placement, visibility, layer filters and overlay cleanup passed");

const assemblySource = { ...board, stackup: [], layers: ["F.Cu", "B.Cu"] };
const rotatedOccurrence = { ...a, designId: "source", thicknessMm: 1.6, localCenterMm: [20, 30, .8], transform: [0, -1, 0, 100, 1, 0, 0, 20, 0, 0, 1, 7, 0, 0, 0, 1] };
const hiddenSibling = { ...rotatedOccurrence, id: "b" };
const transformedLabels = renderLabels({ virtualBoards: [rotatedOccurrence, hiddenSibling], assemblyBoardDesigns: { source: assemblySource }, assemblyBoardVisibility: { b: false }, assemblyExplodeOffsets: { a: 3 } });
assert.equal(transformedLabels.labels.length, 1, "hidden sibling contributes no labels");
const transformed = transformedLabels.labels[0];
assert.deepEqual(transformed.point.slice(0, 2), [80, -90], "occurrence rotation/translation precedes primary center, scale and inverted Y");
assert(Math.abs(transformed.point[2] - 23.36) < 1e-9, "native laminate plane, occurrence Z and assembly explosion precede viewport scaling");
assert.equal(transformed.userData.occurrenceId, "a");
assert.equal(transformed.userData.canonicalNetId, "net-a");
transformedLabels.cleanup(); assert.equal(transformedLabels.scene.children.length, 0);
console.log("Assembly 3D net labels follow nonidentity occurrence transforms, primary frame and explosion");
