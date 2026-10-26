// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
const root = new URL("../../", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("examples/catalog/work-examples.json", root), "utf8"));
const source = name => readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
const assetsSource = source("workExampleAssets.ts");
const allowed = [...assetsSource.split('], { query: "?raw"')[0].matchAll(/"\.\.\/\.\.\/(examples\/[^"*]+)"/g)].map(match => match[1]);
const pictures = [...assetsSource.matchAll(/"\.\.\/\.\.\/(examples\/[^"*]+\.png)"/g)].map(match => match[1]);
const declared = [...new Set(manifest.examples.flatMap(row => row.assets))];
assert.deepEqual([...allowed].sort(), [...declared].sort(), "bundle only the exact manifest resources");
assert.equal(new Set(allowed).size, allowed.length);
const texts = Object.fromEntries(allowed.map(path => {
  assert.match(path, /^examples\/[A-Za-z0-9_./-]+$/);
  assert.ok(!path.includes(".."));
  const file = new URL(path, root);
  const bytes = statSync(file).size;
  const projectRow = manifest.examples.find(row => row.primaryAction === "project" && row.projectAsset === path);
  const limit = projectRow ? (projectRow.id === "promo-ebrake" ? 8 : 4) * 1024 * 1024 : 512 * 1024;
  assert.ok(bytes > 0 && bytes <= limit, `${path}: bounded nonempty text`);
  const text = readFileSync(file, "utf8");
  if (path.endsWith(".json")) JSON.parse(text);
  return [path, text];
}));
assert.ok(Object.entries(texts).filter(([path]) => !path.startsWith("examples/promo_release/")).reduce((size, [, text]) => size + Buffer.byteLength(text), 0) < 1024 * 1024, "existing curated source payload stays below 1 MiB");
assert.ok(Object.values(texts).reduce((size, text) => size + Buffer.byteLength(text), 0) + pictures.reduce((size, path) => size + statSync(new URL(path, root)).size, 0) < 20 * 1024 * 1024, "complete curated payload stays below 20 MiB");
assert.deepEqual(pictures.sort(), manifest.examples.filter(row => row.preview).map(row => row.preview.asset).sort(), "exact picture allowlist");
const receipt = JSON.parse(texts["examples/promo_release/provenance.json"]);
assert.equal(receipt.projects.length, 7);
assert.equal(receipt.solver_runs_performed, false);
assert.equal(receipt.installed_desktop_capture, false);
for (const project of receipt.projects) {
  assert.equal(createHash("sha256").update(texts[project.snapshot]).digest("hex"), project.snapshot_sha256);
  assert.equal(Buffer.byteLength(texts[project.snapshot]), project.snapshot_bytes);
  assert.match(project.source, /READY_TO_OPEN\/.+\.spike$/);
  assert.match(project.manifest_payload_sha256, /^[a-f0-9]{64}$/);
}
for (const picture of pictures) {
  const copy = receipt.copies.find(entry => entry.target === picture);
  assert.ok(copy && !copy.modified);
  assert.equal(createHash("sha256").update(readFileSync(new URL(picture, root))).digest("hex"), copy.sha256);
}
for (const copy of receipt.copies.filter(entry => entry.target in texts)) {
  assert.equal(createHash("sha256").update(texts[copy.target]).digest("hex"), copy.sha256, `${copy.target}: exact provenance copy`);
}
assert.ok(manifest.examples.length >= 20);
assert.ok(new Set(manifest.examples.map(row => row.category)).size >= 6);
assert.equal(new Set(manifest.examples.map(row => row.id)).size, manifest.examples.length);
for (const row of manifest.examples) {
  assert.ok(["runnable", "setup-only", "saved-evidence", "guide"].includes(row.status));
  assert.ok(["download", "emerge-library", "ibis", "spatial", "project"].includes(row.primaryAction));
  assert.equal(row.steps.length, 3, row.id);
  for (const field of ["title", "summary", "engine", "dependencies", "limits", "license"]) assert.ok(row[field]?.length > 5, `${row.id}: ${field}`);
  assert.ok(row.assets.length > 0);
  if (row.status === "runnable") assert.ok(row.command?.includes("python"), `${row.id}: runnable has explicit source command`);
  if (row.primaryAction === "project") {
    assert.equal(row.status, "saved-evidence");
    assert.ok(row.assets.includes(row.projectAsset));
  }
  if (row.preview) assert.match(row.preview.caption, /browser preview.*not installed desktop/i);
}

function load(name, mocks = {}) {
  const compiled = ts.transpileModule(source(name), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  } }).outputText;
  const module = { exports: {} };
  new Function("require", "module", "exports", compiled)(dependency => {
    if (Object.hasOwn(mocks, dependency)) return mocks[dependency];
    if (dependency.endsWith(".css")) return {};
    return require(dependency);
  }, module, module.exports);
  return module.exports;
}
const catalog = load("workExampleCatalog.ts", {
  "../../examples/catalog/work-examples.json": manifest,
  "./optionSearch": load("optionSearch.ts"),
  "./workExampleAssets": { workExampleAssets: Object.fromEntries(allowed.map(path => [`../../${path}`, async () => texts[path]])) },
});
assert.ok(catalog.findWorkExamples("crosstalk").length >= 2);
assert.ok(catalog.findWorkExamples("DECAP", "Power integrity").length >= 1);
assert.ok(catalog.findWorkExamples("", "Signal integrity", "saved-evidence").every(row => row.status === "saved-evidence"));
assert.equal(catalog.findWorkExamples("an impossible absent fixture").length, 0);
await assert.rejects(catalog.loadWorkExampleAsset("pi-dc", "examples/part_limits/part-limits.json"), /not bundled/);
await assert.rejects(catalog.loadWorkExampleAsset("missing", allowed[0]), /not bundled/);
await assert.rejects(catalog.prepareWorkExampleAction("pi-dc"), /no automatic workspace action/);
await assert.rejects(catalog.prepareWorkExampleAction("missing"), /Unknown example/);
const ibis = await catalog.prepareWorkExampleAction("si-ibis");
assert.equal(ibis.kind, "ibis");
assert.equal(ibis.requestText, texts["examples/si/ibis_driver_receiver/request.json"]);
const spatial = await catalog.prepareWorkExampleAction("si-spatial");
assert.equal(spatial.kind, "spatial");
assert.equal(spatial.designText, texts["examples/si/spatial_crosstalk/board.spike-design.json"]);
assert.equal(spatial.solverText, texts["examples/si/spatial_crosstalk/solver.json"]);
assert.equal(spatial.samplesText, texts["examples/si/spatial_crosstalk/samples.json"]);
const parser = load("projectPackage.ts", { "./appVersion": { APP_VERSION: "0.4.2" } });
const projects = manifest.examples.filter(row => row.primaryAction === "project");
for (const row of projects) {
  const action = await catalog.prepareWorkExampleAction(row.id);
  assert.equal(action.kind, "project");
  assert.equal(action.snapshotText, texts[row.projectAsset]);
  assert.equal(action.fileName, row.projectAsset.split("/").at(-1).replace(/\.json$/, ""));
  const original = JSON.parse(action.snapshotText);
  const opened = parser.parseProjectPackage(action.snapshotText);
  assert.equal(opened.migrated, false);
  for (const key of ["design", "analysis", "thermal", "emi", "assembly_ir", "models"]) assert.deepEqual(opened.project[key], original[key], `${row.id}: complete ${key} admitted`);
}
const ebrake = JSON.parse(texts[projects.find(row => row.id === "promo-ebrake").projectAsset]);
assert.ok(ebrake.design.source_board.length > 100000);
const frames = ebrake.thermal.scenario.board_thermal_result.transient;
assert.equal(frames.length, 16);
assert.equal(frames[0].time_s, 0);
assert.equal(frames.at(-1).time_s, 600);
for (const name of ["case-contact", "poor-contact"]) {
  const data = JSON.parse(texts[`examples/promo_release/projects/${name}.spike.json`]);
  assert.ok(data.analysis.assembly_field_study.request);
  assert.ok(data.analysis.assembly_field_study.result.field_result);
  assert.equal(data.models.models[0].uri, "package:models/artifacts/original-case.step");
}
assert.ok(catalog.findWorkExamples("solenoid", "Magnetic machines", "setup-only").length);

let current, saved = [], opened = [], desktop = false, failLoad = false;
const ui = load("WorkExamples.tsx", {
  react: { ...React, useEffect() {}, useId: () => "test-file", useState: initial => {
    const index = current.index++;
    if (!(index in current.states)) current.states[index] = typeof initial === "function" ? initial() : initial;
    const owner = current;
    return [owner.states[index], value => { owner.states[index] = typeof value === "function" ? value(owner.states[index]) : value; }];
  } },
  "./workExampleCatalog": { ...catalog, loadWorkExampleAsset: (...args) => {
    if (failLoad) return Promise.reject(new Error("Resource unavailable; retry after updating resources."));
    return catalog.loadWorkExampleAsset(...args);
  } },
  "./workerBridge": { isDesktopShell: () => desktop, saveExtensionArtifact: async artifact => { saved.push(artifact); return null; } },
  "./emergeSampleExport": { downloadEMergeText: (...args) => saved.push(args) },
  "./workExampleAssets": { workExamplePictures: Object.fromEntries(pictures.map(path => [`../../${path}`, `/assets/${path.split("/").at(-1)}`])) },
});
function harness(Component, props) {
  const context = { states: [], index: 0 };
  return () => { current = context; context.index = 0; return Component(props); };
}
function nodes(node, predicate) {
  if (!node) return [];
  if (Array.isArray(node)) return node.flatMap(value => nodes(value, predicate));
  if (typeof node !== "object") return [];
  return [...(predicate(node) ? [node] : []), ...nodes(node.props?.children, predicate)];
}
const textOf = node => typeof node === "string" ? node : Array.isArray(node) ? node.map(textOf).join("") : textOf(node?.props?.children ?? "");
const button = (tree, text) => nodes(tree, node => node.type === "button" && textOf(node) === text)[0];
const onOpen = async (id, action) => { opened.push([id, action]); };
const renderCatalog = harness(ui.default, { onOpen });
const initial = renderCatalog();
assert.ok(renderToStaticMarkup(initial).includes(`${manifest.examples.length} curated cases`));
const cardElement = nodes(initial, node => typeof node.type === "function" && node.props?.row?.id === "si-ibis")[0];
assert.ok(cardElement);
const renderCard = harness(cardElement.type, cardElement.props);
await button(renderCard(), "Stage IBIS example").props.onClick();
assert.deepEqual(opened[0], ["si-ibis", ibis]);
assert.match(textOf(renderCard()), /No solver has been started/);
await button(renderCard(), "Save selected file").props.onClick();
assert.equal(saved[0][1], ibis.requestText);
await button(renderCard(), "Inspect text").props.onClick();
assert.ok(nodes(renderCard(), node => node.type === "pre").some(node => textOf(node) === ibis.requestText));
desktop = true;
await button(renderCard(), "Save selected file").props.onClick();
assert.match(textOf(renderCard()), /Save cancelled/);
assert.equal(saved.at(-1).file_name, "request.json");
assert.equal(saved.at(-1).data, ibis.requestText);
assert.equal(saved.at(-1).sha256, createHash("sha256").update(ibis.requestText).digest("hex"));
nodes(renderCard(), node => node.type === "select")[0].props.onChange({ target: { value: "examples/si/ibis_driver_receiver/original_cmos.ibs" } });
await button(renderCard(), "Save selected file").props.onClick();
assert.equal(saved.at(-1).file_name, "original_cmos.ibs", "native artifact save retains exact file suffix");
assert.equal(saved.at(-1).data, texts["examples/si/ibis_driver_receiver/original_cmos.ibs"]);
failLoad = true;
await button(renderCard(), "Save selected file").props.onClick();
assert.match(textOf(renderCard()), /Resource unavailable/);
assert.equal(button(renderCard(), "Save selected file").props.disabled, false, "failed resource can be retried");
failLoad = false;
const noStage = harness(cardElement.type, { ...cardElement.props, onOpen: undefined });
assert.equal(button(noStage(), "Stage IBIS example").props.disabled, true);
assert.equal(button(noStage(), "Save selected file").props.disabled, false);
for (const [id, label, expected] of [["si-spatial", "Stage spatial SI example", spatial], ["em-filter", "Open EMerge library", { kind: "emerge-library" }], ["promo-motor", "Open saved project", await catalog.prepareWorkExampleAction("promo-motor")]]) {
  const element = nodes(initial, node => typeof node.type === "function" && node.props?.row?.id === id)[0];
  const render = harness(element.type, element.props);
  await button(render(), label).props.onClick();
  assert.deepEqual(opened.at(-1), [id, expected]);
}
const largeElement = nodes(initial, node => typeof node.type === "function" && node.props?.row?.id === "promo-ebrake")[0];
const renderLarge = harness(largeElement.type, largeElement.props);
await button(renderLarge(), "Inspect text").props.onClick();
assert.ok(nodes(renderLarge(), node => node.type === "pre").every(node => textOf(node).length <= 32768));
assert.match(textOf(renderLarge()), /first 32 KiB/);
const captureElement = nodes(initial, node => typeof node.type === "function" && node.props?.row?.id === "promo-electric-capture")[0];
const captureRender = harness(captureElement.type, captureElement.props);
assert.equal(nodes(captureRender(), node => node.type === "img").length, 1);
assert.match(textOf(captureRender()), /not installed desktop capture/);
const failedStage = harness(cardElement.type, { ...cardElement.props, onOpen: async () => { throw new Error("Workspace context changed; select again."); } });
await button(failedStage(), "Stage IBIS example").props.onClick();
assert.match(textOf(failedStage()), /Workspace context changed/);
assert.equal(button(failedStage(), "Stage IBIS example").props.disabled, false);
const selectors = nodes(renderCatalog(), node => node.type === "select");
selectors[0].props.onChange({ target: { value: "Signal integrity" } });
selectors[1].props.onChange({ target: { value: "saved-evidence" } });
const filteredCards = nodes(renderCatalog(), node => typeof node.type === "function" && node.props?.row);
assert.deepEqual(filteredCards.map(node => node.props.row.id), ["si-spatial"]);
button(renderCatalog(), "Clear filters").props.onClick();
const renderSeeded = harness(ui.default, { initialQuery: "Classic IBIS" });
assert.deepEqual(nodes(renderSeeded(), node => typeof node.type === "function" && node.props?.row).map(node => node.props.row.id), ["si-ibis"]);
const input = nodes(renderCatalog(), node => node.type === "input" && node.props.type === "search")[0];
input.props.onChange({ target: { value: "no such case at all" } });
assert.match(textOf(renderCatalog()), /No matching examples/);
button(renderCatalog(), "Clear filters").props.onClick();
assert.equal(nodes(renderCatalog(), node => typeof node.type === "function" && node.props?.row).length, manifest.examples.length);
console.log(`Work examples: ${manifest.examples.length} entries, ${allowed.length} bounded assets, filtering, staged payloads, interactive save/inspect and recovery passed.`);
