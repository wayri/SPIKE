// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { runNativeProjectWorker } from "./workerBridge";
import type { FieldObject } from "./assemblyFieldStudyPresentation";

/** Component CAD becomes a thermal body only after explicit material/placement review. */
export default function ThermalComponentPromotion({ components, projectPath, manifestDigest, disabled, onBusyChange, onUpdated }: {
  components: FieldObject[]; projectPath: string; manifestDigest: string; disabled: boolean;
  onBusyChange: (busy: boolean) => void; onUpdated: () => Promise<void>;
}) {
  const [selected, setSelected] = useState("");
  const [modelId, setModelId] = useState("");
  const [matrix, setMatrix] = useState("[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]");
  const [conductivity, setConductivity] = useState("");
  const [provenance, setProvenance] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [queue, setQueue] = useState<FieldObject[]>([]);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const ownsBusy = useRef(false);
  useEffect(() => {
    generation.current++; setSelected(""); setModelId(""); setReviewed(false); setError(""); setBusy(false); setQueue([]);
    return () => { generation.current++; if (ownsBusy.current) { ownsBusy.current = false; onBusyChange(false); } };
  }, [projectPath, manifestDigest, onBusyChange]);
  const component = components.find(c => JSON.stringify([c.board_occurrence_id, c.component_id]) === selected);
  const model = component?.models?.find((m: FieldObject) => m.model_id === modelId);
  let transform: unknown = null;
  try { transform = JSON.parse(matrix); } catch { /* Invalid draft remains editable. */ }
  const validTransform = Array.isArray(transform) && transform.length === 16 && transform.every(x => typeof x === "number" && Number.isFinite(x));
  const valid = component && model?.status === "ready" && validTransform && conductivity.trim() && Number.isFinite(Number(conductivity)) && Number(conductivity) > 0 && provenance.trim() && reviewed;
  const draft = () => {
    const materialId = `component-material-${crypto.randomUUID()}`;
    return { label: `${component!.board_occurrence_id} · ${component!.reference || component!.component_id}`,
      selection: { board_occurrence_id: component!.board_occurrence_id, component_id: component!.component_id,
        model_id: modelId, component_to_board_transform_mm: transform, material_id: materialId, placement_reviewed: true },
      material: { id: materialId, thermal_conductivity_w_mk: Number(conductivity), provenance: provenance.trim() } };
  };
  const queueDraft = () => {
    if (disabled || busy || !valid) return;
    const item = draft();
    setQueue(old => [...old.filter(row => row.selection.board_occurrence_id !== item.selection.board_occurrence_id
      || row.selection.component_id !== item.selection.component_id), item].slice(0, 100));
    setReviewed(false);
  };
  async function promote(useQueue = false) {
    if (disabled || busy || (useQueue ? !queue.length : !valid)) return;
    const token = generation.current;
    setBusy(true); ownsBusy.current = true; onBusyChange(true); setError("");
    try {
      const batch = useQueue ? queue : [draft()];
      const response = await runNativeProjectWorker({ method: "promote_thermal_components_in_project", params: {
        project_path: projectPath, expected_manifest_payload_sha256: manifestDigest,
        selections: batch.map(item => item.selection),
        materials: batch.map(item => item.material),
      } });
      if (token !== generation.current) return;
      if (!response.ok) throw new Error(response.error_detail?.detail || response.error || "Component model could not be retained for thermal meshing.");
      await onUpdated();
    } catch (caught) { if (token === generation.current) setError(String(caught)); }
    finally { if (token === generation.current && ownsBusy.current) { ownsBusy.current = false; setBusy(false); onBusyChange(false); } }
  }
  return <details><summary>Include component STEP models as thermal parts</summary>
    <p>Promote a selected retained component model into a distinct physical occurrence. Review its component-to-board rigid transform (row-major 4×4, translation in mm), including mounting height and bottom-side orientation. The retained model offset is applied separately.</p>
    <fieldset disabled={disabled || busy}>
      <label>Board occurrence and component<select value={selected} onChange={e => { setSelected(e.target.value); setModelId(""); setReviewed(false); }}>
        <option value="">Select component…</option>{components.map(c => <option key={JSON.stringify([c.board_occurrence_id, c.component_id])} value={JSON.stringify([c.board_occurrence_id, c.component_id])}>{c.board_occurrence_id} · {c.reference || c.component_id}</option>)}
      </select></label>
      {component && <p>Retained placement: {JSON.stringify(component.placement)}. Already promoted parts: {component.promoted_part_ids?.join(", ") || "none"}.</p>}
      <label>Authoritative STEP model<select value={modelId} onChange={e => { setModelId(e.target.value); setReviewed(false); }}><option value="">Select retained model…</option>
        {(component?.models ?? []).map((m: FieldObject) => <option key={m.model_id} value={m.model_id} disabled={m.status !== "ready"}>{m.model_id} · {m.status}</option>)}
      </select></label>
      {(component?.models ?? []).filter((m: FieldObject) => m.status !== "ready").map((m: FieldObject) => <p key={m.model_id}>{m.model_id}: {m.reason}</p>)}
      {component && !component.models?.length && <p>Retain an authoritative STEP model in the project model index and bind it to this component first. Display placeholders are not thermal solids.</p>}
      <label>Reviewed component-to-board transform<textarea rows={3} value={matrix} onChange={e => { setMatrix(e.target.value); setReviewed(false); }} /></label>
      <label>Thermal conductivity (W/m·K)<input type="number" min="0" step="any" value={conductivity} onChange={e => { setConductivity(e.target.value); setReviewed(false); }} /></label>
      <label>Material property source<input value={provenance} maxLength={256} onChange={e => { setProvenance(e.target.value); setReviewed(false); }} /></label>
      <label><span><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} /> I reviewed model placement and material properties.</span></label>
      <button type="button" disabled={!valid} onClick={() => void promote()}>{busy ? "Retaining thermal component…" : "Retain component for thermal meshing"}</button>
      <button type="button" disabled={!valid || queue.length >= 100} onClick={queueDraft}>Queue reviewed component</button>
      {!!queue.length && <section aria-label="Reviewed component batch"><p>{queue.length} reviewed components queued. Each keeps its own model, placement and material.</p>
        <ul>{queue.map(item => <li key={JSON.stringify([item.selection.board_occurrence_id, item.selection.component_id])}>{item.label}
          <button type="button" aria-label={`Remove ${item.label} from thermal batch`} onClick={() => setQueue(old => old.filter(row => row !== item))}>Remove</button></li>)}</ul>
        <button type="button" onClick={() => void promote(true)}>Retain reviewed component batch</button>
        <p>Joint meshing currently supports at most 64 source solids, including board layers. Review mesh coverage before solving.</p>
      </section>}
    </fieldset>
    <p>This changes the saved assembly and invalidates affected results. Reload the geometry inventory and regenerate the complete volume mesh before solving.</p>
    {error && <p role="alert">{error}</p>}
  </details>;
}
