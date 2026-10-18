// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import { Layers, Search, Save, RefreshCw } from "./icons";
import { runNativeProjectWorker } from "./workerBridge";
import type { AssemblyDesigns, AssemblyIr } from "./mcadAssembly";
import "./MaterialLibraryPanel.css";

type Material = Record<string, unknown> & { id: string; name: string; revision: string; properties: Record<string, unknown> };
type Props = {
  projectPath: string | null; manifestDigest: string | null; assembly: AssemblyIr | null;
  designs: AssemblyDesigns | null;
  desktopShell: boolean; onUpdated: () => Promise<void>; onStatus: (message: string) => void;
};
const label = (value: unknown) => typeof value === "string" ? value : "";
const describe = (value: unknown) => JSON.stringify(value, null, 2);
function PropertyEvidence({ record }: { record: Material }) {
  return <div className="material-properties">{Object.entries(record.properties).map(([name, raw]) => {
    const property = raw as Record<string, unknown>;
    const provenance = property.provenance as Record<string, unknown> | undefined;
    const applicability = property.applicability as Record<string, unknown> | undefined;
    const value = property.shape === "scalar" ? String(property.value)
      : property.shape === "orthotropic" ? `${describe(property.values)} / ${describe(property.axes)}`
      : property.shape === "samples" ? "Sampled temperature / frequency data"
      : "Data unavailable";
    return <div key={name}><b>{name.replace(/_/g, " ")}</b><span>{value} {label(property.unit)}</span><small>{label(property.status)} / {label(applicability?.notes)}</small><small>Source: {label(provenance?.source)}</small>{property.shape === "samples" && <pre>{describe(property.samples)}</pre>}</div>;
  })}</div>;
}

export default function MaterialLibraryPanel({ projectPath, manifestDigest, assembly, designs, desktopShell, onUpdated, onStatus }: Props) {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [target, setTarget] = useState("");
  const [layerId, setLayerId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [custom, setCustom] = useState(false);
  const [draft, setDraft] = useState("");
  const targets = useMemo(() => [
    ...(assembly?.parts ?? []).map(part => ({ key: `part:${part.id}`, kind: "part", id: part.id, name: part.name, extensions: part.extensions })),
    ...(assembly?.boards ?? []).map(board => ({ key: `board:${String(board.id)}`, kind: "board", id: String(board.id), name: label(board.name) || String(board.id), extensions: board.extensions as Record<string, unknown> | undefined })),
  ], [assembly]);
  const selected = materials.find(item => item.id === selectedId);
  const currentTarget = targets.find(item => item.key === target);
  const targetBoard = assembly?.boards.find(board => board.id === currentTarget?.id && currentTarget?.kind === "board");
  const boardDesign = designs?.designs.find(design => design.design_id === targetBoard?.design_id);
  const layers = Array.isArray(boardDesign?.layers) ? boardDesign.layers as Record<string, unknown>[] : [];
  const layerAssignments = currentTarget?.extensions?.["spike.layer-materials"] as Record<string, unknown> | undefined;
  const saved = layerId ? layerAssignments?.[layerId] : currentTarget?.extensions?.["spike.material"];
  const filtered = useMemo(() => {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    return materials.filter(item => terms.every(term => JSON.stringify(item).toLowerCase().includes(term)));
  }, [materials, query]);
  useEffect(() => { if (!filtered.some(item => item.id === selectedId)) setSelectedId(filtered[0]?.id ?? ""); }, [filtered, selectedId]);
  useEffect(() => { if (!targets.some(item => item.key === target)) setTarget(targets[0]?.key ?? ""); }, [targets, target]);
  useEffect(() => { setLayerId(""); }, [target]);
  const load = async () => {
    if (!projectPath || !desktopShell) return;
    setBusy(true); setError("");
    try {
      const response = await runNativeProjectWorker({ method: "list_material_catalog", params: { project_path: projectPath } });
      if (!response.ok || !Array.isArray(response.result?.materials)) throw new Error(response.error || "Material catalog unavailable.");
      const catalog = response.result.materials as Material[];
      setMaterials(catalog); setSelectedId(current => catalog.some(item => item.id === current) ? current : catalog[0]?.id ?? "");
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  };
  useEffect(() => { setMaterials([]); void load(); }, [projectPath, desktopShell]); // catalog is inert; assignment uses the latest manifest
  const assign = async () => {
    if (!currentTarget || !projectPath || !manifestDigest) return;
    setBusy(true); setError("");
    try {
      const materialInput = custom ? { material: JSON.parse(draft) as unknown } : { catalog_material_id: selectedId };
      const response = await runNativeProjectWorker({ method: "assign_material_to_project", params: {
        project_path: projectPath, expected_manifest_payload_sha256: manifestDigest,
        target_kind: layerId ? "board_layer" : currentTarget.kind, target_id: currentTarget.id,
        ...(layerId ? { layer_id: layerId } : {}), ...materialInput,
      } });
      if (!response.ok) throw new Error(response.error || "Material assignment rejected.");
      await onUpdated();
      onStatus(`Material snapshot saved for ${currentTarget.name}. Review material applicability and regenerate affected solver setup before running.`);
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  };
  return <section className="material-library" aria-label="Multiphysics material library">
    <header><h3><Layers size={16} /> Material library</h3><button type="button" onClick={() => void load()} disabled={busy || !projectPath || !desktopShell}><RefreshCw size={14} /> Reload</button></header>
    <p>Retain thermal, electrical and mechanical properties with their source, units and applicability. Generic estimates require review; catalog availability does not qualify a solver.</p>
    {!desktopShell || !projectPath ? <p role="status">Open a saved project in desktop SPIKE to load and assign materials.</p> : <>
      <label className="material-search"><Search size={14} /><input aria-label="Search material library" placeholder="FR4, ceramic, RF, polyimide, conductor..." value={query} onChange={event => setQuery(event.target.value)} /></label>
      <label>Library material<select aria-label="Library material" value={selectedId} onChange={event => { setSelectedId(event.target.value); setCustom(false); }}>
        {filtered.map(item => <option key={item.id} value={item.id}>{item.name} / {label(item.family)}</option>)}
      </select></label>
      <small>{filtered.length} of {materials.length} materials match</small>
      {selected && <><p><b>{selected.name}</b> <small>revision {selected.revision}</small></p>
        <details><summary>Properties, sources and validity</summary><PropertyEvidence record={selected} /></details>
        <details><summary>Advanced material record</summary><pre>{describe(selected)}</pre></details>
        <button type="button" disabled={busy} onClick={() => { setDraft(describe(selected)); setCustom(true); }}>Create editable project material</button></>}
      {custom && <label>Custom material record (JSON)<textarea aria-label="Custom material record" spellCheck={false} value={draft} onChange={event => setDraft(event.target.value)} /><small>Change ID, revision, values and provenance together. The worker validates units, ranges and record structure before saving.</small></label>}
      <label>Assignment target<select aria-label="Material assignment target" value={target} onChange={event => setTarget(event.target.value)}>{targets.map(item => <option key={item.key} value={item.key}>{item.kind}: {item.name}</option>)}</select></label>
      {currentTarget?.kind === "board" && <label>Board region<select aria-label="Material board region" value={layerId} onChange={event => setLayerId(event.target.value)}><option value="">Bulk / equivalent board</option>{layers.map(layer => <option key={String(layer.id)} value={String(layer.id)}>{label(layer.name) || String(layer.id)}</option>)}</select></label>}
      <p>Assign copper, dielectric or heater-film materials to their exact existing layers. Bulk assignments describe an equivalent board. Layer order, geometry and thickness remain separate setup inputs.</p>
      {saved != null && <details><summary>Saved material snapshot</summary><pre>{describe(saved)}</pre></details>}
      <button type="button" className="spike-control--primary" disabled={busy || !manifestDigest || !currentTarget || (!custom && !selected)} onClick={() => void assign()}><Save size={14} /> {busy ? "Working..." : "Save material snapshot"}</button>
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
