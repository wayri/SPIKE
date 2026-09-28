// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import type Plotly from "plotly.js-dist-min";

type Props = { data: Record<string, unknown>[]; layout: Record<string, unknown>; revision: string };

export default function PlotlyChart({ data, layout, revision }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const plotlyRef = useRef<typeof Plotly | null>(null);
  const renderRevision = useRef(0);
  const [ready, setReady] = useState(0);
  const [state, setState] = useState({ loading: true, error: "" });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    const element = host.current;
    void import("plotly.js-dist-min").then(module => {
      if (!alive) return;
      plotlyRef.current = module.default;
      setReady(value => value + 1);
    }, reason => { if (alive) setState({ loading: false, error: reason instanceof Error ? reason.message : String(reason) }); });
    return () => { alive = false; renderRevision.current += 1; if (element && plotlyRef.current) plotlyRef.current.purge(element); plotlyRef.current = null; };
  }, [retry]);
  useEffect(() => {
    const plotly = plotlyRef.current, element = host.current;
    if (!plotly || !element) return;
    const token = ++renderRevision.current;
    setState({ loading: true, error: "" });
    void plotly.react(element, data, { ...layout, autosize: true }, { responsive: true, displaylogo: false }).then(() => {
      if (token === renderRevision.current) setState({ loading: false, error: "" });
    }, reason => { if (token === renderRevision.current) setState({ loading: false, error: reason instanceof Error ? reason.message : String(reason) }); });
  }, [data, layout, revision, ready]);
  useEffect(() => {
    const element = host.current;
    const resize = () => { if (element && plotlyRef.current) plotlyRef.current.Plots.resize(element); };
    window.addEventListener("resize", resize);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
    if (element) observer?.observe(element);
    return () => { window.removeEventListener("resize", resize); observer?.disconnect(); };
  }, []);
  return <div className="trace-plot-host"><div ref={host} className="trace-plot-canvas" aria-label="Interactive trace result graph" />
    {state.loading && <div className="trace-plot-loading" role="status">Loading interactive graph…</div>}
    {state.error && <div className="trace-plot-error" role="alert"><b>Graph rendering failed</b><span>{state.error}</span><button onClick={() => setRetry(value => value + 1)}>Retry</button></div>}
  </div>;
}
