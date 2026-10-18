// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { readSolverBlockCatalog, filterSolverBlocks } = await importTestTypescript("solverBlockModel");
const snapshot = JSON.parse(readFileSync(new URL("../src/solverBlockCatalogSnapshot.json", import.meta.url), "utf8"));
const catalog = readSolverBlockCatalog(snapshot);
assert.equal(catalog.managed_downloads, false);
assert.equal(catalog.plan.action, "preview_only");
for (const id of ["pcb", "harness", "mcad", "cfd", "cht", "thermal"]) assert.ok(catalog.groups.some(group => group.id === id));
assert.ok(filterSolverBlocks(catalog, "CHT", "all").some(block => block.id === "cht-assembly"));
assert.ok(filterSolverBlocks(catalog, "", "thermal").every(block => block.groups.includes("thermal")));
assert.equal(filterSolverBlocks(catalog, "no-such-block-x999", "all").length, 0);
for (const mutate of [
  item => { item.contract = "wrong"; }, item => { item.managed_downloads = true; },
  item => { item.plan.action = "install"; }, item => { item.blocks.push(item.blocks[0]); },
  item => { item.blocks[0].requires = ["not-real"]; }, item => { item.plan.ordered_blocks.push("not-real"); },
]) { const copy = structuredClone(snapshot); mutate(copy); assert.throws(() => readSolverBlockCatalog(copy)); }

const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/SolverBlockPanel.tsx", import.meta.url))], bundle: true,
  write: false, format: "esm", platform: "node", external: ["react", "react/jsx-runtime"], loader: { ".css": "empty" },
  plugins: [{ name: "block-icons", setup(context) {
    context.onResolve({ filter: /\/icons$/ }, () => ({ path: "icons", namespace: "stub" }));
    context.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ contents: "export const Boxes=()=>null;export const GitBranch=()=>null;export const Package=()=>null;export const Search=()=>null;" }));
  } }],
});
const code = bundle.outputFiles[0].text.replaceAll('from "react"', `from ${JSON.stringify(new URL("../node_modules/react/index.js", import.meta.url).href)}`)
  .replaceAll('from "react/jsx-runtime"', `from ${JSON.stringify(new URL("../node_modules/react/jsx-runtime.js", import.meta.url).href)}`);
const { default: Panel } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
const html = renderToStaticMarkup(React.createElement(Panel));
assert.equal((html.match(/class="solver-block-card"/g) ?? []).length, catalog.blocks.length);
for (const text of ["All first-party blocks ship together", "Preview base only", "Required automatically", "Optional links", "Separate external runtime", "Planned / unavailable", "not install, remove or download", "worker dependency preview has not been confirmed"]) {
  assert.ok(html.includes(text), text);
}
assert.ok(html.includes('aria-label="Include block: Base contracts and worker" checked="" disabled=""') || /aria-label="Include block: Base contracts and worker"[^>]*disabled=""[^>]*checked=""/.test(html), "Base cannot be removed through the UI");
const filtered = renderToStaticMarkup(React.createElement(Panel, { initialQuery: "no-such-block-x999" }));
assert.ok(filtered.includes("No matching blocks"));
console.log(`Solver blocks: ${catalog.blocks.length} descriptors, identity admission, group/search filtering and truthful preview states passed.`);
