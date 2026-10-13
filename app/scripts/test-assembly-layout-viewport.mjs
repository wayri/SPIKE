// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { importTestTypescript } from "./import-test-typescript.mjs";

const api = await importTestTypescript("assemblyLayout2d");
assert.equal(api.resolveAssemblyLayerFocus({layers:["F.Cu","B.Cu"]},"F.Cu"),"F.Cu");
for (const stale of ["In9.Cu", {}, null, 42]) assert.equal(api.resolveAssemblyLayerFocus({layers:["F.Cu","B.Cu"]},stale),"All");
const interaction = await importTestTypescript("assemblyViewportInteraction");
const transform = [0, -1, 0, 100, 1, 0, 0, 20, 0, 0, 1, 7, 0, 0, 0, 1];
assert.deepEqual(api.projectAssemblyPoint(transform, [2, 3, 0]), [97, 22, 7]);
assert.equal(api.assemblySvgMatrix(transform), "matrix(0 1 -1 0 100 20)");
const visual = { id: "upper", name: "Upper", designId: "cpu", active: true, widthMm: 20, heightMm: 10, localCenterMm: [5, 10, 0], transform };
const board = { bounds: { minX: 0, minY: 0, maxX: 20, maxY: 10 }, width: 20, height: 10, nets: { "12": "VCC", "19": "GND" } };
assert.deepEqual(api.assemblyBoardBounds(visual, board), { x: 90, y: 20, width: 10, height: 20 });
assert.equal(api.boardAssemblyZ(visual), 7, "stacked boards retain explicit assembly Z for ordering and selector labels");
const secondOccurrence = { ...visual, id: "upper-copy", transform: [1, 0, 0, -30, 0, 1, 0, 4, 0, 0, 1, 1, 0, 0, 0, 1] };
const harness = { id: "h1", routeMm: [], endpointA: { positionMm: [70, 10, 0] }, endpointB: { positionMm: [110, 50, 0] } };
assert.deepEqual(api.harnessAssemblyPoints(harness), [[70, 10, 0], [110, 50, 0]], "unrouted harnesses retain both exact endpoints");
const bounds = api.assemblyContentBounds([visual, secondOccurrence], { cpu: board }, [harness]);
assert.ok(bounds.x < 70 && bounds.y < 10 && bounds.x + bounds.width > 110 && bounds.y + bounds.height > 50, "fit includes complete boards and harness routes");
assert.equal(api.canonicalNetId(board, { VCC: "net-uuid-vcc" }, "VCC"), "net-uuid-vcc", "retained canonical net IDs take priority over parser IDs");
assert.equal(api.canonicalNetId(board, undefined, "GND"), "19", "legacy parser IDs remain a bounded fallback");
assert.equal(api.canonicalNetId(board, undefined, "LOCAL"), null, "unmapped geometry names cannot submit fabricated canonical IDs");
const firstOccurrenceNetIds = { VCC: "same-canonical-id" };
const secondOccurrenceNetIds = { VCC: "same-canonical-id" };
assert.equal(api.assemblyNetIsSelected(board, firstOccurrenceNetIds, ["same-canonical-id"], "VCC"), true);
assert.equal(api.assemblyNetIsSelected(board, secondOccurrenceNetIds, [], "VCC"), false,
  "identical net IDs and names on another occurrence do not inherit selection");
assert.equal(api.assemblyLayerIsRendered("F.Cu", {"F.Cu":true}, {"F.Cu":1}), true);
assert.equal(api.assemblyLayerIsRendered("F.Cu", {"F.Cu":false}, {"F.Cu":1}), false, "an occurrence layer toggle removes source art and its hit geometry");
assert.equal(api.assemblyLayerIsRendered("F.Cu", {"F.Cu":true}, {"F.Cu":0}), false, "zero occurrence opacity removes source art and its hit geometry");
assert.notDeepEqual(api.assemblyBoardBounds(visual, board), api.assemblyBoardBounds(secondOccurrence, board), "repeated designs keep occurrence transforms independent");
const physicalBefore = structuredClone([visual.transform, secondOccurrence.transform]);
const plotted = { ...board, bounds: {minX:114,minY:78,maxX:134,maxY:88},
  layoutViewBox:[40,25,24,14], layoutLayerUrls:{"F.Cu":"blob:layer"} };
assert.deepEqual(api.assemblyLayoutImageBounds(plotted), {x:112,y:76,width:24,height:14},
  "offset plot page must be mapped back to source board coordinates");
const sourceFrame = api.assemblyLayoutSourceFrame(plotted);
assert.deepEqual(sourceFrame.sourceViewBox, {x:40,y:25,width:24,height:14}, "retained SVG viewBox origin remains explicit");
assert.deepEqual(sourceFrame.boardToSourceOffset, [-72,-51], "native board coordinates map into the retained SVG page");
assert.deepEqual(sourceFrame.sourceToBoardOffset, [72,51], "source page coordinates map back into the native board frame");
assert.deepEqual([114 + sourceFrame.boardToSourceOffset[0] + sourceFrame.sourceToBoardOffset[0], 78 + sourceFrame.boardToSourceOffset[1] + sourceFrame.sourceToBoardOffset[1]], [114,78],
  "source and normalized geometry frames cancel before the occurrence transform");
const differentlyLocated = { ...plotted, bounds: {minX:-34,minY:205,maxX:-14,maxY:215}, layoutViewBox:[-8,9,24,14] };
assert.notDeepEqual(api.assemblyLayoutSourceFrame(differentlyLocated).boardToSourceOffset, sourceFrame.boardToSourceOffset,
  "each differently located board derives its own source-to-native alignment");
const actualUnoOutline = { ...plotted, outlineLoops: [], drawings: [
  { layer:"Edge.Cuts", points:[[114.2111,79.3336],[114.2111,130.6736]] },
  { layer:"Edge.Cuts", points:[[115.2111,78.3336],[178.7271,78.3336]] },
  { layer:"Edge.Cuts", points:[[115.2111,131.6736],[179.2511,131.6736]] },
] };
const actualUnoEdgeSvg = `<svg viewBox="0 0 83.058 63.5762"><path d="M2.3600 8.5902 L2.3600 59.9302"/><path d="M3.3600 7.5902 L66.8760 7.5902"/><path d="M3.3600 60.9302 L67.4000 60.9302"/></svg>`;
const actualUnoOffset = api.inferAssemblyLayoutBoardToSourceOffset(actualUnoOutline, actualUnoEdgeSvg);
assert.ok(actualUnoOffset);
assert.ok(Math.abs(actualUnoOffset[0] + 111.8511) < 1e-9 && Math.abs(actualUnoOffset[1] + 70.7434) < 1e-9,
  "real KiCad Edge.Cuts coordinates recover the asymmetric plot-page translation instead of assuming centered margins");
const actualUnoFrame = api.assemblyLayoutSourceFrame(actualUnoOutline, actualUnoOffset);
const alignedUnoPoint = [114.2111 + actualUnoFrame.boardToSourceOffset[0], 79.3336 + actualUnoFrame.boardToSourceOffset[1]];
assert.ok(Math.abs(alignedUnoPoint[0] - 2.36) < 1e-9 && Math.abs(alignedUnoPoint[1] - 8.5902) < 1e-9,
  "a parsed UNO outline endpoint lands exactly on its retained SVG endpoint");
const plottedPlacements = api.arrangeAssemblyBoards([visual, secondOccurrence], {cpu:plotted});
assert.deepEqual(plottedPlacements.map(item => [item.bounds.width,item.bounds.height]), [[14,24],[24,14]],
  "fit and packing include the full plot page under occurrence rotation");
const overlapping = { ...secondOccurrence, id: "overlap", transform: [...visual.transform] };
const rotated = { ...visual, id: "rotated", transform: [Math.SQRT1_2, -Math.SQRT1_2, 0, 0, Math.SQRT1_2, Math.SQRT1_2, 0, 0, 0, 0, 1, 3, 0, 0, 0, 1] };
const placements = api.arrangeAssemblyBoards([visual, secondOccurrence, overlapping, rotated], { cpu: board });
assert.equal(placements.length, 4, "every board occurrence receives a display placement");
for (let i = 0; i < placements.length; i += 1) for (let j = i + 1; j < placements.length; j += 1) {
  const a = placements[i].bounds, b = placements[j].bounds;
  assert.ok(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y, `display AABBs ${placements[i].visual.id}/${placements[j].visual.id} do not overlap`);
}
assert.deepEqual([visual.transform, secondOccurrence.transform], physicalBefore, "display packing leaves physical occurrence transforms unchanged");
const rotatedBounds = api.assemblyBoardBounds(rotated, board);
assert.ok(rotatedBounds.width > 20 && rotatedBounds.height > 20, "rotated bounds conservatively include all transformed corners");
const offsets = api.displayOffsetByBoard(placements);
const linkedHarness = { id: "linked", routeMm: [[97, 22, 7], [40, 12, 3], [-25, 9, 1]], endpointA: { boardId: "upper", positionMm: [97, 22, 7] }, endpointB: { boardId: "upper-copy", positionMm: [-25, 9, 1] } };
const displayedRoute = api.harnessDisplayPoints(linkedHarness, offsets);
assert.deepEqual(displayedRoute[0].slice(0, 2), [97 + offsets.upper[0], 22 + offsets.upper[1]], "displayed link starts at relocated connector endpoint");
assert.deepEqual(displayedRoute.at(-1).slice(0, 2), [-25 + offsets["upper-copy"][0], 9 + offsets["upper-copy"][1]], "displayed link ends at relocated connector endpoint");

const squareViewport = { left: 10, top: 20, width: 400, height: 400 };
const wideView = { x: 0, y: 0, width: 200, height: 100 };
assert.deepEqual(interaction.assemblyClientPoint(wideView, squareViewport, 210, 220), [100, 50], "client mapping removes SVG's vertical letterbox inset");
const wheelClient = [310, 270];
const wheelAnchor = interaction.assemblyClientPoint(wideView, squareViewport, ...wheelClient);
const zoomed = interaction.zoomAssemblyViewBox(wideView, squareViewport, ...wheelClient, .82);
const anchoredAfterZoom = interaction.assemblyClientPoint(zoomed, squareViewport, ...wheelClient);
assert.ok(Math.hypot(anchoredAfterZoom[0] - wheelAnchor[0], anchoredAfterZoom[1] - wheelAnchor[1]) < 1e-9, "wheel zoom preserves the pointed assembly coordinate through letterboxing");
assert.deepEqual(interaction.panAssemblyViewBox(wideView, squareViewport, 40, -20), { x: -20, y: 10, width: 200, height: 100 }, "drag pan uses the SVG uniform meet scale on both axes");
assert.equal(interaction.assemblyPanStarted(3, 0), false, "small pointer motion remains a click for board/component/net picking");
assert.equal(interaction.assemblyPanStarted(4, 0), true, "intentional drag crosses the pan threshold");
const focused = interaction.focusAssemblyViewBox({ x: 50, y: 20, width: 30, height: 10 }, 2);
assert.ok(Math.abs(focused.width / focused.height - 2) < 1e-12 && focused.x < 50 && focused.x + focused.width > 80, "Focus frames the selected bounds at viewport aspect with margin");

const fixturePath = fileURLToPath(new URL("../../build/multiboard-workspace-20261003/arduino-r4-relay-demo.spike", import.meta.url));
if (existsSync(fixturePath)) {
  const python = process.platform === "win32" ? "python" : "python3";
  const fixtureRows = JSON.parse(execFileSync(python, ["-c", `import json,sys,zipfile
z=zipfile.ZipFile(sys.argv[1])
a=json.loads(z.read('design/assembly-ir.json'))
d=json.loads(z.read('design/assembly-designs.json'))
print(json.dumps({'active_design_id':d['active_design_id'],'boards':a['boards'],'designs':[{'design_id':x['design_id'],'bounds':x['metadata']['board_bounds_mm'],'tracks':len(x['tracks']),'pads':len(x['pads']),'zones':len(x['zones']),'components':len(x['components'])} for x in d['designs']]}))`, fixturePath], { encoding: "utf8" }));
  const fixtureDesigns = Object.fromEntries(fixtureRows.designs.map(row => [row.design_id, { bounds: { minX: row.bounds[0], minY: row.bounds[1], maxX: row.bounds[2], maxY: row.bounds[3] }, width: row.bounds[2] - row.bounds[0], height: row.bounds[3] - row.bounds[1] }]));
  const fixtureVisuals = fixtureRows.boards.map(row => { const bounds = fixtureDesigns[row.design_id].bounds; return { id: row.id, name: row.name, designId: row.design_id, active: true, widthMm: bounds.maxX - bounds.minX, heightMm: bounds.maxY - bounds.minY, localCenterMm: [(bounds.minX + bounds.maxX) / 2, (bounds.minY + bounds.maxY) / 2, 0], transform: row.frame.transform }; });
  const realPlacements = api.arrangeAssemblyBoards(fixtureVisuals, fixtureDesigns);
  const realFit = api.displayContentBounds(realPlacements);
  assert.deepEqual(realPlacements.map(row => row.visual.id).sort(), ["relay-shield", "uno-r4-minima"], "real retained fixture contributes both occurrence-scoped boards");
  const fixtureCounts = Object.fromEntries(fixtureRows.designs.map(row => [row.design_id, [row.tracks, row.pads, row.zones, row.components]]));
  assert.deepEqual(fixtureCounts[fixtureRows.active_design_id], [1319, 304, 24, 85], "the active UNO fixture retains its real manufacturing geometry");
  const relayDesignId = fixtureRows.boards.find(row => row.id === "relay-shield").design_id;
  assert.deepEqual(fixtureCounts[relayDesignId], [356, 167, 2, 47], "the relay fixture retains its real manufacturing geometry");
  const realZoom = interaction.zoomAssemblyViewBox(realFit, { left: 0, top: 0, width: 997, height: 563 }, 640, 281, .82);
  const realPan = interaction.panAssemblyViewBox(realZoom, { left: 0, top: 0, width: 997, height: 563 }, 73, -41);
  assert.ok(realPan.width < realFit.width && realPan.x !== realFit.x && realPan.y !== realFit.y, "real two-board fit supports combined anchored zoom and pan gestures");
}
const viewportSource = await readFile(new URL("../src/AssemblyLayoutViewport.tsx", import.meta.url), "utf8");
assert.match(viewportSource, /onComponentSelect\?: \(boardId: string, componentId: string\)/, "component selection is an optional viewport API");
assert.match(viewportSource, /event\.stopPropagation\(\);\s*onFocus\(visual\.id, event\.currentTarget\);\s*onBoardSelect\(visual\);\s*onComponentSelect\?\.\(visual\.id, item\.id\)/, "component hits retain focus, select their occurrence, and cannot fall through to a net target");
assert.match(viewportSource, /const useFallback = !hasAlignedSource/, "retained vector geometry remains visible while source alignment is pending or unavailable");
assert.match(viewportSource, /<ComponentShapes[^>]+sourceLayers=\{hasAlignedSource\}/, "component art switches to transparent hit geometry only after source SVG alignment succeeds");
assert.match(viewportSource, /addEventListener\("wheel", onWheel, \{ passive: false \}\)/, "wheel cancellation is installed on a native non-passive listener");
assert.match(viewportSource, /selectionFilter !== "net"/, "Net selection mode removes component hitboxes that would occlude pads and tracks");
assert.match(viewportSource, /linked=\{linkedNets\[visual\.id\] \?\? \[\]\}/, "equal net IDs and names remain scoped to each board occurrence");
assert.match(viewportSource, /useFallback && <g[^>]*><BoardFallback/, "hiding every retained source layer does not draw a fallback ghost board");
assert.match(viewportSource, /data-layout-source-frame[\s\S]*data-layout-board-frame/, "source SVG and normalized hit geometry use explicit inverse frames");
assert.match(viewportSource, /stroke="#55e5d5"/, "selected assembly nets use the SPIKE teal highlight");
assert.doesNotMatch(viewportSource, /drop-shadow\([^)]*#ffe25b|stroke=\{selected\(item\.net\) \? "#ffe25b"/, "legacy broad yellow net glow is removed");
assert.match(viewportSource, /setLocalFocusedLayerByBoard\(current => \(\{ \.\.\.current, \[selected\.id\]: layer \}\)\); onLayerFocus\?\.\(selected\.id, layer\)/, "quick layer focus mutates and reports only the selected occurrence preference");
assert.match(viewportSource, /data-layer-focus=\{layerFocus\}/, "each occurrence retains and renders its own quick layer preference");
assert.match(viewportSource, /inferAssemblyLayoutBoardToSourceOffset\(board, await response\.text\(\)\)/, "retained Edge.Cuts establishes the actual source-page offset before source layers render");

const instrumentedViewportSource = viewportSource.replace(
  /useState<Record<string, \{ board: ParsedBoard; offset: AssemblyDisplayOffset \| null \}>>\(\{\}\)/,
  "useState<Record<string, { board: ParsedBoard; offset: AssemblyDisplayOffset | null }>>((globalThis.__assemblyTestSourceAlignments ?? {}))",
);
assert.notEqual(instrumentedViewportSource, viewportSource, "the behavioral renderer controls only the initial alignment state");
const viewportBundle = await build({
  stdin: {
    contents: instrumentedViewportSource,
    loader: "tsx",
    resolveDir: fileURLToPath(new URL("../src", import.meta.url)),
    sourcefile: "AssemblyLayoutViewport.tsx",
  },
  bundle: true,
  write: false,
  format: "cjs",
  platform: "node",
  jsx: "automatic",
  external: ["react"],
  loader: { ".css": "empty" },
});
const viewportModule = { exports: {} };
const require = createRequire(import.meta.url);
new Function("require", "module", "exports", viewportBundle.outputFiles[0].text)(
  name => name === "react" ? React : require(name),
  viewportModule,
  viewportModule.exports,
);
const AssemblyLayoutViewport = viewportModule.exports.default;
let pendingBoard = {
  bounds: { minX: 0, minY: 0, maxX: 20, maxY: 10 },
  width: 20,
  height: 10,
  outlineLoops: [[[0, 0], [20, 0], [20, 10], [0, 10], [0, 0]]],
  layers: ["F.Cu"],
  layerDefinitions: [{ id: 0, name: "F.Cu", kind: "signal" }],
  nets: { 1: "VCC" },
  drawings: [],
  tracks: [{ id: "pending-track", start: [1, 2], end: [9, 2], width: .25, layer: "F.Cu", net: "VCC" }],
  zones: [],
  vias: [],
  pads: [],
  components: [{ id: "pending-part", ref: "U1", at: [5, 5], width: 2, height: 2, rotation: 0 }],
  layoutViewBox: [0, 0, 20, 10],
  layoutLayerUrls: { "F.Cu": "blob:pending-layer", "Edge.Cuts": "blob:pending-outline" },
};
const pendingVisual = {
  id: "pending-occurrence",
  name: "Pending board",
  designId: "pending-design",
  active: true,
  widthMm: 20,
  heightMm: 10,
  localCenterMm: [10, 5, 0],
  transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
};
const renderPending = (visibleLayers, options = {}) => renderToStaticMarkup(React.createElement(AssemblyLayoutViewport, {
  designs: { "pending-design": pendingBoard },
  boards: [pendingVisual],
  harnesses: [],
  selectedBoardId: "pending-occurrence",
  linkedNets: options.linkedNets ?? {},
  visibleLayers,
  showNetNames:options.showNetNames ?? false,
  layerOpacity: options.layerOpacity ?? {},
  showVias: true,
  onBoardSelect() {},
  onNetSelect() {},
}));
const labeledMarkup=renderPending({}, {showNetNames:true});
assert.match(labeledMarkup,/data-net-label="1" data-occurrence-id="pending-occurrence"/);
assert.match(labeledMarkup,/>VCC<\/text>/);
assert.doesNotMatch(renderPending({}, {showNetNames:false}),/data-net-label=/);
assert.doesNotMatch(renderPending({"F.Cu":false}, {showNetNames:true}),/data-net-label=/,"hidden layer nets are not labeled");
const pendingMarkup = renderPending({});
assert.match(pendingMarkup, /<line x1="1" y1="2" x2="9" y2="2" stroke="#[0-9a-f]+"/, "pending source alignment renders retained track geometry instead of a blank outline");
assert.match(pendingMarkup, />U1<\/text>/, "pending source alignment renders retained component art");
assert.doesNotMatch(pendingMarkup, /<image/, "pending source alignment does not render an unaligned source image");
globalThis.__assemblyTestSourceAlignments = { "pending-design": { board: pendingBoard, offset: null } };
const unavailableMarkup = renderPending({});
assert.match(unavailableMarkup, /<line x1="1" y1="2" x2="9" y2="2" stroke="#[0-9a-f]+"/, "failed source alignment keeps retained track geometry visible");
assert.doesNotMatch(unavailableMarkup, /<image/, "failed source alignment does not render source images");
globalThis.__assemblyTestSourceAlignments = { "pending-design": { board: pendingBoard, offset: [0, 0] } };
const focusedMarkup = renderPending({}, {linkedNets:{"pending-occurrence":["1"]},layerOpacity:{"F.Cu":.5}});
assert.match(focusedMarkup,/data-net-focus="active"/);
assert.match(focusedMarkup,/opacity="0.16" style="filter:grayscale\(1\) brightness\(\.68\)"/);
assert.match(focusedMarkup,/stroke="#55e5d5"/,"selected canonical net remains vivid above gray source geometry");
const clearedFocus = renderPending({}, {layerOpacity:{"F.Cu":.5}});
assert.doesNotMatch(clearedFocus,/grayscale\(1\)/,"clearing focus restores source colors");

const alignedMarkup = renderPending({});
assert.match(alignedMarkup, /<image[^>]+href="blob:pending-layer"/, "resolved source alignment renders the retained source image");
assert.doesNotMatch(alignedMarkup, /<line x1="1" y1="2" x2="9" y2="2" stroke="#[0-9a-f]+"/, "resolved source alignment replaces fallback tracks instead of drawing duplicate art");
assert.doesNotMatch(alignedMarkup, />U1<\/text>/, "resolved source alignment keeps component hit geometry without duplicate fallback labels");
globalThis.__assemblyTestSourceAlignments = { "pending-design": { board: pendingBoard, offset: [0, 0] } };
const replacementBoard = { ...pendingBoard, tracks: [...pendingBoard.tracks] };
const originalBoard = pendingBoard;
pendingBoard = replacementBoard;
const replacementMarkup = renderPending({});
assert.match(replacementMarkup, /<line x1="1" y1="2" x2="9" y2="2" stroke="#[0-9a-f]+"/, "an immutable active-board replacement falls back while its new identity awaits alignment");
assert.doesNotMatch(replacementMarkup, /<image/, "a stale alignment from the prior active-board identity is never shared with its replacement");
pendingBoard = originalBoard;
globalThis.__assemblyTestSourceAlignments = {};
const hiddenPendingMarkup = renderPending({ "F.Cu": false, "Edge.Cuts": false });
assert.doesNotMatch(hiddenPendingMarkup, /<line x1="1" y1="2" x2="9" y2="2" stroke="#[0-9a-f]+"/, "explicitly hidden retained layers remain hidden during pending alignment");
delete globalThis.__assemblyTestSourceAlignments;
console.log("Assembly 2D transforms, real-fixture gestures, picking, net mapping and Fit/Focus passed");
