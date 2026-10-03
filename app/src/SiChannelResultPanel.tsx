// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
import { useMemo, useState } from "react";
import { AlertTriangle, Download, Maximize2, Minimize2 } from "lucide-react";
import PlotlyChart from "./PlotlyChart";
import { buildSiChannelHtmlReport, buildSiCrosstalkCsv, buildSiImpedanceCsv, floorSiDb, normalizeSiChannelResult, SiChartSeries } from "./siChannelResults";

type Props = { result: Record<string, unknown>; onStatus: (message: string) => void };
type Tab = "s" | "reflection" | "tdr" | "xtalk" | "z" | "eye" | "mixed";

const download = (name: string, body: string, type: string) => {
  const url = URL.createObjectURL(new Blob([body], { type }));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url);
};

const engineering = (value: number) => {
  if (!Number.isFinite(value)) return "—";
  const magnitude = Math.abs(value);
  const prefixes: [number, string][] = [[1e12, "T"], [1e9, "G"], [1e6, "M"], [1e3, "k"], [1, ""], [1e-3, "m"], [1e-6, "µ"], [1e-9, "n"], [1e-12, "p"]];
  const [scale, prefix] = prefixes.find(([candidate]) => magnitude >= candidate) ?? [1e-15, "f"];
  return `${(value / scale).toPrecision(6)} ${prefix}`;
};

function Chart({ title, xLabel, yLabel, series, defaultShowAll = false }: { title: string; xLabel: string; yLabel: string; series: readonly SiChartSeries[]; defaultShowAll?: boolean }) {
  const available = useMemo(() => series.filter(item => item.points.length), [series]);
  const [traceId, setTraceId] = useState("");
  const [activeCursor, setActiveCursor] = useState<"A" | "B">("A");
  const [cursorA, setCursorA] = useState<{ x: number; y: number } | null>(null);
  const [cursorB, setCursorB] = useState<{ x: number; y: number } | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [showAll, setShowAll] = useState(defaultShowAll);
  const selected = available.find(item => item.id === traceId) ?? available[0];
  const displayed = showAll ? available : selected ? available.filter(item => item.id === selected.id) : [];
  const placeCursor = (targetX: number) => {
    if (!selected?.points.length) return;
    const nearest = selected.points.reduce((best, point) => Math.abs(point.x - targetX) < Math.abs(best.x - targetX) ? point : best, selected.points[0]);
    if (!nearest) return;
    (activeCursor === "A" ? setCursorA : setCursorB)({ x: nearest.x, y: nearest.y });
  };
  if (!displayed.length) return <div className="si-channel-empty">No retained samples for this result.</div>;
  const colors = ["#67e8f9", "#fbbf24", "#a78bfa", "#4ade80", "#fb7185", "#60a5fa"];
  const data = displayed.map((item, index) => ({ type: "scatter", mode: "lines", name: item.label,
    x: item.points.map(point => point.x), y: item.points.map(point => point.y), connectgaps: false,
    line: { color: colors[index % colors.length], width: 1.35 }, hovertemplate: "%{x:.6g}, %{y:.6g}<extra></extra>" }));
  const cursors: { id: "A" | "B"; point: { x: number; y: number }; color: string }[] = [];
  if (cursorA) cursors.push({ id: "A", point: cursorA, color: "#fbbf24" });
  if (cursorB) cursors.push({ id: "B", point: cursorB, color: "#67e8f9" });
  const cursorShapes = cursors.flatMap(({ point, color }) => [
    { type: "line", x0: point.x, x1: point.x, y0: 0, y1: 1, xref: "x", yref: "paper", line: { color, width: 1, dash: "dot" } },
    { type: "line", x0: 0, x1: 1, y0: point.y, y1: point.y, xref: "paper", yref: "y", line: { color, width: 1, dash: "dot" } },
  ]);
  const cursorAnnotations = cursors.map(({ id, point, color }) => ({
    x: point.x, y: 1, xref: "x", yref: "paper", text: id, showarrow: false, xanchor: "left", font: { color },
  }));
  const layout = { paper_bgcolor: "#08141b", plot_bgcolor: "#08141b", font: { color: "#b3c5cc", size: 10 },
    margin: { t: 18, r: 22, b: 52, l: 66 }, xaxis: { title: xLabel, gridcolor: "#263d47" }, yaxis: { title: yLabel, gridcolor: "#263d47" },
    showlegend: false, hovermode: "x", shapes: cursorShapes, annotations: cursorAnnotations };
  const revision = `${title}:${displayed.map(item => item.id).join("|")}:${cursorA?.x ?? ""}:${cursorB?.x ?? ""}`;
  return <section className={`si-channel-chart ${expanded ? "expanded" : ""}`}><div className="si-chart-toolbar"><h4>{title}</h4><label>Trace<select value={selected?.id ?? ""} onChange={event => { setTraceId(event.target.value); setCursorA(null); setCursorB(null); }}>{available.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>{available.length > 1 && <button className={showAll ? "selected" : ""} aria-pressed={showAll} onClick={() => setShowAll(value => !value)}>{showAll ? "Show selected" : `Compare all (${available.length})`}</button>}<button className={activeCursor === "A" ? "selected" : ""} onClick={() => setActiveCursor("A")}>Cursor A</button><button className={activeCursor === "B" ? "selected" : ""} onClick={() => setActiveCursor("B")}>Cursor B</button><button title={expanded ? "Restore plot" : "Maximize plot"} onClick={() => setExpanded(value => !value)}>{expanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}</button></div><div style={{ height: expanded ? "calc(100vh - 170px)" : 320 }}><PlotlyChart title={title} data={data} layout={layout} revision={revision} onPointClick={(point: { x: number }) => placeCursor(point.x)} /></div><div className="si-cursor-readout"><span>A: {cursorA ? `${engineering(cursorA.x)}${xLabel.includes("Hz") ? "Hz" : xLabel.includes("s") ? "s" : ""}, ${engineering(cursorA.y)}${yLabel}` : "click plot"}</span><span>B: {cursorB ? `${engineering(cursorB.x)}${xLabel.includes("Hz") ? "Hz" : xLabel.includes("s") ? "s" : ""}, ${engineering(cursorB.y)}${yLabel}` : "click plot"}</span><b>Δ: {cursorA && cursorB ? `${engineering(cursorB.x - cursorA.x)} x, ${engineering(cursorB.y - cursorA.y)} y` : "place A and B"}</b></div><div className="si-channel-legend">{displayed.map((item, index) => <span key={item.id} className={`series-${index % 6}`}>{item.label} ({item.points.length} retained samples)</span>)}</div></section>;
}

export default function SiChannelResultPanel({ result, onStatus }: Props) {
  const [tab, setTab] = useState<Tab>("s");
  const charts = useMemo(() => normalizeSiChannelResult(result), [result]);
  const crosstalk = [charts.nextDb, charts.fextDb].filter((item): item is SiChartSeries => item !== null && item.points.length > 0);
  const exportJson = () => { download("geometry-channel.experimental.json", JSON.stringify(result, null, 2), "application/json"); onStatus("Experimental SI channel JSON exported"); };
  const exportReport = () => { download("geometry-channel.experimental.html", buildSiChannelHtmlReport(result), "text/html"); onStatus("Experimental SI channel SVG report exported"); };
  return <section className="si-channel-results">
    <header><div><b>Native channel results</b><small>Ports: {charts.portOrder.join(" → ") || "worker-declared order"}</small></div><div><button onClick={exportJson}><Download size={13} /> JSON</button><button onClick={exportReport}><Download size={13} /> SVG report</button></div></header>
    <div className="si-channel-warning"><AlertTriangle size={14} /> Experimental only: production qualified false; compliance {charts.complianceStatus}. Values are not protocol-compliance or signoff evidence.</div>
    <nav aria-label="SI result views">{(["s", "reflection", "tdr", "xtalk", "z", "eye", "mixed"] as Tab[]).map(item => <button key={item} className={tab === item ? "selected" : ""} aria-current={tab === item ? "page" : undefined} onClick={() => setTab(item)}>{({ s: "S parameters", reflection: "Reflections / VSWR", tdr: "TDR / TDT", xtalk: "NEXT / FEXT", z: "Impedance / resonance", eye: "Eye", mixed: "Mixed mode" } as Record<Tab, string>)[item]}</button>)}</nav>
    {tab === "s" && <><Chart title="S magnitude" xLabel="Frequency (Hz)" yLabel="dB" series={charts.sMagnitudeDb} /><Chart title="S phase" xLabel="Frequency (Hz)" yLabel="deg" series={charts.sPhaseDeg} /></>}
    {tab === "reflection" && <><p>Matched-reference port reflection and VSWR use worker-returned per-port samples. Infinite and non-passive VSWR statuses remain gaps. Older saved results without these samples show no retained trace data.</p><Chart title="Reflection magnitude" xLabel="Frequency (Hz)" yLabel="|rho|" series={charts.reflectionMagnitude} /><Chart title="VSWR" xLabel="Frequency (Hz)" yLabel="ratio" series={charts.vswr} /></>}
    {tab === "tdr" && <><Chart title="TDR impedance" xLabel="Time (s)" yLabel="ohm" series={[charts.tdrImpedanceOhm]} /><Chart title="TDR reflection" xLabel="Time (s)" yLabel="rho" series={[charts.tdrReflection]} /><Chart title="TDT normalized step" xLabel="Time (s)" yLabel="normalized" series={[charts.tdtNormalizedStep]} /></>}
    {tab === "xtalk" && <>
      <div className="si-channel-intro"><b>NEXT / FEXT from the bounded coupled channel</b><p>Matched-port power-wave coupling and loaded victim/source voltage transfer are separate results. The plotted dB floor is −160 dB; CSV preserves retained values.</p></div>
      <button onClick={() => { download("si-crosstalk.csv", buildSiCrosstalkCsv(result), "text/csv;charset=utf-8"); onStatus("Retained crosstalk samples exported as CSV"); }}><Download size={13} /> Crosstalk CSV</button>
      {crosstalk.length > 0 ? <><Chart title="Matched NEXT / FEXT" xLabel="Frequency (Hz)" yLabel="dB" series={floorSiDb(crosstalk)} defaultShowAll /><Chart title="Matched linear coupling" xLabel="Frequency (Hz)" yLabel="power-wave ratio" series={charts.crosstalkLinear} defaultShowAll /></> : <div className="si-channel-empty">No matched NEXT/FEXT samples were returned for this result.</div>}
      {charts.loadedCrosstalkDb.some(item => item.points.length) ? <><Chart title="Loaded victim/source voltage transfer" xLabel="Frequency (Hz)" yLabel="dB V/V" series={floorSiDb(charts.loadedCrosstalkDb)} defaultShowAll /><Chart title="Loaded linear voltage transfer" xLabel="Frequency (Hz)" yLabel="V/V" series={charts.loadedCrosstalkLinear} defaultShowAll /></> : <div className="si-channel-empty">No loaded victim/source transfer was returned.</div>}
      {charts.crosstalkVoltage.length > 0 ? <Chart title="Source and victim waveforms" xLabel="Time (s)" yLabel="V" series={charts.crosstalkVoltage} /> : <p>No voltage waveform retained: {charts.crosstalkTimeStatus}. The UI does not manufacture waveforms from magnitude-only traces.</p>}
    </>}
    {tab === "z" && <>
      <button onClick={() => { download("si-driving-impedance.csv", buildSiImpedanceCsv(result), "text/csv;charset=utf-8"); onStatus("Retained impedance samples and masks exported"); }}><Download size={13} /> Impedance CSV</button>
      <p>Frequency-domain driving-point impedance; other ports terminated ({charts.impedanceTermination}), selected-port load excluded. This is not TDR impedance. Open/pole and unresolved samples remain gaps.</p>
      <Chart title="Resistance R(f)" xLabel="Frequency (Hz)" yLabel="ohm" series={charts.impedanceReal} />
      <Chart title="Reactance X(f)" xLabel="Frequency (Hz)" yLabel="ohm" series={charts.impedanceImag} />
      <Chart title="Magnitude |Z(f)|" xLabel="Frequency (Hz)" yLabel="ohm" series={charts.impedanceMagnitude} />
      <h4>Sampled resonance candidates</h4><p>Finite-grid peaks, dips and reactance sign changes only—not fitted poles, Q values or physical resonance qualification.</p>
      {charts.impedanceCandidates.length ? <ul>{charts.impedanceCandidates.map((candidate, index) => <li key={index}>{candidate.port}: {candidate.kind}; {candidate.frequencyHz === null ? "bracket only" : `${engineering(candidate.frequencyHz)}Hz`}; bracket {candidate.bracketHz.map(value => `${engineering(value)}Hz`).join(" – ")}</li>)}</ul> : <p>No candidates retained. This does not establish absence of resonances.</p>}
      {charts.impedanceCandidateTruncated && <p>Worker candidate output was truncated.</p>}
    </>}
    {tab === "eye" && <>
      {charts.eye.length > 0 && <Chart title={`Normalized NRZ eye${charts.eyeSamplesPerUi ? ` (${charts.eyeSamplesPerUi} samples/UI)` : ""}`} xLabel="Unit interval" yLabel="normalized" series={charts.eye.slice(0, 96)} />}
      {charts.pam4EyeHeights.length > 0 && <Chart title="PAM4 eye height by sampling phase" xLabel="Unit interval" yLabel="normalized" series={charts.pam4EyeHeights} />}
      {charts.pam4BerProxies.length > 0 && <Chart title="PAM4 BER proxies by sampling phase" xLabel="Unit interval" yLabel="BER proxy" series={charts.pam4BerProxies} />}
      {charts.eye.length === 0 && charts.pam4EyeHeights.length === 0 && <div className="si-channel-empty">No retained eye samples for this result.</div>}
    </>}
    {tab === "mixed" && <div className="si-channel-metrics">{Object.keys(charts.mixedModeMetrics).length ? Object.entries(charts.mixedModeMetrics).map(([name, value]) => <div key={name}><span>{name}</span><b>{value.toPrecision(6)}</b></div>) : <div className="si-channel-empty">No mixed-mode metrics were retained by this bounded result. The UI does not derive them from single-ended data.</div>}</div>}
    <p className="si-channel-warning">E/H field plots require returned spatial electric or magnetic vector samples in an AnalysisResult. This channel result contains network and time-domain samples only.</p>
  </section>;
}
