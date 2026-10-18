// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import type { ParsedBoard } from "./boardParser";
import { FileDown, FileUp, Play, Plus, RotateCcw, Trash2, X } from "./icons";
import PlotlyChart from "./PlotlyChart";
import { openNativeTextFile, runLocalWorker, saveNativeTextFile } from "./workerBridge";
import "./SheetFoldingPanel.css";

export type SheetBend = {
  id: string; start_x_mm: number; angle_deg: number; inside_radius_mm: number;
  k_factor: number; fixed_side: "negative_x"; segments: number;
};
export type SheetDefinition = {
  contract: "spike/sheet-folding/v1";
  id: string;
  kind: "sheet" | "sheet_metal" | "flex_pcb" | "rigid_flex_pcb";
  sheet: { length_mm: number; width_mm: number; thickness_mm: number; material: unknown };
  bends: SheetBend[];
  flex_regions: { id: string; start_x_mm: number; end_x_mm: number }[];
};
type SheetDraft = Omit<SheetDefinition, "sheet"> & { sheet: Omit<SheetDefinition["sheet"], "thickness_mm"> & { thickness_mm: number | null }; import_status?: "requires_thickness" };
type PreviewMesh = {
  vertices: { id: string; position_mm: [number, number, number] }[];
  triangles: { id: string; vertex_ids: [string, string, string] }[];
};
export type SheetFoldPreview = {
  contract: "spike/sheet-folding-preview/v1";
  source_contract: string; source_id: string; fraction: number;
  model_status: "analytical_geometry_preview"; flat_mesh: PreviewMesh; folded_mesh: PreviewMesh;
  bends: unknown[]; limitations: string[];
};
export type SheetFoldingPanelProps = {
  board: ParsedBoard | null;
  onStatus: (message: string) => void;
  onClose?: () => void;
};

const DEFAULT_SHEET: SheetDefinition = {
  contract: "spike/sheet-folding/v1", id: "rectangular-sheet", kind: "sheet_metal",
  sheet: { length_mm: 100, width_mm: 60, thickness_mm: 1, material: null },
  bends: [{ id: "bend-1", start_x_mm: 50, angle_deg: 90, inside_radius_mm: 2, k_factor: 0.4, fixed_side: "negative_x", segments: 12 }],
  flex_regions: [],
};
const jsonText = (value: unknown) => JSON.stringify(value, null, 2);
const finitePositive = (value: unknown) => Number.isFinite(value) && Number(value) > 0;

export function parseSheetDefinition(text: string): SheetDefinition {
  if (new TextEncoder().encode(text).byteLength > 2_000_000) throw new Error("Sheet definition exceeds the 2 MB editor limit.");
  const value = JSON.parse(text) as Partial<SheetDefinition>;
  if (!value || value.contract !== "spike/sheet-folding/v1" || typeof value.id !== "string" || !value.id.trim()) throw new Error("Expected a spike/sheet-folding/v1 definition with a non-empty id.");
  if (!(["sheet", "sheet_metal", "flex_pcb", "rigid_flex_pcb"] as unknown[]).includes(value.kind)) throw new Error("Choose a general sheet, sheet metal, flex PCB or rigid-flex PCB.");
  if (!value.sheet || !finitePositive(value.sheet.length_mm) || !finitePositive(value.sheet.width_mm) || !finitePositive(value.sheet.thickness_mm)) throw new Error("Sheet length, width, and thickness must be positive millimetre values.");
  if (!Array.isArray(value.bends) || value.bends.length > 64) throw new Error("Sheet definition must contain at most 64 bends.");
  value.bends.forEach((bend, index) => {
    if (!bend || typeof bend.id !== "string" || !bend.id.trim() || !Number.isFinite(bend.start_x_mm) || !Number.isFinite(bend.angle_deg) || bend.angle_deg === 0 || !finitePositive(bend.inside_radius_mm) || !Number.isFinite(bend.k_factor) || bend.k_factor < 0 || bend.k_factor > 1 || !Number.isInteger(bend.segments) || bend.segments < 1 || bend.segments > 128 || bend.fixed_side !== "negative_x") throw new Error(`Bend ${index + 1} has invalid position, angle, radius, k-factor, segments, or fixed side.`);
  });
  if (!Array.isArray(value.flex_regions)) throw new Error("Sheet definition flex_regions must be an array.");
  value.flex_regions.forEach((region, index) => { if (!region || typeof region.id !== "string" || !region.id.trim() || !Number.isFinite(region.start_x_mm) || !Number.isFinite(region.end_x_mm) || region.end_x_mm <= region.start_x_mm) throw new Error(`Flex region ${index + 1} requires an id and increasing start/end positions.`); });
  if ((value.kind === "flex_pcb" || value.kind === "rigid_flex_pcb") && value.flex_regions.length === 0) throw new Error("Flex and rigid-flex sheets require at least one explicit flex region.");
  return value as SheetDefinition;
}

export function editableSheetDraft(value: unknown): SheetDraft | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const draft = value as Partial<SheetDraft>;
  const rowsSafe = (rows: unknown) => Array.isArray(rows) && rows.every(row => row && typeof row === "object" && !Array.isArray(row) && typeof row.id === "string");
  return draft.contract === "spike/sheet-folding/v1" && typeof draft.id === "string" && draft.sheet !== null && typeof draft.sheet === "object" && rowsSafe(draft.bends) && rowsSafe(draft.flex_regions) ? draft as SheetDraft : null;
}

export function previewMeshTrace(mesh: PreviewMesh): Record<string, unknown> {
  const index = new Map(mesh.vertices.map((vertex, item) => [vertex.id, item]));
  const admitted = mesh.triangles.map(triangle => triangle.vertex_ids.map(id => index.get(id))).filter((face): face is [number, number, number] => face.length === 3 && face.every(item => item !== undefined));
  if (!mesh.vertices.length || !admitted.length) throw new Error("Fold preview contains no displayable triangle mesh.");
  return { type: "mesh3d", x: mesh.vertices.map(item => item.position_mm[0]), y: mesh.vertices.map(item => item.position_mm[1]), z: mesh.vertices.map(item => item.position_mm[2]), i: admitted.map(item => item[0]), j: admitted.map(item => item[1]), k: admitted.map(item => item[2]), color: "#65b7bd", flatshading: true, opacity: 0.92, hovertemplate: "X %{x:.5g} mm<br>Y %{y:.5g} mm<br>Z %{z:.5g} mm<extra>Geometry preview</extra>" };
}

export default function SheetFoldingPanel({ board, onStatus, onClose }: SheetFoldingPanelProps) {
  const [text, setText] = useState(() => jsonText(DEFAULT_SHEET));
  const [sourceName, setSourceName] = useState("Built-in rectangular example");
  const [fraction, setFraction] = useState(1);
  const [preview, setPreview] = useState<SheetFoldPreview | null>(null);
  const [busy, setBusy] = useState<"import" | "preview" | "export" | null>(null);
  const [error, setError] = useState("");
  const parsed = useMemo(() => { try { return parseSheetDefinition(text); } catch { return null; } }, [text]);
  const draft = useMemo(() => { try { return editableSheetDraft(JSON.parse(text)); } catch { return null; } }, [text]);
  const plotData = useMemo(() => { if (!preview) return []; try { return [previewMeshTrace(preview.folded_mesh)]; } catch { return []; } }, [preview]);
  const replaceSheet = (sheet: SheetDefinition, source: string) => { setText(jsonText(sheet)); setSourceName(source); setPreview(null); setError(""); };
  const patchDraft = (edit: (sheet: SheetDraft) => void) => { if (!draft) return; const next = structuredClone(draft); edit(next); setText(jsonText(next)); setPreview(null); setError(""); };
  const importSource = async () => {
    try { setBusy("import"); setError(""); const file = await openNativeTextFile("sheet"); if (!file) return;
      const sourceFormat = file.fileName.toLowerCase().endsWith(".dxf") ? "dxf" : "json";
      const response = await runLocalWorker({ method: "import_sheet_definition", params: { contents: file.contents, source_format: sourceFormat } });
      if (!response.ok || !response.result?.sheet) throw new Error(response.error ?? "Sheet import returned no normalized definition.");
      const sheet = response.result.sheet as unknown as SheetDraft; if (!sheet || sheet.contract !== "spike/sheet-folding/v1") throw new Error("Sheet import returned an unsupported definition contract.");
      const material = sheet.sheet?.material;
      const assumedUnits = material && typeof material === "object" && "units_assumption_requires_review" in material && material.units_assumption_requires_review === true;
      setText(jsonText(sheet)); setSourceName(`${file.fileName} (${sourceFormat.toUpperCase()}, source read only${assumedUnits ? "; unitless coordinates interpreted as mm - review dimensions" : ""})`); setPreview(null);
      if (sheet.sheet?.thickness_mm === null) setError("DXF does not define sheet thickness. Enter a positive thickness in millimetres before previewing or exporting.");
      onStatus(`Imported ${file.fileName} as a neutral sheet definition. The source file was not changed.`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { setBusy(null); }
  };
  const requestPreview = async () => {
    try { const sheet = parseSheetDefinition(text); setBusy("preview"); setError(""); setPreview(null);
      const response = await runLocalWorker({ method: "preview_sheet_fold", params: { sheet, fraction } });
      if (!response.ok || !response.result?.preview) throw new Error(response.error ?? "Sheet folding preview returned no geometry.");
      const candidate = response.result.preview as unknown as SheetFoldPreview;
      if (candidate.contract !== "spike/sheet-folding-preview/v1" || candidate.model_status !== "analytical_geometry_preview") throw new Error("Worker returned an unsupported sheet folding preview contract.");
      previewMeshTrace(candidate.folded_mesh); setPreview(candidate); onStatus(`Generated an analytical geometry preview at ${Math.round(fraction * 100)}% of the defined bend angles.`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { setBusy(null); }
  };
  const exportDefinition = async () => {
    try { const sheet = parseSheetDefinition(text); setBusy("export"); setError(""); const path = await saveNativeTextFile(`${sheet.id}.spike-sheet.json`, jsonText(sheet), "result"); if (path) onStatus(`Saved ${sheet.id}.spike-sheet.json.`); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { setBusy(null); }
  };
  return <section className="sheet-folding-panel" aria-labelledby="sheet-folding-title">
    <header><div><h2 id="sheet-folding-title">Sheet folding preview</h2><small>Bounded rectangular panels and parallel finite-radius bends</small></div>{onClose && <button type="button" className="secondary-btn" onClick={onClose} disabled={busy !== null} aria-label="Close sheet folding preview"><X size={14}/>Close</button>}</header>
    <p className="sheet-folding-boundary">This is an analytical geometry preview in millimetres. It does not calculate strain, springback, collision, manufacturability, or solver-ready deformed PCB physics.</p>
    <div className="sheet-folding-toolbar"><button type="button" className="secondary-btn" disabled={busy !== null} onClick={() => void importSource()}><FileDown size={14}/>Import JSON or DXF</button><button type="button" className="secondary-btn" disabled={busy !== null} onClick={() => replaceSheet(structuredClone(DEFAULT_SHEET), "Built-in rectangular example")}><RotateCcw size={14}/>Load example</button><button type="button" className="secondary-btn" disabled={busy !== null || !parsed} onClick={() => void exportDefinition()}><FileUp size={14}/>Export definition</button><span title={sourceName}>{sourceName}</span></div>
    <div className="sheet-folding-layout"><div className="sheet-folding-editor">
      {draft && <section aria-label="Common sheet fields"><div className="sheet-folding-fields"><label>Kind<select value={draft.kind} disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.kind = event.target.value as SheetDefinition["kind"]; })}><option value="sheet">General sheet (nonmetal)</option><option value="sheet_metal">Sheet metal</option><option value="flex_pcb">Flex PCB</option><option value="rigid_flex_pcb">Rigid-flex PCB</option></select></label><label>Length (mm)<input type="number" min="0.000001" step="any" value={draft.sheet.length_mm} disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.sheet.length_mm = Number(event.target.value); })}/></label><label>Width (mm)<input type="number" min="0.000001" step="any" value={draft.sheet.width_mm} disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.sheet.width_mm = Number(event.target.value); })}/></label><label>Thickness (mm)<input type="number" min="0.000001" step="any" value={draft.sheet.thickness_mm ?? ""} placeholder="Required for DXF" disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.sheet.thickness_mm = event.target.value === "" ? null : Number(event.target.value); if (sheet.sheet.thickness_mm !== null && sheet.sheet.thickness_mm > 0) delete sheet.import_status; })} /></label></div>
      <div className="sheet-folding-section-heading"><h3>Bends</h3><button type="button" className="secondary-btn" disabled={busy !== null || draft.bends.length >= 64} onClick={() => patchDraft(sheet => { sheet.bends.push({ id: `bend-${crypto.randomUUID()}`, start_x_mm: sheet.sheet.length_mm / 2, angle_deg: 90, inside_radius_mm: 1, k_factor: 0.4, fixed_side: "negative_x", segments: 12 }); })}><Plus size={14}/>Add bend</button></div>
      {draft.bends.map((bend, index) => <fieldset key={`${bend.id}:${index}`}><legend>Bend {index + 1}: {bend.id}</legend><div className="sheet-folding-fields"><label>Start X (mm)<input aria-label={`Bend ${index + 1} start position`} type="number" step="any" value={bend.start_x_mm} disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.bends[index].start_x_mm = Number(event.target.value); })}/></label><label>Angle (deg)<input aria-label={`Bend ${index + 1} angle`} type="number" step="any" value={bend.angle_deg} disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.bends[index].angle_deg = Number(event.target.value); })} /></label><label>Inside radius (mm)<input aria-label={`Bend ${index + 1} inside radius`} type="number" min="0.000001" step="any" value={bend.inside_radius_mm} disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.bends[index].inside_radius_mm = Number(event.target.value); })} /></label><label>K-factor<input aria-label={`Bend ${index + 1} k-factor`} type="number" min="0" max="1" step="any" value={bend.k_factor} disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.bends[index].k_factor = Number(event.target.value); })} /></label><label>Arc segments<input aria-label={`Bend ${index + 1} segments`} type="number" min="1" max="128" step="1" value={bend.segments} disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.bends[index].segments = Number(event.target.value); })}/></label><button type="button" className="secondary-btn sheet-folding-remove" disabled={busy !== null} onClick={() => patchDraft(sheet => { sheet.bends.splice(index, 1); })}><Trash2 size={14}/>Remove bend</button></div></fieldset>)}
      <div className="sheet-folding-section-heading"><h3>Flex regions</h3><button type="button" className="secondary-btn" disabled={busy !== null} onClick={() => patchDraft(sheet => { sheet.flex_regions.push({ id: `flex-${sheet.flex_regions.length + 1}`, start_x_mm: 0, end_x_mm: sheet.sheet.length_mm }); })}><Plus size={14}/>Add flex region</button></div>
      {draft.flex_regions.map((region, index) => <fieldset key={`${region.id}:${index}`}><legend>Flex region {index + 1}: {region.id}</legend><div className="sheet-folding-fields"><label>Start X (mm)<input aria-label={`Flex region ${index + 1} start`} type="number" step="any" value={region.start_x_mm} disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.flex_regions[index].start_x_mm = Number(event.target.value); })}/></label><label>End X (mm)<input aria-label={`Flex region ${index + 1} end`} type="number" step="any" value={region.end_x_mm} disabled={busy !== null} onChange={event => patchDraft(sheet => { sheet.flex_regions[index].end_x_mm = Number(event.target.value); })}/></label><button type="button" className="secondary-btn sheet-folding-remove" disabled={busy !== null} onClick={() => patchDraft(sheet => { sheet.flex_regions.splice(index, 1); })}><Trash2 size={14}/>Remove region</button></div></fieldset>)}</section>}
      <label>Neutral sheet definition JSON<textarea aria-label="Neutral sheet definition JSON" rows={18} value={text} disabled={busy !== null} spellCheck={false} onChange={event => { setText(event.target.value); setPreview(null); setError(""); }} /></label>
    </div><div className="sheet-folding-preview"><label>Fold fraction: {Math.round(fraction * 100)}%<input aria-label="Fold fraction" type="range" min="0" max="1" step="0.01" value={fraction} disabled={busy !== null} onChange={event => { setFraction(Number(event.target.value)); setPreview(null); }} /></label>
      <button type="button" className="run-btn" disabled={busy !== null || !parsed} onClick={() => void requestPreview()}><Play size={14}/>{busy === "preview" ? "Generating preview…" : "Preview fold"}</button>
      {plotData.length ? <><div className="sheet-folding-plot"><PlotlyChart title="Returned folded sheet triangle mesh" data={plotData} revision={`${preview?.source_id}:${preview?.fraction}`} layout={{ margin: { l: 0, r: 0, t: 15, b: 0 }, scene: { aspectmode: "data", xaxis: { title: "X (mm)" }, yaxis: { title: "Y (mm)" }, zaxis: { title: "Z (mm)" } } }} /></div><p><b>Model status:</b> analytical geometry preview · {preview?.folded_mesh.triangles.length} returned triangles</p>{preview?.limitations?.length ? <ul aria-label="Fold preview limitations">{preview.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul> : null}</> : <p className="sheet-folding-empty">Choose a fold fraction, then request a preview. Changing a field clears stale geometry and does not write any file.</p>}
      {board && <p className="sheet-folding-board">Loaded PCB context: {Number(board.width).toPrecision(5)} × {Number(board.height).toPrecision(5)} mm. This definition is not mapped to board regions automatically.</p>}
    </div></div>{error && <p className="sheet-folding-error" role="alert">{error}</p>}
  </section>;
}
