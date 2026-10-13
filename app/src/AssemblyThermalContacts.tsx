// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { runLocalWorker } from "./workerBridge";
import type { FieldObject } from "./assemblyFieldStudyPresentation";

/** Total K/W resistance is converted using matched mesh area, never a guessed footprint. */
export default function AssemblyThermalContacts({ request, problem, disabled, onApply }: {
  request: FieldObject; problem: FieldObject; disabled: boolean; onApply: (problem: FieldObject) => void;
}) {
  const contacts = request.assembly?.thermal_contacts ?? [];
  const [selected, setSelected] = useState("");
  const [resistance, setResistance] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<FieldObject | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const token = useRef(0);
  useEffect(() => { token.current++; setBusy(false); setMessage(""); setPreview(null); setChecked([]); }, [request, problem]);
  useEffect(() => { setSelected(contacts[0]?.id ?? ""); }, [request]);
  const contact = contacts.find((c: FieldObject) => c.id === selected);
  useEffect(() => { setResistance(contact?.thermal_resistance_k_per_w == null ? "" : String(contact.thermal_resistance_k_per_w)); }, [selected, request]);
  useEffect(() => () => { token.current++; }, []);
  const value = Number(resistance);
  async function autolink(applySelection: boolean) {
    if (disabled || busy) return;
    const current = ++token.current;
    setBusy(true); setMessage("");
    try {
      const response = await runLocalWorker({ method: applySelection ? "autolink_assembly_thermal_contacts" : "discover_assembly_thermal_links", params: {
        request, problem, ...(applySelection ? { contact_ids: checked } : {}),
      } });
      if (current !== token.current) return;
      if (!response.ok || !response.result) throw new Error(response.error_detail?.detail || response.error || "Interface discovery failed.");
      if (applySelection) {
        const next = response.result.problem;
        if (!next || typeof next !== "object" || Array.isArray(next)) throw new Error("Invalid linked thermal problem.");
        onApply(next as FieldObject);
      } else { setPreview(response.result); setChecked([]); }
    } catch (error) { if (current === token.current) setMessage(error instanceof Error ? error.message : String(error)); }
    finally { if (current === token.current) setBusy(false); }
  }
  async function apply() {
    const current = ++token.current;
    setBusy(true); setMessage("");
    try {
      const response = await runLocalWorker({ method: "prepare_assembly_thermal_contact_model", params: {
        request, problem, contact_id: selected, thermal_resistance_k_per_w: value,
      } });
      if (current !== token.current) return;
      if (!response.ok || !response.result) throw new Error(response.error_detail?.detail || response.error || "Thermal link could not be prepared.");
      const nextProblem = response.result.problem;
      if (!nextProblem || typeof nextProblem !== "object" || Array.isArray(nextProblem)) throw new Error("Worker returned an invalid thermal problem.");
      onApply(nextProblem as FieldObject);
      setMessage(`${response.result.face_pair_count} matched faces · ${response.result.contact_area_mm2} mm² · ${value} K/W. Review and apply the edited setup.`);
    } catch (error) { if (current === token.current) setMessage(error instanceof Error ? error.message : String(error)); }
    finally { if (current === token.current) setBusy(false); }
  }
  return <details><summary>Thermal part links · {contacts.length}</summary>
    <p>Use retained board/part contact identities. The mesh must have matching interface triangles. Total resistance is K/W; conductance uses their actual area.</p>
    <div className="assembly-field-actions"><button type="button" disabled={disabled || busy} onClick={() => void autolink(false)}>Discover thermal interfaces</button>
      <button type="button" disabled={disabled || busy || !checked.length || checked.length > 64} onClick={() => void autolink(true)}>Autolink selected retained contacts</button></div>
    <p>Discovery checks coincident triangles and opposing outward normals. Select links to use their retained resistance. New geometric candidates require an explicit assembly contact and reviewed resistance; proximity alone creates no link.</p>
    {preview && <fieldset disabled={disabled || busy}><legend>Review interface candidates</legend>
      {(preview.proposals ?? []).slice(0, 100).map((p: FieldObject, index: number) => <label key={index}><span>
        <input type="checkbox" disabled={p.status !== "ready"} checked={checked.includes(p.contact_id)} onChange={e => setChecked(old => e.target.checked ? [...old, p.contact_id] : old.filter(id => id !== p.contact_id))} />
        {p.endpoints?.join(" ↔ ")} · {p.face_pair_count} faces · {p.contact_area_mm2} mm² · {p.thermal_resistance_k_per_w ?? "unassigned"} K/W
      </span>{p.reason && <span>{p.reason}</span>}</label>)}
      {!(preview.proposals ?? []).length && <p>No conforming interfaces found. Review placement and mesh interfaces.</p>}
      {!!preview.unmatched_contact_ids?.length && <p>Unmatched retained contacts: {preview.unmatched_contact_ids.join(", ")}</p>}
      {!!preview.ambiguous_interfaces?.length && <p>Ambiguous interfaces: {preview.ambiguous_interfaces.length}. Inspect overlapping bodies before linking.</p>}
      {(preview.proposals ?? []).length > 100 && <p>Showing the first 100 candidates. Process smaller assemblies or use the bounded worker API.</p>}
    </fieldset>}
    {!contacts.length ? <p>Add a thermal contact in the assembly placement setup before linking volumes.</p> : <fieldset className="assembly-field-boundary" disabled={disabled || busy}>
      <label>Retained link<select value={selected} onChange={e => setSelected(e.target.value)}>{contacts.map((c: FieldObject) => <option key={c.id} value={c.id}>{c.id} · {c.endpoint_a} ↔ {c.endpoint_b}</option>)}</select></label>
      <label>Total thermal resistance (K/W)<input type="number" min="0" step="any" value={resistance} onChange={e => setResistance(e.target.value)} /></label>
      <button type="button" disabled={!selected || !resistance || !Number.isFinite(value) || value <= 0} onClick={() => void apply()}>{busy ? "Matching contact faces…" : "Prepare thermal link"}</button>
    </fieldset>}
    {message && <p role="status">{message}</p>}
  </details>;
}
