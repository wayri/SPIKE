import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const root = new URL("../", import.meta.url);
const assemblySource = readFileSync(new URL("src/mcadAssembly.ts", root), "utf8");
const packageShapesSource = readFileSync(new URL("src/assemblyPackageShapes.ts", root), "utf8");
const panel = readFileSync(new URL("src/McadAttachmentPanel.tsx", root), "utf8");
const semanticsEditor = readFileSync(new URL("src/AssemblySemanticsEditor.tsx", root), "utf8");
const topologyEditor = readFileSync(new URL("src/AssemblyTopologyEditor.tsx", root), "utf8");
const structureEditor = readFileSync(new URL("src/AssemblyStructureEditor.tsx", root), "utf8");
const app = readFileSync(new URL("src/App.tsx", root), "utf8");
const bridge = readFileSync(new URL("src/workerBridge.ts", root), "utf8");
const host = readFileSync(new URL("src-tauri/src/lib.rs", root), "utf8");
const tauriConfig = JSON.parse(readFileSync(new URL("src-tauri/tauri.conf.json", root), "utf8"));

const transpiled = ts.transpileModule(assemblySource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const assembly = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);
const packageShapes = await import(`data:text/javascript;base64,${Buffer.from(ts.transpileModule(packageShapesSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText).toString("base64")}`);

assert.equal(assembly.modelDisplayStatus({ model_type: "step" }), "STEP retained; tessellation required for viewport display");
assert.match(assembly.modelDisplayStatus({ model_type: "gltf" }), /visualizable from a verified desktop package/);
assert.match(assembly.modelDisplayStatus({ model_type: "glb" }), /visualizable from a verified desktop package/);
assert.equal(assembly.normalizeAssemblyIr({ contract: "wrong", boards: [], parts: [] }), null);
const retainedDesigns = assembly.normalizeAssemblyDesigns({ contract: "spike/assembly-designs/v1", active_design_id: "design-a", designs: [{ contract: "spike/design-ir/v2", design_id: "design-a", name: "Main board" }, { contract: "spike/design-ir/v2", design_id: "design-b", name: "Control board" }] });
assert.deepEqual(retainedDesigns.designs.map(design => design.design_id), ["design-a", "design-b"]);
assert.equal(assembly.normalizeAssemblyDesigns({ ...retainedDesigns, active_design_id: "missing" }), null);
assert.equal(assembly.normalizeAssemblyDesigns({ ...retainedDesigns, designs: [...retainedDesigns.designs, retainedDesigns.designs[0]] }), null);
assert.equal(assembly.normalizeModelIndex(null).contract, "spike/model-index/v1");
assert.deepEqual(assembly.DEFAULT_ASSEMBLY_SECTION, {
  enabled: false, mode: "plane", axis: "x", offsetMm: 0,
  minXMm: -100, maxXMm: 100, minYMm: -100, maxYMm: 100, minZMm: -100, maxZMm: 100,
});
const sectionTransform = { centerX: 10, centerY: 20, scale: 2 };
const planeSection = { ...assembly.DEFAULT_ASSEMBLY_SECTION, enabled: true, axis: "y", offsetMm: 7 };
assert.deepEqual(assembly.buildAssemblySectionClippingPlanes(planeSection, sectionTransform), [
  { normal: [0, -1, 0], point: [0, 26, 0] },
]);
const boxSection = { ...assembly.DEFAULT_ASSEMBLY_SECTION, enabled: true, mode: "box", minXMm: 1, maxXMm: 5, minYMm: 3, maxYMm: 9, minZMm: -2, maxZMm: 4 };
assert.deepEqual(assembly.buildAssemblySectionClippingPlanes(boxSection, sectionTransform), [
  { normal: [1, 0, 0], point: [-18, 0, 0] }, { normal: [-1, 0, 0], point: [-10, 0, 0] },
  { normal: [0, -1, 0], point: [0, 34, 0] }, { normal: [0, 1, 0], point: [0, 22, 0] },
  { normal: [0, 0, 1], point: [0, 0, -4] }, { normal: [0, 0, -1], point: [0, 0, 8] },
]);
assert.deepEqual(assembly.buildAssemblySectionClippingPlanes({ ...boxSection, minXMm: 6, maxXMm: 5 }, sectionTransform), [], "inverted boxes must fail closed");
assert.deepEqual(assembly.buildAssemblySectionClippingPlanes({ ...boxSection, maxZMm: Number.NaN }, sectionTransform), [], "nonfinite boxes must fail closed");
assert.deepEqual(assembly.buildAssemblySectionClippingPlanes({ ...planeSection, offsetMm: Number.NaN }, sectionTransform), [], "nonfinite planes must fail closed");
const exactIndex = {
  contract: "spike/assembly-package-shapes/v1", assembly_id: "assembly",
  shapes: [{
    shape_id: "shape", part_id: "part", source_model_id: "step", source_artifact_uri: "package:models/artifacts/part.step",
    source_sha256: "1".repeat(64), topology_artifact_uri: "package:geometry/package-shapes/shape.spkshape", topology_artifact_sha256: "2".repeat(64),
    kernel: { id: "freecad-occ", contract: "spike/package-shape-kernel/v1", version: "7.8.1" },
    extraction: { status: "complete", source_format: "step", source_model_transform_sha256: "3".repeat(64), topology_ready: true, solver_ready: false },
    entities: [{ topology_id: "face-id", kind: "face", native_persistent_id: "face:native", fingerprint_sha256: "4".repeat(64), support: { surface_kind: "plane", curve_kind: null, axis_topology_id: null } }],
    selector_preview: { contract: "spike/package-shape-selector-preview/v1", artifact_uri: "package:geometry/package-shapes/shape.spkselect.glb", artifact_sha256: "5".repeat(64), source_sha256: "1".repeat(64), topology_artifact_sha256: "2".repeat(64), selector_inventory_sha256: "6".repeat(64), freecad_version: "1.1.3", linear_deflection_mm: 0.1, face_count: 1, edge_count: 0, axis_count: 0, visual_only: true, solver_ready: false },
    extensions: {},
  }], constraints: [], thermal_contact_bindings: [], electrical_bond_bindings: [], extensions: {}, metadata: {},
};
assert.equal(packageShapes.normalizeAssemblyPackageShapes(exactIndex).shapes.length, 1);
assert.equal(packageShapes.packageShapeForPart(exactIndex, "part").shape_id, "shape");
assert.equal(packageShapes.topologyEntityOptions(exactIndex, new Set(["face"]), "native").length, 1);
assert.equal(packageShapes.normalizeAssemblyPackageShapes({ ...exactIndex, contract: "wrong" }), null);

const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const assemblyIr = {
  contract: "spike/assembly-ir/v1",
  assembly_id: "assembly",
  name: "Fixture",
  boards: [],
  parts: [{ id: "part", model_id: "visual", name: "Housing", frame: { frame_id: "part-frame", parent_frame_id: "assembly", units: "mm", handedness: "right", transform: identity } }],
};
const modelIndex = {
  contract: "spike/model-index/v1",
  models: [{ id: "visual", model_type: "glb", name: "Housing", transform: [] }, { id: "step", model_type: "step", name: "Exact source", transform: [] }],
};
assert.deepEqual(assembly.visualModelIds(assemblyIr, modelIndex), ["visual"]);
assert.deepEqual(assembly.assemblyPartViewportStates(assemblyIr, modelIndex), { part: "pending" });
assert.equal(assembly.assemblyPartViewportStatusDetail("ready"), "viewport ready");
assert.equal(assembly.assemblyPartViewportStatusDetail("failed"), "viewport load failed");
assert.equal(assembly.assemblyPartViewportStatusDetail("step_requires_tessellation"), "awaiting STEP tessellation");
const sceneModels = assembly.createAssemblySceneModels(assemblyIr, modelIndex, new Map([["visual", "blob:fixture"]]));
assert.equal(sceneModels.length, 1);
assert.equal(sceneModels[0].url, "blob:fixture");
assert.deepEqual(sceneModels[0].modelTransform, identity);
assert.equal(sceneModels[0].visible, true);
assert.equal(sceneModels[0].opacity, 1);

let frameReads = 0;
const denseAssembly = { ...assemblyIr, boards: [], parts: Array.from({ length: 20_000 }, (_, i) => {
  const transform = [...identity]; transform[3] = 1;
  const frame = { frame_id: `dense-${i}`, parent_frame_id: i ? `dense-${i - 1}` : 'assembly',
    units: 'mm', handedness: 'right', transform };
  return { ...assemblyIr.parts[0], id: `part-${i}`, get frame() { frameReads++; return frame; } };
}) };
const denseStarted = performance.now();
const denseModels = assembly.createAssemblySceneModels(denseAssembly, modelIndex, new Map([['visual', 'blob:fixture']]));
assert.equal(denseModels.length, 20_000);
assert.equal(denseModels.at(-1).partTransform[3], 20_000);
assert.ok(frameReads <= 20_000 * 5, `frame lookup rebuilt per part: ${frameReads} reads`);
const allRows = assembly.assemblyHierarchyRows(denseAssembly, modelIndex);
assert.equal(allRows.length, 20_001, 'hierarchy must retain rows beyond the former 121-row cutoff');
assert.equal(allRows.at(-1).depth, 20_000, 'deep hierarchies must avoid recursive stack overflow');
denseAssembly.parts[0].frame.transform[3] = 2;
assert.equal(assembly.resolveFrameToAssembly(denseAssembly, denseAssembly.parts.at(-1).frame)[3], 20_001,
  'new projections must observe edited transforms');
console.log(`20,000 nested assembly frames: exact composition and complete hierarchy in ${Math.round(performance.now() - denseStarted)} ms`);
const selectorModels = assembly.createAssemblySelectorPreviewModels(assemblyIr, modelIndex, exactIndex, new Map([["shape", "blob:selector-preview"]]));
assert.equal(selectorModels.length, 1);
assert.equal(selectorModels[0].url, "blob:selector-preview");
assert.equal(selectorModels[0].references.get("face-id").topology_kind, "face");
assert.deepEqual(assembly.placementPolicySettings(assemblyIr.parts[0]), { translationSnapMm: 0, rotationSnapDeg: 0 });
assemblyIr.parts[0].placement_policy = {
  contract: "spike/assembly-placement-policy/v1",
  translation_snap_mm: 0.5,
  rotation_snap_deg: 30,
};
assert.deepEqual(assembly.placementPolicySettings(assemblyIr.parts[0]), { translationSnapMm: 0.5, rotationSnapDeg: 30 });
const hiddenAssembly = structuredClone(assemblyIr);
hiddenAssembly.parts[0].extensions = { "spike.visual": { visible: false, opacity: 0.35 } };
assert.deepEqual(assembly.visualModelIds(hiddenAssembly, modelIndex), []);
assert.deepEqual(assembly.assemblyPartViewportStates(hiddenAssembly, modelIndex), { part: "hidden" });
assert.deepEqual(assembly.partVisualSettings(hiddenAssembly.parts[0]), { visible: false, opacity: 0.35 });
assert.match(assembly.partDisplayStatus(hiddenAssembly.parts[0], modelIndex.models[0], hiddenAssembly), /hidden after reopen/);
const stepAssembly = structuredClone(assemblyIr);
stepAssembly.parts[0].model_id = "step";
assert.deepEqual(assembly.assemblyPartViewportStates(stepAssembly, modelIndex), { part: "step_requires_tessellation" });
const unavailableAssembly = structuredClone(assemblyIr);
unavailableAssembly.parts[0].model_id = "missing";
assert.deepEqual(assembly.assemblyPartViewportStates(unavailableAssembly, modelIndex), { part: "unavailable" });
const nestedAssembly = structuredClone(assemblyIr);
nestedAssembly.parts[0].frame.parent_frame_id = "board-frame";
nestedAssembly.boards = [{ id: "board", frame: { frame_id: "board-frame", parent_frame_id: "assembly", units: "mm", handedness: "right", transform: [1, 0, 0, 100, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] } }];
nestedAssembly.parts[0].frame.transform = [1, 0, 0, 5, 0, 1, 0, 6, 0, 0, 1, 7, 0, 0, 0, 1];
assert.deepEqual(assembly.visualModelIds(nestedAssembly, modelIndex), ["visual"]);
assert.deepEqual(assembly.resolveFrameToAssembly(nestedAssembly, nestedAssembly.parts[0].frame), [1, 0, 0, 105, 0, 1, 0, 6, 0, 0, 1, 7, 0, 0, 0, 1]);
assert.deepEqual(assembly.localTransformFromAssembly(nestedAssembly, nestedAssembly.parts[0], [1, 0, 0, 112, 0, 1, 0, 9, 0, 0, 1, 11, 0, 0, 0, 1]), [1, 0, 0, 12, 0, 1, 0, 9, 0, 0, 1, 11, 0, 0, 0, 1]);
const rotatedParentAssembly = structuredClone(nestedAssembly);
rotatedParentAssembly.boards[0].frame.transform = [0, -1, 0, 100, 1, 0, 0, 50, 0, 0, 1, 0, 0, 0, 0, 1];
const desiredLocal = assembly.transformFromPlacement({ xMm: 7, yMm: -4, zMm: 3, rxDeg: 0, ryDeg: 0, rzDeg: 30 });
const desiredWorld = assembly.resolveFrameToAssembly(rotatedParentAssembly, { ...rotatedParentAssembly.parts[0].frame, transform: desiredLocal });
const recoveredLocal = assembly.localTransformFromAssembly(rotatedParentAssembly, rotatedParentAssembly.parts[0], desiredWorld);
for (let index = 0; index < 16; index += 1) assert.ok(Math.abs(recoveredLocal[index] - desiredLocal[index]) < 1e-9, `nested gizmo local matrix drifted at ${index}`);
assert.match(assembly.partDisplayStatus(nestedAssembly.parts[0], modelIndex.models[0], nestedAssembly), /nested parent-frame transform composed/);
const targets = assembly.validReparentTargets(nestedAssembly, "part");
assert.deepEqual(targets.map(target => target.frameId), ["assembly", "board-frame"]);
const descendantAssembly = structuredClone(nestedAssembly);
descendantAssembly.parts.push({ id: "child", model_id: "visual", name: "Child", frame: { frame_id: "child-frame", parent_frame_id: "part-frame", units: "mm", handedness: "right", transform: identity } });
assert.ok(!assembly.validReparentTargets(descendantAssembly, "part").some(target => target.frameId === "child-frame"), "descendant frames must not be reparent targets");
descendantAssembly.parts.push({ id: "root-part", model_id: "visual", name: "Root heatsink", part_type: "heatsink", frame: { frame_id: "root-part-frame", parent_frame_id: "assembly", units: "mm", handedness: "right", transform: identity } });
const hierarchyRows = assembly.assemblyHierarchyRows(descendantAssembly, modelIndex);
assert.deepEqual(hierarchyRows.map(row => row.entityId), ["assembly", "board", "part", "child", "root-part"]);
assert.deepEqual(hierarchyRows.map(row => row.depth), [0, 1, 2, 3, 1]);
assert.ok(hierarchyRows.filter(row => row.kind === "part").every(row => row.actionable), "resolved MCAD hierarchy rows must focus the editor");
assert.match(hierarchyRows.find(row => row.entityId === "part").detail, /visualizable from a verified desktop package/);
const hierarchyStates = assembly.assemblyHierarchyRows(descendantAssembly, modelIndex, { part: "ready", child: "failed", "root-part": "hidden" });
assert.equal(hierarchyStates.find(row => row.entityId === "part").viewportState, "ready");
assert.match(hierarchyStates.find(row => row.entityId === "part").detail, /viewport ready/);
assert.match(hierarchyStates.find(row => row.entityId === "child").detail, /viewport load failed/);
assert.match(hierarchyStates.find(row => row.entityId === "root-part").detail, /hidden after reopen/);
const cyclicAssembly = structuredClone(nestedAssembly);
cyclicAssembly.boards[0].frame.parent_frame_id = nestedAssembly.parts[0].frame.frame_id || "part-frame";
cyclicAssembly.parts[0].frame.frame_id = nestedAssembly.parts[0].frame.frame_id || "part-frame";
assert.equal(assembly.resolveFrameToAssembly(cyclicAssembly, cyclicAssembly.parts[0].frame), null);
const cyclicRows = assembly.assemblyHierarchyRows(cyclicAssembly, modelIndex);
assert.equal(cyclicRows.length, 3);
assert.ok(cyclicRows.slice(1).every(row => !row.resolved && !row.actionable), "cyclic hierarchy nodes must terminate as unresolved diagnostics");
const placed = assembly.transformFromPlacement({ xMm: 10, yMm: -20, zMm: 30, rxDeg: 15, ryDeg: -25, rzDeg: 40 });
const restoredPlacement = assembly.placementFromTransform(placed);
for (const [key, expected] of Object.entries({ xMm: 10, yMm: -20, zMm: 30, rxDeg: 15, ryDeg: -25, rzDeg: 40 })) {
  assert.ok(Math.abs(restoredPlacement[key] - expected) < 1e-9, `${key} placement round trip drifted`);
}
assert.throws(() => assembly.transformFromPlacement({ xMm: Number.NaN, yMm: 0, zMm: 0, rxDeg: 0, ryDeg: 0, rzDeg: 0 }), /finite/);

for (const field of ["project_path", "source_path", "part_type", "material_id"]) {
  assert.ok(panel.includes(field), `MCAD attachment request is missing ${field}`);
}
assert.ok(panel.includes('method: "attach_mcad_part_to_project"'), "MCAD panel must use the transactional project worker method");
assert.ok(panel.includes('method: "update_mcad_part_in_project"'), "MCAD panel must persist numeric placement transactionally");
assert.ok(panel.includes('method: "update_mcad_placement_policy_in_project"'), "MCAD panel must persist placement policy through its dedicated transaction");
assert.ok(panel.includes('method: "reparent_mcad_part_in_project"'), "MCAD panel must use the dedicated world-preserving reparent worker method");
assert.ok(panel.includes('method: "tessellate_mcad_part_in_project"'), "MCAD panel must expose the bounded manifest-bound STEP tessellator");
assert.ok(panel.includes('method: "extract_mcad_package_shape_in_project"'), "MCAD panel must expose bounded exact STEP topology extraction");
assert.ok(panel.includes('method: "generate_mcad_selector_preview_in_project"'), "MCAD panel must expose bounded exact-selector preview generation");
assert.ok(panel.includes("AssemblyTopologyEditor"), "MCAD panel must expose typed topology-addressed setup after extraction");
assert.ok(panel.includes("AssemblyStructureEditor"), "MCAD panel must expose board-instance and harness structure editing");
assert.ok(structureEditor.includes('method: "update_assembly_structure_in_project"'), "assembly structure edits must use their manifest-bound transaction");
for (const field of ["boards", "harnesses", "connector_mappings", "rigid_flex_links", "expected_manifest_payload_sha256"]) {
  assert.ok(structureEditor.includes(field), `assembly structure request is missing ${field}`);
}
assert.ok(structureEditor.includes("Coupled analysis remains disabled"), "assembly structure UI must preserve its coupled-physics qualification boundary");
assert.ok(structureEditor.includes("assemblyDesigns.designs.map"), "assembly board instances must select from retained DesignIR identities");
assert.ok(structureEditor.includes("assemblyDesigns?.active_design_id"), "new board instances must default to the retained active DesignIR identity");
assert.ok(topologyEditor.includes('method: "update_assembly_topology_setup_in_project"'), "exact topology setup must use its dedicated immutable-shape transaction");
assert.ok(topologyEditor.includes('method: "apply_assembly_geometric_constraint_in_project"'), "exact topology setup must expose its manifest-bound single-constraint transaction");
assert.ok(topologyEditor.includes("exact BREP descriptors"), "geometric snapping must name its authoritative geometry source");
assert.ok(topologyEditor.includes("no triangle picking, placement solve, collision/contact solve, mesh qualification, or solver readiness"), "exact topology setup must state its qualification boundary");
assert.ok(panel.includes('role="tree"'), "MCAD editor must expose a semantic board/part hierarchy tree");
assert.ok(panel.includes("buildAssemblyHierarchy"), "MCAD editor must derive its tree from canonical AssemblyIR frames");
assert.ok(panel.includes("expected_manifest_payload_sha256"), "MCAD edits must bind to the verified project identity");
for (const control of ["Visible after reopen", "Isolate temporarily", "Visual cross-section", "Save part and placement", "Save placement policy", "Reparent without moving", "Tessellate STEP for viewport", "Extract exact STEP topology", "3D transform gizmo", "GRID SNAP (mm)", "ANGLE SNAP (deg)", "Face/edge/axis/concentric/coincident/distance constraint resolution remains topology-gated"]) {
  assert.ok(panel.includes(control), `MCAD assembly controls are missing ${control}`);
}
for (const control of ["Bounded box", "MIN X (mm)", "MAX X (mm)", "MIN Y (mm)", "MAX Y (mm)", "MIN Z (mm)", "MAX Z (mm)", "Temporary visual-only viewport clipping"]) {
  assert.ok(panel.includes(control), `MCAD visual-only section-box controls are missing ${control}`);
}
assert.ok(semanticsEditor.includes('method: "update_assembly_semantics_in_project"'), "assembly semantics must persist through a transactional worker");
for (const field of ["materials", "thermal_contacts", "electrical_bonds", "expected_manifest_payload_sha256"]) {
  assert.ok(semanticsEditor.includes(field), `assembly semantics request is missing ${field}`);
}
assert.ok(panel.includes("STEP tessellation is still required"), "STEP display limit must be explicit after attach");
assert.ok(panel.includes("no material properties, contact, bond, boundary, or solver semantics are inferred"), "solver non-claim is missing");
assert.ok(panel.includes("visual-only and not solver-qualified"), "derived STEP visualization must not imply solver geometry");
assert.ok(app.includes("assembly_ir: assemblyIr, assembly_designs: assemblyDesigns, assembly_package_shapes: assemblyPackageShapes, models: modelIndex"), "frontend snapshots must preserve AssemblyIR, retained designs, exact package shapes, and model index");
assert.ok(app.includes("setAssemblyDesigns(normalizeAssemblyDesigns(data.assembly_designs))"), "frontend open must retain the complete multi-design projection");
assert.ok(app.includes("setAssemblyPackageShapes(normalizeAssemblyPackageShapes(data.assembly_package_shapes))"), "frontend open must retain the exact package-shape projection");
assert.ok(app.includes("onAssemblyPart={partId =>"), "scene hierarchy part rows must focus the existing MCAD editor");
assert.ok(app.includes("focusedPartId={mcadFocusedPartId}"), "focused hierarchy identity must reach the MCAD editor");
assert.ok(app.includes("loadNativeProjectFromApprovedPath(projectPath"), "successful attachment must reopen the verified package");
assert.ok(app.includes('method: "read_project_model_artifacts"'), "desktop project must resolve visual MCAD package artifacts");
assert.ok(app.includes('method: "read_project_package_shape_selector_previews"'), "desktop project must use the dedicated manifest-bound selector-preview reader");
assert.ok(app.includes("if (!assemblyModelReadReady) return"), "selector previews must wait for the heavy visual-model read instead of racing the native single-flight gate");
assert.ok(app.includes("if (!settled) void cancelLocalWorkerCleanup(requestId)"), "package-read teardown must use silent lifecycle cancellation instead of publishing false worker failures");
assert.ok(bridge.includes("export async function cancelLocalWorkerCleanup(operationId: string)"), "worker bridge must distinguish silent effect teardown from user-initiated cancellation");
assert.match(tauriConfig.app.security.csp, /connect-src[^;]*\bblob:/, "verified in-memory GLB artifacts require a narrowly scoped blob fetch allowance");
assert.ok(app.includes("assemblyModels={assemblySceneModels}"), "resolved MCAD scene models must reach the viewport");
assert.ok(app.includes("assemblyPartViewportStates={assemblyPartViewportStates}"), "per-part viewport states must reach the assembly hierarchy");
assert.ok(app.includes("assemblySelectorPreviews={assemblySelectorPreviews}"), "resolved exact-selector previews must reach the viewport");
assert.ok(app.includes("isolatedAssemblyPartId={isolatedAssemblyPartId}"), "temporary part isolation must reach the viewport");
assert.ok(app.includes("assemblySection={assemblySection}"), "visual assembly section state must reach the viewport");
assert.ok(bridge.includes('"select_mcad_file"'), "worker bridge must expose the restricted MCAD picker");
assert.ok(host.includes('&["project_path", "source_path"]'), "native gateway must require both approved MCAD paths");
assert.ok(host.includes("select_mcad_file"), "native MCAD picker command is missing");
assert.ok(host.includes('&["step", "stp", "gltf", "glb"]'), "native MCAD picker allowlist is incomplete");
const viewport = readFileSync(new URL("src/BoardViewport.tsx", root), "utf8");
assert.ok(viewport.includes("renderer.localClippingEnabled = true"), "assembly sectioning requires local clipping");
assert.ok(viewport.includes("buildAssemblySectionClippingPlanes"), "visual models and selector previews must share the pure section-plane builder");
assert.ok(viewport.includes("assemblySectionClippingPlanes(assemblySection, boardTransformRef.current)"), "visual models and selector previews must apply identical section clipping");
assert.ok(viewport.includes("assemblyPartId"), "assembly display controls require stable part identities");
assert.ok(viewport.includes("onAssemblyPartViewportStatus"), "renderer outcomes must propagate by stable assembly part identity");
assert.ok(viewport.includes("partStates[assemblyModels[index].partId]"), "each visual-model load result must be attributed to its AssemblyIR part");
assert.ok(viewport.includes("loadSceneWithRetry(() => cloneCachedGltfScene(instance.url))"), "visual model loads must retry transient failures while retaining the shared decode cache");
assert.ok(viewport.includes("refreshAssemblyDisplayRef.current()"), "async assembly loading must reapply display controls");
assert.ok(viewport.includes("TransformControls"), "assembly dragging must use one explicit Three.js transform gizmo");
assert.ok(viewport.includes("matrixToRowMajor(object.matrix)"), "gizmo commits must leave renderer matrices through the canonical row-major boundary");
assert.ok(viewport.includes('publishGizmoTransform("commit")'), "gizmo persistence must occur once at drag completion");
assert.ok(viewport.includes("controls3d.enabled = false"), "orbit navigation must pause while the gizmo owns pointer interaction");
assert.ok(viewport.includes("selectorPreviewPickablesRef"), "exact-selector previews require a dedicated pick set outside board pickables");
assert.ok(viewport.includes("topologyReference"), "selector clicks must resolve to canonical topology references");
assert.ok(viewport.includes("assemblyGizmo.dragging"), "selector picking must not run while the transform gizmo is dragging");
assert.ok(!viewport.includes("DragControls"), "assembly parts must not enter an unbounded generic drag controller");

console.log("MCAD attachment, projection, path-approval, and honest-status contracts passed.");
