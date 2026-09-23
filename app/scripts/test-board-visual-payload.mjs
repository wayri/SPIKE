import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import ts from "typescript";

globalThis.crypto ??= webcrypto;

const source = readFileSync(new URL("../src/boardVisualBundles.ts", import.meta.url), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const module = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);

const artifact = (name, media, contents) => ({
  file_name: name,
  media_type: media,
  bytes: Buffer.byteLength(contents),
  sha256: createHash("sha256").update(contents).digest("hex"),
  artifact_base64: Buffer.from(contents).toString("base64"),
});
const boardArtifact = artifact("board.glb", "model/gltf-binary", "board-glb");
const componentArtifact = artifact("components.glb", "model/gltf-binary", "component-glb");
const layerArtifact = artifact("board-F_Cu.svg", "image/svg+xml", "<svg/>");
const artifactBytes = boardArtifact.bytes + componentArtifact.bytes + layerArtifact.bytes;
const payload = {
  contract: "spike/visual-bundle-payload/v1",
  status: "ready_with_warnings",
  scenes: { board: boardArtifact, components: componentArtifact },
  layout: { layers: { "F.Cu": layerArtifact }, view_box: [0, 0, 40, 20] },
  quality: { missing_model_count: 1, missing_references: ["U9"] },
  artifact_bytes: artifactBytes,
  artifact_limit_bytes: 4096,
  security: { self_contained_glb_required: true, external_resource_uris_allowed: false },
};
const created = [];
const revoked = [];
const result = await module.materializeVisualBundle(
  { tracks: [], components: [] },
  payload,
  blob => { const url = `blob:test-${created.length}`; created.push({ url, blob }); return url; },
  url => revoked.push(url),
);
assert.equal(result.board.boardModelUrl, "blob:test-0");
assert.equal(result.board.componentModelUrl, "blob:test-1");
assert.equal(result.board.layoutLayerUrls["F.Cu"], "blob:test-2");
assert.equal(result.board.modelManifestUrl, "blob:test-3");
assert.deepEqual(result.board.layoutViewBox, [0, 0, 40, 20]);
assert.deepEqual(result.missingReferences, ["U9"]);
result.dispose();
result.dispose();
assert.deepEqual(revoked, created.map(item => item.url), "all object URLs must be revoked exactly once");

const manyLayers = Object.fromEntries(Array.from({ length: 100 }, (_, i) => [`User.${i + 1}`, layerArtifact]));
const largeLayerBundle = await module.materializeVisualBundle({}, {
  ...payload,
  layout: { ...payload.layout, layers: manyLayers },
  artifact_bytes: boardArtifact.bytes + componentArtifact.bytes + layerArtifact.bytes * 100,
}, () => 'blob:layer', () => {});
assert.equal(Object.keys(largeLayerBundle.board.layoutLayerUrls).length, 100,
  'high-layer boards must not fail the former 80-artifact cap');
largeLayerBundle.dispose();

await assert.rejects(
  module.materializeVisualBundle({}, { ...payload, artifact_bytes: artifactBytes + 1 }),
  /accounting/,
);
const partialCreated = [];
const partialRevoked = [];
await assert.rejects(
  module.materializeVisualBundle({}, {
    ...payload,
    scenes: { ...payload.scenes, components: { ...payload.scenes.components, sha256: "0".repeat(64) } },
  }, blob => { const url = `blob:partial-${partialCreated.length}`; partialCreated.push({ url, blob }); return url; }, url => partialRevoked.push(url)),
  /SHA-256/,
);
assert.deepEqual(partialRevoked, partialCreated.map(item => item.url),
  "a later digest failure must revoke URLs already created for earlier artifacts");
await assert.rejects(
  module.materializeVisualBundle({}, { ...payload, security: { self_contained_glb_required: false, external_resource_uris_allowed: true } }),
  /security boundary/,
);
for (const hostileSvg of [
  '<svg><image href="https://example.invalid/pixel"/></svg>',
  '<svg><style>.c{fill:url(https://example.invalid/style.css)}</style></svg>',
  '<!DOCTYPE svg [<!ENTITY xxe SYSTEM "https://example.invalid/entity">]><svg>&xxe;</svg>',
  '<!DOCTYPE svg SYSTEM "https://example.invalid/svg.dtd"><svg/>',
  '<svg><image href="data:image/svg+xml;base64,PHN2Zy8+"/></svg>',
  '<svg><style>.c{fill:u\\72l(https://example.invalid/style.css)}</style></svg>',
]) {
  const hostileLayer = artifact("board-F_Cu.svg", "image/svg+xml", hostileSvg);
  await assert.rejects(
    module.materializeVisualBundle({}, {
      ...payload,
      scenes: {},
      layout: { ...payload.layout, layers: { "F.Cu": hostileLayer } },
      artifact_bytes: hostileLayer.bytes,
    }),
    /unsupported active or external SVG content/,
    "verified native-stage SVG bytes must not create an active or external-resource blob URL",
  );
}
const kicadSvg = '<?xml version="1.0" standalone="no"?>\r\n <!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" \r\n "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd"> \r\n<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>';
const kicadLayer = artifact("arts-1_irca-F_Cu.svg", "image/svg+xml", kicadSvg);
const kicadCreated = [];
const kicadResult = await module.materializeVisualBundle({}, {
  ...payload,
  scenes: {},
  layout: { ...payload.layout, layers: { "F.Cu": kicadLayer } },
  artifact_bytes: kicadLayer.bytes,
  artifact_limit_bytes: kicadLayer.bytes,
}, blob => { kicadCreated.push(blob); return "blob:kicad"; }, () => {});
assert.equal(kicadCreated.length, 1, "known KiCad SVG 1.1 PUBLIC output remains renderable");
assert.doesNotMatch(await kicadCreated[0].text(), /<!DOCTYPE\b/i,
  "only the render buffer is normalized; the verified package artifact is unchanged");
kicadResult.dispose();

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const importSource = readFileSync(new URL("../src/boardImport.ts", import.meta.url), "utf8");
assert.match(appSource, /await parseDesignSourceOffThread\(fileName, source\)/,
  "raw board import must parse off the UI thread");
assert.match(appSource, /openNativeTextFile\("board"\)/,
  "desktop board import must retain its approved native path for project-relative 3D models");
const workflowSource = readFileSync(new URL("../src/useBoardVisualImport.ts", import.meta.url), "utf8");
assert.match(workflowSource, /board_path: input.path/,
  "native visual export must use the approved source path instead of a basename-only temporary board");
assert.match(appSource, /(?:const|let) parsed = source \? await parseDesignSourceOffThread\(sourceFile, source/,
  "project-package reopen must not parse a large embedded board on the UI thread");
assert.match(importSource, /new Worker\(new URL\("\.\/boardImportWorker\.ts"/,
  "large-board parsing must use a Vite module worker");
assert.match(workflowSource, /continue; \/\/ Finished stages remain usable/,
  "visual export failure must retain finished layers and continue subsequent stages");

console.log("arbitrary-board visual payload and nonblocking import assertions passed");

// Optional real stage responses exercise the same digest, SVG and size checks as import.
for (const filename of process.argv.slice(2)) {
  const response = JSON.parse(readFileSync(filename, "utf8"));
  assert.equal(response.ok, true);
  const result = await module.materializeVisualBundle({ tracks: [], components: [] }, response.result);
  for (const [layer, artifact] of Object.entries(response.result.layout?.layers ?? {})) {
    const svg = Buffer.from(artifact.artifact_base64, "base64").toString("utf8");
    const match = svg.match(/viewBox="([^"]+)"/);
    assert.ok(match, `${layer} must have a coordinate frame`);
    assert.deepEqual(match[1].trim().split(/[ ,]+/).map(Number), response.result.layout.view_box, `${layer} must align to shared board coordinates`);
  }
  assert.ok(Object.values(result.board.layoutLayerUrls ?? {}).every(Boolean));
  result.dispose();
  console.log(JSON.stringify({file: filename, layers: Object.keys(response.result.layout?.layers ?? {}).length, verifiedBytes: response.result.artifact_bytes}));
}
