// SPDX-License-Identifier: Apache-2.0
import { forwardRef, type CSSProperties } from "react";
import { traceSparklinePoints, type TracePopupModel, type TracePopupSeries } from "./traceValuePopupModel";
import { numericExtent } from "./numericRange";
import "./TraceValuePopup.css";

function compactValue(value: number | undefined, unit: string): string {
  return value === undefined ? "unavailable" : `${value.toPrecision(5)} ${unit}`;
}

function Sparkline({ series }: { series: TracePopupSeries }) {
  if (series.history.length < 2) return <small className="trace-value-popup-no-history">Saved time history unavailable</small>;
  const values = series.history.map(point => point.value);
  const { minimum, maximum } = numericExtent(values);
  const points = traceSparklinePoints(series.history).map(([x, y]) => `${(x + 2).toFixed(2)},${(y + 4).toFixed(2)}`).join(" ");
  const start = series.history[0].timeS, end = series.history[series.history.length - 1].timeS;
  return <div className="trace-value-popup-graph">
    <svg viewBox="0 0 96 28" role="img" aria-label={`${series.label} saved history from ${start} to ${end} seconds`}>
      <polyline points={points} fill="none" vectorEffect="non-scaling-stroke" />
    </svg>
    <div className="trace-value-popup-range"><small>{minimum.toPrecision(4)} {series.unit}</small><small>{maximum.toPrecision(4)} {series.unit}</small></div>
    <small>{start.toPrecision(3)}–{end.toPrecision(3)} s · {series.history.length} saved samples</small>
  </div>;
}

const TraceValuePopup = forwardRef<HTMLElement, { model: TracePopupModel; style?: CSSProperties }>(function TraceValuePopup({ model, style }, ref) {
  return <aside ref={ref} className="trace-value-popup" style={style} aria-label={`Saved values for trace ${model.net}`}>
    <div className="trace-value-popup-heading"><strong>{model.net}</strong><span>PINNED TRACE</span></div>
    <small title={model.traceId}>{model.layer} · {model.traceId}</small>
    {model.series.map(series => <section key={series.quantity}>
      <div><span>{series.label}</span><b>{compactValue(series.value, series.unit)}</b></div>
      <small className="trace-value-popup-source">{series.source === "trace_id" ? "Exact trace sample" : "Nearby saved sample (within 0.5 mm)"}</small>
      <Sparkline series={series} />
    </section>)}
    {model.unavailable.map(message => <p key={message}>{message}</p>)}
  </aside>;
});

export default TraceValuePopup;
