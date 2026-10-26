// SPDX-License-Identifier: Apache-2.0
import type { AdmittedSiSpatialNoise, SiSpatialNoiseDisplay, SiSpatialNoiseSettings } from "./siSpatialNoise";
import { availableSiSpatialNoiseQuantities, searchSiSpatialNoiseSamples } from "./siSpatialNoise";
import "./buttonStandard.css";
import "./SiSpatialNoiseControls.css";

export default function SiSpatialNoiseControls({ data, settings, display, selectedSample, query, error, onSettings, onSelectSample, onQuery, onRetry }: {
  data: AdmittedSiSpatialNoise | null; settings: SiSpatialNoiseSettings; display: SiSpatialNoiseDisplay | null;
  selectedSample: number | null; query: string; error?: string; onSettings: (settings: SiSpatialNoiseSettings) => void;
  onSelectSample: (index: number) => void; onQuery: (query: string) => void; onRetry?: () => void;
}) {
  if (error) return <section className="si-spatial-controls is-error" aria-label="SI spatial noise controls"><b>Spatial SI data unavailable</b><p role="alert">{error}</p>{onRetry && <button type="button" onClick={onRetry}>Retry data</button>}</section>;
  if (!data) return <section className="si-spatial-controls is-empty" aria-label="SI spatial noise controls"><b>No spatial SI samples</b><p>Import supported trace voltage or electric-field samples, review their source identities, and explicitly bind to this design revision and request.</p></section>;
  const quantities = availableSiSpatialNoiseQuantities(data), matches = display ? searchSiSpatialNoiseSamples(display, query) : [];
  const selected = display && selectedSample !== null && selectedSample >= 0 && selectedSample < display.values.length ? selectedSample : null;
  const update = (change: Partial<SiSpatialNoiseSettings>) => onSettings({ ...settings, ...change });
  return <section className="si-spatial-controls" aria-label="SI spatial noise controls">
    <header><b>Spatial SI noise</b><span className={`model-status ${data.modelStatus}`}>{data.modelStatus}</span></header>
    <div className="si-spatial-grid">
      <label>Quantity<select value={settings.quantity} onChange={event => update({ quantity: event.target.value as SiSpatialNoiseSettings["quantity"], component: "norm", projection: "magnitude" })}>{quantities.map(quantity => <option key={quantity} value={quantity}>{quantity === "induced_voltage" ? "Victim trace voltage" : "Surrounding E-field"}</option>)}</select></label>
      <label>Frequency<select value={settings.frequencyIndex} onChange={event => update({ frequencyIndex: Number(event.target.value) })}>{data.frequenciesHz.map((frequency, index) => <option key={frequency} value={index}>{frequency.toLocaleString()} Hz</option>)}</select></label>
      {settings.quantity === "electric_field" && <label>Component<select value={settings.component} onChange={event => { const component = event.target.value as SiSpatialNoiseSettings["component"]; update({ component, projection: component === "norm" ? "magnitude" : settings.projection }); }}><option value="norm">Vector magnitude</option><option value="x">X</option><option value="y">Y</option><option value="z">Z</option></select></label>}
      <label>Projection<select value={settings.projection} onChange={event => update({ projection: event.target.value as SiSpatialNoiseSettings["projection"] })} disabled={settings.quantity === "electric_field" && settings.component === "norm"}><option value="magnitude">Magnitude</option><option value="real">Signed real</option><option value="imaginary">Signed imaginary</option><option value="phase">Phase</option><option value="instantaneous">Phase-rotated real (phasor units)</option></select></label>
      {settings.projection === "instantaneous" && <label>Phase <input type="number" value={settings.phaseDeg} min={-360} max={360} onChange={event => update({ phaseDeg: Number(event.target.value) })} /> deg</label>}
      <label>Opacity <input type="range" min={.05} max={1} step={.05} value={settings.opacity} onChange={event => update({ opacity: Number(event.target.value) })} /></label>
      <label>Scale limit <input type="number" min={0} placeholder="Auto" value={settings.scaleLimit ?? ""} onChange={event => update({ scaleLimit: event.target.value === "" ? null : Number(event.target.value) })} /> {settings.projection === "phase" ? "degrees" : settings.quantity === "induced_voltage" ? "V" : "V/m"}</label>
    </div>
    <label className="si-spatial-search">Find sample<input type="search" value={query} placeholder="Segment or field sample ID" onChange={event => onQuery(event.target.value)} /></label>
    <select className="si-spatial-samples" aria-label="Matching spatial SI samples" size={Math.min(5, Math.max(2, matches.length))} value={selected ?? ""} onChange={event => onSelectSample(Number(event.target.value))}>{matches.slice(0, 200).map(index => <option key={`${display!.sourceIds[index]}-${index}`} value={index}>{display!.sourceIds[index]} · {display!.values[index].toPrecision(5)} {display!.unit}</option>)}</select>
    {matches.length > 200 && <small>Showing the first 200 of {matches.length} matching samples; refine the search or click a point in the viewport.</small>}
    {display ? <><p className="si-spatial-probe" role="status">{selected === null ? `${display.values.length} returned samples` : `Sample ${selected}: ${display.values[selected].toPrecision(6)} ${display.unit} at ${display.positionsMm[selected].map(value => value.toPrecision(5)).join(", ")} mm`}</p>{display.notices.map(notice => <small key={notice}>{notice}</small>)}</> : <p role="alert">The selected projection is unavailable for these returned samples.</p>}
  </section>;
}
