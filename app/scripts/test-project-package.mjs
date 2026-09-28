import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const projectPackageSource = readFileSync(new URL("../src/projectPackage.ts", import.meta.url), "utf8");
const versionSource = readFileSync(new URL("../src/appVersion.ts", import.meta.url), "utf8");
const version = versionSource.match(/APP_VERSION\s*=\s*"([^"]+)"/)?.[1];
assert.ok(version, "the application version must be declared");
const source = projectPackageSource.replace(
  /import \{ APP_VERSION \} from "\.\/appVersion";\s*/,
  `const APP_VERSION = ${JSON.stringify(version)};\n`,
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const bridgeSource = readFileSync(new URL("../src/workerBridge.ts", import.meta.url), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const projectPackage = await import(
  `data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`
);

const payload = {
  emi: { setup: { contract: "spike/emi-setup/v1", chamber: { distance_m: 3, table_height_m: .8, antenna_height_m: 2, orientation: "upright", azimuth_deg: 45, polarization: "vertical", floor: "absorber", cutaway: true } } },
  project: { name: "round-trip.spike" },
  studies: [{ version: 1, id: "study-1", name: "Mixed study", notes: "", cases: [
    { id: "pi-1", type: "pi", mode: "DC IR Drop", name: "Baseline", notes: "", scenario: { label: "open air" }, settings: { boardFile: "fixture.kicad_pcb" } },
    { id: "thermal-1", type: "thermal", mode: "", name: "Enclosed", notes: "", scenario: { label: "closed box" }, settings: { boardFile: "fixture.kicad_pcb" } },
  ] }],
  design: {
    source_file: "fixture.kicad_pcb",
    source_board: "(kicad_pcb (version 20260101))",
    stackup: [{ name: "F.Cu", thickness_mm: 0.035 }],
  },
  analysis: {
    show_net_names: true,
    mode: "DC IR Drop",
    result_display: "dc-result-1",
    latest_result: { analysis_id: "dc-1" },
    pdn_review: {
      contract: "spike/pdn-review/v1",
      status: "violated",
      model_status: "approximate",
      net: "+1V8_CORE",
      target_ohm: 0.02,
      maximum_impedance_ohm: 0.031,
      violation_count: 4,
      resonances: [{ frequency_hz: 1e6, magnitude_ohm: 0.031 }],
      anti_resonances: [],
      candidate_screening: [{ id: "C1", status: "evaluated", placement_method: "series_connection_path", model_status: "approximate", passes_target: false }],
    },
  },
  spice: {
    workspace: {
      contract: "spike/spice-workspace/v1",
      domain: "pi",
      assignments: [{ id: "model-u1", component_id: "u1", enabled: true }],
      parasitics: [{ id: "rlc-vin", endpoint_reviewed: true }],
    },
  },
  workspace: {
    contract: "spike/workspace-state/v1",
    viewMode: "3D",
    docks: { leftOpen: true, rightOpen: false, bottomOpen: true, sidePanelsPinned: true, bottomPinned: false, leftWidthPx: 260, rightWidthPx: 340, bottomHeightPx: 220, activeBottomDock: "Console" },
    viewports: { threeD: { contract: "spike/viewport-camera/v1", position: [1, 2, 3], target: [0, 0, 0], up: [0, 0, 1] } },
  },
  probes: [{ id: "p1", x: 1, y: 2 }],
  selection: { id: "u1", type: "component" },
  assembly_ir: { contract: "spike/assembly-ir/v1", assembly_id: "assembly-1", name: "Fixture", boards: [], parts: [] },
  assembly_designs: { contract: "spike/assembly-designs/v1", active_design_id: "design-a", designs: [{ contract: "spike/design-ir/v2", design_id: "design-a", name: "Main board" }, { contract: "spike/design-ir/v2", design_id: "design-b", name: "Control board" }] },
  assembly_package_shapes: { contract: "spike/assembly-package-shapes/v1", assembly_id: "assembly-1", shapes: [], constraints: [], thermal_contact_bindings: [], electrical_bond_bindings: [], extensions: {}, metadata: {} },
  models: { contract: "spike/model-index/v1", models: [] },
};

const created = projectPackage.createProjectPackage(payload);
assert.equal(created.format, "spike-project-package/v2");
assert.ok(created.manifest.content.includes("spice"));
assert.ok(created.manifest.content.includes("studies"));
assert.ok(created.manifest.content.includes("workspace"));
assert.ok(created.manifest.content.includes("assembly_package_shapes"));
assert.ok(created.manifest.content.includes("assembly_designs"));
assert.match(created.manifest.source_checksum, /^fnv1a32:[0-9a-f]{8}$/);

const reopened = projectPackage.parseProjectPackage(JSON.stringify(created));
assert.equal(reopened.migrated, false);
assert.deepEqual(reopened.project.design.stackup, payload.design.stackup);
assert.deepEqual(reopened.project.analysis.latest_result, payload.analysis.latest_result);
assert.deepEqual(reopened.project.studies, payload.studies);
assert.equal(reopened.project.analysis.result_display, "dc-result-1");
assert.deepEqual(reopened.project.analysis.pdn_review, payload.analysis.pdn_review);
assert.equal(reopened.project.analysis.show_net_names, true, "net-name visibility survives save/reopen");
assert.deepEqual(reopened.project.spice.workspace, payload.spice.workspace);
assert.deepEqual(reopened.project.emi.setup.chamber, payload.emi.setup.chamber);
assert.deepEqual(reopened.project.workspace, payload.workspace);
assert.deepEqual(reopened.project.probes, payload.probes);
assert.deepEqual(reopened.project.selection, payload.selection);
assert.deepEqual(reopened.project.assembly_ir, payload.assembly_ir);
assert.deepEqual(reopened.project.assembly_designs, payload.assembly_designs);
assert.deepEqual(reopened.project.assembly_package_shapes, payload.assembly_package_shapes);
assert.deepEqual(reopened.project.models, payload.models);

const damaged = structuredClone(created);
damaged.design.source_board += "\n; modified after save";
assert.throws(
  () => projectPackage.parseProjectPackage(JSON.stringify(damaged)),
  /checksum does not match/,
);

assert.match(bridgeSource, /invoke<NativeSelectedFile \| null>\("take_startup_project"\)/);
assert.match(appSource, /takeStartupProject\(\)/);
assert.match(appSource, /loadNativeProjectFromApprovedPath\(file\.path, file\.fileName\)/);
const importedBoardHandler = appSource.match(
  /const applyImportedBoard = async[\s\S]*?(?=  const importNativeBoard = async)/,
)?.[0] ?? "";
assert.match(importedBoardHandler, /setProjectPath\(null\)/,
  "importing a board must clear the prior project path before a Save As request");
assert.match(importedBoardHandler, /setProjectManifestDigest\(null\)/,
  "importing a board must clear the prior package identity");
for (const reset of [
  "setModelAssignments({})", "setAssemblyIr(null)", "setAssemblyDesigns(null)",
  "setAssemblyPackageShapes(null)", "setModelIndex(normalizeModelIndex(null))",
  "setComponentBonds([])", "setResultRecords([])", "setResultDisplay(\"none\")",
  "setSelectedSiSuite(null)", "setSiChannelResult(null)", "setThermalScenario(null)",
]) {
  assert.ok(importedBoardHandler.includes(reset),
    `importing a board must clear prior board-bound state: ${reset}`);
}
assert.match(appSource, /base_package_path: projectPath/,
  "only the active saved project path may be offered as a lossless Save As base");
assert.match(appSource, /result_display: resultDisplay/,
  "the selected result display must persist with the project");
assert.match(appSource, /setResultDisplay\(restoredDisplay\)/,
  "reopening a solved project must restore a visible result instead of a blank viewport");

console.log("SPIKE project package round-trip and checksum assertions passed");
