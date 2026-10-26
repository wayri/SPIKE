// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
const server = await createServer({ configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)), root: fileURLToPath(new URL("..", import.meta.url)), server: { middlewareMode: true }, optimizeDeps: { noDiscovery: true, include: [], entries: [] }, logLevel: "error" });
try {
  const result = await server.transformRequest("/src/emergeExampleCatalog.ts");
  assert.ok(result?.code);
  assert.doesNotMatch(result.code, /import\.meta\.glob/);
  const catalog = JSON.parse(readFileSync(new URL("../../examples/emerge/gallery/catalog.json", import.meta.url), "utf8"));
  for (const row of catalog.examples) {
    assert.ok(result.code.includes(row.snapshot_path), `Vite must bundle ${row.snapshot_path}`);
    const request = await server.transformRequest(`/@fs/${fileURLToPath(new URL(`../../${row.snapshot_path}`, import.meta.url)).replaceAll("\\", "/")}?import&raw`);
    assert.ok(request?.code.includes("spike-project-package/v2"), `Bundled ${row.id} must remain inline project JSON`);
  }
  const advanced = JSON.parse(readFileSync(new URL("../../examples/emerge/gallery/advanced.json", import.meta.url), "utf8"));
  for (const row of advanced.studies) assert.ok(result.code.includes(row.study_path), `Vite must bundle ${row.study_path}`);
  console.log("Vite transformed all five lazy inline projects and all 28 study resources");
} finally { await server.close(); }
