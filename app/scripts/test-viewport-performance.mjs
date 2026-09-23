import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { copperNetLabels, sceneRowWindow, boundedMatches, firstObjectByNet, evenlyBoundedDisplayItems, KeyedResourcePool, partitionComponentProxies, takeWithinCostBudget, throughHoleComponentRefs, uniqueViewportNets } from "../src/viewportPerformance.ts";
import { buildBoundsSpatialIndex, nearestPointSample, pointBoundsCandidates, rayBoundsCandidates } from "../src/viewportSpatialIndex.ts";

const pads = Array.from({ length: 100_000 }, (_, index) => ({
  ref: `U${Math.floor(index / 4)}`,
  drill: index % 17 === 0 ? 0.3 : 0,
}));
const componentIds = new Set(Array.from({ length: 10_000 }, (_, i) => `U${i}`));
const proxies = Array.from({ length: 100_000 }, (_, i) => ({ userData: {
  id: `U${i % 10_000}`, type: i < 10_000 ? "component" : "track",
} }));
const partition = partitionComponentProxies(proxies, componentIds);
assert.equal(partition.inspected, 100_000, "replacement must inspect each proxy once, not once per component");
assert.equal(partition.replaced.length, 10_000);
assert.deepEqual(partition.retained, proxies.slice(10_000), "noncomponent proxies sharing IDs must survive");
assert.equal(partitionComponentProxies(proxies, new Set()).retained.length, proxies.length);
const throughHole = throughHoleComponentRefs(pads);
assert.ok(throughHole.has("U0"));
assert.ok(!throughHole.has("U1"));
assert.ok(throughHole.size < pads.length, "the mount index must aggregate pads by component reference");

const nets = uniqueViewportNets([
  ...Array.from({ length: 100_000 }, (_, index) => `N${index % 250}`),
  undefined, null, "", "GND",
]);
assert.equal(nets.length, 251);
assert.equal(nets[0], "N0");
assert.equal(nets.at(-1), "GND");

const samples = Array.from({ length: 120_000 }, (_, index) => ({
  id: index,
  x_mm: index % 600,
  y_mm: Math.floor(index / 600),
}));
const nearest = nearestPointSample(samples, 311.1, 84.05);
assert.equal(nearest.sample?.id, 84 * 600 + 311);
assert.ok(nearest.inspected < 500,
  `indexed contour hover inspected ${nearest.inspected} of ${samples.length} samples`);
assert.ok(nearest.bucketCount > 1_000);

const separated = [{ x_mm: -1e6, y_mm: -1e6, id: 'left' }, { x_mm: 1e6, y_mm: 1e6, id: 'right' }];
const gap = nearestPointSample(separated, 1, 1);
assert.equal(gap.sample.id, 'right');
assert.ok(gap.rings <= 4, 'empty space between boards must not create unbounded grid searches');
const collinear = Array.from({ length: 10_000 }, (_, i) => ({ x_mm: i * 1000, y_mm: 0, id: i }));
assert.equal(nearestPointSample(collinear, 5010500.1, 0).sample.id, 5011);
for (let i = 0; i < 40; i++) {
  const x = (i * 173.7) % 9000 * 1000;
  const actual = nearestPointSample(collinear, x, 0).sample;
  const expected = collinear.reduce((a, b) => Math.abs(a.x_mm - x) <= Math.abs(b.x_mm - x) ? a : b);
  assert.equal(actual.id, expected.id);
}
const netObjects = Array.from({ length: 100_000 }, (_, i) => ({ net: `N${i % 20_000}`, id: i }));
const netIndex = firstObjectByNet(netObjects);
assert.equal(netIndex.size, 20_000);
assert.equal(netIndex.get('N19999').id, 19999);
let matchInspections = 0;
assert.equal(boundedMatches(netObjects, () => { matchInspections++; return true; }, 120).length, 120);
assert.equal(matchInspections, 120);
for (const scrollTop of [0, 10_000, 20_000 * 38, 1e12]) {
  const window = sceneRowWindow(20_000, scrollTop);
  assert.ok(window.end - window.start <= 17, 'large hierarchies mount only a bounded visible window');
  assert.equal(window.before + (window.end - window.start) * 38 + window.after, 20_000 * 38);
}
assert.equal(sceneRowWindow(20_000, 1e12).end, 20_000, 'last row remains reachable');
assert.deepEqual(sceneRowWindow(0, 100), { start: 0, end: 0, before: 0, after: 0 });

const bounds = Array.from({ length: 100_000 }, (_, index) => {
  const x = index % 500;
  const y = Math.floor(index / 500);
  return { value: index, minX: x - 0.2, maxX: x + 0.2, minY: y - 0.2, maxY: y + 0.2, minZ: 0, maxZ: 1 };
});
// A very large pick target exceeds the per-object grid budget and must remain
// exact through the always-tested global bucket.
bounds.push({ value: 100_000, minX: -1_000, maxX: 1_000, minY: -1_000, maxY: 1_000, minZ: -1, maxZ: 2 });
const pickIndex = buildBoundsSpatialIndex(bounds);
const pickQuery = rayBoundsCandidates(pickIndex, [250.1, 100.1, 10], [0, 0, -1]);
assert.ok(pickQuery.values.includes(100 * 500 + 250), "local exact pick candidate was retained");
assert.ok(pickQuery.values.includes(100_000), "oversized global exact pick candidate was retained");
assert.ok(pickQuery.values.length < bounds.length * 0.02,
  `raycast broad phase retained ${pickQuery.values.length} of ${bounds.length} candidates`);
const pointQuery = pointBoundsCandidates(pickIndex, 250.1, 100.1, 0.5);
assert.ok(pointQuery.values.includes(100 * 500 + 250));
assert.ok(pointQuery.values.includes(100_000));
assert.ok(pointQuery.inspected < bounds.length * 0.02,
  `2D point broad phase inspected ${pointQuery.inspected} of ${bounds.length} candidates`);

let allocations = 0;
const materialPool = new KeyedResourcePool();
for (let index = 0; index < 100_000; index += 1) {
  const key = `layer-${index % 32}|kind-${index % 4}`;
  materialPool.acquire(key, () => ({ allocation: allocations++ }));
}
assert.equal(materialPool.requests, 100_000);
assert.equal(materialPool.size, 32,
  "identical procedural material specifications must share one pre-batch allocation");
assert.equal(allocations, materialPool.size);

const budgeted = takeWithinCostBudget(
  [{ id: "a", triangles: 40 }, { id: "b", triangles: 70 }, { id: "c", triangles: 50 }],
  100,
  item => item.triangles,
);
assert.deepEqual(budgeted.items.map(item => item.id), ["a", "c"]);
assert.equal(budgeted.cost, 90);
assert.equal(budgeted.omitted, 1);

const displayLod = evenlyBoundedDisplayItems(Array.from({ length: 232_496 }, (_, index) => index), 20_000);
assert.equal(displayLod.length, 20_000);
assert.equal(displayLod[0], 0);
assert.equal(displayLod.at(-1), 232_495);
assert.ok(displayLod.every((value, index) => index === 0 || value > displayLod[index - 1]));

const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
const viewportSource = await readFile(new URL("../src/BoardViewport.tsx", import.meta.url), "utf8");
assert.match(appSource, /const viewportAnalysisNets = useMemo\(/,
  "analysis-net identity must survive telemetry-only App renders");
assert.match(appSource, /analysisNets=\{viewportAnalysisNets\}/,
  "BoardViewport must receive the memoized analysis-net array");
assert.doesNotMatch(viewportSource, /activeBoard\.pads\.some\(/,
  "component mount classification must not rescan every pad for every component");
assert.doesNotMatch(appSource, /boardData\.pads\.some\(/, 'layer-manager counts must not scan all pads per part');
assert.doesNotMatch(viewportSource, /analysisNets\.includes\(/,
  "large-board traversals must use the indexed analysis-net membership set");
assert.doesNotMatch(viewportSource, /loadedComponents\.getObjectByName\(/,
  "component-model matching must not traverse the complete scene once per part");
assert.match(viewportSource, /componentObjectsByName/,
  "component-model matching must build one indexed name lookup");
assert.match(viewportSource, /dataset\.contourHoverQuery/,
  "contour hover must publish inspected-sample telemetry");
assert.match(viewportSource, /dataset\.raycastBroadphase/,
  "large-board click selection must publish broad-phase candidate telemetry");
assert.match(viewportSource, /dataset\.proceduralMaterialPool/,
  "large-board construction must publish material allocation telemetry");
assert.match(viewportSource, /dataset\.proceduralLod/,
  "large-board construction must publish viewport-only LOD telemetry");

console.log(`viewport performance contracts: all assertions passed; contour=${nearest.inspected}/${samples.length}; raycast=${pickQuery.values.length}/${bounds.length}; materials=${materialPool.size}/${materialPool.requests}`);

const labelView = { minX: 0, minY: 0, maxX: 100, maxY: 60, unitsPerPixel: .1 };
const labelTrack = { id: "t", net: "+1V0", layer: "top", start: [2, 4], end: [50, 4], width: 2 };
const labels = copperNetLabels([labelTrack], [], labelView);
assert.equal(labels.length, 1);
assert.equal(labels[0].kind, "trace");
assert.equal(labels[0].angle, 0);
assert.equal(copperNetLabels([{ ...labelTrack, width: .1 }], [], labelView).length, 0, "unreadable fine traces wait for zoom");
assert.equal(copperNetLabels([{ ...labelTrack, width: .1 }], [], {...labelView, unitsPerPixel: .01}).length, 1);
assert.equal(copperNetLabels([{ ...labelTrack, start: [50,4], end: [2,4] }], [], labelView)[0].angle, 0, "reverse routing keeps text upright");
assert.equal(copperNetLabels([labelTrack, {...labelTrack, id:'overlap'}], [], labelView).length, 1, "overlapping labels are suppressed");
const clipped = copperNetLabels([{ ...labelTrack, start: [-200,4], end: [200,4] }], [], labelView);
assert.equal(clipped[0].x, 50, "long traces label the visible section");
const ring = [[5,10],[95,10],[95,50],[5,50]];
const hole = [[20,15],[80,15],[80,45],[20,45]];
const zoneLabels = copperNetLabels([], [{id:'z',net:'GND',layer:'top',points:ring,holes:[hole]}], labelView);
assert.equal(zoneLabels.length, 1);
assert.ok(zoneLabels.every(p => !(p.x > 20 && p.x < 80 && p.y > 15 && p.y < 45)), "zone text must avoid holes");
assert.equal(copperNetLabels([labelTrack], [], labelView, 0).length, 0);
assert.equal(copperNetLabels([{...labelTrack, net:'X'.repeat(10000)}], [], labelView).length, 0, "oversized names cannot explode collision allocation");
console.log("Copper net labels: zoom, rotation, holes, viewport clipping and collision budget passed");
