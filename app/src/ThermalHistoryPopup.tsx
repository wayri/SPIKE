// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState } from "react";
import PlotlyChart from "./PlotlyChart";
import type { ThermalProbeHistoryResult } from "./thermalProbeHistory";
import "./buttonStandard.css";
import "./ThermalHistoryPopup.css";

export default function ThermalHistoryPopup({ history, onClose }: {
  history: ThermalProbeHistoryResult; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useId();
  const [seriesIndex, setSeriesIndex] = useState(0);
  useEffect(() => setSeriesIndex(0), [history]);
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  const selectedSeries = history.traces[Math.min(seriesIndex, history.traces.length - 1)];
  const traces = (selectedSeries ? [selectedSeries] : []).map(series => ({ type: "scatter", mode: "lines+markers", name: series.label,
    x: series.samples.map(sample => sample.time_s),
    y: series.samples.map(sample => series.unit === "K" ? sample.temperature - 273.15 : sample.temperature),
    hovertemplate: "%{x:.6g} s<br>%{y:.6g} °C<extra>%{fullData.name}</extra>", marker: { size: 4 } }));
  return <dialog ref={dialog} className="thermal-history-popup" aria-labelledby={title}
    onCancel={event => { event.preventDefault(); onClose(); }} onKeyDown={event => event.stopPropagation()}>
    <header><h2 id={title}>Temperature vs time</h2><button type="button" aria-label="Close temperature history" onClick={onClose}>×</button></header>
    <p className="thermal-history-popup__identity">{history.label}</p>
    {history.traces.length > 1 && <label>Retained temperature curve (1 to {history.traces.length})
      <input type="number" min="1" max={history.traces.length} value={seriesIndex + 1}
        onChange={event => { const value = Number(event.target.value); if (Number.isInteger(value) && value >= 1 && value <= history.traces.length) setSeriesIndex(value - 1); }} />
      <span>{selectedSeries?.label}</span></label>}
    {traces.length ? <>
      <PlotlyChart title="Saved transient temperature" revision={JSON.stringify([selectedSeries?.identity, selectedSeries?.samples])}
        data={traces} layout={{ xaxis: { title: { text: "Time (s)" }, automargin: true },
          yaxis: { title: { text: "Temperature (°C)" }, automargin: true }, hovermode: "closest",
          margin: { t: 20, l: 70, r: 25, b: 75 }, legend: { orientation: "h", y: -.25 } }} />
      <p>Exact saved time samples. Lines connect samples for display; they are not additional solved time steps.
        This plot preserves the selected cell, component or solid-node identity and the result's model limitations.</p>
    </> : <p role="status">{history.unavailableReason ?? "No saved transient temperature samples are available."}
      {" "}Run a transient thermal study with this object included and retain its time samples, then reopen this plot.</p>}
    <footer><button type="button" onClick={onClose}>Close</button></footer>
  </dialog>;
}
