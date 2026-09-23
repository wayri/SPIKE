import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const moduleSource = readFileSync(new URL("../src/componentPlaceholder.ts", import.meta.url), "utf8");
const code = ts.transpileModule(moduleSource, { compilerOptions: {
  module: ts.ModuleKind.ESNext,
  target: ts.ScriptTarget.ES2022,
} }).outputText;
const { deriveComponentPlaceholder } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);

const marble0201 = {
  ref: "C43", value: "CC0201_100NF_6.3V_10%_X5R", library: "CAPC0603X33N",
  at: [276.2885, -93.93682], width: 23.059525, height: 2.59925, rotation: -270,
  properties: [{ name: "Manufacturer1_ComponentHeight", values: ["0.33mm"] }],
};
const marble0201Pads = [
  { at: [276.2885, -94.28682], width: 0.4, height: 0.35, rotation: -270 },
  { at: [276.2885, -93.58682], width: 0.4, height: 0.35, rotation: -270 },
];
const tiny = deriveComponentPlaceholder(marble0201, marble0201Pads, "smd");
assert.equal(tiny.planarSource, "pads", "Marble copper pads must outrank its text-polluted ODB package bounds");
assert.ok(tiny.widthMm <= 1.2 && tiny.depthMm <= 1.2, `0201 proxy must remain sub-1.2 mm, got ${tiny.widthMm} x ${tiny.depthMm}`);
assert.equal(tiny.heightMm, 0.33, "explicit Marble component height must be preserved in millimeters");
assert.equal(tiny.heightSource, "metadata");

const connector = deriveComponentPlaceholder({
  ref: "J15", value: "FMC connector", library: "FMC_HPC", at: [20, 30], width: 100, height: 100, rotation: 0,
  bodyBounds: { minX: -22.5, minY: -6, maxX: 22.5, maxY: 6 },
}, [
  { at: [0, 27], width: 1, height: 2, rotation: 0 },
  { at: [40, 33], width: 1, height: 2, rotation: 0 },
], "tht");
assert.equal(connector.planarSource, "body");
assert.deepEqual(connector.centerOffsetMm, [0, 0]);
assert.deepEqual([connector.widthMm, connector.depthMm], [45, 12], "connector body must expand beyond its pad field");
assert.equal(connector.heightMm, 9, "connector default height must scale from its housing side");

const bottom = deriveComponentPlaceholder({
  ref: "U7", at: [100, 50], width: 90, height: 90, rotation: 90,
}, [
  { at: [100, 54], width: 1, height: 2, rotation: 90 },
  { at: [100, 46], width: 1, height: 2, rotation: 90 },
], "smd");
assert.equal(bottom.planarSource, "pads");
assert.ok(Math.abs(bottom.widthMm - 9) < 1e-9 && Math.abs(bottom.depthMm - 2) < 1e-9,
  `rotated bottom-side proxy must recover local orientation, got ${bottom.widthMm} x ${bottom.depthMm}`);

const body = deriveComponentPlaceholder({
  ref: "U1", at: [0, 0], width: 40, height: 40, rotation: 0,
  bodyBounds: { minX: -3, minY: -2, maxX: 3, maxY: 2 },
  courtyardBounds: { minX: -4, minY: -3, maxX: 4, maxY: 3 },
}, [], "smd");
assert.equal(body.planarSource, "body");
assert.deepEqual([body.widthMm, body.depthMm], [6, 4]);

const courtyard = deriveComponentPlaceholder({
  ref: "X1", at: [0, 0], rotation: 0,
  courtyardBounds: { minX: -2.5, minY: -1.5, maxX: 2.5, maxY: 1.5 },
}, [], "smd");
assert.equal(courtyard.planarSource, "courtyard");
assert.deepEqual([courtyard.widthMm, courtyard.depthMm], [4.5, 2.5], "courtyard clearance must not become solid body");

for (const filename of process.argv.slice(2)) {
  const snapshot = JSON.parse(readFileSync(filename, "utf8"));
  const design = snapshot.design ?? snapshot.canonical_design;
  const padsByRef = new Map();
  for (const pad of design.pads ?? []) {
    const ref = pad.component ?? pad.component_id;
    if (!ref) continue;
    const size = pad.size ?? pad.size_mm ?? [1, 1];
    const normalized = { at: pad.at ?? pad.center_mm, width: size[0], height: size[1], rotation: pad.rotation ?? pad.rotation_deg ?? 0,
      drill: pad.drill ?? pad.drill_size_mm?.[0] ?? 0 };
    const grouped = padsByRef.get(ref);
    if (grouped) grouped.push(normalized); else padsByRef.set(ref, [normalized]);
  }
  const results = (design.components ?? []).map(component => {
    const packageBounds = (component.odb_package_ref ?? component.odb_package)?.bounds_mm;
    const width = packageBounds ? packageBounds[2] - packageBounds[0] : 2;
    const height = packageBounds ? packageBounds[3] - packageBounds[1] : 2;
    const pads = padsByRef.get(component.reference) ?? [];
    const mount = pads.some(pad => Number(pad.drill) > 0) ? "tht" : "smd";
    return { ref: component.reference, side: component.side, packageSideMm: Math.max(width, height), result: deriveComponentPlaceholder({
      ...component, ref: component.reference, at: component.at ?? component.position_mm,
      rotation: component.rotation ?? component.rotation_deg ?? 0,
      library: component.footprint ?? component.library ?? "", width, height,
    }, pads, mount) };
  });
  assert.ok(results.length > 900, "Marble validation must cover the full component population");
  assert.ok(results.every(({ result }) => [result.widthMm, result.depthMm, result.heightMm].every(Number.isFinite)));
  const largestSides = results.map(({ result }) => Math.max(result.widthMm, result.depthMm)).sort((a, b) => a - b);
  const packageSides = results.map(entry => entry.packageSideMm).sort((a, b) => a - b);
  const sources = Object.fromEntries([...new Set(results.map(({ result }) => result.planarSource))]
    .map(sourceName => [sourceName, results.filter(({ result }) => result.planarSource === sourceName).length]));
  const measuredC43 = results.find(entry => entry.ref === "C43")?.result;
  const measuredBottom = results.find(entry => entry.side === "bottom");
  assert.ok(measuredC43 && measuredC43.widthMm < 2 && measuredC43.heightMm === 0.33,
    "real Marble C43 must reject the package text extent and retain explicit height");
  console.log(JSON.stringify({ file: filename, components: results.length, sources,
    metadataHeights: results.filter(({ result }) => result.heightSource === "metadata").length,
    priorPackageLargestSideMm: packageSides.at(-1), priorPackageP95SideMm: packageSides[Math.floor(packageSides.length * 0.95)],
    largestSideMm: largestSides.at(-1), p95SideMm: largestSides[Math.floor(largestSides.length * 0.95)],
    C43: measuredC43, bottomExample: measuredBottom }, null, 2));
}

console.log(JSON.stringify({ marble0201: tiny, connector, bottom, body, courtyard }, null, 2));
console.log("component placeholder sizing: all assertions passed");
