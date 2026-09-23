import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const root = new URL("../", import.meta.url);
const mcadSource = readFileSync(new URL("src/mcadAssembly.ts", root), "utf8");
const harnessSource = readFileSync(new URL("src/harnessVisualization.ts", root), "utf8");
const viewportSource = readFileSync(new URL("src/BoardViewport.tsx", root), "utf8");
const appSource = readFileSync(new URL("src/App.tsx", root), "utf8");
const compile = source => ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const mcadUrl = `data:text/javascript;base64,${Buffer.from(compile(mcadSource)).toString("base64")}`;
const harness = await import(`data:text/javascript;base64,${Buffer.from(compile(harnessSource)
  .replace('from "./mcadAssembly"', `from "${mcadUrl}"`)).toString("base64")}`);

const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const translatedBoard = [1, 0, 0, 100, 0, 1, 0, 50, 0, 0, 1, 8, 0, 0, 0, 1];
const board = (id, transform) => ({ id, design_id: `${id}-design`, frame: { frame_id: `${id}-frame`, parent_frame_id: "assembly", units: "mm", handedness: "right", transform } });
const assembly = {
  contract: "spike/assembly-ir/v1", assembly_id: "fixture", name: "Harness fixture", parts: [],
  boards: [board("power", identity), board("control", translatedBoard)],
  connector_mappings: [
    { id: "J_PWR", data: { board_id: "power", connector_id: "J_PWR", position_mm: [10, 20, 1] } },
    { id: "J_CTL", data: { board_id: "control", connector_id: "J_CTL", position_mm: [2, 3, 4] } },
  ],
  harnesses: [
    { id: "harness-main", name: "Main loom", endpoint_a: "power::J_PWR", endpoint_b: "control::J_CTL", length_mm: 180 },
    { id: "harness-missing", endpoint_a: "power::J_PWR", endpoint_b: "control::J_MISSING", length_mm: 100 },
    { id: "harness-main", endpoint_a: "power::J_PWR", endpoint_b: "control::J_CTL", length_mm: 180 },
  ],
};

const projection = harness.buildVirtualHarnessVisualization(assembly);
const routedAssembly = structuredClone(assembly);
const savedRoute = [[10, 20, 1], [10, 53, 1], [102, 53, 1], [102, 53, 12]];
routedAssembly.harnesses = [{ ...assembly.harnesses[0], extensions: { "spike.harness-routing": { route_mm: savedRoute } } }];
const routedProjection = harness.buildVirtualHarnessVisualization(routedAssembly);
assert.deepEqual(routedProjection.visuals[0].routeMm, savedRoute, "authored keepout routes remain exact polylines");
assert.equal(routedProjection.visuals[0].routedPolyline, true);
routedAssembly.boards[1].frame.transform[3] += 10;
const movedProjection = harness.buildVirtualHarnessVisualization(routedAssembly);
assert.ok(movedProjection.diagnostics.some(d => d.code === "stale_route"), "moving a board invalidates the authored route");
assert.equal(movedProjection.visuals[0].routedPolyline, false);
assert.equal(projection.visuals.length, 1, "only uniquely resolved stable IDs are drawable");
assert.equal(projection.visuals[0].id, "harness-main");
assert.deepEqual(projection.visuals[0].endpointA.positionMm, [10, 20, 1]);
assert.deepEqual(projection.visuals[0].endpointB.positionMm, [102, 53, 12], "endpoint B composes its board-instance transform");
assert.equal(projection.unresolvedHarnesses, 2);
assert.ok(projection.diagnostics.some(item => item.code === "unresolved_connector"));
assert.ok(projection.diagnostics.some(item => item.code === "duplicate_harness_id"));
assert.equal(projection.visuals[0].routeMm.length, 4, "virtual route uses a bounded control-point count");

const capped = harness.buildVirtualHarnessVisualization({
  ...assembly,
  harnesses: [
    assembly.harnesses[0],
    { id: "harness-secondary", endpoint_a: "power::J_PWR", endpoint_b: "control::J_CTL", length_mm: 190 },
  ],
}, 1);
assert.equal(capped.visuals.length, 1);
assert.equal(capped.truncatedHarnesses, 1);
assert.ok(capped.diagnostics.some(item => item.code === "visualization_limit"));
assert.equal(harness.MAX_VIRTUAL_HARNESS_VISUALS, 512);

const boardProjection = harness.buildVirtualBoardVisualization(assembly, {
  contract: "spike/assembly-designs/v1", active_design_id: "power-design",
  designs: [
    { contract: "spike/design-ir/v2", design_id: "power-design", metadata: { board_bounds_mm: [0, 0, 1000, 1000] } },
    { contract: "spike/design-ir/v2", design_id: "control-design", metadata: { board_size_mm: [120, 80] } },
  ],
});
assert.equal(boardProjection.visuals.length, 2);
assert.equal(boardProjection.visuals[0].active, true);
assert.equal(boardProjection.visuals[0].widthMm, 1000);
assert.equal(boardProjection.visuals[1].heightMm, 80);
assert.deepEqual(boardProjection.unresolvedBoardIds, []);

const marblePlacement = (xMm, yMm, zMm, rxDeg, ryDeg, rzDeg) => {
  const rx = rxDeg * Math.PI / 180, ry = ryDeg * Math.PI / 180, rz = rzDeg * Math.PI / 180;
  const sx = Math.sin(rx), cx = Math.cos(rx), sy = Math.sin(ry), cy = Math.cos(ry), sz = Math.sin(rz), cz = Math.cos(rz);
  return [
    cy * cz, sx * sy * cz - cx * sz, cx * sy * cz + sx * sz, xMm,
    cy * sz, sx * sy * sz + cx * cz, cx * sy * sz - sx * cz, yMm,
    -sy, sx * cy, cx * cy, zMm,
    0, 0, 0, 1,
  ];
};
const marbleBoards = [
  ["marble-power", "marble-power-design", marblePlacement(0, 0, 0, 0, 0, 0)],
  ["marble-control", "marble-control-design", marblePlacement(14, -9, 6, 10, 0, 90)],
  ["marble-sensor", "marble-sensor-design", marblePlacement(-12, 7.5, 18, 0, -20, 35)],
  ["marble-interface", "marble-interface-design", marblePlacement(5, 16, 29, 15, 25, -40)],
];
const marbleAssembly = {
  contract: "spike/assembly-ir/v1", assembly_id: "marble-four", name: "Four Marble boards", parts: [],
  boards: marbleBoards.map(([id, design_id, transform]) => board(id, transform)),
  connector_mappings: marbleBoards.map(([id], index) => ({ id: `${id}-J`, data: { board_id: id, connector_id: "J", position_mm: [index + 1, 0, 0] } })),
  harnesses: [
    { id: "power-control", endpoint_a: "marble-power::J", endpoint_b: "marble-control::J", length_mm: 45 },
    { id: "control-sensor", endpoint_a: "marble-control::J", endpoint_b: "marble-sensor::J", length_mm: 52 },
    { id: "sensor-interface", endpoint_a: "marble-sensor::J", endpoint_b: "marble-interface::J", length_mm: 61 },
  ],
};
const marbleProjection = harness.buildVirtualHarnessVisualization(marbleAssembly);
const marbleBoardProjection = harness.buildVirtualBoardVisualization(marbleAssembly, {
  contract: "spike/assembly-designs/v1", active_design_id: "marble-power-design",
  designs: marbleBoards.map(([id, design_id]) => ({ contract: "spike/design-ir/v2", design_id, metadata: { board_size_mm: [72, 48] } })),
});
assert.equal(marbleBoardProjection.visuals.length, 4, "four retained Marble board identities must project independently");
assert.deepEqual(marbleBoardProjection.visuals.map(item => item.designId), marbleBoards.map(([, designId]) => designId));
for (const [actual, [, , expected]] of marbleBoardProjection.visuals.map((item, index) => [item.transform, marbleBoards[index]])) {
  assert.ok(actual.every((value, index) => Math.abs(value - expected[index]) < 1e-12), "XYZ placement rotations must reach board proxies unchanged");
}
assert.equal(marbleProjection.visuals.length, 3);
assert.deepEqual(marbleProjection.visuals.map(item => item.endpointA.boardId), ["marble-power", "marble-control", "marble-sensor"]);
assert.deepEqual(marbleProjection.visuals.map(item => item.endpointB.boardId), ["marble-control", "marble-sensor", "marble-interface"]);
const expectedMarbleEndpoints = [[14, -7, 6], [-9.690746606039829, 9.116956634087269, 19.026060429977007], [7.777088176059535, 13.669746335721658, 27.309526953037203]];
for (const [actual, expected] of marbleProjection.visuals.map((item, index) => [item.endpointB.positionMm, expectedMarbleEndpoints[index]])) {
  assert.ok(actual.every((value, index) => Math.abs(value - expected[index]) < 1e-12), "harness endpoints must compose each board's XYZ rotation and translation");
}

assert.ok(harnessSource.includes("new Map"), "endpoint resolution must be indexed");
assert.ok(!harnessSource.includes("components") && !harnessSource.includes("nets"), "harness projection must not scan dense board features");
assert.ok(viewportSource.includes("harnessPickablesRef"), "harness picking must remain separate from dense board pickables");
assert.ok(viewportSource.includes("virtualHarnessScene"), "viewport must expose bounded harness render diagnostics");
assert.ok(viewportSource.includes("virtualBoardPickablesRef"), "board-instance proxies need a bounded dedicated picking set");
assert.ok(appSource.includes("buildVirtualHarnessVisualization"), "App must project canonical AssemblyIR harnesses");
assert.ok(appSource.includes("buildVirtualBoardVisualization"), "App must project retained board instances without scanning dense features");
assert.ok(appSource.includes("onHarnessSelect={handleHarnessSelect}"), "App must receive stable harness selections");

console.log("Virtual harness projection, diagnostics, bounded rendering, and viewport wiring passed.");
