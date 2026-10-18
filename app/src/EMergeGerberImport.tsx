// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { Download, FileUp, Layers3, Plus, X } from "./icons";
import { copperName, gerberDraftFromSource, gerberSourceFromDraft, GERBER_FILE_BYTES, GERBER_TOTAL_BYTES, newGerberDraft, type EMergeGerberSource, type GerberDraft, type GerberFile } from "./emergeGerberSource";
import { usePanelPresentation } from "./panelPresentation";
import "./EMergeGerberImport.css";

type Props = { source?: EMergeGerberSource | null; runtime?: Record<string, unknown> | null; disabled?: boolean;
  onImport: (source: EMergeGerberSource) => Promise<void>; onClose: () => void };
export default function EMergeGerberImport({ source, runtime, disabled = false, onImport, onClose }: Props) {
  const { ownerDocument } = usePanelPresentation();
  const [draft, setDraft] = useState<GerberDraft>(() => source ? gerberDraftFromSource(source) : newGerberDraft());
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [reading, setReading] = useState(0);
  const generation = useRef(0), fileReads = useRef(new Map<string, number>()), dialog = useRef<HTMLElement>(null), close = useRef<HTMLButtonElement>(null);
  useEffect(() => { const previous = ownerDocument?.activeElement as HTMLElement | null; close.current?.focus(); return () => { generation.current++; if (previous?.isConnected) previous.focus(); }; }, [ownerDocument]);
  const locked = disabled || busy || reading > 0;
  const field = (key: "name" | "resolution", value: string) => setDraft(current => ({ ...current, [key]: value }));
  const read = async (file: File, key: string, apply: (file: GerberFile) => void) => {
    const currentGeneration = generation.current, revision = (fileReads.current.get(key) ?? 0) + 1;
    fileReads.current.set(key, revision); setReading(count => count + 1); setError("");
    try {
      if (file.size > GERBER_FILE_BYTES) throw new Error("Each source file is limited to 512 KiB.");
      const bytes = await file.arrayBuffer(), content = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
      if (generation.current === currentGeneration && fileReads.current.get(key) === revision) apply({ file_name: file.name, content });
    } catch (failure) { if (generation.current === currentGeneration) setError(failure instanceof Error ? failure.message : "Cannot read source file."); }
    finally { if (generation.current === currentGeneration) setReading(count => count - 1); }
  };
  const loadPackage = async (file: File) => {
    generation.current++; const revision = generation.current; fileReads.current.clear(); setReading(1); setError("");
    try {
      if (file.size > GERBER_TOTAL_BYTES + 512 * 1024) throw new Error("Source package exceeds the bounded JSON import limit.");
      const text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      const next = gerberDraftFromSource(JSON.parse(text));
      if (revision === generation.current) setDraft(next);
    } catch (failure) { if (revision === generation.current) setError(failure instanceof Error ? failure.message : "Cannot open Gerber source package."); }
    finally { if (revision === generation.current) setReading(0); }
  };
  const addLayer = () => setDraft(current => ({ ...current,
    layers: [...current.layers.slice(0, -1), { file_name: "", content: "" }, current.layers[current.layers.length - 1]],
    dielectrics: [...current.dielectrics, { thickness: "0.2", epsilon: "4.2", loss: "0" }] }));
  const removeLayer = (index: number) => { generation.current++; setReading(0); setDraft(current => ({ ...current,
    layers: current.layers.filter((_, item) => item !== index), dielectrics: current.dielectrics.filter((_, item) => item !== index),
    ports: current.ports.map(port => ({ ...port, signal: Math.min(port.signal >= index ? port.signal - 1 : port.signal, current.layers.length - 3) })) })); };
  const importStudy = async () => {
    setError(""); setBusy(true);
    try { await onImport(gerberSourceFromDraft(draft)); onClose(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Gerber import failed. Your setup is retained."); }
    finally { setBusy(false); }
  };
  const exportSource = () => {
    try { if (!ownerDocument) throw new Error("The panel document is unavailable."); const url = URL.createObjectURL(new Blob([JSON.stringify(gerberSourceFromDraft(draft), null, 2)], { type: "text/plain;charset=utf-8" })); const link = ownerDocument.createElement("a"); link.href = url; link.download = "native-gerber.spike-gerber.json"; link.click(); URL.revokeObjectURL(url); setError(""); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Complete the source setup before exporting."); }
  };
  return <div className="modal-shade"><section ref={dialog} className="emerge-gerber-manager" role="dialog" aria-modal="true" aria-labelledby="emerge-gerber-title" onKeyDown={event => {
    event.stopPropagation(); if (event.key === "Escape" && !busy) onClose();
    if (event.key === "Tab") { const items = [...(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled),select:not(:disabled),input:not(:disabled),summary,[tabindex='0']") ?? [])].filter(item => item.getClientRects().length > 0);
      const index = items.indexOf(ownerDocument?.activeElement as HTMLElement); if (event.shiftKey && index <= 0 || !event.shiftKey && index === items.length - 1) { event.preventDefault(); items[event.shiftKey ? items.length - 1 : 0]?.focus(); } }
  }}>
    <header><div><Layers3 size={22}/><h2 id="emerge-gerber-title">Native EMerge Gerber study</h2></div><button ref={close} aria-label="Close Gerber setup" title="Close setup and retain the current design" disabled={busy} onClick={onClose}><X size={18}/></button></header>
    <p>Load original copper files through EMerge's native Gerber tools. Define the physical stack and port planes explicitly; Gerber artwork supplies no verified net or pad identities.</p>
    <div className="emerge-gerber-actions"><label className="emerge-gerber-file secondary-btn" title="Restore the original files and setup from a portable Gerber source package"><FileUp size={16}/>Open source package<input aria-label="Open Gerber source package" type="file" accept=".json,.spike-gerber.json" disabled={locked} onChange={event => { const file = event.target.files?.[0]; if (file) void loadPackage(file); event.target.value = ""; }}/></label><button className="secondary-btn" onClick={exportSource} disabled={locked} title="Export original Gerber contents, materials, bounds and ports"><Download size={16}/>Export source package</button></div>
    {runtime?.gerber_available === false && <p role="status">{String(runtime.gerber_reason ?? "Native Gerber tools are unavailable in the selected solver Python. Install EMerge's gerber extra there, then check the runtime again.")}</p>}
    <fieldset disabled={locked} className="emerge-gerber-fields"><legend>Source and fabrication coordinates</legend><div className="emerge-gerber-grid">
      <label>Study name<input value={draft.name} maxLength={128} onChange={event => field("name", event.target.value)}/></label>
      <label title="Native loader contour sampling; this differs from the tetrahedral mesh size">Gerber contour resolution (mm)<input type="number" min="0.001" max="1" step="0.001" value={draft.resolution} onChange={event => field("resolution", event.target.value)}/></label>
      {(["Minimum X", "Minimum Y", "Maximum X", "Maximum Y"] as const).map((label, index) => <label key={label}>{label} (mm)<input type="number" value={draft.bounds[index]} onChange={event => setDraft(current => ({ ...current, bounds: current.bounds.map((value, item) => item === index ? event.target.value : value) as GerberDraft["bounds"] }))}/></label>)}
    </div><small>Keep the Gerber source origin. The entered rectangle defines the substrate; it is a declared model boundary, not an extracted board outline.</small></fieldset>
    <fieldset disabled={locked} className="emerge-gerber-fields"><legend>Copper and dielectric stack, top to bottom</legend>
      {draft.layers.map((layer, index) => <div key={index} className="emerge-gerber-layer"><div className="emerge-gerber-layer-title"><b>{copperName(index, draft.layers.length)}</b><span title={layer.file_name}>{layer.file_name || "Choose a copper Gerber file"}</span><label className="emerge-gerber-file secondary-btn" title="Read the original file without converting it to KiCad"><FileUp size={15}/>Choose file<input type="file" aria-label={`Gerber file for ${copperName(index, draft.layers.length)}`} accept=".gbr,.ger,.gerber,.gtl,.gbl,.g1,.g2,.g3,.g4,.g5,.g6,.pho,.art" onChange={event => { const file = event.target.files?.[0]; if (file) void read(file, `layer:${index}`, next => setDraft(current => ({ ...current, layers: current.layers.map((entry, item) => item === index ? next : entry) }))); event.target.value = ""; }}/></label>{index > 0 && index < draft.layers.length - 1 && <button className="secondary-btn" title="Remove this inner layer and its following dielectric" aria-label={`Remove ${copperName(index, draft.layers.length)}`} onClick={() => removeLayer(index)}><X size={15}/></button>}</div>
        {index < draft.dielectrics.length && <div className="emerge-gerber-grid">{([['thickness','Dielectric thickness (mm)'],['epsilon','Relative permittivity'],['loss','Loss tangent']] as const).map(([key,label]) => <label key={key}>{label}<input aria-label={`${label} below ${copperName(index, draft.layers.length)}`} type="number" step="any" value={draft.dielectrics[index][key]} onChange={event => setDraft(current => ({ ...current, dielectrics: current.dielectrics.map((gap, item) => item === index ? { ...gap, [key]: event.target.value } : gap) }))}/></label>)}</div>}
      </div>)}
      <button className="secondary-btn" disabled={draft.layers.length + draft.drills.length >= 8} onClick={addLayer} title="Insert a copper layer before the bottom layer; review the dielectric thicknesses"><Plus size={15}/>Add inner copper layer</button>
    </fieldset>
    <fieldset disabled={locked} className="emerge-gerber-fields"><legend>Explicit vertical port planes</legend><small>Each plane extends along X and Z at the entered Y, between adjacent layers. Confirm contact with the intended conductors in the native mesh before solving.</small>
      {draft.ports.map((port, index) => <div key={index} className="emerge-gerber-port"><b>P{index + 1}</b><div className="emerge-gerber-grid">{([['x','Centre X (mm)'],['y','Y (mm)'],['width','Plane width (mm)']] as const).map(([key,label]) => <label key={key}>{label}<input aria-label={`P${index + 1} ${label}`} type="number" step="any" value={port[key]} onChange={event => setDraft(current => ({ ...current, ports: current.ports.map((entry, item) => item === index ? { ...entry, [key]: event.target.value } : entry) }))}/></label>)}<label>Signal / lower return layers<select value={port.signal} onChange={event => setDraft(current => ({ ...current, ports: current.ports.map((entry, item) => item === index ? { ...entry, signal: Number(event.target.value) } : entry) }))}>{draft.layers.slice(0, -1).map((_, item) => <option key={item} value={item}>{copperName(item, draft.layers.length)} / {copperName(item + 1, draft.layers.length)}</option>)}</select></label></div>{index === 1 && <button className="secondary-btn" onClick={() => setDraft(current => ({ ...current, ports: current.ports.slice(0, 1) }))}><X size={15}/>Remove P2</button>}</div>)}
      {draft.ports.length === 1 && <button className="secondary-btn" onClick={() => setDraft(current => ({ ...current, ports: [...current.ports, { x: "15", y: "5", width: "1", signal: 0 }] }))}><Plus size={15}/>Add receive port P2</button>}
    </fieldset>
    <fieldset disabled={locked} className="emerge-gerber-fields"><legend>Excellon drill sources</legend><small>Drill sources are retained in the package. Native drill and via execution is pending; a study containing these files is blocked before meshing or solving.</small>{draft.drills.map((file, index) => <div className="emerge-gerber-layer-title" key={index}><span title={file.file_name}>{file.file_name}</span><button className="secondary-btn" aria-label={`Remove drill file ${file.file_name}`} onClick={() => setDraft(current => ({ ...current, drills: current.drills.filter((_, item) => item !== index) }))}><X size={15}/>Remove</button></div>)}<label className="emerge-gerber-file secondary-btn"><FileUp size={15}/>Add drill file<input aria-label="Add Excellon drill source" type="file" accept=".drl,.xln,.exc,.tap,.txt" disabled={draft.layers.length + draft.drills.length >= 8} onChange={event => { const file = event.target.files?.[0]; if (file) void read(file, "drill", next => setDraft(current => ({ ...current, drills: [...current.drills, next] }))); event.target.value = ""; }}/></label></fieldset>
    <p>Loading makes this source the active design. Original files and setup are retained when the project is saved. Copper geometry is reviewed through EMerge's native mesh; the initial board view shows the declared substrate extent.</p>
    {error && <p role="alert" className="emerge-gerber-error">{error}</p>}
    <footer><span aria-live="polite">{reading ? "Reading source files…" : busy ? "Preparing the Gerber source design…" : "Sources: up to eight files, 512 KiB each, 2 MiB total"}</span><button className="primary-btn" disabled={locked} onClick={() => void importStudy()} title="Load source definitions as the active design, then prepare the native EMerge mesh"><Layers3 size={16}/>Load Gerber study</button></footer>
  </section></div>;
}
