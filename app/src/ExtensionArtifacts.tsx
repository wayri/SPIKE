import { useState } from "react";
import { ExtensionArtifact, saveExtensionArtifact } from "./workerBridge";

export function ExtensionArtifacts({ data }: { data: Record<string, any> }) {
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const artifacts: ExtensionArtifact[] = Array.isArray(data.artifacts) ? data.artifacts : [];
  const save = async (artifact: ExtensionArtifact) => {
    setSaving(true);
    try {
      const path = await saveExtensionArtifact(artifact);
      setStatus(path ? `Saved ${path}` : "Save cancelled");
    } catch (error) { setStatus(String(error)); }
    finally { setSaving(false); }
  };
  return <section aria-label="Engineering export artifacts">
    <p>{data.contract === "spike/mcad-export/v1" ? "Save the collaboration ZIP to keep the STEP assembly, FreeCAD document, individual BREP bodies, materials, properties and source IDs together." : "Choose an artifact to save. Its content digest is checked before the save dialog opens."}</p>
    <div>{artifacts.map(a => <button key={a.file_name} disabled={saving} onClick={() => void save(a)}>Save {a.file_name}</button>)}</div>
    <p role="status">{status}</p>
    <details><summary>Export verification and omissions</summary><pre>{JSON.stringify(data.manifest, null, 2)}</pre></details>
  </section>;
}

export function McadOptions({ text, onChange, onError }: { text: string; onChange: (value: string) => void; onError: (value: string) => void }) {
  let options: Record<string, any> = {};
  try { options = JSON.parse(text); } catch { /* The shared Run handler reports syntax errors. */ }
  return <fieldset><legend>Mechanical exchange</legend>
    <p>Preview the mechanical assembly first. Automatic board projection includes dielectric bodies; omitted components, copper and drills are listed. Load an assembly document for explicitly defined cells, components, materials and harness solids.</p>
    <label><input type="checkbox" checked={options?.allow_partial === true} onChange={e => {
      onChange(JSON.stringify({ ...options, allow_partial: e.target.checked }, null, 2));
    }} /> Allow export with the omissions listed in the preview</label>
    <label>Load assembly JSON <input type="file" accept=".json" onChange={async e => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        if (file.size > 64 * 1024 * 1024) throw new Error("Assembly document exceeds 64 MiB.");
        const assembly = JSON.parse(await file.text());
        if (assembly.contract !== "spike/mcad-assembly/v1") throw new Error("Select a SPIKE mechanical assembly v1 document.");
        onChange(JSON.stringify({ assembly }, null, 2)); onError("");
      } catch (error) { onError(String(error)); }
    }} /></label>
  </fieldset>;
}
