import { performance } from "node:perf_hooks";
import { resultConductorIndexStats, resultDatumFitsConductor } from "../src/resultGeometryMask.ts";
import { buildScalarSvgBatches } from "../src/resultSvgBatches.ts";

const featureCount = Number(process.argv[2] ?? 20000);
const sampleCount = Number(process.argv[3] ?? 21000);
const width = Math.max(featureCount * 0.02 + 2, 100);
const board = {
  width, height: 100, bounds: { minX: 0, minY: 0, maxX: width, maxY: 100 }, outlineLoops: [],
  tracks: Array.from({ length: featureCount }, (_, index) => ({
    id: `T${index}`, start: [index * 0.02, index % 80 + 10], end: [index * 0.02 + 0.018, index % 80 + 10],
    width: 0.04, layer: index % 2 ? "B.Cu" : "F.Cu", net: `N${index % 500}`,
  })),
  zones: [], pads: [], vias: [], components: [], drawings: [], layers: ["F.Cu", "B.Cu"],
  layerDefinitions: [], stackup: [], nets: {},
};
const samples = Array.from({ length: sampleCount }, (_, index) => {
  const feature = board.tracks[index % featureCount];
  return { x_mm: feature.start[0] + 0.009, y_mm: feature.start[1], layer: feature.layer, net: feature.net, element_id: feature.id, value: index / Math.max(sampleCount - 1, 1) };
});

const started = performance.now();
const admitted = samples.reduce((total, sample) => total + Number(resultDatumFitsConductor(board, sample)), 0);
const coldMaskMs = performance.now() - started;
const warmStarted = performance.now();
samples.forEach(sample => resultDatumFitsConductor(board, sample));
const warmMaskMs = performance.now() - warmStarted;
const svgStarted = performance.now();
const svgBatches = buildScalarSvgBatches(samples, { minimum: 0, maximum: 1, cellSize: 0.04, smooth: false, project: point => point });
const svgBatchMs = performance.now() - svgStarted;

console.log(JSON.stringify({
  featureCount, sampleCount, admitted, coldMaskMs: Number(coldMaskMs.toFixed(2)),
  warmMaskMs: Number(warmMaskMs.toFixed(2)), svgBatchMs: Number(svgBatchMs.toFixed(2)),
  svgDomNodes: svgBatches.length, index: resultConductorIndexStats(board),
}, null, 2));
