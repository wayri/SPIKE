// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
const server = await createServer({ configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)), root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true }, optimizeDeps: { noDiscovery: true, include: [], entries: [] }, logLevel: "error" });
try {
  const manifest = JSON.parse(readFileSync(new URL("../../examples/catalog/work-examples.json", import.meta.url), "utf8"));
  const transformed = await server.transformRequest("/src/workExampleAssets.ts");
  assert.ok(transformed?.code && !transformed.code.includes("import.meta.glob"));
  const assets = [...new Set(manifest.examples.flatMap(row => row.assets))];
  for (const path of assets) {
    const absolute = fileURLToPath(new URL(`../../${path}`, import.meta.url)).replaceAll("\\", "/");
    assert.ok(server.config.server.fs.allow.some(allowed => absolute.startsWith(`${allowed.replaceAll("\\", "/")}/`)), `${path} requires a bounded development resource admission`);
    const resource = await server.transformRequest(`/@fs/${absolute}?import&raw`);
    assert.ok(resource?.code.includes("export default"), `Vite must transform ${path} into an offline frontend asset`);
  }
  for (const path of manifest.examples.filter(row => row.preview).map(row => row.preview.asset)) {
    const absolute = fileURLToPath(new URL(`../../${path}`, import.meta.url)).replaceAll("\\", "/");
    const resource = await server.transformRequest(`/@fs/${absolute}?import&url`);
    assert.ok(resource?.code.includes("export default"), `${path}: bundled preview picture URL`);
  }
  console.log(`Vite admitted and transformed all ${assets.length} exact work-example assets.`);
} finally { await server.close(); }
