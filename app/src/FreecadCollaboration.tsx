import { useEffect, useState } from "react";
import { openNativeTextFile, saveNativeTextFile, runNativeProjectWorker } from "./workerBridge";

type Props = {
  projectPath: string | null;
  manifestDigest: string | null;
  disabled: boolean;
  onUpdated: () => Promise<void>;
  onStatus: (message: string) => void;
};
type Change = { id: string; before_name: string; after_name: string; before_transform: number[]; after_transform: number[]; moved: boolean };
type Measurement = { object_a_id: string; object_b_id: string; distance_mm: number; overlap_volume_mm3: number };
type Preview = { changes: Change[]; measurements: Measurement[]; warnings: string[]; feedback_sha256: string; already_applied: boolean };
const xyz = (m: number[]) => [m[3], m[7], m[11]].map(n => n.toFixed(3)).join(", ");

export default function FreecadCollaboration({ projectPath, manifestDigest, disabled, onUpdated, onStatus }: Props) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Record<string, unknown> | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [diagnostics, setDiagnostics] = useState<string[]>([]);
  useEffect(() => { setFeedback(null); setPreview(null); setDiagnostics([]); }, [projectPath, manifestDigest]);
  const unavailable = disabled || busy || !projectPath || !manifestDigest;
  const request = async (method: string, extras: Record<string, unknown> = {}) => {
    const response = await runNativeProjectWorker({ method, params: {
      project_path: projectPath, expected_manifest_payload_sha256: manifestDigest, ...extras,
    } });
    if (!response.ok || !response.result) throw new Error(response.error || "FreeCAD collaboration failed.");
    return response.result;
  };
  const exportSession = async () => {
    setBusy(true);
    try {
      const session = await request("export_mcad_session");
      setDiagnostics(session.diagnostics as string[]);
      const path = await saveNativeTextFile("assembly-freecad-session.json", JSON.stringify(session, null, 2), "result");
      if (path) onStatus("Session saved. In the SPIKE FreeCAD workbench, choose Open SPIKE Collaboration Session. Review the geometry omissions shown here.");
    } catch (error) { onStatus(String(error)); }
    finally { setBusy(false); }
  };
  const review = async () => {
    setBusy(true); setPreview(null); setFeedback(null);
    try {
      const file = await openNativeTextFile("result");
      if (!file) return;
      const result = await request("preview_mcad_feedback", { feedback_json: file.contents });
      setFeedback(result.feedback as Record<string, unknown>); setPreview(result as unknown as Preview);
      onStatus("FreeCAD feedback checked against the saved assembly. Review names, translations, rotations and measurements before applying.");
    } catch (error) { onStatus(String(error)); }
    finally { setBusy(false); }
  };
  const apply = async () => {
    if (!feedback || !preview) return;
    setBusy(true);
    try {
      const result = await request("apply_mcad_feedback", { feedback, reviewed_feedback_sha256: preview.feedback_sha256 });
      setFeedback(null); setPreview(null);
      await onUpdated();
      onStatus(result.no_op ? "Feedback contains no new placement changes." : "FreeCAD feedback applied. Earlier result contexts are archived in the project; review harness routes, contacts and meshes before analysis.");
    } catch (error) { onStatus(String(error)); }
    finally { setBusy(false); }
  };
  return <section className="mcad-semantics-editor">
    <h4>FreeCAD collaboration</h4>
    <p>Arrange board and STEP part occurrences in FreeCAD, then review their placements here. Board solids omit components, copper and drills; unsupported geometry is represented by an origin. Save assembly edits before exchanging a session.</p>
    <div className="field-row">
      <button className="secondary-btn" disabled={unavailable} onClick={() => void exportSession()}>Export FreeCAD session</button>
      <button className="secondary-btn" disabled={unavailable} onClick={() => void review()}>Review FreeCAD feedback</button>
    </div>
    {diagnostics.length > 0 && <details open><summary>Export geometry and limitations</summary><ul>{diagnostics.map((item, i) => <li key={i}>{item}</li>)}</ul></details>}
    {preview && <div>
      <p>{preview.already_applied ? "This feedback has already been applied." : `${preview.changes.length} changed occurrences.`}</p>
      {preview.changes.length > 0 && <table className="data-table"><thead><tr><th>Occurrence</th><th>Name</th><th>XYZ before → after (mm)</th><th>Rigid transform</th></tr></thead><tbody>
        {preview.changes.map(row => <tr key={row.id}><td>{row.id}</td><td>{row.before_name} → {row.after_name}</td><td>{xyz(row.before_transform)} → {xyz(row.after_transform)}</td><td><details><summary>{row.moved ? "Placement changed" : "Name only"}</summary><p>Before: {JSON.stringify(row.before_transform)}</p><p>After: {JSON.stringify(row.after_transform)}</p></details></td></tr>)}
      </tbody></table>}
      {preview.measurements.length > 0 && <table className="data-table"><thead><tr><th>Pair</th><th>Separation (mm)</th><th>Overlap (mm³)</th></tr></thead><tbody>
        {preview.measurements.map((row, i) => <tr key={i}><td>{row.object_a_id} / {row.object_b_id}</td><td>{row.distance_mm.toPrecision(6)}</td><td>{row.overlap_volume_mm3.toPrecision(6)}</td></tr>)}
      </tbody></table>}
      <ul>{preview.warnings.map(w => <li key={w}>{w}</li>)}</ul>
      <button className="run-btn" disabled={unavailable || preview.changes.length === 0} onClick={() => void apply()}>Apply reviewed placements</button>
    </div>}
  </section>;
}
