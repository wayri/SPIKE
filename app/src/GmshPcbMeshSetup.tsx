// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { runLocalWorker } from "./workerBridge";
import "./assemblyFieldStudyEditor.css";

/** Explicit normalized solids stay in the worker compiler; no viewport inference. */
export default function GmshPcbMeshSetup({ design, onParameters, disabled = false }: {
  design: Record<string, unknown>; onParameters: (parameters: Record<string, unknown> | null) => void; disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [prepared, setPrepared] = useState<Record<string, any> | null>(null);
  const generation = useRef(0);
  const publish = useRef(onParameters); publish.current = onParameters;
  const designIdentity = JSON.stringify(design);
  useEffect(() => {
    generation.current++; setPrepared(null); setError(""); publish.current(null);
    return () => { generation.current++; };
  }, [designIdentity]);
  const change = (next: string) => {
    generation.current++; setText(next); setPrepared(null); setError(""); publish.current(null);
  };
  const prepare = async () => {
    if (disabled || busy) return;
    const token = generation.current;
    setBusy(true); setError(""); setPrepared(null); publish.current(null);
    try {
      if (new TextEncoder().encode(text).length > 8 * 1024 * 1024) throw new Error("Normalized PCB request exceeds 8 MiB.");
      const request = JSON.parse(text);
      const response = await runLocalWorker({ method: "invoke_extension", params: {
        extension_id: "spike.gmsh-suite", contribution_id: "gmsh-prepare-pcb", context: { design, parameters: { request } },
      } });
      if (token !== generation.current) return;
      const data = response.result?.data as Record<string, any> | undefined;
      if (!response.ok || !data?.job) throw new Error(response.error || "No validated whole-board volume job was returned.");
      const expected = data.design_binding?.digest_sha256;
      if (typeof expected !== "string" || !/^[a-f0-9]{64}$/.test(expected)) throw new Error("Prepared volume job has no current design binding.");
      setPrepared(data);
      publish.current({ request, expected_design_sha256: expected });
    } catch (caught) {
      if (token === generation.current) setError(String(caught));
    } finally { setBusy(false); }
  };
  return <section className="assembly-field-study" aria-label="Gmsh complete PCB mesh setup">
    <h4>Gmsh complete PCB volumes</h4>
    <p>Supply the complete normalized board outline, physical stack, copper polygons, plated via spans and drill materials. The worker validates ownership and creates conforming 3D solids. Net focus changes mesh size; it does not remove unselected conductors.</p>
    <p>This input is an explicit source model, not an automatic conversion of viewport shapes. Thermal, EM and SI solvers still require their own physical properties, boundaries and translators.</p>
    <fieldset disabled={disabled || busy}><label>Complete PCB volume request JSON<textarea rows={14} spellCheck={false} value={text}
      placeholder={'{"contract":"spike/pcb-volume-mesh-request/v1","model":{},"sizing":{},"resources":{}}'}
      onChange={event => change(event.target.value)} /></label>
      <button type="button" className="spike-control--primary" disabled={!text.trim()} onClick={() => void prepare()}>Validate complete PCB solids</button>
    </fieldset>
    {busy && <p role="status">Validating geometry, source ownership and mesh budgets…</p>}
    {error && <p role="alert">{error}</p>}
    {prepared && <><p role="status">Ready to generate {prepared.job.solids.length} source solids for {String(design.design_id ?? "the current board")}. No mesh or field solution has been generated yet.</p>
      <details><summary>Whole-board source and sizing evidence</summary><pre>{JSON.stringify({ geometry: prepared.geometry_evidence, sizing: prepared.focus_plan, request_sha256: prepared.request_sha256, job_sha256: prepared.job_sha256 }, null, 2)}</pre></details></>}
    <p>Request format and an original example: <code>examples/pcb_focus_mesh/whole_board.json</code>. Missing geometry, intersecting cross-net copper and unsupported shapes remain blocked.</p>
  </section>;
}
