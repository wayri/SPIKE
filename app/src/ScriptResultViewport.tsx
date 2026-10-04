// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import PlotlyChart from "./PlotlyChart";
import SpatialDataViewport from "./SpatialDataViewport";
import { Activity, Crosshair, Table2, X } from "./icons";
import type { DataView, SpatialSample } from "./scriptDataViews";
import {
  admitScriptResultViews, defaultPlotIds, normalizeViewId, plotChoices, plotPresentation,
  probeRows, provenanceLabel, radiationDisplayNotice, combinedSpatialBounds, spatialChoices, physicalGeometry, matchingPhysicalGeometry,
} from "./scriptResultViewportModel";
import "./buttonStandard.css";
import "./ScriptResultViewport.css";

export type ScriptResultViewportProps = {
  views: unknown;
  runLabel: string;
  onClose: () => void;
  onExplore?: () => void;
};

const rangeText = (range: [number, number], unit: string) => `${range[0].toPrecision(6)} to ${range[1].toPrecision(6)}${unit ? ` ${unit}` : ""}`;

export default function ScriptResultViewport({ views: rawViews, runLabel, onClose, onExplore }: ScriptResultViewportProps) {
  const views = useMemo(() => admitScriptResultViews(rawViews), [rawViews]);
  const scenes = useMemo(() => spatialChoices(views), [views]);
  const plots = useMemo(() => plotChoices(views), [views]);
  const defaults = useMemo(() => defaultPlotIds(plots), [plots]);
  const [sceneId, setSceneId] = useState<string | null>(scenes[0]?.view.id ?? null);
  const [plotIds, setPlotIds] = useState<[string | null, string | null]>(defaults);
  const [selected, setSelected] = useState<number[]>([]);

  useEffect(() => {
    setSceneId(current => normalizeViewId(scenes.map(choice => choice.view), current));
    setPlotIds(current => [normalizeViewId(plots, current[0], 0), normalizeViewId(plots, current[1], 1)]);
  }, [scenes, plots]);
  useEffect(() => setSelected([]), [sceneId]);

  const sceneChoice = scenes.find(choice => choice.view.id === sceneId) ?? scenes[0];
  const scene = sceneChoice?.view;
  const physicalModel = useMemo(() => scene ? matchingPhysicalGeometry(scene, views) : null, [scene, views]);
  const standalonePhysical = scene ? physicalGeometry(scene) : null;
  const bounds = scene ? combinedSpatialBounds(scene, physicalModel) : null;
  const sceneSamples: SpatialSample[] = useMemo(() => scene?.kind === "spatial" ? scene.samples ?? []
    : scene?.kind === "mesh" ? (scene.vertices ?? []).map(([x, y, z]) => ({ x, y, z })) : [], [scene]);
  const selectedRows = scene ? probeRows(scene, selected[0] ?? -1) : [];

  if (!views.length) return <section className="script-result-viewport script-result-viewport--empty" aria-label="Script results viewport">
    <header className="script-result-header"><div><Activity size={20}/><span><h2>Script results</h2><small>{runLabel}</small></span></div><button type="button" className="secondary-btn" aria-label="Close script results" onClick={onClose}><X size={15}/><span>Close script results</span></button></header>
    <div className="script-result-empty" role="status"><h3>No supported numeric output</h3><p>This run did not publish an admitted spatial, mesh, line, or polar data view. Unsupported or malformed output is withheld from the viewport.</p>{onExplore && <button type="button" className="secondary-btn" aria-label="Open data explorer" onClick={onExplore}><Table2 size={15}/><span>Open data explorer</span></button>}</div>
  </section>;

  const hasSupported = scenes.length > 0 || plots.length > 0;
  return <section className={`script-result-viewport ${scenes.length ? "" : "script-result-viewport--plots-only"}`} aria-label="Script results viewport">
    <header className="script-result-header">
      <div><Activity size={20}/><span><h2>Simulation results</h2><small title={runLabel}>{runLabel} · admitted script output</small></span></div>
      <div className="script-result-header-actions">{onExplore && <button type="button" className="secondary-btn" aria-label="Explore data" onClick={onExplore}><Table2 size={15}/><span>Explore data</span></button>}<button type="button" className="secondary-btn" aria-label="Close results" onClick={onClose}><X size={15}/><span>Close results</span></button></div>
    </header>
    {!hasSupported ? <div className="script-result-empty" role="status"><h3>No viewport-compatible datasets</h3><p>The run returned admitted tables or scatter data, but no spatial, mesh, line, or polar view that this result surface can display.</p></div> : <div className="script-result-body">
      {scenes.length > 0 && scene && <article className="script-result-scene">
        <div className="script-result-card-header"><span><h3>{scene.title}</h3><small>{sceneChoice.role === "radiation" ? "3D radiation display" : standalonePhysical ? "Physical model geometry" : scene.kind === "mesh" ? "Returned mesh" : "Returned spatial samples"}</small></span><label>3D dataset<select aria-label="3D result dataset" value={scene.id} onChange={event => setSceneId(event.target.value)}>{scenes.map(choice => <option key={choice.view.id} value={choice.view.id}>{choice.view.title} · {choice.role}</option>)}</select></label></div>
        <div className="script-result-evidence">
          <span><b>Quantity</b>{scene.kind === "spatial" ? `${scene.quantity} [${scene.value_unit}]` : "mesh geometry"}</span>
          <span title={scene.provenance}><b>Provenance</b>{provenanceLabel(scene)}</span>
          {bounds && <span><b>Bounds</b>X {rangeText(bounds.x, bounds.unit)} · Y {rangeText(bounds.y, bounds.unit)} · Z {rangeText(bounds.z, bounds.unit)}</span>}
        </div>
        <div className="script-result-notices">{radiationDisplayNotice(scene, !!physicalModel) && <p className="script-result-caveat">{radiationDisplayNotice(scene, !!physicalModel)}</p>}
        {physicalModel && <p className="script-result-caveat">{standalonePhysical?.phase === "geometry" ? "Model geometry preview; no solved field values are shown. " : "Physical model and selected dataset share the published scene, run, metre units, and coordinate frame. "}Copper / PEC is amber; dielectric is translucent blue. Coordinates and region materials come from the worker.</p>}
        {scene.kind === "mesh" && !standalonePhysical && <p className="script-result-caveat">Triangle connectivity and vertex coordinates are shown exactly as published. This preview does not infer board alignment, materials, ports, or solved field values.</p>}
        </div><div className="script-result-scene-stage"><SpatialDataViewport samples={sceneSamples} physicalModel={physicalModel} triangles={scene.kind === "mesh" ? scene.triangles : undefined} selected={selected} onSelect={setSelected}/></div>
        <div className="script-result-probe" aria-live="polite"><div><Crosshair size={15}/><b>Sample probe</b><span>{selectedRows.length ? `selected index ${selected[0]}` : "Select a returned point or mesh vertex"}</span></div>{selectedRows.length > 0 && <dl>{selectedRows.map(row => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}{row.unit ? ` ${row.unit}` : ""}</dd></div>)}</dl>}</div>
      </article>}
      {plots.length > 0 && <section className="script-result-plots" aria-label="Published result plots">
        {[0, 1].map(slot => {
          const plot = plots.find(view => view.id === plotIds[slot]);
          return <article className="script-result-plot-card" key={slot}>
            <div className="script-result-card-header"><span><h3>{plot?.title ?? `Plot ${slot + 1}`}</h3><small>{plot ? provenanceLabel(plot) : "No additional line or polar dataset was returned"}</small></span><label>Plot {slot + 1}<select aria-label={`Result plot ${slot + 1} dataset`} value={plot?.id ?? ""} onChange={event => setPlotIds(current => current.map((value, index) => index === slot ? event.target.value : value) as [string | null, string | null])}><option value="" disabled>Select dataset</option>{plots.map(view => <option key={view.id} value={view.id}>{view.title}</option>)}</select></label></div>
            {plot ? <div className="script-result-plot-surface"><PlotlyChart title={plot.title} {...plotPresentation(plot)} revision={`script-main:${slot}:${plot.id}`}/></div> : <div className="script-result-plot-empty">A second admitted line or polar dataset is needed for this plot slot.</div>}
          </article>;
        })}
      </section>}
    </div>}
  </section>;
}
