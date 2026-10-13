// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import AssemblyFieldStudyEditor from "./AssemblyFieldStudyEditor";
import type { AssemblyIr } from "./mcadAssembly";
import { runNativeProjectWorker } from "./workerBridge";
import { runSerializedAutomaticWorker } from "./automaticWorkerQueue";

export default function RetainedVolumeEngineSetup({ projectPath, manifestDigest, engineId, disabled, onUpdated, onSave, onStatus }: {
  projectPath: string | null; manifestDigest: string | null; engineId: string; disabled: boolean;
  onUpdated: () => Promise<void>; onSave: () => void; onStatus: (value: string) => void;
}) {
  const [assembly, setAssembly] = useState<AssemblyIr | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true; setAssembly(null); setError("");
    if (!projectPath || !manifestDigest || disabled) return;
    void runSerializedAutomaticWorker(async () => {
      const response = await runNativeProjectWorker({ method: "read_assembly_thermal_mesh_setup", params: {
        project_path: projectPath, expected_manifest_payload_sha256: manifestDigest,
      } });
      if (!response.ok || !response.result) throw new Error(response.error || "Cannot read retained assembly geometry.");
      if (active) setAssembly(response.result.assembly as AssemblyIr);
    }, () => active).catch(cause => { if (active) setError(String(cause)); });
    return () => { active = false; };
  }, [projectPath, manifestDigest, disabled]);
  return <section aria-label="Retained volume engine setup">
    <p>Use retained board layers and mechanical solids with explicit materials, sources, contacts and ambient exchange. Geometry-only meshing does not establish EM or SI solver compatibility.</p>
    {(!projectPath || !manifestDigest || disabled) && <><p role="status">Save the current project before preparing a retained volume study.</p><button type="button" onClick={onSave}>Save project</button></>}
    {error && <p role="alert">{error}</p>}
    {assembly && <AssemblyFieldStudyEditor assembly={assembly} projectPath={projectPath} manifestDigest={manifestDigest} disabled={disabled}
      initialSolver={engineId === "spike.calculix-suite" ? "calculix" : "internal"} initialMesher="gmsh"
      onUpdated={onUpdated} onStatus={onStatus} />}
  </section>;
}
