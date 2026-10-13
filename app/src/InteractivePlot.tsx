// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Copy, ClipboardPaste, Image, RotateCcw, Move, ZoomIn, ZoomOut, MousePointer2, X, SlidersHorizontal } from "./icons";
import type Plotly from "plotly.js-dist-min";
import CommandStrip from "./CommandStrip";
import { copyPlotData, isCartesianPlot, pastePlotTraces, plotAxisLabel, type PlotTrace } from "./plotClipboard";
import { plotPanChanges, plotResetChanges, plotWheelTarget, plotZoomChanges, wheelPlotFactor, type FullPlotLayout, type PlotAxis, type WheelPreference, type WheelTarget } from "./plotInteraction";
import { preparePlotLayout } from "./plotLayout";
import { sampleProbe, probeDelta, probeTable, probeMarkers, type PlotProbe } from "./plotProbes";
import PlotAxisEditor from "./PlotAxisEditor";
import { buildPlotAxes, type AxisDraft, type AxisSettings } from "./plotAxisSettings";
import { openContextScript, plotScriptContext } from "./contextScript";
import ResultValueScale from "./ResultValueScale";
import { plotColorScales, type PlotColorScale } from "./plotColorScales";
import "./PlotlyChart.css";

type Point = { x: number; y: number; curveNumber: number; pointNumber: number; pointIndex?: number; customdata?: unknown };
type PlotContextAction = { label: string; onSelect: () => void; disabled?: boolean };
type Props = { contextActions?: PlotContextAction[]; data: PlotTrace[]; layout: Record<string, unknown>; revision: string; title?: string; onPointClick?: (point: Point) => void; onSelectSamples?: (indices: number[]) => void };
type Graph = HTMLDivElement & { _fullLayout?: FullPlotLayout; _fullData?: PlotTrace[];
  on?: (event: string, callback: (value: { points?: Point[] }) => void) => void; removeListener?: (event: string, callback: (value: { points?: Point[] }) => void) => void };
async function clipboardAccess<T>(task: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try { return await Promise.race([task, new Promise<T>((_, reject) => { timer = setTimeout(() => reject(new Error("Clipboard access did not respond. Use Paste X/Y table or Download PNG from the context menu.")), 3000); })]); }
  finally { clearTimeout(timer); }
}

export default function InteractivePlot({ data, layout, revision, title = "Interactive result plot", onPointClick, onSelectSamples, contextActions = [] }: Props) {
  const host = useRef<Graph>(null), plotlyRef = useRef<typeof Plotly | null>(null), renderRevision = useRef(0);
  const renderQueue = useRef<Promise<void>>(Promise.resolve());
  const controls = useRef({ wheelZoom: true, wheelTarget: "auto" as WheelPreference, data, layout, comparisons: [] as PlotTrace[], onPointClick, onSelectSamples });
  const [probes, setProbes] = useState<PlotProbe[]>([]);
  const [colorScales, setColorScales] = useState<PlotColorScale[]>([]);
  const [ready, setReady] = useState(0), [retry, setRetry] = useState(0);
  const [state, setState] = useState({ loading: true, error: "" });
  const [notice, setNotice] = useState(""), [busy, setBusy] = useState(false), [mode, setMode] = useState("pan"), [wheelZoom, setWheelZoom] = useState(true);
  const [wheelTarget, setWheelTarget] = useState<WheelPreference>("auto");
  const [comparisons, setComparisons] = useState<PlotTrace[]>([]);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const [pasteOpen, setPasteOpen] = useState(false), [pasteText, setPasteText] = useState("");
  const [axisEditor, setAxisEditor] = useState<AxisSettings | null>(null), [axisOverrides, setAxisOverrides] = useState<Record<string, Record<string, unknown>>>({}), [axisRevision, setAxisRevision] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null), pasteRef = useRef<HTMLTextAreaElement>(null);
  const cartesian = isCartesianPlot(data), scene = data.some(trace => ["scatter3d", "mesh3d", "surface", "cone", "volume", "isosurface", "streamtube"].includes(String(trace.type))), polar = data.some(trace => ["scatterpolar", "scatterpolargl", "barpolar"].includes(String(trace.type))), usable = !state.loading && !state.error && Boolean(ready);
  const canPaste = cartesian && data.every(trace => ["scatter", "scattergl", "bar"].includes(String(trace.type ?? "scatter")));
  controls.current = { wheelZoom, wheelTarget, data, layout, comparisons, onPointClick, onSelectSamples };
  useEffect(() => {
    let alive = true; const element = host.current;
    setState({ loading: true, error: "" });
    void import("plotly.js-dist-min").then(module => { if (alive) { plotlyRef.current = module.default; setReady(value => value + 1); } },
      reason => { if (alive) setState({ loading: false, error: String(reason instanceof Error ? reason.message : reason) }); });
    return () => { alive = false; renderRevision.current += 1; if (element && plotlyRef.current) plotlyRef.current.purge(element); plotlyRef.current = null; };
  }, [retry]);
  useEffect(() => { setComparisons([]); setProbes([]); setNotice(""); setAxisOverrides({}); setAxisEditor(null); }, [revision, data]);
  useEffect(() => { setColorScales([]); }, [data, layout, revision]);
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
      await plotly.react(element, [...figure.data, ...probeMarkers(probes, themed.getPropertyValue("--spike-table-text").trim() || "#8397a6")], { ...figure.layout, autosize: true, dragmode: scene ? mode === "pan" ? "orbit" : "pan" : mode, uirevision: `${revision}:${axisRevision}` },
        { responsive: true, displaylogo: false, displayModeBar: false, scrollZoom: false, doubleClick: "reset+autosize" });
      if (token === renderRevision.current) {
        setColorScales(plotColorScales(element._fullData ?? figure.data, (element._fullLayout ?? figure.layout) as Record<string, unknown>));
        setState({ loading: false, error: "" });
      }
    }).catch(reason => { if (token === renderRevision.current) setState({ loading: false, error: String(reason instanceof Error ? reason.message : reason) }); });
  }, [data, layout, revision, ready, comparisons, mode, axisOverrides, axisRevision, probes]);
  useEffect(() => {
    const element = host.current; if (!element || !ready || state.loading) return;
    const refresh = () => setColorScales(plotColorScales(element._fullData ?? [], (element._fullLayout ?? {}) as Record<string, unknown>));
    element.on?.("plotly_restyle", refresh);
    return () => { element.removeListener?.("plotly_restyle", refresh); };
  }, [ready, state.loading]);
  const update = (changes: Record<string, unknown>) => {
    if (host.current && plotlyRef.current && Object.keys(changes).length) void plotlyRef.current.relayout(host.current, changes).catch(reason => setNotice(`Plot interaction failed: ${String(reason instanceof Error ? reason.message : reason)}`));
  };
  const zoom = (factor: number, target?: WheelTarget) => {
    const element = host.current, full = element?._fullLayout; if (!element || !full) return;
    update(plotZoomChanges(full, factor, target));
  };
  const pan = (axis: "xaxis" | "yaxis", fraction: number) => {
    const full = host.current?._fullLayout; if (full) update(plotPanChanges(full, axis, fraction));
  };
  const reset = () => { const full = host.current?._fullLayout; if (full) update(plotResetChanges(full, layout)); };
  const editAxes = () => {
    const full = host.current?._fullLayout;
    const draft = (axis?: PlotAxis): AxisDraft => ({ scale: axis?.type === "log" ? "log" : "linear", auto: Boolean(axis?.autorange),
      minimum: String(axis?.type === "log" ? 10 ** Number(axis.range?.[0] ?? 0) : axis?.range?.[0] ?? 0),
      maximum: String(axis?.type === "log" ? 10 ** Number(axis.range?.[1] ?? 1) : axis?.range?.[1] ?? 1) });
    setAxisEditor({ x: draft(full?.xaxis), y: draft(full?.yaxis), grid: full?.xaxis?.minor?.showgrid ? "minor" : full?.xaxis?.showgrid ? "major" : "off", crosshair: Boolean(full?.xaxis?.showspikes) });
  };
  useEffect(() => {
    const element = host.current; if (!element) return;
    let frame = 0, pending = 0, target: WheelTarget | null = null;
    const wheel = (event: WheelEvent) => {
      if (!plotlyRef.current || !element._fullLayout) return;
      if (!controls.current.wheelZoom && !event.ctrlKey && !event.metaKey) return;
      const node = event.target instanceof Element ? event.target : null;
      if (node?.closest(".legend,.colorbar,.modebar")) return;
      let hint: string | undefined;
      for (let item = node; item && item !== element; item = item.parentElement) {
        const match = (item.getAttribute("class") ?? "").match(/(?:^|[\s-])([xy]\d*)(?:tick|title)(?:\s|$)/);
        if (match) { hint = `${match[1][0]}axis${match[1].slice(1)}`; break; }
        if (item.classList.contains("radialaxistick")) hint = "polar.radialaxis";
        if (item.classList.contains("angularaxistick")) hint = "polar.angularaxis";
      }
      const bounds = element.getBoundingClientRect(), next = plotWheelTarget(element._fullLayout, event.clientX - bounds.left, event.clientY - bounds.top, controls.current.wheelTarget, hint);
      if (!next || !Object.keys(plotZoomChanges(element._fullLayout, 1.1, next)).length) return;
      event.preventDefault(); event.stopPropagation();
      if (event.shiftKey && next.kind === "cartesian") {
        const axes = next.axes.filter(key => key.startsWith("x"));
        for (const key of axes) update(plotPanChanges(element._fullLayout, key, Math.max(-.2, Math.min(.2, (event.deltaX || event.deltaY) * .001)))); return;
      }
      if (target && JSON.stringify({ ...target, x: 0, y: 0, fraction: 0 }) !== JSON.stringify({ ...next, x: 0, y: 0, fraction: 0 })) pending = 0;
      target = next; pending += Math.log(wheelPlotFactor(event.deltaY || event.deltaX, event.deltaMode));
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; if (target) zoom(Math.exp(Math.max(-1, Math.min(1, pending))), target); pending = 0; });
    };
    const resize = () => { if (plotlyRef.current && element._fullLayout) void Promise.resolve(plotlyRef.current.Plots.resize(element)).catch(reason => setNotice(`Plot resize failed: ${String(reason)}`)); };
    const observer = new ResizeObserver(resize); observer.observe(element); element.addEventListener("wheel", wheel, { passive: false, capture: true });
    return () => { observer.disconnect(); element.removeEventListener("wheel", wheel, true); if (frame) cancelAnimationFrame(frame); };
  }, []);
  useEffect(() => {
    const element = host.current; if (!element || !ready || state.loading) return;
    const click = (event: { points?: Point[] }) => { const point = event.points?.[0];
      if (point) {
        const current = controls.current;
        const probe = sampleProbe([...current.data, ...current.comparisons], current.layout, point, current.data.length);
        if (probe) setProbes(old => old.length === 1 ? [...old, probe] : [probe]);
      }
      if (point && point.curveNumber < controls.current.data.length && Number.isFinite(point.x) && Number.isFinite(point.y)) controls.current.onPointClick?.(point);
      select(event); };
    const select = (event: { points?: Point[] }) => { const indices = [...new Set((event.points ?? []).filter(point => point.curveNumber < controls.current.data.length).map(point => typeof point.customdata === "number" ? point.customdata : point.pointIndex ?? point.pointNumber).filter(index => Number.isInteger(index) && index >= 0))];
      if (indices.length) controls.current.onSelectSamples?.(indices); };
    element.on?.("plotly_click", click); element.on?.("plotly_selected", select);
    return () => { element.removeListener?.("plotly_click", click); element.removeListener?.("plotly_selected", select); };
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
  const openScript = () => { try { openContextScript({ kind: "plot", title, payload: plotScriptContext([...data, ...comparisons], layout, revision, data.length) }); setNotice("Plot source samples opened in an unsaved Python draft."); } catch (error) { setNotice(String(error)); } };
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
  const openMenu = (x: number, y: number) => setMenu({ x: Math.max(8, Math.min(x, window.innerWidth - 238)), y: Math.max(8, Math.min(y, window.innerHeight - 390)) });
  return <section className="trace-plot-host spike-plot" aria-label={title}>
    <CommandStrip label="Plot tools" className="spike-plot-toolbar">
      {button(scene ? "Orbit" : "Pan", () => setMode("pan"), <Move size={14}/>, !usable || busy, mode === "pan")}
      {button(scene ? "Pan 3D" : "Box zoom", () => setMode("zoom"), <MousePointer2 size={14}/>, !usable || busy, mode === "zoom")}
      {onSelectSamples && cartesian && button("Select samples", () => setMode("select"), <MousePointer2 size={14}/>, !usable || busy, mode === "select")}
      {button("Zoom in", () => zoom(.8), <ZoomIn size={14}/>)}{button("Zoom out", () => zoom(1.25), <ZoomOut size={14}/>)}{button("Fit", reset, <RotateCcw size={14}/>)}
      {button("Axes", editAxes, <SlidersHorizontal size={14}/>, !usable || busy || !cartesian)}
      {probes.length > 0 && button("Clear probes", () => setProbes([]), <X size={14}/>)}
      {probes.length > 0 && button("Copy probes", () => void action(async () => { await clipboardAccess(navigator.clipboard.writeText(probeTable(probes))); setNotice("Exact probe samples copied with axis labels."); }), <Copy size={14}/>)}
      <button type="button" aria-pressed={wheelZoom} disabled={!usable} title="Wheel zoom is enabled by default. Turn off to scroll the panel; Ctrl+wheel still zooms." onClick={() => setWheelZoom(value => !value)}>Wheel zoom: {wheelZoom ? "on" : "off"}</button>
      <label className="spike-plot-wheel-target">Wheel target<select aria-label="Wheel zoom target" title="Pointer: zoom the hovered axis, or both axes inside the plot. Choose an axis to lock wheel zoom to it." value={wheelTarget} onChange={event => setWheelTarget(event.target.value as WheelPreference)}>
        <option value="auto">Pointer</option>{cartesian && <><option value="both">Both axes</option><option value="x">X axis</option><option value="y">Y axis</option></>}{polar && <><option value="radial">Radius</option><option value="angular">Angle</option></>}{scene && <><option value="x">X axis</option><option value="y">Y axis</option><option value="z">Z axis</option></>}
      </select></label>
      {button("Copy image", () => void copyImage(), <Image size={14}/>)}{button("Copy data", () => void copyData(), <Copy size={14}/>)}
      {button("Paste traces", () => void paste(), <ClipboardPaste size={14}/>, !usable || busy || !canPaste)}
      {comparisons.length > 0 && button("Clear pasted", () => { setComparisons([]); setNotice("Clipboard comparisons removed."); }, <X size={14}/>)}
    </CommandStrip>
    {!!probes.length && <div className="spike-plot-probes" aria-label="Pinned exact samples" aria-live="polite">
      {probes.map((probe, index) => <div key={index}><strong>{index ? "B" : "A"} · {probe.trace}{probe.comparison ? " · comparison" : ""}</strong><span>Sample {probe.index} · {probe.xLabel}: {probe.x.toPrecision(7)} · {probe.yLabel}: {probe.y.toPrecision(7)}</span></div>)}
      {probeDelta(probes) && <div><strong>B − A</strong><span>Δ {probes[0].xLabel}: {probeDelta(probes)!.x.toPrecision(7)} · Δ {probes[0].yLabel}: {probeDelta(probes)!.y.toPrecision(7)}</span></div>}
    </div>}
    <div className="spike-plot-surface" onContextMenu={event => { event.preventDefault(); event.stopPropagation(); openMenu(event.clientX, event.clientY); }}>
      <div ref={host} className="trace-plot-canvas" tabIndex={0} role="group" aria-label={`${title}. Wheel zooms; hover an axis to zoom only it, or choose Wheel target. Shift+wheel pans; right-click for plot actions.`}
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
    {!!colorScales.length && <div className="spike-plot-value-scales" aria-label="Result color scales">{colorScales.map((scale, index) => <ResultValueScale key={index} {...scale}/>)}</div>}
    <div className="spike-plot-hint">{scene && <span className="spike-plot-scene-labels">{["xaxis", "yaxis", "zaxis"].map(key => plotAxisLabel((layout.scene as Record<string, unknown> | undefined)?.[key])).filter(Boolean).join(" · ")}</span>}{wheelZoom ? "Wheel: zoom · Axis hover / Wheel target: one axis · " : "Wheel: scroll panel · Ctrl+wheel: zoom · "}{cartesian ? "Shift+wheel: pan · " : scene ? "Drag: orbit · " : "Rim: angle zoom · "}Ctrl+C: image · Ctrl+Shift+C: data{canPaste ? " · Ctrl+V: paste" : ""}</div>
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
      {contextActions.map(item => <button key={item.label} role="menuitem" disabled={!usable || item.disabled}
        onClick={() => { setMenu(null); item.onSelect(); }}>{item.label}</button>)}
      {[{ name: "Fit plot", run: reset }, { name: "Axes and grid…", run: editAxes, disabled: !cartesian }, { name: "Zoom in", run: () => zoom(.8) }, { name: "Zoom out", run: () => zoom(1.25) },
        { name: "Open plot data in script", run: openScript }, { name: "Copy image · Ctrl+C", run: () => void copyImage() }, { name: "Copy data · Ctrl+Shift+C", run: () => void copyData() },
        { name: "Paste traces · Ctrl+V", run: () => void paste(), disabled: !canPaste },
        { name: "Paste X/Y table…", run: () => setPasteOpen(true), disabled: !canPaste }, { name: "Download PNG", run: () => void downloadImage() },
        { name: "Clear pasted comparisons", run: () => setComparisons([]), disabled: !comparisons.length }].map(item => <button key={item.name} role="menuitem" disabled={!usable || busy || item.disabled} onClick={() => { setMenu(null); item.run(); host.current?.focus(); }}>{item.name}</button>)}
    </div>, document.body)}
  </section>;
}
