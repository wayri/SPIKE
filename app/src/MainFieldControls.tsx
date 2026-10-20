// SPDX-License-Identifier: Apache-2.0
// Controls only; BoardViewport owns the shared scene and camera.
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Box, Eye, EyeOff, Upload, Download, Play, Pause, X, ArrowLeft, ArrowRight, SkipForward, RotateCcw } from "./icons";
import { admitFieldVolume, type FieldViewOptions } from "./fieldVolumeModel";
import { fieldStreamAvailability } from "./fieldStreamPresentation";
import { createPlaybackTimeline } from "./transientPlayback";
import type { MainFieldView } from "./mainFieldViewport";
import "./buttonStandard.css";
import "./MainFieldControls.css";
type Props = { view: MainFieldView | null; open: boolean; onOpen: (open: boolean) => void; onPresent: (data: unknown) => void; onOptions: (patch: Partial<FieldViewOptions>) => void; onVisible: (value: boolean) => void; onClear: () => void };
export default function MainFieldControls({ view, open, onOpen, onPresent, onOptions, onVisible, onClear }: Props) {
  const trigger = useRef<HTMLButtonElement>(null), panel = useRef<HTMLElement>(null), input = useRef<HTMLInputElement>(null);
  const [position, setPosition] = useState({ top: 70, left: 12 }), [error, setError] = useState("");
  const [playing, setPlaying] = useState(false), [speed, setSpeed] = useState(1), [loop, setLoop] = useState(false);
  const source = view?.data, settings = view?.options;
  const frame = Math.min(settings?.frame ?? 0, Math.max(0, (source?.frames.length ?? 1) - 1));
  const times = useMemo(() => source?.frames.map(f => f.timeS) ?? [], [source]);
  const timeline = useMemo(() => { try { return createPlaybackTimeline(times); } catch { return null; } }, [times]);
  const available = useMemo(() => source ? fieldStreamAvailability(source, frame) : { supplied: false, grid: false }, [source, frame]);
  const streamMode = settings?.mode === "streamlines" || settings?.mode === "streamtubes", generated = settings?.mode === "streamtubes" && !available.supplied;
  const quantity = source?.quantities.find(q => q.id === settings?.quantity) ?? source?.quantities[0];
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
    const outside = (e: PointerEvent) => { if (!panel.current?.contains(e.target as Node) && !trigger.current?.contains(e.target as Node)) onOpen(false); };
    window.addEventListener("resize", place); document.addEventListener("keydown", key); document.addEventListener("pointerdown", outside);
    return () => { window.removeEventListener("resize", place); document.removeEventListener("keydown", key); document.removeEventListener("pointerdown", outside); };
  }, [open, onOpen]);
  const step = (next: number) => { setPlaying(false); onOptions({ frame: Math.max(0, Math.min(times.length - 1, next)) }); };
  const download = () => { if (!source) return; const url = URL.createObjectURL(new Blob([JSON.stringify(source)], { type: "application/json" })); const a = document.createElement("a"); a.href = url; a.download = "spike-field-volume.json"; a.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); };
  const select = (label: string, value: string | number, values: [string | number, string, boolean?][], change: (value: string) => void, disabled = false) => <label>{label}<select aria-label={label} value={value} disabled={disabled} onChange={e => change(e.target.value)}>{values.map(([id, text, off]) => <option key={id} value={id} disabled={off}>{text}</option>)}</select></label>;
  const range = (label: string, value: number, min: number, max: number, step: number, change: (value: number) => void, disabled = false) => <label>{label}<input type="range" aria-label={label} min={min} max={max} step={step} value={value} disabled={disabled} onChange={e => change(Number(e.target.value))} /></label>;
  return <div className="main-field-tools" role="group" aria-label="Main viewport field tools" onPointerDown={e => e.stopPropagation()}>
    <button ref={trigger} type="button" className="main-field-trigger" aria-label="Volume and airflow controls" title="Volume and airflow controls" aria-expanded={open} onClick={() => onOpen(!open)}><Box size={15} /><span>Fields</span></button>
    {source && <>{timeline && <><button type="button" aria-label={playing ? "Pause field playback" : "Play field playback"} onClick={() => { if (!playing && frame === times.length - 1) onOptions({ frame: 0 }); onVisible(true); setPlaying(!playing); }}>{playing ? <Pause size={14} /> : <Play size={14} />}</button><input className="main-field-scrubber" type="range" aria-label="Field playback frame" min="0" max={times.length - 1} value={frame} onChange={e => step(Number(e.target.value))} /><small>{times[frame].toPrecision(4)} s</small></>}<button type="button" aria-label={view!.visible ? "Hide field layer" : "Show field layer"} title={view!.visible ? "Hide field layer" : "Show field layer"} onClick={() => onVisible(!view!.visible)}>{view!.visible ? <EyeOff size={14} /> : <Eye size={14} />}</button></>}
    <input ref={input} hidden type="file" accept=".json" aria-label="Field visualization JSON file" onChange={async e => { const file = e.target.files?.[0]; e.target.value = ""; if (!file) return; try { if (file.size > 64 * 1024 * 1024) throw new Error("Field import is limited to 64 MiB."); onPresent(admitFieldVolume(JSON.parse(await file.text()))); setError(""); } catch (reason) { setError(`Import rejected; previous field retained: ${reason instanceof Error ? reason.message : String(reason)}`); } }} />
    {open && createPortal(<section ref={panel} className="main-field-popover" style={position} role="dialog" aria-label="Field display settings" onPointerDown={e => e.stopPropagation()}>
      <header><strong>Field display</strong><div><button type="button" title="Import field JSON" aria-label="Import field" onClick={() => input.current?.click()}><Upload size={14} /></button><button type="button" title="Export field JSON" aria-label="Export field" disabled={!source} onClick={download}><Download size={14} /></button><button type="button" aria-label="Close field controls" onClick={() => { onOpen(false); trigger.current?.focus(); }}><X size={14} /></button></div></header>
      {error && <p role="alert">{error}</p>}{!source && <p>Import a field dataset, or choose Show fields in main viewport in a CFD result. Fields share the board scene and camera.</p>}
      {source && settings && <><p className="main-field-name" title={source.label}>{source.label}</p><div className="main-field-grid">
        {select("Volume quantity", quantity!.id, source.quantities.map(q => [q.id, `${q.label} (${q.unit})`]), value => onOptions({ quantity: value }), generated)}
        {select("Volume display", settings.mode, [["voxels", "Voxels", !source.cells.sizes], ["points", "Points"], ["streamlines", "Streamlines", !available.supplied], ["streamtubes", "Streamtubes", !available.supplied && !available.grid]], value => onOptions({ mode: value as FieldViewOptions["mode"] }))}
        {range("Field opacity", settings.opacity, .1, 1, .05, value => onOptions({ opacity: value }))}
        {select("Field detail", settings.budget, [500, 2500, 8000].map(n => [n, n.toLocaleString()]), value => onOptions({ budget: Number(value) }))}
        {!streamMode && <label><input type="checkbox" checked={settings.arrows} disabled={!source.frames[frame].vectors} onChange={e => onOptions({ arrows: e.target.checked })} /> Velocity arrows</label>}
        {!generated && quantity?.unit === "K" && <label><input type="checkbox" checked={settings.celsius} onChange={e => onOptions({ celsius: e.target.checked })} /> Celsius</label>}
        {streamMode ? range("Stream width", settings.streamWidth ?? 2, 1, 6, .5, value => onOptions({ streamWidth: value })) : <>{select("Field cut axis", settings.sliceAxis, ["all", "x", "y", "z"].map(a => [a, a]), value => onOptions({ sliceAxis: value as FieldViewOptions["sliceAxis"] }))}{range("Field cut position", settings.slicePercent, 0, 100, 1, value => onOptions({ slicePercent: value }), settings.sliceAxis === "all")}</>}
        {generated && <>{select("Stream seed plane", settings.seedAxis ?? "x", ["x", "y", "z"].map(a => [a, `Center ${a.toUpperCase()}`]), value => onOptions({ seedAxis: value as "x" | "y" | "z" }))}{select("Stream seed density", settings.seedDensity ?? 4, [2, 4, 6, 8].map(n => [n, `${n} × ${n}`]), value => onOptions({ seedDensity: Number(value) }))}</>}
      </div>{timeline && <div className="main-field-transport" aria-label="Saved field playback"><button type="button" aria-label="First saved field frame" onClick={() => step(0)}><RotateCcw size={14} /></button><button type="button" aria-label="Previous saved field frame" onClick={() => step(frame - 1)}><ArrowLeft size={14} /></button><button type="button" aria-label="Next saved field frame" onClick={() => step(frame + 1)}><ArrowRight size={14} /></button><button type="button" aria-label="Last saved field frame" onClick={() => step(times.length - 1)}><SkipForward size={14} /></button>{select("Playback speed", speed, [.25, .5, 1, 2, 4, 10].map(n => [n, `${n}×`]), value => setSpeed(Number(value)))}<label><input type="checkbox" checked={loop} onChange={e => setLoop(e.target.checked)} /> Loop</label></div>}
      <details><summary>Dataset and display limits</summary><p>{source.geometryNote} Coordinates use the source {source.lengthUnit} frame; no alignment or physical connection is inferred. Curves show saved instantaneous fields, not particle histories. Imported fields are session-only; export JSON to retain them.</p></details><button type="button" className="main-field-remove" onClick={() => { setPlaying(false); onClear(); }}>Remove field layer</button></>}
    </section>, document.body)}
  </div>;
}
