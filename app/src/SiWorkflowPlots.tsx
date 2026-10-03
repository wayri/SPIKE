import { useEffect, useRef, useState } from "react";
import PlotlyChart from "./PlotlyChart";
import { reflectionMetrics } from "./siChannelResults";

export type Point = { x: number; y: number };
export type Curve = { name: string; points: Point[] };
const colors = ["#38bdf8", "#fbbf24", "#a78bfa", "#34d399", "#fb7185"];

export function nearestPointIndex(points: Point[], targetX: number): number {
  let nearest = -1;
  let nearestDistance = Infinity;
  points.forEach((point, index) => {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return;
    const distance = Math.abs(point.x - targetX);
    if (distance < nearestDistance) {
      nearest = index;
      nearestDistance = distance;
    }
  });
  return nearest;
}

export function svgViewBoxX(clientX: number, left: number, width: number, height: number, viewBoxWidth = 790, viewBoxHeight = 270): number {
  if (width <= 0 || height <= 0 || viewBoxWidth <= 0 || viewBoxHeight <= 0) return 0;
  const scale = Math.min(width / viewBoxWidth, height / viewBoxHeight);
  const renderedWidth = viewBoxWidth * scale;
  const horizontalInset = (width - renderedWidth) / 2;
  return (clientX - left - horizontalInset) / scale;
}

export function SiPlot({ title, curves, xLabel, yLabel }: { title: string; curves: Curve[]; xLabel: string; yLabel: string }) {
  const [expanded, setExpanded] = useState(false);
  const expandButton = useRef<HTMLButtonElement>(null);
  const expandedWindow = useRef<HTMLElement>(null);
  const restoreExpandedFocus = useRef(false);
  useEffect(() => {
    if (!expanded) {
      if (restoreExpandedFocus.current) expandButton.current?.focus();
      restoreExpandedFocus.current = false;
      return;
    }
    restoreExpandedFocus.current = true;
    const containKeyboardFocus = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setExpanded(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...(expandedWindow.current?.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])") ?? [])]
        .filter(element => !element.hasAttribute("disabled"));
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", containKeyboardFocus);
    return () => window.removeEventListener("keydown", containKeyboardFocus);
  }, [expanded]);
  const hasData = curves.some(curve => curve.points.some(point => Number.isFinite(point.x) && Number.isFinite(point.y)));
  if (!hasData) return <div className="si-plot"><h4>{title}</h4><p>No returned trace data.</p></div>;
  const data = curves.map((curve, index) => ({
    type: "scatter",
    mode: "lines",
    name: curve.name,
    x: curve.points.map(point => Number.isFinite(point.x) ? point.x : null),
    y: curve.points.map(point => Number.isFinite(point.y) ? point.y : null),
    connectgaps: false,
    line: { color: colors[index % colors.length], width: curves.length > 10 ? 0.6 : 1.7 },
    opacity: curves.length > 10 ? 0.35 : 1,
    hovertemplate: "%{x:.4g}, %{y:.4g}<extra></extra>",
  }));
  const layout = {
    paper_bgcolor: "#101c2c",
    plot_bgcolor: "#101c2c",
    font: { color: "#cbd5e1", size: 10 },
    margin: { t: 16, r: 22, b: 52, l: 66 },
    xaxis: { title: xLabel, gridcolor: "#334155", zerolinecolor: "#475569" },
    yaxis: { title: yLabel, gridcolor: "#334155", zerolinecolor: "#475569" },
    hovermode: "x",
    legend: { orientation: "h", x: 0, y: 1.08 },
  };
  const revision = `${title}:${xLabel}:${yLabel}:${curves.map(curve => `${curve.name}:${curve.points.length}`).join("|")}`;
  const chart = <div style={{ height: expanded ? "100%" : 320, minHeight: 280 }}>
    <PlotlyChart title={title} data={data} layout={layout} revision={revision} />
  </div>;
  return <><div className="si-plot"><div className="si-plot-heading"><h4>{title}</h4><button ref={expandButton} type="button" onClick={() => setExpanded(true)} aria-label={`Expand ${title}`}>Expand</button></div>{chart}</div>
    {expanded && <div className="si-plot-shade" role="presentation" onPointerDown={event => { if (event.target === event.currentTarget) setExpanded(false); }}>
      <section ref={expandedWindow} className="si-plot-window" role="dialog" aria-modal="true" aria-labelledby={`si-plot-title-${title.replace(/[^a-z0-9]+/gi, "-")}`}>
        <header><h3 id={`si-plot-title-${title.replace(/[^a-z0-9]+/gi, "-")}`}>{title}</h3><button type="button" autoFocus onClick={() => setExpanded(false)} aria-label={`Close expanded ${title}`}>Close</button></header>
        <div className="si-plot-window-body">{chart}</div>
      </section>
    </div>}
  </>;
}

type Row = Record<string, unknown>;
const rec = (v: unknown): Row => v && typeof v === "object" && !Array.isArray(v) ? v as Row : {};
const rows = (v: unknown): Row[] => Array.isArray(v) ? v.map(rec) : [];
function curve(name: string, points: Row[], x: string, y: string, xScale = 1): Curve {
  return { name, points: points.filter(p => typeof p[x] === "number" && typeof p[y] === "number").map(p => ({ x: Number(p[x]) * xScale, y: Number(p[y]) })) };
}
export default function SiWorkflowPlots({ result }: { result: Row }) {
  const network = rec(result.network), traces = rec(network.traces);
  const keys = Object.keys(traces);
  const [selected, setSelected] = useState("S21");
  const [metric, setMetric] = useState("magnitude_db");
  const [dbFloor, setDbFloor] = useState(-120);
  const [observed, setObserved] = useState(0);
  const [rxIndex, setRxIndex] = useState(0);
  const loaded = rows(result.loaded_transfers), time = rec(result.time_domain), rx = rows(time.receivers);
  const selectedRx = rx[Math.min(rxIndex, rx.length - 1)] ?? {};
  const eye = rows(selectedRx.traces).map((trace, i) => ({ name: `UI ${i}`, points: (trace.phase_ui as number[]).map((phase, j) => ({ x: phase, y: (trace.voltage_v as number[])[j] })) }));
  const tdr = rec(result.tdr);
  const reflection = reflectionMetrics(network);
  const floorDb = (c: Curve): Curve => ({ ...c, points: c.points.map(p => ({ ...p, y: Math.max(dbFloor, p.y) })) });
  const selectedKey = keys.includes(selected) ? selected : keys[0];
  const parameterPicker = useRef<HTMLDetailsElement>(null);
  return <div className="si-result-plots">
    <div className="si-fields"><div className="si-parameter-field"><span>S-parameter</span><details ref={parameterPicker} onKeyDown={event => { if (event.key === "Escape") { parameterPicker.current?.removeAttribute("open"); parameterPicker.current?.querySelector("summary")?.focus(); } }}><summary aria-label={`S-parameter ${selectedKey ?? "unavailable"}`}>{selectedKey ?? "No returned traces"}</summary><div className="si-parameter-options" role="group" aria-label="Choose S-parameter trace">{keys.map(key => <button type="button" key={key} aria-current={key === selectedKey ? "true" : undefined} onClick={() => { setSelected(key); parameterPicker.current?.removeAttribute("open"); parameterPicker.current?.querySelector("summary")?.focus(); }}>{key}</button>)}</div></details></div>
      <label>Quantity<select value={metric} onChange={e => setMetric(e.target.value)}><option value="magnitude_db">Magnitude (dB)</option><option value="phase_deg">Phase (degrees)</option><option value="magnitude">Linear magnitude</option></select></label>
      <label>Display floor (dB)<input type="number" value={dbFloor} max="0" min="-6000" onChange={e => { const n = Number(e.target.value); if (Number.isFinite(n) && n <= 0) setDbFloor(n); }} /></label></div>
    <SiPlot title="Edited channel S-parameters" curves={selectedKey ? [(metric === "magnitude_db" ? floorDb : (v: Curve) => v)(curve(selectedKey, rows(traces[selectedKey]), "frequency_hz", metric, 1e-9))] : []} xLabel="Frequency (GHz)" yLabel={metric} />
    <SiPlot title="Matched-port reflection magnitude" curves={reflection.reflectionMagnitude.map(item => ({ name: item.label, points: item.points.map(point => ({ x: point.x * 1e-9, y: point.y })) }))} xLabel="Frequency (GHz)" yLabel="|rho|" />
    <SiPlot title="Matched-port VSWR" curves={reflection.vswr.map(item => ({ name: item.label, points: item.points.map(point => ({ x: point.x * 1e-9, y: point.y })) }))} xLabel="Frequency (GHz)" yLabel="ratio" />
    <p>Matched-reference reflection and VSWR use worker-returned per-port samples. Infinite and non-passive VSWR statuses remain gaps. Older saved results without these samples show no returned trace data.</p>
    <label>Loaded transfer / crosstalk<select value={Math.min(observed, loaded.length - 1)} onChange={e => setObserved(Number(e.target.value))}>{loaded.map((t, i) => <option key={i} value={i}>Source port {Number(t.source_port) + 1} → observed port {Number(t.observed_port) + 1}</option>)}</select></label>
    <SiPlot title="Loaded voltage transfer at channel-facing ports" curves={[floorDb(curve("Vout / Vsource", rows(loaded[Math.min(observed, loaded.length - 1)]?.trace), "frequency_hz", "magnitude_db", 1e-9))]} xLabel="Frequency (GHz)" yLabel="Voltage gain (dB)" />
    <p>Values below {dbFloor} dB are clipped for display. Complete values remain in the exported result and Touchstone.</p>
    {time.status === "blocked" && <p className="sparam-error">Time domain blocked: {String(time.reason)}</p>}
    {rx.length > 0 && <><label>Receiver<select value={Math.min(rxIndex, rx.length - 1)} onChange={e => setRxIndex(Number(e.target.value))}>{rx.map((r, i) => <option key={i} value={i}>Port {Number(r.port) + 1}</option>)}</select></label>
      <div className="si-metrics">{["eye_height_v", "high_margin_v", "low_margin_v", "overshoot_v", "undershoot_v"].map(k => <div key={k}><span>{k.replace(/_/g, " ")}</span><b>{Number(selectedRx[k]).toPrecision(5)} V</b></div>)}</div>
      <SiPlot title="Receiver eye with deterministic aggressors" curves={eye} xLabel="Phase (UI)" yLabel="Voltage (V)" />
      <SiPlot title="Receiver waveform" curves={[curve("Receiver", rows(selectedRx.waveform), "time_s", "voltage_v", 1e9)]} xLabel="Time (ns)" yLabel="Voltage (V)" />
    </>}
    {tdr.status === "completed" && <SiPlot title="Channel TDR with reference terminations" curves={[curve("Impedance", rows(tdr.tdr), "time_s", "impedance_ohm", 1e9)]} xLabel="Time (ns)" yLabel="Impedance (ohm)" />}
    {tdr.status === "completed" && <SiPlot title="Channel TDR reflection" curves={[curve("Reflection", rows(tdr.tdr), "time_s", "reflection", 1e9)]} xLabel="Time (ns)" yLabel="rho" />}
    <p>Spatial E/H field plots: {String(rec(result.field_maps).reason ?? "No spatial field samples returned by this network result.")} Open a compatible field AnalysisResult to inspect returned vector samples.</p>
    <p>Eyes contain deterministic signals and crosstalk. Noise is reported separately; threshold margins are engineering measurements, not protocol compliance.</p>
  </div>;
}
