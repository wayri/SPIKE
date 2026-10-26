// SPDX-License-Identifier: Apache-2.0
// Controls only; BoardViewport owns the shared scene and camera.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Box, Eye, EyeOff, Upload, Download, Play, Pause, X, ArrowLeft, ArrowRight, SkipForward, RotateCcw } from "./icons";
import { fieldInspectionPresets, fieldSampleInspection, fieldSavedRange, fieldSavedSpeedRange, fieldColorRange, type FieldViewOptions } from "./fieldVolumeModel";
import { admitFieldPresentation, fieldPresentationEnvelope } from "./fieldCompositePresentation";
import { fieldStreamAvailability } from "./fieldStreamPresentation";
import { createPlaybackTimeline } from "./transientPlayback";
import type { MainFieldView } from "./mainFieldViewport";
import "./buttonStandard.css";
import "./MainFieldControls.css";
export type ViewportResultLayer = {id:string;label:string;available:boolean;visible:boolean;onVisible:(value:boolean)=>void;opacity?:number;onOpacity?:(value:number)=>void;onManage?:()=>void};
type Props = {managedPlayback?: boolean; layers?:ViewportResultLayer[];resultPicker?:ReactNode;onManageAll?:()=>void; view: MainFieldView | null; open: boolean; onOpen: (open: boolean) => void; onPresent: (data: unknown) => void; onOptions: (patch: Partial<FieldViewOptions>) => void; onVisible: (value: boolean) => void; onClear: () => void };
export default function MainFieldControls({ managedPlayback = false, view, open, onOpen, onPresent, onOptions, onVisible, onClear, layers=[], resultPicker, onManageAll }: Props) {
  const trigger = useRef<HTMLButtonElement>(null), panel = useRef<HTMLElement>(null), input = useRef<HTMLInputElement>(null);
  const [position, setPosition] = useState({ top: 70, left: 12 }), [error, setError] = useState("");
  const [playing, setPlaying] = useState(false), [speed, setSpeed] = useState(1), [loop, setLoop] = useState(false);
  const [preview,setPreview]=useState(false);
  const [rangeDraft, setRangeDraft] = useState<[string, string]>(["", ""]), [rangeError, setRangeError] = useState("");
  const previewRef=useRef(preview),leaveTimer=useRef<ReturnType<typeof setTimeout>|null>(null);previewRef.current=preview;
  const cancelLeave=()=>{if(leaveTimer.current!==null)clearTimeout(leaveTimer.current);leaveTimer.current=null;};
  const leave=()=>{cancelLeave();if(previewRef.current)leaveTimer.current=setTimeout(()=>{if(previewRef.current)onOpen(false);},120);};
  useEffect(()=>()=>cancelLeave(),[]);
  useEffect(()=>{if(!open)setPreview(false);},[open]);
  const source = view?.data, settings = view?.options;
  const frame = Math.min(settings?.frame ?? 0, Math.max(0, (source?.frames.length ?? 1) - 1));
  const times = useMemo(() => source?.frames.map(f => f.timeS) ?? [], [source]);
  const timeline = useMemo(() => { try { return createPlaybackTimeline(times); } catch { return null; } }, [times]);
  const available = useMemo(() => source ? fieldStreamAvailability(source, frame) : { supplied: false, grid: false }, [source, frame]);
  const streamMode = settings?.mode === "streamlines" || settings?.mode === "streamtubes", generated = settings?.mode === "streamtubes" && !available.supplied;
  const quantity = source?.quantities.find(q => q.id === settings?.quantity) ?? source?.quantities[0];
  const savedRange = useMemo(() => source && settings ? fieldSavedRange(source, settings) : null, [source, settings?.quantity, settings?.celsius]);
  const savedSpeedRange = useMemo(() => source ? fieldSavedSpeedRange(source) : null, [source]);
  const inspection = useMemo(() => source && settings ? fieldSampleInspection(source, settings) : null, [source, settings?.quantity, settings?.celsius, frame, settings?.sampleIndex]);
  const presets = useMemo(() => source ? fieldInspectionPresets(source, frame) : [], [source, frame]);
  const secondaryRange = useMemo(() => view?.secondary ? fieldColorRange(view.secondary.options.colorRange, ...fieldSavedRange(view.secondary.data, view.secondary.options)) : null, [view?.secondary]);
  useEffect(() => { const endpoints = settings?.colorRange ?? savedRange; setRangeDraft(endpoints ? [String(endpoints[0]), String(endpoints[1])] : ["", ""]); setRangeError(""); }, [savedRange, settings?.colorRange]);
  const applyRange = () => {
    const values = rangeDraft.map(value => value.trim() === "" ? NaN : Number(value));
    if (!values.every(Number.isFinite) || values[0] >= values[1]) { setRangeError("Enter finite endpoints with minimum below maximum."); return; }
    setRangeError(""); onOptions({ colorRange: [values[0], values[1]] });
  };
  useEffect(() => { setPlaying(false); }, [source]);
  useEffect(() => { if (!view?.visible) setPlaying(false); }, [view?.visible]);
  useEffect(() => {
    if (!playing || !view?.visible || !timeline) return;
    let start = performance.now(), first = frame, request = 0;
    const tick = (now: number) => { const next = timeline.frameAtElapsed(first, now - start, speed); onOptions({ frame: next.frameIndex });
      if (next.ended && !loop) setPlaying(false); else { if (next.ended) { start = now; first = 0; onOptions({ frame: 0 }); } request = requestAnimationFrame(tick); } };
    request = requestAnimationFrame(tick); return () => cancelAnimationFrame(request);
  }, [playing, speed, loop, timeline, view?.visible, onOptions]);
  useEffect(() => {
    if (!open) return;
    const place = () => { const rect = trigger.current?.getBoundingClientRect(); if (rect) setPosition({ top: Math.min(rect.bottom + 6, window.innerHeight - 140), left: Math.max(8, Math.min(rect.right - 340, window.innerWidth - 348)) }); }; place();
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { onOpen(false); trigger.current?.focus(); } };
    const outside = (e: PointerEvent) => { if (!(e.target instanceof Element && e.target.closest(".select-search")) && !panel.current?.contains(e.target as Node) && !trigger.current?.contains(e.target as Node)) onOpen(false); };
    window.addEventListener("resize", place); document.addEventListener("keydown", key); document.addEventListener("pointerdown", outside);
    return () => { window.removeEventListener("resize", place); document.removeEventListener("keydown", key); document.removeEventListener("pointerdown", outside); };
  }, [open, onOpen]);
  const step = (next: number) => { setPlaying(false); onOptions({ frame: Math.max(0, Math.min(times.length - 1, next)) }); };
  const download = () => { if (!view) return; const url = URL.createObjectURL(new Blob([JSON.stringify(fieldPresentationEnvelope(view))], { type: "application/json" })); const a = document.createElement("a"); a.href = url; a.download = view.secondary ? "spike-field-composite.json" : "spike-field-volume.json"; a.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); };
  const select = (label: string, value: string | number, values: [string | number, string, boolean?][], change: (value: string) => void, disabled = false) => <label>{label}<select aria-label={label} value={value} disabled={disabled} onChange={e => change(e.target.value)}>{values.map(([id, text, off]) => <option key={id} value={id} disabled={off}>{text}</option>)}</select></label>;
  const range = (label: string, value: number, min: number, max: number, step: number, change: (value: number) => void, disabled = false) => <label>{label}<input type="range" aria-label={label} min={min} max={max} step={step} value={value} disabled={disabled} onChange={e => change(Number(e.target.value))} /></label>;
  return <div className="main-field-tools" role="group" aria-label="Main viewport field tools" onPointerDown={e => e.stopPropagation()}>
    <button ref={trigger} type="button" className="main-field-trigger" aria-label="Result layers and fields" title="Result layers and fields" aria-expanded={open} onMouseEnter={()=>{cancelLeave();if(!open){setPreview(true);onOpen(true);}}} onMouseLeave={leave} onClick={()=>{cancelLeave();setPreview(false);onOpen(preview||!open);}}><Box size={15} /><span>Fields</span></button>
    {source && <>{timeline && !managedPlayback && <><button type="button" aria-label={playing ? "Pause field playback" : "Play field playback"} onClick={() => { if (!playing && frame === times.length - 1) onOptions({ frame: 0 }); onVisible(true); setPlaying(!playing); }}>{playing ? <Pause size={14} /> : <Play size={14} />}</button><input className="main-field-scrubber" type="range" aria-label="Field playback frame" min="0" max={times.length - 1} value={frame} onChange={e => step(Number(e.target.value))} /><small>{times[frame].toPrecision(4)} s</small></>}<button type="button" aria-label={view!.visible ? "Hide field layer" : "Show field layer"} title={view!.visible ? "Hide field layer" : "Show field layer"} onClick={() => onVisible(!view!.visible)}>{view!.visible ? <EyeOff size={14} /> : <Eye size={14} />}</button></>}
    <input ref={input} hidden type="file" accept=".json" aria-label="Field visualization JSON file" onChange={async e => { const file = e.target.files?.[0]; e.target.value = ""; if (!file) return; try { if (file.size > 64 * 1024 * 1024) throw new Error("Field import is limited to 64 MiB."); onPresent(admitFieldPresentation(JSON.parse(await file.text()))); setError(""); } catch (reason) { setError(`Import rejected; previous field retained: ${reason instanceof Error ? reason.message : String(reason)}`); } }} />
    {open && createPortal(<section ref={panel} className="main-field-popover" style={position} role="dialog" aria-label="Field display settings" onPointerEnter={cancelLeave} onPointerLeave={leave} onPointerDown={e => {setPreview(false);cancelLeave();e.stopPropagation();}}>
      <header><strong>Result layers and fields</strong><div><button type="button" title="Import field JSON" aria-label="Import field" onClick={() => input.current?.click()}><Upload size={14} /></button><button type="button" title="Export field JSON" aria-label="Export field" disabled={!source} onClick={download}><Download size={14} /></button><button type="button" aria-label="Close field controls" onClick={() => { onOpen(false); trigger.current?.focus(); }}><X size={14} /></button></div></header>
      <section className="main-field-layers" aria-label="Result layer visibility">{resultPicker}{layers.map(layer=><div className="main-field-layer" key={layer.id}><label><input type="checkbox" aria-label={`Show ${layer.label}`} disabled={!layer.available} checked={layer.available&&layer.visible} onChange={event=>layer.onVisible(event.target.checked)}/><span>{layer.label}</span>{!layer.available&&<small>No data</small>}</label>{layer.onManage&&<button type="button" disabled={!layer.available} aria-label={`Manage ${layer.label}`} onClick={layer.onManage}>Manage</button>}{layer.onOpacity&&<label className="main-field-layer-opacity">Opacity<input type="range" aria-label={`${layer.label} opacity`} min="0" max="1" step="0.01" disabled={!layer.available} value={layer.opacity??1} onChange={event=>layer.onOpacity?.(Number(event.target.value))}/><output>{Math.round((layer.opacity??1)*100)}%</output></label>}</div>)}{onManageAll&&<button type="button" className="main-field-manager" onClick={onManageAll}>Manage analysis results</button>}</section>
      {error && <p role="alert">{error}</p>}{!source && <p>Import a field dataset, or choose Show fields in main viewport in a CFD result. Fields share the board scene and camera.</p>}
      {source && settings && <><p className="main-field-name" title={source.label}>{source.label}</p>
      {view.secondary && secondaryRange && <section className="main-field-inspection" aria-label="Independent solid field legend"><strong>{view.secondary.data.label}</strong><p>Independent solid field: {view.secondary.data.quantities.find(q => q.id === view.secondary!.options.quantity)?.label}. {view.secondary.options.colorRange ? "User range" : "Fixed saved range"} {secondaryRange.map(value => value.toPrecision(6)).join(" – ")} {fieldSampleInspection(view.secondary.data, view.secondary.options).unit}.</p><small>Primary controls below inspect {source.label}. Solid samples retain their own values, coordinates and scale.</small></section>}
      <section className="main-field-presets" aria-label="Field inspection presets">{presets.map(preset => <button type="button" key={preset.id} disabled={!preset.available} title={preset.reason || preset.label} onClick={() => onOptions(preset.patch)}>{preset.label}</button>)}{!available.supplied && <small>No saved curves in this frame; field lines require supplied curves. Generated flow requires a supported complete fluid grid and velocity vectors.</small>}</section>
      <div className="main-field-grid">
        {select("Volume quantity", quantity!.id, source.quantities.map(q => [q.id, `${q.label} (${q.unit})`]), value => onOptions({ quantity: value, colorRange: undefined }), generated)}
        {select("Volume display", settings.mode, [["voxels", "Voxels", !source.cells.sizes], ["points", "Points"], ["streamlines", "Streamlines", !available.supplied], ["streamtubes", "Streamtubes", !available.supplied && !available.grid]], value => onOptions({ mode: value as FieldViewOptions["mode"], colorRange: undefined }))}
        {range("Field opacity", settings.opacity, .1, 1, .05, value => onOptions({ opacity: value }))}
        {range("Geometry context opacity", settings.contextOpacity ?? 1, 0, 1, .05, value => onOptions({ contextOpacity: value }))}
        {range("Sample size (px)", settings.pointSize ?? 4, 2, 18, 1, value => onOptions({ pointSize: value }))}
        {select("Field detail", settings.budget, [500, 2500, 8000].map(n => [n, n.toLocaleString()]), value => onOptions({ budget: Number(value) }))}
        {!streamMode && <label><input type="checkbox" checked={settings.arrows} disabled={!source.frames[frame].vectors} onChange={e => onOptions({ arrows: e.target.checked })} /> Velocity arrows</label>}
        {!generated && quantity?.unit === "K" && <label><input type="checkbox" checked={settings.celsius} onChange={e => onOptions({ celsius: e.target.checked, colorRange: undefined })} /> Celsius</label>}
        <label><input type="checkbox" checked={settings.showSolids !== false} disabled={!source.geometry?.solids.length} onChange={e => onOptions({ showSolids: e.target.checked })} /> Source solid geometry</label>
        {range("Solid opacity", settings.solidOpacity ?? .15, 0, 1, .05, value => onOptions({ solidOpacity: value }), !source.geometry?.solids.length || settings.showSolids === false)}
        {streamMode ? range("Stream width", settings.streamWidth ?? 2, 1, 6, .5, value => onOptions({ streamWidth: value })) : <>{select("Field cut axis", settings.sliceAxis, ["all", "x", "y", "z"].map(a => [a, a]), value => onOptions({ sliceAxis: value as FieldViewOptions["sliceAxis"] }))}{range("Field cut position", settings.slicePercent, 0, 100, 1, value => onOptions({ slicePercent: value }), settings.sliceAxis === "all")}</>}
        {generated && <>{select("Stream seed plane", settings.seedAxis ?? "x", ["x", "y", "z"].map(a => [a, `Center ${a.toUpperCase()}`]), value => onOptions({ seedAxis: value as "x" | "y" | "z" }))}{select("Stream seed density", settings.seedDensity ?? 4, [2, 4, 6, 8].map(n => [n, `${n} × ${n}`]), value => onOptions({ seedDensity: Number(value) }))}</>}
      </div><small>Geometry context opacity ghosts the board, copper and component models behind the results. Sample size changes stored point markers in both fields; it does not create a temperature surface or resize voxels.</small>{!source.geometry?.solids.length && <small>No source solid geometry is attached to this primary dataset.</small>}
      <section className="main-field-inspection" aria-label="Field color scale"><strong>Color range {generated ? "(generated speed, m/s)" : `(${inspection?.unit})`}</strong><p>{!generated && settings.colorRange ? "User range; values outside endpoints saturate." : "Saved-data range, fixed across all saved frames."}</p>
        <div className="main-field-grid">{(["Minimum", "Maximum"] as const).map((label, index) => <label key={label}>{label}<input type="number" step="any" aria-label={`Color range ${label.toLowerCase()}`} value={generated ? savedSpeedRange?.[index] ?? "" : rangeDraft[index]} disabled={generated} onChange={event => setRangeDraft(previous => index === 0 ? [event.target.value, previous[1]] : [previous[0], event.target.value])} /></label>)}</div>
        <div className="main-field-inspection-actions"><button type="button" disabled={generated} onClick={applyRange}>Apply color range</button><button type="button" disabled={generated || !settings.colorRange} onClick={() => onOptions({ colorRange: undefined })}>Reset to saved range</button></div>{rangeError && <p role="alert">{rangeError}</p>}{generated && <small>Generated curves use the saved velocity-speed range. Choose a supplied-data view to edit its scalar range.</small>}
      </section>
      {inspection && <section className="main-field-inspection" aria-label="Stored cell sample inspection"><strong>Stored cell samples ({inspection.unit})</strong><p>Current frame, all {inspection.count.toLocaleString()} cells before cutaway or display reduction; curve samples are excluded.</p>{(["minimum", "maximum"] as const).map(key => <div className="main-field-sample" key={key}><span>{key === "minimum" ? "Min" : "Max"}: {inspection[key].value.toPrecision(6)} at ({inspection[key].point.map(v => v.toPrecision(4)).join(", ")}) {source.lengthUnit}</span><button type="button" onClick={() => onOptions({ sampleIndex: inspection[key].index })}>Inspect {key === "minimum" ? "min" : "max"}</button></div>)}
        <label>Sample number<input type="number" aria-label="Stored cell sample number" min={1} max={inspection.count} step={1} value={inspection.selected.index + 1} onChange={event => { const number = Number(event.target.value); if (Number.isInteger(number) && number >= 1 && number <= inspection.count) onOptions({ sampleIndex: number - 1 }); }} /></label><output>{inspection.selected.value.toPrecision(6)} {inspection.unit} at ({inspection.selected.point.map(v => v.toPrecision(6)).join(", ")}) {source.lengthUnit}</output>
        <small>{streamMode ? "Cell marker is available in volume and point views." : "An inspected cell appears as a white marker, including when excluded by the cutaway."}</small><button type="button" disabled={settings.sampleIndex === undefined} onClick={() => onOptions({ sampleIndex: undefined })}>Clear sample marker</button>
      </section>}
      {timeline && !managedPlayback && <div className="main-field-transport" aria-label="Saved field playback"><button type="button" aria-label="First saved field frame" onClick={() => step(0)}><RotateCcw size={14} /></button><button type="button" aria-label="Previous saved field frame" onClick={() => step(frame - 1)}><ArrowLeft size={14} /></button><button type="button" aria-label="Next saved field frame" onClick={() => step(frame + 1)}><ArrowRight size={14} /></button><button type="button" aria-label="Last saved field frame" onClick={() => step(times.length - 1)}><SkipForward size={14} /></button>{select("Playback speed", speed, [.25, .5, 1, 2, 4, 10].map(n => [n, `${n}×`]), value => setSpeed(Number(value)))}<label><input type="checkbox" checked={loop} onChange={e => setLoop(e.target.checked)} /> Loop</label></div>}
      <details><summary>Dataset and display limits</summary><p>{source.geometryNote} Coordinates use the source {source.lengthUnit} frame; no alignment or physical connection is inferred. Curves show saved instantaneous fields, not particle histories. Imported fields are session-only; export JSON to retain them.</p></details><button type="button" className="main-field-remove" onClick={() => { setPlaying(false); onClear(); }}>Remove field layer</button></>}
    </section>, document.body)}
  </div>;
}
