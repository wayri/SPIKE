import { useEffect, useRef, useState } from "react";
import { cancelLocalWorker, cancelLocalWorkerCleanup, openNativeTextFile, runLocalWorker, saveNativeTextFile } from "./workerBridge";

type Props = { onClose: () => void; onStatus: (message: string) => void };
const DEFAULT_REQUEST = { contract: "spike/gmsh-occ-mesh/v1", solids: [{ id: "fixture-cube", material_id: "development-material", priority: 0, shape: { kind: "polygon_prism", outer_mm: [[0, 0], [4, 0], [4, 3], [0, 3]], holes_mm: [], z_min_mm: 0, z_max_mm: 1 } }], mesh: { min_size_mm: 0.1, max_size_mm: 1, max_cells: 10000, max_vertices: 10000 } };
const boundedInteger = (value: unknown, minimum: number, maximum: number) => Number.isInteger(value) && Number(value) >= minimum && Number(value) <= maximum;
const MAX_RESULT_JSON_BYTES = 64 * 1024 * 1024;
const boundedJson = (value: unknown) => { const text = JSON.stringify(value, null, 2); if (new TextEncoder().encode(text).byteLength > MAX_RESULT_JSON_BYTES) throw new Error("Tetrahedral mesh JSON exceeds the 64 MiB UI exchange limit."); return text; };

export function parseTetraMeshRequest(text: string): Record<string, any> {
  if (text.length > 2_000_000) throw new Error("Tetrahedral mesh request exceeds the 2 MB editor limit.");
  const value = JSON.parse(text);
  if (!value || typeof value !== "object" || Array.isArray(value) || value.contract !== "spike/gmsh-occ-mesh/v1" || !Array.isArray(value.solids) || value.solids.length < 1 || value.solids.length > 64) throw new Error("Expected a spike/gmsh-occ-mesh/v1 request with 1–64 explicit solids.");
  const mesh = value.mesh;
  if (!mesh || typeof mesh !== "object" || !Number.isFinite(mesh.min_size_mm) || !Number.isFinite(mesh.max_size_mm) || mesh.min_size_mm < 0.000001 || mesh.max_size_mm < mesh.min_size_mm || !boundedInteger(mesh.max_cells, 4, 100000) || !boundedInteger(mesh.max_vertices, 4, 100000)) throw new Error("Mesh sizes or output budgets are invalid.");
  return value;
}

export function normalizeTetraMeshResult(value: any): Record<string, any> {
  if (!value || typeof value !== "object" || Array.isArray(value) || value.contract !== "spike/gmsh-occ-mesh-result/v1") throw new Error("Expected a spike/gmsh-occ-mesh-result/v1 result.");
  const mesh = value.mesh; const counts = mesh?.counts;
  if (!mesh || mesh.contract !== "spike/solver-mesh/v1" || !Array.isArray(mesh.vertices) || !Array.isArray(mesh.cells) || !counts || counts.vertices !== mesh.vertices.length || counts.cells !== mesh.cells.length || !boundedInteger(counts.vertices, 4, 100000) || !boundedInteger(counts.cells, 4, 100000)) throw new Error("Tetrahedral result mesh counts or bounded arrays are invalid.");
  return value;
}

export default function TetraMeshPanel({ onClose, onStatus }: Props) {
  const [text, setText] = useState(() => JSON.stringify(DEFAULT_REQUEST, null, 2)); const [result, setResult] = useState<Record<string, any> | null>(null);
  const [resultSource, setResultSource] = useState<"worker" | "import" | null>(null);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const requestId = useRef<string | null>(null);
  useEffect(() => () => { if (requestId.current) void cancelLocalWorkerCleanup(requestId.current); }, []);
  const importJson = async () => {
    try { const file = await openNativeTextFile("result"); if (!file) return; if (new TextEncoder().encode(file.contents).byteLength > MAX_RESULT_JSON_BYTES) throw new Error("Tetrahedral mesh JSON exceeds the 64 MiB UI exchange limit."); const parsed = JSON.parse(file.contents);
      if (parsed?.contract === "spike/gmsh-occ-mesh-result/v1") { setResult(normalizeTetraMeshResult(parsed)); setResultSource("import"); setError(""); onStatus(`Loaded tetrahedral mesh result ${file.fileName}; qualification claims remain untrusted imported metadata.`); }
      else { parseTetraMeshRequest(file.contents); setText(JSON.stringify(parsed, null, 2)); setResult(null); setResultSource(null); setError(""); onStatus(`Loaded tetrahedral mesh request ${file.fileName}.`); }
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
  };
  const run = async () => {
    try { const request = structuredClone(parseTetraMeshRequest(text)); setBusy(true); setError(""); setResult(null); const id = globalThis.crypto?.randomUUID?.() ?? `tetra-mesh-${Date.now()}`; requestId.current = id;
      const response = await runLocalWorker({ id, method: "generate_tetrahedral_mesh", params: { request, timeout_s: 180, memory_limit_mb: 2048 } });
      if (requestId.current !== id) return; if (!response.ok || !response.result) throw new Error(response.error ?? "Tetrahedral mesher returned no result.");
      setResult(normalizeTetraMeshResult(response.result)); setResultSource("worker"); onStatus("Generated an explicit development tetrahedral mesh; solver compatibility remains unverified until admitted by the target solver.");
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { requestId.current = null; setBusy(false); }
  };
  const counts = result?.mesh?.counts ?? {}; const metrics = result?.metrics ?? {};
  return <div className="modal-shade" role="presentation" onKeyDown={event => { if (event.key === "Escape" && !busy) onClose(); }}><section className="floating-panel tetra-mesh-panel" role="dialog" aria-modal="true" aria-labelledby="tetra-mesh-title">
    <div className="floating-heading"><div><b id="tetra-mesh-title">EXPLICIT TETRAHEDRAL MESH</b><small>Typed Gmsh OCC development tool</small></div><button autoFocus disabled={busy} onClick={onClose} aria-label="Close tetrahedral mesh tool">×</button></div>
    <p className="modal-note">Development-only first-order tetrahedra for explicit polygon prisms and analytic tubes. This tool does not translate the active PCB or switch PI/SI solvers to tetrahedra. Exported meshes must pass the target solver’s separate compatibility and admission checks.</p>
    <p className="mcad-gate">Windows execution uses the pinned local CPython 3.11 runtime. A project-local CPython 3.12 environment is not the qualified Gmsh runtime.</p>
    <label>Typed request JSON<textarea aria-label="Tetrahedral mesh request JSON" rows={18} disabled={busy} value={text} onChange={event => { setText(event.target.value); setResult(null); setResultSource(null); }} /></label>
    <div className="field-row"><button className="secondary-btn" disabled={busy} onClick={() => { setText(JSON.stringify(DEFAULT_REQUEST, null, 2)); setResult(null); setResultSource(null); setError(""); }}>Load development cube</button><button className="secondary-btn" disabled={busy} onClick={() => void importJson()}>Import request / result JSON</button><button className="secondary-btn" disabled={busy} onClick={() => { try { const request = parseTetraMeshRequest(text); void saveNativeTextFile("tetra-mesh-request.json", boundedJson(request), "result").catch(caught => setError(caught instanceof Error ? caught.message : String(caught))); } catch (caught) { setError(String(caught)); } }}>Export normalized request</button>{result && <button className="secondary-btn" disabled={busy} onClick={() => { try { void saveNativeTextFile("tetra-mesh-result.json", boundedJson(result), "result").catch(caught => setError(caught instanceof Error ? caught.message : String(caught))); } catch (caught) { setError(String(caught)); } }}>Export result</button>}</div>
    <button className={busy ? "run-btn stop" : "run-btn"} onClick={() => void (busy && requestId.current ? cancelLocalWorker(requestId.current) : run())}>{busy ? "Stop tetrahedral mesh" : "Generate tetrahedral mesh"}</button>
    {error && <p role="alert">{error}</p>}{result && <section aria-label="Tetrahedral mesh result"><p><b>{String(result.status ?? "returned").toUpperCase()}</b> · {Number(counts.vertices ?? 0).toLocaleString()} vertices · {Number(counts.cells ?? 0).toLocaleString()} tetrahedra · {Array.isArray(result.interface_faces) ? result.interface_faces.length.toLocaleString() : "unavailable"} interfaces</p><dl><dt>Scope</dt><dd>{String(result.scope ?? "unreported")}</dd><dt>Production qualified</dt><dd>{resultSource === "import" ? "Unverified imported claim" : result.production_qualified === true ? "Worker reported yes" : "No"}</dd><dt>CAD volume</dt><dd>{typeof metrics.cad_volume_mm3 === "number" ? `${metrics.cad_volume_mm3.toPrecision(7)} mm³` : "Unavailable"}</dd><dt>Minimum mean-ratio quality</dt><dd>{typeof metrics.minimum_mean_ratio_quality === "number" ? metrics.minimum_mean_ratio_quality.toPrecision(6) : "Unavailable"}</dd></dl><p className="mcad-gate">Result retention here is an export/review surface. It does not attach this mesh to board analysis or establish target-solver compatibility.</p></section>}
  </section></div>;
}
