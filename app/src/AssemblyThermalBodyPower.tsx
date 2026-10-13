// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import type { FieldObject } from "./assemblyFieldStudyPresentation";
import { bodyPowerParameters } from "./assemblyThermalBodyPowerModel";
import { runLocalWorker } from "./workerBridge";

export default function AssemblyThermalBodyPower({ request, problem, handoff, disabled, onBusyChange, onApply }: {
  request: FieldObject; problem: FieldObject; handoff: FieldObject | null; disabled: boolean;
  onBusyChange: (busy: boolean) => void; onApply: (sources: FieldObject[]) => void;
}) {
  const [selected, setSelected] = useState("");
  const [watts, setWatts] = useState("");
  const [replace, setReplace] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const busyOwner = useRef<number | null>(null);
  useEffect(() => {
    generation.current++; setSelected(""); setWatts(""); setReviewed(false); setReplace(false); setError(""); setBusy(false);
    return () => {
      generation.current++;
      if (busyOwner.current !== null) {
        busyOwner.current = null;
        onBusyChange(false);
      }
    };
  }, [request, problem, onBusyChange]);
  const bodies: FieldObject[] = handoff?.source_traceability ?? [];
  const body = bodies.find(row => row.occurrence_id === selected);
  const existing = (problem.heat_sources ?? []).filter((source: FieldObject) => source.occurrence_id === selected).length;
  let parameters: FieldObject | null = null;
  try { if (handoff) parameters = bodyPowerParameters(request, problem, handoff, selected, watts, replace); } catch { /* Draft remains editable. */ }
  const change = () => { generation.current++; setReviewed(false); setError(""); };
  async function apply() {
    if (disabled || busy || busyOwner.current !== null || !parameters || !reviewed) return;
    const token = generation.current;
    setBusy(true); busyOwner.current = token; onBusyChange(true); setError("");
    try {
      const response = await runLocalWorker({ method: "assign_assembly_thermal_body_power", params: parameters });
      if (token !== generation.current) return;
      if (!response.ok || !response.result) throw new Error(response.error_detail?.detail || response.error || "Body power could not be assigned.");
      const result: FieldObject = response.result;
      if (result.request_digest !== handoff?.request_digest || !Array.isArray(result.problem?.heat_sources)) throw new Error("Body power response is stale or incomplete. Validate volumes and retry.");
      onApply(result.problem.heat_sources);
      if (token === generation.current) { setReviewed(false); setReplace(false); }
    } catch (caught) { if (token === generation.current) setError(String(caught)); }
    finally {
      if (busyOwner.current === token) {
        busyOwner.current = null;
        if (token === generation.current) setBusy(false);
        onBusyChange(false);
      }
    }
  }
  return <details><summary>Assign heat to a meshed body</summary>
    <p>{bodies.length} retained meshed occurrences available. Power is spread uniformly through the selected body's actual tetrahedral volume. This is a bulk material source; it does not infer a die, leads, junction temperature or electrical losses.</p>
    <fieldset disabled={disabled || busy}>
      <label>Powered occurrence<select aria-label="Powered occurrence" value={selected} onChange={event => { change(); setSelected(event.target.value); setWatts(""); setReplace(false); }}>
        <option value="">Select meshed board or STEP part...</option>
        {bodies.map(row => { const owner = [...(request.assembly?.boards ?? []), ...(request.assembly?.parts ?? [])].find(item => item.id === row.occurrence_id); return <option key={row.occurrence_id} value={row.occurrence_id}>{owner?.name || row.occurrence_id} ({row.occurrence_id})</option>; })}
      </select></label>
      {body && <p>{Object.keys(body.cell_map ?? {}).length} tetrahedra; {body.volume_m3} m3 admitted volume; {existing} existing source cells on this occurrence.</p>}
      <label>Dissipated power (W)<input aria-label="Body dissipated power (W)" type="number" min="0" step="any" value={watts} onChange={event => { change(); setWatts(event.target.value); }} /></label>
      {!!existing && <label><span><input type="checkbox" checked={replace} onChange={event => { change(); setReplace(event.target.checked); }} /> Replace existing cell sources on this occurrence.</span></label>}
      <label><span><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} /> I reviewed this power and uniform volume distribution.</span></label>
      <button type="button" disabled={!parameters || !reviewed} onClick={() => void apply()}>{busy ? "Assigning body power..." : "Apply body power"}</button>
    </fieldset>
    <p>Zero watts removes this body's sources after replacement review. Other bodies' sources are preserved. Both current solid solver paths accept at most 5,000 tetrahedra and 10,000 nodes; source authoring is limited to 5,000 cell entries. Transient schedules may override these base loads. Define contacts and cooling before solving.</p>
    {error && <p role="alert">{error}</p>}
  </details>;
}
