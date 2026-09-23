import { useEffect, useMemo, useState } from "react";
import { Box, CircuitBoard, FileBox, Link2, Move3d, PackageOpen, ShieldAlert, X } from "lucide-react";
import { runNativeProjectWorker, selectNativeMcadFile, type NativeSelectedFile } from "./workerBridge";
import { buildAssemblyHierarchy, localTransformFromAssembly, partVisualSettings, placementFromTransform, placementPolicySettings, transformFromPlacement, validReparentTargets, type AssemblyDesigns, type AssemblyHierarchyNode, type AssemblyIr, type AssemblyPartVisual, type AssemblyPlacement, type AssemblySection } from "./mcadAssembly";
import AssemblySemanticsEditor from "./AssemblySemanticsEditor";
import AssemblyTopologyEditor from "./AssemblyTopologyEditor";
import AssemblyStructureEditor from "./AssemblyStructureEditor";
import { packageShapeForPart, type AssemblyPackageShapesIndex, type TopologyReference } from "./assemblyPackageShapes";

type Props = {
  projectPath: string | null;
  projectManifestDigest: string | null;
  assemblyIr: AssemblyIr | null;
  assemblyDesigns: AssemblyDesigns | null;
  assemblyPackageShapes: AssemblyPackageShapesIndex | null;
  focusedPartId: string | null;
  focusedTopologyReference: TopologyReference | null;
  desktopShell: boolean;
  isolatedPartId: string | null;
  section: AssemblySection;
  onIsolatedPart: (partId: string | null) => void;
  onSection: (section: AssemblySection) => void;
  onAttached: () => Promise<void>;
  onStatus: (message: string) => void;
  onClose: () => void;
  onOpenHarnessEditor?: () => void;
};

const sourceKind = (file: NativeSelectedFile | null) => file?.fileName.split(".").pop()?.toLowerCase() ?? "";
const EMPTY_PLACEMENT: AssemblyPlacement = { xMm: 0, yMm: 0, zMm: 0, rxDeg: 0, ryDeg: 0, rzDeg: 0 };
const PART_TYPES = ["mechanical", "enclosure", "heatsink", "fan", "potting", "fixture"];
const EMPTY_ASSEMBLY: AssemblyIr = { contract: "spike/assembly-ir/v1", assembly_id: "assembly", name: "Assembly", boards: [], parts: [] };

function HierarchyBranch({ node, selectedPartId, onSelectPart }: { node: AssemblyHierarchyNode; selectedPartId: string; onSelectPart: (partId: string) => void }) {
  const Icon = node.kind === "board" ? CircuitBoard : node.kind === "part" ? PackageOpen : Box;
  return <li data-kind={node.kind} data-frame-id={node.frameId}>
    <button className={node.kind === "part" && node.entityId === selectedPartId ? "selected" : ""} disabled={node.kind !== "part"} onClick={() => node.kind === "part" && onSelectPart(node.entityId)}>
      <Icon size={14} /><span><b>{node.label}</b><small>{node.kind} · {node.frameId}</small></span>
    </button>
    {node.children.length > 0 && <ul>{node.children.map(child => <HierarchyBranch key={child.frameId} node={child} selectedPartId={selectedPartId} onSelectPart={onSelectPart} />)}</ul>}
  </li>;
}

export default function McadAttachmentPanel({ projectPath, projectManifestDigest, assemblyIr, assemblyDesigns, assemblyPackageShapes, focusedPartId, focusedTopologyReference, desktopShell, isolatedPartId, section, onIsolatedPart, onSection, onAttached, onStatus, onClose, onOpenHarnessEditor }: Props) {
  const [source, setSource] = useState<NativeSelectedFile | null>(null);
  const [name, setName] = useState("");
  const [partType, setPartType] = useState("mechanical");
  const [materialId, setMaterialId] = useState("");
  const [selectedPartId, setSelectedPartId] = useState(assemblyIr?.parts[0]?.id ?? "");
  const [editName, setEditName] = useState("");
  const [editPartType, setEditPartType] = useState("mechanical");
  const [editMaterialId, setEditMaterialId] = useState("");
  const [placement, setPlacement] = useState<AssemblyPlacement>(EMPTY_PLACEMENT);
  const [visual, setVisual] = useState<AssemblyPartVisual>({ visible: true, opacity: 1 });
  const [reparentTarget, setReparentTarget] = useState("");
  const [gizmoEnabled, setGizmoEnabled] = useState(true);
  const [gizmoMode, setGizmoMode] = useState<"translate" | "rotate">("translate");
  const [translationSnapMm, setTranslationSnapMm] = useState(0);
  const [rotationSnapDeg, setRotationSnapDeg] = useState(0);
  const [busy, setBusy] = useState(false);
  const canAttach = desktopShell && Boolean(projectPath && source) && !busy;
  const selectedPart = useMemo(() => assemblyIr?.parts.find(part => part.id === selectedPartId) ?? null, [assemblyIr, selectedPartId]);
  const selectedPackageShape = useMemo(() => packageShapeForPart(assemblyPackageShapes, selectedPartId), [assemblyPackageShapes, selectedPartId]);
  const rootFrameId = assemblyIr?.frame?.frame_id || "assembly";
  const canSavePart = desktopShell && Boolean(projectPath && projectManifestDigest && selectedPart) && !busy;
  const canEditPlacement = canSavePart;
  const reparentTargets = useMemo(() => assemblyIr && selectedPart ? validReparentTargets(assemblyIr, selectedPart.id) : [], [assemblyIr, selectedPart]);
  const hierarchy = useMemo(() => assemblyIr ? buildAssemblyHierarchy(assemblyIr) : null, [assemblyIr]);
  const mcadExtension = selectedPart?.extensions?.["spike.mcad"];
  const tessellationExtension = selectedPart?.extensions?.["spike.mcad.tessellation"];
  const selectedHasRetainedStep = Boolean(mcadExtension && typeof mcadExtension === "object" && "source_format" in mcadExtension && mcadExtension.source_format === "step");
  const selectedIsRetainedStep = selectedHasRetainedStep && !tessellationExtension;
  const selectedVisualizable = Boolean(tessellationExtension || (mcadExtension && typeof mcadExtension === "object" && "source_format" in mcadExtension && (mcadExtension.source_format === "gltf" || mcadExtension.source_format === "glb")));
  const gizmoEligible = Boolean(canSavePart && selectedVisualizable && visual.visible && (!isolatedPartId || isolatedPartId === selectedPart?.id));
  const canTessellate = canSavePart && selectedIsRetainedStep;
  const canExtractExactShape = canSavePart && selectedHasRetainedStep;
  const canGenerateSelectorPreview = canSavePart && Boolean(selectedPackageShape);

  useEffect(() => {
    if (focusedPartId && assemblyIr?.parts.some(part => part.id === focusedPartId)) setSelectedPartId(focusedPartId);
  }, [assemblyIr, focusedPartId]);

  useEffect(() => {
    if (!selectedPart) return;
    setEditName(selectedPart.name);
    setEditPartType(selectedPart.part_type);
    setEditMaterialId(selectedPart.material_id);
    setPlacement(placementFromTransform(selectedPart.frame.transform));
    const policy = placementPolicySettings(selectedPart);
    setTranslationSnapMm(policy.translationSnapMm);
    setRotationSnapDeg(policy.rotationSnapDeg);
    setVisual(partVisualSettings(selectedPart));
    setReparentTarget(selectedPart.frame.parent_frame_id || rootFrameId);
  }, [rootFrameId, selectedPart]);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("spike-mcad-gizmo-config", { detail: {
      partId: selectedPart?.id ?? "", enabled: Boolean(gizmoEnabled && gizmoEligible),
      mode: gizmoMode, translationSnapMm, rotationSnapDeg,
    } }));
    return () => { window.dispatchEvent(new CustomEvent("spike-mcad-gizmo-config", { detail: { partId: "", enabled: false } })); };
  }, [gizmoEligible, gizmoEnabled, gizmoMode, rotationSnapDeg, selectedPart?.id, translationSnapMm]);

  const pickSource = async () => {
    try {
      const selected = await selectNativeMcadFile();
      if (!selected) return;
      setSource(selected);
      if (!name.trim()) setName(selected.fileName.replace(/\.(?:step|stp|gltf|glb)$/i, ""));
      onStatus(`MCAD source approved: ${selected.fileName}`);
    } catch (error) {
      onStatus(error instanceof Error ? `MCAD selection failed: ${error.message}` : "MCAD selection failed");
    }
  };

  const updatePlacement = async (transformOverride?: number[], interaction = "numeric") => {
    if (!canSavePart || !projectPath || !projectManifestDigest || !selectedPart) return;
    setBusy(true);
    try {
      const response = await runNativeProjectWorker({
        method: "update_mcad_part_in_project",
        params: {
          project_path: projectPath,
          expected_manifest_payload_sha256: projectManifestDigest,
          part_id: selectedPart.id,
          name: editName.trim(),
          part_type: editPartType,
          material_id: editMaterialId.trim(),
          visual,
          frame: {
            ...selectedPart.frame,
            parent_frame_id: selectedPart.frame.parent_frame_id || rootFrameId,
            units: "mm",
            handedness: "right",
            transform: transformOverride ?? transformFromPlacement(placement),
          },
        },
      });
      if (!response.ok) throw new Error(response.error ?? "The MCAD placement worker rejected the edit.");
      await onAttached();
      onStatus(`${editName.trim() || selectedPart.name} ${interaction === "gizmo" ? "gizmo transform" : "metadata, appearance, and placement"} saved transactionally.`);
    } catch (error) {
      onStatus(error instanceof Error ? `MCAD placement update failed: ${error.message}` : "MCAD placement update failed");
    } finally {
      setBusy(false);
    }
  };

  const updatePlacementPolicy = async () => {
    if (!canSavePart || !projectPath || !projectManifestDigest || !selectedPart) return;
    setBusy(true);
    try {
      const response = await runNativeProjectWorker({
        method: "update_mcad_placement_policy_in_project",
        params: {
          project_path: projectPath,
          expected_manifest_payload_sha256: projectManifestDigest,
          part_id: selectedPart.id,
          placement_policy: {
            contract: "spike/assembly-placement-policy/v1",
            translation_snap_mm: translationSnapMm > 0 ? translationSnapMm : null,
            rotation_snap_deg: rotationSnapDeg > 0 ? rotationSnapDeg : null,
          },
        },
      });
      if (!response.ok) throw new Error(response.error ?? "The MCAD placement-policy worker rejected the edit.");
      await onAttached();
      onStatus(`${selectedPart.name || selectedPart.id} placement increments saved without changing its transform.`);
    } catch (error) {
      onStatus(error instanceof Error ? `MCAD placement-policy update failed: ${error.message}` : "MCAD placement-policy update failed");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const preview = (event: Event) => {
      const detail = (event as CustomEvent<{ partId?: string; assemblyTransform?: unknown }>).detail;
      if (!assemblyIr || !selectedPart || detail?.partId !== selectedPart.id) return;
      const local = localTransformFromAssembly(assemblyIr, selectedPart, detail.assemblyTransform);
      if (local) setPlacement(placementFromTransform(local));
    };
    const commit = (event: Event) => {
      const detail = (event as CustomEvent<{ partId?: string; assemblyTransform?: unknown }>).detail;
      if (!assemblyIr || !selectedPart || detail?.partId !== selectedPart.id || busy) return;
      const local = localTransformFromAssembly(assemblyIr, selectedPart, detail.assemblyTransform);
      if (!local) {
        onStatus("MCAD gizmo commit was rejected because the parent frame could not be resolved.");
        return;
      }
      setPlacement(placementFromTransform(local));
      void updatePlacement(local, "gizmo");
    };
    window.addEventListener("spike-mcad-transform-preview", preview);
    window.addEventListener("spike-mcad-transform-commit", commit);
    return () => {
      window.removeEventListener("spike-mcad-transform-preview", preview);
      window.removeEventListener("spike-mcad-transform-commit", commit);
    };
  }, [assemblyIr, busy, onStatus, selectedPart, updatePlacement]);

  const editNumber = (field: keyof AssemblyPlacement, value: string) => {
    const parsed = Number(value);
    setPlacement(current => ({ ...current, [field]: Number.isFinite(parsed) ? parsed : 0 }));
  };

  const reparent = async () => {
    if (!canSavePart || !projectPath || !projectManifestDigest || !selectedPart || !reparentTarget) return;
    const currentParent = selectedPart.frame.parent_frame_id || rootFrameId;
    if (reparentTarget === currentParent) return;
    setBusy(true);
    try {
      const response = await runNativeProjectWorker({
        method: "reparent_mcad_part_in_project",
        params: {
          project_path: projectPath,
          expected_manifest_payload_sha256: projectManifestDigest,
          part_id: selectedPart.id,
          new_parent_frame_id: reparentTarget,
        },
      });
      if (!response.ok) throw new Error(response.error ?? "The MCAD reparent worker rejected the edit.");
      await onAttached();
      onStatus(`${selectedPart.name || selectedPart.id} moved in the hierarchy with its assembly-world transform preserved.`);
    } catch (error) {
      onStatus(error instanceof Error ? `MCAD reparent failed: ${error.message}` : "MCAD reparent failed");
    } finally {
      setBusy(false);
    }
  };

  const tessellate = async () => {
    if (!canTessellate || !projectPath || !projectManifestDigest || !selectedPart) return;
    setBusy(true);
    try {
      const response = await runNativeProjectWorker({
        method: "tessellate_mcad_part_in_project",
        params: {
          project_path: projectPath,
          expected_manifest_payload_sha256: projectManifestDigest,
          part_id: selectedPart.id,
        },
      });
      if (!response.ok) throw new Error(response.error ?? "The bounded STEP tessellator rejected the part.");
      await onAttached();
      onStatus(`${selectedPart.name || selectedPart.id} now has a verified-package visual GLB; its original STEP remains retained. The mesh is visual-only and not solver-qualified.`);
    } catch (error) {
      onStatus(error instanceof Error ? `STEP tessellation failed: ${error.message}` : "STEP tessellation failed");
    } finally {
      setBusy(false);
    }
  };

  const extractExactShape = async () => {
    if (!canExtractExactShape || !projectPath || !projectManifestDigest || !selectedPart) return;
    setBusy(true);
    try {
      const response = await runNativeProjectWorker({
        method: "extract_mcad_package_shape_in_project",
        params: {
          project_path: projectPath,
          expected_manifest_payload_sha256: projectManifestDigest,
          part_id: selectedPart.id,
        },
      });
      if (!response.ok) throw new Error(response.error ?? "The bounded exact STEP topology extractor rejected the part.");
      const entityCount = Number(response.result?.entity_count ?? 0);
      await onAttached();
      onStatus(`${selectedPart.name || selectedPart.id} now owns a digest-bound exact BREP and ${entityCount.toLocaleString()} topology selectors. This enables topology-addressed setup only; it is not solver-qualified geometry.`);
    } catch (error) {
      onStatus(error instanceof Error ? `Exact STEP topology extraction failed: ${error.message}` : "Exact STEP topology extraction failed");
    } finally {
      setBusy(false);
    }
  };

  const generateSelectorPreview = async () => {
    if (!canGenerateSelectorPreview || !projectPath || !projectManifestDigest || !selectedPackageShape) return;
    setBusy(true);
    try {
      const response = await runNativeProjectWorker({
        method: "generate_mcad_selector_preview_in_project",
        params: {
          project_path: projectPath,
          expected_manifest_payload_sha256: projectManifestDigest,
          shape_id: selectedPackageShape.shape_id,
        },
      });
      if (!response.ok) throw new Error(response.error ?? "The bounded exact-selector preview generator rejected the shape.");
      await onAttached();
      onStatus(`${selectedPart?.name || selectedPackageShape.part_id} now has a digest-bound exact-selector visual aid. It maps BREP-owned face, edge, and axis identities; it is visual-only and not solver geometry.`);
    } catch (error) {
      onStatus(error instanceof Error ? `Exact-selector preview generation failed: ${error.message}` : "Exact-selector preview generation failed");
    } finally {
      setBusy(false);
    }
  };

  const attach = async () => {
    if (!canAttach || !projectPath || !source) return;
    setBusy(true);
    try {
      const response = await runNativeProjectWorker({
        method: "attach_mcad_part_to_project",
        params: {
          project_path: projectPath,
          source_path: source.path,
          name: name.trim(),
          part_type: partType,
          material_id: materialId.trim(),
        },
      });
      if (!response.ok) throw new Error(response.error ?? "The MCAD attachment worker rejected the artifact.");
      await onAttached();
      const format = sourceKind(source);
      onStatus(format === "step" || format === "stp"
        ? `${source.fileName} attached and retained; STEP tessellation is still required before viewport display.`
        : `${source.fileName} attached as a visualizable ${format.toUpperCase()} artifact; verified package scene loading will begin after reopen.`);
      onClose();
    } catch (error) {
      onStatus(error instanceof Error ? `MCAD attachment failed: ${error.message}` : "MCAD attachment failed");
    } finally {
      setBusy(false);
    }
  };

  return <div className="modal-shade mcad-attachment-shade" role="dialog" aria-modal="true" aria-labelledby="mcad-attachment-title">
    <section className="mcad-attachment-panel">
      <header><div><Box size={18} /><span><b id="mcad-attachment-title">MCAD assembly</b><small>Transactional attachment and numeric placement</small></span></div><button className="canvas-icon" onClick={onClose} title="Close MCAD assembly"><X size={16} /></button></header>
      <div className="mcad-attachment-body">
        <div className="mcad-boundary-note"><ShieldAlert size={16} /><span><b>Qualification boundary</b>STEP/STP is retained and may be tessellated by the bounded optional FreeCAD adapter for viewport display. A separate bounded extraction can retain an exact BREP plus source-owned face, edge, axis, solid, shell, and vertex selectors. Self-contained glTF/GLB remains visual-only. Neither tessellation nor exact-selector extraction establishes a solver mesh, material region, contact physics, or production-qualified geometry. Material IDs are explicit labels only; no material properties, contact, bond, boundary, or solver semantics are inferred.</span></div>
        {!desktopShell && <p className="mcad-gate">MCAD attachment requires the SPIKE desktop shell.</p>}
        {desktopShell && !projectPath && <p className="mcad-gate">Save this project as a native <code>.spike</code> package before attaching MCAD.</p>}
        <button className="mcad-source-picker" onClick={() => void pickSource()} disabled={!desktopShell || busy}><FileBox size={17} /><span><b>{source?.fileName ?? "Select STEP, STP, glTF, or GLB"}</b><small>{source?.path ?? "The native picker approves this exact source path for one project operation."}</small></span></button>
        <div className="mcad-fields">
          <label>PART NAME<input value={name} onChange={event => setName(event.target.value)} placeholder="Use source filename" /></label>
          <label>PART TYPE<select value={partType} onChange={event => setPartType(event.target.value)}>{PART_TYPES.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
          <label>MATERIAL ID<input value={materialId} onChange={event => setMaterialId(event.target.value)} placeholder="Explicit assignment optional" /></label>
        </div>
        {assemblyIr?.parts.length ? <section className="mcad-placement-editor">
          <h3><Move3d size={15} /> Numeric placement</h3>
          {hierarchy && <div className="mcad-hierarchy"><span>ASSEMBLY HIERARCHY</span><ul role="tree" aria-label="Assembly board and MCAD hierarchy"><HierarchyBranch node={hierarchy} selectedPartId={selectedPartId} onSelectPart={setSelectedPartId} /></ul></div>}
          {selectedPart && <>
            <div className="mcad-fields">
              <label>PART NAME<input value={editName} onChange={event => setEditName(event.target.value)} /></label>
              <label>PART TYPE<select value={editPartType} onChange={event => setEditPartType(event.target.value)}>{PART_TYPES.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
              <label>MATERIAL ID<input value={editMaterialId} onChange={event => setEditMaterialId(event.target.value)} placeholder="Explicit assignment optional" /></label>
            </div>
            <div className="mcad-fields mcad-transform-fields">
              {([['xMm', 'X (mm)'], ['yMm', 'Y (mm)'], ['zMm', 'Z (mm)'], ['rxDeg', 'RX (deg)'], ['ryDeg', 'RY (deg)'], ['rzDeg', 'RZ (deg)']] as const).map(([field, label]) => <label key={field}>{label}<input type="number" step="any" disabled={!canEditPlacement} value={placement[field]} onChange={event => editNumber(field, event.target.value)} /></label>)}
            </div>
            <div className="mcad-gizmo-controls">
              <label><input type="checkbox" checked={gizmoEnabled} disabled={!gizmoEligible} onChange={event => setGizmoEnabled(event.target.checked)} /> 3D transform gizmo</label>
              <div><button className={gizmoMode === "translate" ? "selected" : ""} onClick={() => setGizmoMode("translate")}>Translate</button><button className={gizmoMode === "rotate" ? "selected" : ""} onClick={() => setGizmoMode("rotate")}>Rotate</button></div>
              <label>GRID SNAP (mm)<input type="number" min="0" step="0.1" value={translationSnapMm} onChange={event => setTranslationSnapMm(Math.max(0, Number(event.target.value) || 0))} /></label>
              <label>ANGLE SNAP (deg)<input type="number" min="0" max="180" step="1" value={rotationSnapDeg} onChange={event => setRotationSnapDeg(Math.max(0, Math.min(180, Number(event.target.value) || 0)))} /></label>
              <button className="secondary-btn" onClick={() => void updatePlacementPolicy()} disabled={!canSavePart}>Save placement policy</button>
            </div>
            <div className="mcad-display-controls">
              <label><input type="checkbox" checked={visual.visible} onChange={event => setVisual(current => ({ ...current, visible: event.target.checked }))} /> Visible after reopen</label>
              <label>OPACITY <input type="range" min="0" max="1" step="0.05" value={visual.opacity} onChange={event => setVisual(current => ({ ...current, opacity: Number(event.target.value) }))} /><span>{Math.round(visual.opacity * 100)}%</span></label>
              <button className="secondary-btn" onClick={() => onIsolatedPart(isolatedPartId === selectedPart.id ? null : selectedPart.id)}>{isolatedPartId === selectedPart.id ? "Show all" : "Isolate temporarily"}</button>
            </div>
            <div className="mcad-fields"><label>PARENT FRAME<select value={reparentTarget} onChange={event => setReparentTarget(event.target.value)}>{reparentTargets.map(target => <option key={target.frameId} value={target.frameId}>{target.kind}: {target.label}</option>)}</select></label></div>
            <p className="mcad-gate">Persisted grid/angle increments are enforced by the worker against parent-local placement deltas; zero disables that increment. Reparenting preserves the assembly-world transform and policy. Face/edge/axis/concentric/coincident/distance constraint resolution remains topology-gated.</p>
            {selectedIsRetainedStep && <><p className="mcad-gate">Optional FreeCAD tessellation retains the source STEP and creates a derived visual-only GLB. It does not create solver regions, contacts, or qualified geometry.</p><button className="secondary-btn" onClick={() => void tessellate()} disabled={!canTessellate}>{busy ? "Tessellating..." : "Tessellate STEP for viewport"}</button></>}
            {selectedHasRetainedStep && <><p className="mcad-gate">Exact STEP topology extraction writes a digest-bound OCC BREP and owned selector inventory. It enables topology-addressed constraints/contact/bond setup only; no solve semantics are inferred.</p><button className="secondary-btn" onClick={() => void extractExactShape()} disabled={!canExtractExactShape}>{busy ? "Extracting exact topology..." : "Extract exact STEP topology"}</button></>}
            {selectedPackageShape && <><div className="mcad-boundary-note"><ShieldAlert size={15} /><span><b>Exact package shape retained</b>{selectedPackageShape.entities.length.toLocaleString()} source-owned selectors · {selectedPackageShape.kernel.id} {selectedPackageShape.kernel.version} · artifact {selectedPackageShape.topology_artifact_sha256.slice(0, 12)}…<br />{selectedPackageShape.selector_preview ? `${selectedPackageShape.selector_preview.face_count} faces · ${selectedPackageShape.selector_preview.edge_count} edges · ${selectedPackageShape.selector_preview.axis_count} axes have a digest-bound selector preview.` : "No scene selector preview has been generated yet."}<br />Topology addressing is ready; the preview is a derived visual aid and solver geometry remains false.</span></div><button className="secondary-btn" onClick={() => void generateSelectorPreview()} disabled={!canGenerateSelectorPreview}>{busy ? "Generating selector preview..." : selectedPackageShape.selector_preview ? "Regenerate exact-selector preview" : "Generate exact-selector preview"}</button></>}
            <button className="secondary-btn" onClick={() => void reparent()} disabled={!canSavePart || !reparentTarget || reparentTarget === (selectedPart.frame.parent_frame_id || rootFrameId)}>{busy ? "Reparenting..." : "Reparent without moving"}</button>
            <button className="run-btn" onClick={() => void updatePlacement()} disabled={!canSavePart}>{busy ? "Saving..." : "Save part and placement"}</button>
          </>}
        </section> : null}
        <section className="mcad-section-controls">
          <h3>Visual cross-section</h3>
          <p className="mcad-gate">Temporary visual-only viewport clipping for visualized glTF/GLB meshes and exact-selector previews. It does not create solver regions, section geometry, package data, or physics.</p>
          <label><input type="checkbox" checked={section.enabled} onChange={event => onSection({ ...section, enabled: event.target.checked })} /> Enable assembly section</label>
          <label>MODE<select value={section.mode} onChange={event => onSection({ ...section, mode: event.target.value as AssemblySection["mode"] })}><option value="plane">Plane</option><option value="box">Bounded box</option></select></label>
          {section.mode === "plane" ? <>
            <label>AXIS<select value={section.axis} onChange={event => onSection({ ...section, axis: event.target.value as AssemblySection["axis"] })}><option value="x">X</option><option value="y">Y</option><option value="z">Z</option></select></label>
            <label>OFFSET (mm)<input type="number" step="any" value={section.offsetMm} onChange={event => onSection({ ...section, offsetMm: Number(event.target.value) || 0 })} /></label>
          </> : <div className="mcad-fields">
            <label>MIN X (mm)<input type="number" step="any" value={section.minXMm} onChange={event => onSection({ ...section, minXMm: Number(event.target.value) })} /></label>
            <label>MAX X (mm)<input type="number" step="any" value={section.maxXMm} onChange={event => onSection({ ...section, maxXMm: Number(event.target.value) })} /></label>
            <label>MIN Y (mm)<input type="number" step="any" value={section.minYMm} onChange={event => onSection({ ...section, minYMm: Number(event.target.value) })} /></label>
            <label>MAX Y (mm)<input type="number" step="any" value={section.maxYMm} onChange={event => onSection({ ...section, maxYMm: Number(event.target.value) })} /></label>
            <label>MIN Z (mm)<input type="number" step="any" value={section.minZMm} onChange={event => onSection({ ...section, minZMm: Number(event.target.value) })} /></label>
            <label>MAX Z (mm)<input type="number" step="any" value={section.maxZMm} onChange={event => onSection({ ...section, maxZMm: Number(event.target.value) })} /></label>
            <p className="mcad-gate">Bounds must be finite and each minimum must not exceed its maximum; invalid bounds fail closed and apply no clipping.</p>
          </div>}
          <button className="secondary-btn" onClick={() => onSection({ ...section, enabled: false })}>Clear section</button>
        </section>
        {assemblyIr && <AssemblySemanticsEditor projectPath={projectPath} projectManifestDigest={projectManifestDigest} assemblyIr={assemblyIr} onUpdated={onAttached} onStatus={onStatus} />}
        <AssemblyStructureEditor projectPath={projectPath} projectManifestDigest={projectManifestDigest} assemblyIr={assemblyIr ?? EMPTY_ASSEMBLY} assemblyDesigns={assemblyDesigns} onUpdated={onAttached} onStatus={onStatus} onOpenHarnessEditor={onOpenHarnessEditor} />
        {assemblyIr && assemblyPackageShapes && <AssemblyTopologyEditor projectPath={projectPath} projectManifestDigest={projectManifestDigest} assemblyIr={assemblyIr} index={assemblyPackageShapes} focusedReference={focusedTopologyReference} onUpdated={onAttached} onStatus={onStatus} />}
      </div>
      <footer><span><Link2 size={13} /> Attachment writes transactionally, then reopens the verified package.</span><button className="secondary-btn" onClick={onClose} disabled={busy}>Cancel</button><button className="run-btn" onClick={() => void attach()} disabled={!canAttach}>{busy ? "Attaching..." : "Attach part"}</button></footer>
    </section>
  </div>;
}
