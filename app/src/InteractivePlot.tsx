// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Copy, ClipboardPaste, Image, RotateCcw, Move, ZoomIn, ZoomOut, MousePointer2, X, SlidersHorizontal } from "lucide-react";
import type Plotly from "plotly.js-dist-min";
import CommandStrip from "./CommandStrip";
import { copyPlotData, isCartesianPlot, pastePlotTraces, plotAxisLabel, type PlotTrace } from "./plotClipboard";
import { panPlotRange, wheelPlotFactor, zoomPlotRange, type PlotRange } from "./plotInteraction";
import { preparePlotLayout } from "./plotLayout";
import PlotAxisEditor from "./PlotAxisEditor";
import { buildPlotAxes, type AxisDraft, type AxisSettings } from "./plotAxisSettings";
import "./PlotlyChart.css";

type Point = { x: number; y: number; curveNumber: number; pointNumber: number };
type Props = { data: PlotTrace[]; layout: Record<string, unknown>; revision: string; title?: string; onPointClick?: (point: Point) => void };
type Axis = { range?: PlotRange; type?: string; autorange?: boolean; showgrid?: boolean; showspikes?: boolean; minor?: { showgrid?: boolean }; _offset?: number; _length?: number };
type Graph = HTMLDivElement & { _fullLayout?: { xaxis?: Axis; yaxis?: Axis; scene?: { camera?: { eye?: { x: number; y: number; z: number } } } };
  on?: (event: string, callback: (value: { points?: Point[] }) => void) => void; removeListener?: (event: string, callback: (value: { points?: Point[] }) => void) => void };
async function clipboardAccess<T>(task: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try { return await Promise.race([task, new Promise<T>((_, reject) => { timer = setTimeout(() => reject(new Error("Clipboard access did not respond. Use Paste X/Y table or Download PNG from the context menu.")), 3000); })]); }
  finally { clearTimeout(timer); }
}

export default function InteractivePlot({ data, layout, revision, title = "Interactive result plot", onPointClick }: Props) {
  const host = useRef<Graph>(null), plotlyRef = useRef<typeof Plotly | null>(null), renderRevision = useRef(0);
  const renderQueue = useRef<Promise<void>>(Promise.resolve());
  const controls = useRef({ wheelZoom: false, data, onPointClick });
  const [ready, setReady] = useState(0), [retry, setRetry] = useState(0);
  const [state, setState] = useState({ loading: true, error: "" });
  const [notice, setNotice] = useState(""), [busy, setBusy] = useState(false), [mode, setMode] = useState("pan"), [wheelZoom, setWheelZoom] = useState(false);
  const [comparisons, setComparisons] = useState<PlotTrace[]>([]);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const [pasteOpen, setPasteOpen] = useState(false), [pasteText, setPasteText] = useState("");
  const [axisEditor, setAxisEditor] = useState<AxisSettings | null>(null), [axisOverrides, setAxisOverrides] = useState<Record<string, Record<string, unknown>>>({}), [axisRevision, setAxisRevision] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null), pasteRef = useRef<HTMLTextAreaElement>(null);
  const cartesian = isCartesianPlot(data), usable = !state.loading && !state.error && Boolean(ready);
  const canPaste = cartesian && data.every(trace => ["scatter", "scattergl", "bar"].includes(String(trace.type ?? "scatter")));
  controls.current = { wheelZoom, data, onPointClick };
  useEffect(() => {
    let alive = true; const element = host.current;
    setState({ loading: true, error: "" });
    void import("plotly.js-dist-min").then(module => { if (alive) { plotlyRef.current = module.default; setReady(value => value + 1); } },
      reason => { if (alive) setState({ loading: false, error: String(reason instanceof Error ? reason.message : reason) }); });
    return () => { alive = false; renderRevision.current += 1; if (element && plotlyRef.current) plotlyRef.current.purge(element); plotlyRef.current = null; };
  }, [retry]);
  useEffect(() => { setComparisons([]); setNotice(""); setAxisOverrides({}); setAxisEditor(null); }, [revision]);
  useEffect(() => {
    const plotly = plotlyRef.current, element = host.current;
    if (!plotly || !element) return;
    const token = ++renderRevision.current; setState({ loading: true, error: "" });
    // Plotly can annotate its inputs; protect solver-owned arrays and metadata.
    renderQueue.current = renderQueue.current.then(async () => {
      if (token !== renderRevision.current) return;
      const themed = getComputedStyle(element), merged = { ...layout };
      for (const [key, value] of Object.entries(axisOverrides)) merged[key] = { ...(layout[key] as object ?? {}), ...value };
      if (axisOverrides.xaxis?.showspikes) merged.hovermode = "closest";
      const figure = { data: structuredClone([...data, ...comparisons]), layout: preparePlotLayout(merged, { text: themed.getPropertyValue("--spike-table-text").trim(), line: themed.getPropertyValue("--spike-table-muted").trim(), grid: themed.getPropertyValue("--spike-table-border").trim(), surface: themed.getPropertyValue("--spike-table-surface").trim() }) };
      await plotly.react(element, figure.data, { ...figure.layout, autosize: true, dragmode: cartesian ? mode : mode === "pan" ? "orbit" : "pan", uirevision: `${revision}:${axisRevision}` },
        { responsive: true, displaylogo: false, displayModeBar: false, scrollZoom: false, doubleClick: "reset+autosize" });
      if (token === renderRevision.current) setState({ loading: false, error: "" });
    }).catch(reason => { if (token === renderRevision.current) setState({ loading: false, error: String(reason instanceof Error ? reason.message : reason) }); });
  }, [data, layout, revision, ready, comparisons, mode, axisOverrides, axisRevision]);
  const update = (changes: Record<string, unknown>) => {
    if (host.current && plotlyRef.current) void plotlyRef.current.relayout(host.current, changes).catch(reason => setNotice(`Plot interaction failed: ${String(reason instanceof Error ? reason.message : reason)}`));
  };
  const zoom = (factor: number, client?: { x: number; y: number }) => {
    const element = host.current, full = element?._fullLayout; if (!element || !full) return;
    if (!isCartesianPlot(controls.current.data)) {
      const eye = full.scene?.camera?.eye ?? { x: 1.25, y: 1.25, z: 1.25 }, distance = Math.hypot(eye.x, eye.y, eye.z);
      const scale = Math.max(.05, Math.min(100, distance * factor)) / Math.max(distance, .001);
      update({ "scene.camera.eye": { x: eye.x * scale, y: eye.y * scale, z: eye.z * scale } }); return;
    }
    const bounds = element.getBoundingClientRect(), changes: Record<string, unknown> = {};
    for (const key of ["xaxis", "yaxis"] as const) {
      const axis = full[key]; if (!axis?.range || !axis.range.every(Number.isFinite)) continue;
      const pixel = client ? key === "xaxis" ? client.x - bounds.left : client.y - bounds.top : undefined;
      let fraction = pixel === undefined ? .5 : (pixel - (axis._offset ?? 0)) / Math.max(1, axis._length ?? (key === "xaxis" ? bounds.width : bounds.height));
      if (key === "yaxis" && pixel !== undefined) fraction = 1 - fraction;
      changes[`${key}.range`] = zoomPlotRange(axis.range, factor, fraction); changes[`${key}.autorange`] = false;
    }
    update(changes);
  };
  const pan = (axis: "xaxis" | "yaxis", fraction: number) => {
    const range = host.current?._fullLayout?.[axis]?.range;
    if (range?.every(Number.isFinite)) update({ [`${axis}.range`]: panPlotRange(range, fraction), [`${axis}.autorange`]: false });
  };
  const reset = () => cartesian ? update({ "xaxis.autorange": true, "yaxis.autorange": true }) : update({ "scene.camera": (layout.scene as Record<string, unknown> | undefined)?.camera ?? { eye: { x: 1.25, y: 1.25, z: 1.25 }, up: { x: 0, y: 0, z: 1 }, center: { x: 0, y: 0, z: 0 } } });
  const editAxes = () => {
    const full = host.current?._fullLayout;
    const draft = (axis?: Axis): AxisDraft => ({ scale: axis?.type === "log" ? "log" : "linear", auto: Boolean(axis?.autorange),
      minimum: String(axis?.type === "log" ? 10 ** (axis.range?.[0] ?? 0) : axis?.range?.[0] ?? 0),
      maximum: String(axis?.type === "log" ? 10 ** (axis.range?.[1] ?? 1) : axis?.range?.[1] ?? 1) });
    setAxisEditor({ x: draft(full?.xaxis), y: draft(full?.yaxis), grid: full?.xaxis?.minor?.showgrid ? "minor" : full?.xaxis?.showgrid ? "major" : "off", crosshair: Boolean(full?.xaxis?.showspikes) });
  };
  useEffect(() => {
    const element = host.current; if (!element) return;
    let frame = 0, pending = 0, client = { x: 0, y: 0 };
    const wheel = (event: WheelEvent) => {
      if (!plotlyRef.current || !element._fullLayout) return;
      if (event.shiftKey && isCartesianPlot(controls.current.data)) {
        event.preventDefault(); event.stopPropagation(); pan("xaxis", Math.max(-.2, Math.min(.2, (event.deltaX || event.deltaY) * .001))); return;
      }
      if (!controls.current.wheelZoom && !event.ctrlKey && !event.metaKey) return;
      event.preventDefault(); event.stopPropagation(); pending += Math.log(wheelPlotFactor(event.deltaY, event.deltaMode)); client = { x: event.clientX, y: event.clientY };
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; zoom(Math.exp(Math.max(-1, Math.min(1, pending))), client); pending = 0; });
    };
    const resize = () => { if (plotlyRef.current && element._fullLayout) void Promise.resolve(plotlyRef.current.Plots.resize(element)).catch(reason => setNotice(`Plot resize failed: ${String(reason)}`)); };
    const observer = new ResizeObserver(resize); observer.observe(element); element.addEventListener("wheel", wheel, { passive: false });
    return () => { observer.disconnect(); element.removeEventListener("wheel", wheel); if (frame) cancelAnimationFrame(frame); };
  }, []);
  useEffect(() => {
    const element = host.current; if (!element || !ready || state.loading) return;
    const click = (event: { points?: Point[] }) => { const point = event.points?.[0];
      if (point && point.curveNumber < controls.current.data.length && Number.isFinite(point.x) && Number.isFinite(point.y)) controls.current.onPointClick?.(point); };
    element.on?.("plotly_click", click); return () => { element.removeListener?.("plotly_click", click); };
  }, [ready, state.loading]);
  useEffect(() => {
    if (!menu) return;
    menuRef.current?.querySelector<HTMLElement>("button:not(:disabled)")?.focus();
    const dismiss = (event: PointerEvent) => { if (!menuRef.current?.contains(event.target as Node)) setMenu(null); }, close = () => setMenu(null);
    document.addEventListener("pointerdown", dismiss); window.addEventListener("resize", close); window.addEventListener("scroll", close, true);
    return () => { document.removeEventListener("pointerdown", dismiss); window.removeEventListener("resize", close); window.removeEventListener("scroll", close, true); };
  }, [menu]);
  useEffect(() => { if (pasteOpen) pasteRef.current?.focus(); }, [pasteOpen]);
  const action = async (task: () => Promise<void>) => {
    setMenu(null); setBusy(true); try { await task(); } catch (reason) { setNotice(String(reason instanceof Error ? reason.message : reason)); } finally { setBusy(false); }
  };
  const copyData = () => action(async () => { await clipboardAccess(navigator.clipboard.writeText(copyPlotData([...data, ...comparisons], layout, title))); setNotice("Plot data copied. Paste into a spreadsheet or another compatible 2D plot."); });
  const copyImage = () => action(async () => {
    if (!host.current || !plotlyRef.current) return;
    if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") throw new Error("Image clipboard is unavailable here. Use Download PNG from the context menu.");
    const url = await plotlyRef.current.toImage(host.current, { format: "png", width: Math.min(2400, Math.max(640, host.current.clientWidth * 2)), height: Math.min(1600, Math.max(400, host.current.clientHeight * 2)) });
    const blob = await (await fetch(url)).blob(); await clipboardAccess(navigator.clipboard.write([new ClipboardItem({ "image/png": blob })])); setNotice("Plot image copied. Paste directly into a document, slide or message.");
  });
  const downloadImage = () => action(async () => {
    if (!host.current || !plotlyRef.current) return;
    const url = await plotlyRef.current.toImage(host.current, { format: "png", width: 1200, height: 800 });
    const link = document.createElement("a"); link.href = url; link.download = "spike-plot.png"; link.click(); setNotice("Plot PNG downloaded.");
  });
  const importText = (text: string) => {
    try {
      if (!canPaste) throw new Error("Paste traces into a 2D line or bar chart; field maps and 3D scenes do not accept trace overlays.");
      const currentLayout = { ...layout, xaxis: { ...(layout.xaxis as object ?? {}), ...axisOverrides.xaxis }, yaxis: { ...(layout.yaxis as object ?? {}), ...axisOverrides.yaxis } };
      setComparisons(pastePlotTraces(text, currentLayout)); setPasteOpen(false); setNotice("Clipboard comparisons added to this view only. Solver results are unchanged.");
    } catch (reason) { setNotice(String(reason instanceof Error ? reason.message : reason)); }
  };
  const paste = () => action(async () => {
    try {
      const text = await clipboardAccess(navigator.clipboard.readText());
      if (!text.trim()) throw new Error("No clipboard text");
      importText(text);
    } catch { setPasteOpen(true); setNotice("Paste your X/Y table into the text box, then choose Add comparison."); }
  });
  const button = (name: string, run: () => void, icon: ReactNode, disabled = !usable || busy, pressed?: boolean) => <button type="button" disabled={disabled} aria-pressed={pressed} title={name} onClick={run}>{icon}<span>{name}</span></button>;
  const openMenu = (x: number, y: number) => setMenu({ x: Math.max(8, Math.min(x, window.innerWidth - 238)), y: Math.max(8, Math.min(y, window.innerHeight - 340)) });
  return <section className="trace-plot-host spike-plot" aria-label={title}>
    <CommandStrip label="Plot tools" className="spike-plot-toolbar">
      {button(cartesian ? "Pan" : "Orbit", () => setMode("pan"), <Move size={14}/>, !usable || busy, mode === "pan")}
      {button(cartesian ? "Box zoom" : "Pan 3D", () => setMode("zoom"), <MousePointer2 size={14}/>, !usable || busy, mode === "zoom")}
      {button("Zoom in", () => zoom(.8), <ZoomIn size={14}/>)}{button("Zoom out", () => zoom(1.25), <ZoomOut size={14}/>)}{button("Fit", reset, <RotateCcw size={14}/>)}
      {button("Axes", editAxes, <SlidersHorizontal size={14}/>, !usable || busy || !cartesian)}
      <button type="button" aria-pressed={wheelZoom} disabled={!usable} title="Enable plain wheel zoom; Ctrl+wheel always zooms" onClick={() => setWheelZoom(value => !value)}>Wheel zoom: {wheelZoom ? "on" : "off"}</button>
      {button("Copy image", () => void copyImage(), <Image size={14}/>)}{button("Copy data", () => void copyData(), <Copy size={14}/>)}
      {button("Paste traces", () => void paste(), <ClipboardPaste size={14}/>, !usable || busy || !canPaste)}
      {comparisons.length > 0 && button("Clear pasted", () => { setComparisons([]); setNotice("Clipboard comparisons removed."); }, <X size={14}/>)}
    </CommandStrip>
    <div className="spike-plot-surface" onContextMenu={event => { event.preventDefault(); event.stopPropagation(); openMenu(event.clientX, event.clientY); }}>
      <div ref={host} className="trace-plot-canvas" tabIndex={0} role="group" aria-label={`${title}. Ctrl+wheel zooms; Shift+wheel pans; right-click for plot actions.`}
        onPointerDownCapture={() => host.current?.focus({ preventScroll: true })}
        onPaste={event => { event.preventDefault(); event.stopPropagation(); importText(event.clipboardData.getData("text/plain")); }}
        onKeyDown={event => {
          if ((event.target as HTMLElement).closest("input,select,textarea,[contenteditable=true]")) return;
          const key = event.key.toLowerCase();
          if ((event.ctrlKey || event.metaKey) && key === "c") { event.preventDefault(); event.stopPropagation(); void (event.shiftKey ? copyData() : copyImage()); return; }
          if ((event.ctrlKey || event.metaKey) && key === "v") { event.stopPropagation(); return; }
          if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) { event.preventDefault(); event.stopPropagation(); const box = event.currentTarget.getBoundingClientRect(); openMenu(box.left + 20, box.top + 20); return; }
          if (!usable || event.ctrlKey || event.metaKey || event.altKey) return;
          const actions: Record<string, () => void> = { "+": () => zoom(.8), "=": () => zoom(.8), "-": () => zoom(1.25), "0": reset, ArrowLeft: () => pan("xaxis", -.1), ArrowRight: () => pan("xaxis", .1), ArrowUp: () => pan("yaxis", .1), ArrowDown: () => pan("yaxis", -.1) };
          if (actions[event.key]) { event.preventDefault(); event.stopPropagation(); actions[event.key](); }
        }}/>
      {state.loading && <div className="trace-plot-loading" role="status">Loading interactive graph…</div>}
      {state.error && <div className="trace-plot-error" role="alert"><b>Graph rendering failed</b><span>{state.error}</span><button onClick={() => setRetry(value => value + 1)}>Retry</button></div>}
    </div>
    <div className="spike-plot-hint">{!cartesian && <span className="spike-plot-scene-labels">{["xaxis", "yaxis", "zaxis"].map(key => plotAxisLabel((layout.scene as Record<string, unknown> | undefined)?.[key])).filter(Boolean).join(" · ")}</span>}{cartesian ? "Wheel: scroll panel · Ctrl+wheel: zoom · Shift+wheel: pan · " : "Drag: orbit · Ctrl+wheel: zoom · "}Ctrl+C: image · Ctrl+Shift+C: data{canPaste ? " · Ctrl+V: paste" : ""}</div>
    {notice && <div className="spike-plot-notice" role="status">{notice}</div>}
    {pasteOpen && <div className="spike-plot-paste" role="group" aria-label="Paste plot comparison" onKeyDown={event => { event.stopPropagation(); if (event.key === "Escape") setPasteOpen(false); }}>
      <label>Paste X/Y data<textarea ref={pasteRef} value={pasteText} onChange={event => setPasteText(event.target.value)} placeholder={"X\tY\n0\t1\n1\t2"}/></label>
      <div><button onClick={() => importText(pasteText)}>Add comparison</button><button onClick={() => setPasteOpen(false)}>Cancel</button></div>
    </div>}
    {axisEditor && <PlotAxisEditor initial={axisEditor} labels={{ x: plotAxisLabel(layout.xaxis), y: plotAxisLabel(layout.yaxis) }} onClose={() => setAxisEditor(null)} onApply={settings => {
      try { setAxisOverrides(buildPlotAxes(settings, [...data, ...comparisons])); setAxisRevision(value => value + 1); setAxisEditor(null); setNotice("Axis settings applied to this view. Sample values and units are unchanged."); return ""; }
      catch (reason) { return String(reason instanceof Error ? reason.message : reason); }
    }}/>}
    {menu && createPortal(<div ref={menuRef} className="spike-plot-menu" role="menu" aria-label="Plot context menu" style={{ left: menu.x, top: menu.y }} onKeyDown={event => {
      event.stopPropagation();
      if (event.key === "Escape") { event.preventDefault(); setMenu(null); host.current?.focus(); }
      const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")], index = items.indexOf(document.activeElement as HTMLButtonElement);
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) { event.preventDefault(); items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length]?.focus(); }
      if (event.key === "Tab") { event.preventDefault(); setMenu(null); host.current?.focus(); }
    }}>
      {[{ name: "Fit plot", run: reset }, { name: "Axes and grid…", run: editAxes, disabled: !cartesian }, { name: "Zoom in", run: () => zoom(.8) }, { name: "Zoom out", run: () => zoom(1.25) },
        { name: "Copy image · Ctrl+C", run: () => void copyImage() }, { name: "Copy data · Ctrl+Shift+C", run: () => void copyData() },
        { name: "Paste traces · Ctrl+V", run: () => void paste(), disabled: !canPaste },
        { name: "Paste X/Y table…", run: () => setPasteOpen(true), disabled: !canPaste }, { name: "Download PNG", run: () => void downloadImage() },
        { name: "Clear pasted comparisons", run: () => setComparisons([]), disabled: !comparisons.length }].map(item => <button key={item.name} role="menuitem" disabled={!usable || busy || item.disabled} onClick={() => { setMenu(null); item.run(); host.current?.focus(); }}>{item.name}</button>)}
    </div>, document.body)}
  </section>;
}
