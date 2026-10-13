// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import InteractivePlot from "./InteractivePlot";
import { Su2ResultsDialog } from "./Su2ResultsDialog";
import type { PlotTrace } from "./plotClipboard";
import "./Su2ResultPanel.css";

type Row = Record<string, unknown>;
type Figure = { title: string; data: PlotTrace[]; layout: Row };
type Presentation = { title: string; status: string; error: string; plots: Figure[]; previews: Figure[]; details: [string, string][]; residuals: [string, number][]; metrics: [string, number][]; provenance: [string, string][]; limitations: string[] };
const record = (value: unknown): Row => value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
function numbers(value: unknown, minimum = 1, maximum = 20000): number[] {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum || !value.every(finite)) throw new Error("Returned plot samples must be bounded finite numeric arrays.");
  return value;
}
const axis = (x: string, y: string): Row => ({ xaxis: { title: { text: x } }, yaxis: { title: { text: y } }, margin: { l: 65, r: 25, t: 30, b: 60 } });
function line(title: string, x: number[], y: number[], xLabel: string, yLabel: string): Figure {
  if (x.length !== y.length) throw new Error("Returned plot coordinates and values have different lengths.");
  return { title, data: [{ type: "scatter", mode: "lines+markers", name: yLabel, x, y }], layout: axis(xLabel, yLabel) };
}
function field(title: string, x: number[], y: number[], values: number[], unit: string): Figure {
  if (x.length !== y.length || x.length !== values.length) throw new Error("Returned field coordinates and values have different lengths.");
  return { title, data: [{ type: "scattergl", mode: "markers", name: title, x, y,
    marker: { size: 5, color: values, colorscale: "Viridis", showscale: true, colorbar: { title: { text: unit } } },
    customdata: values, hovertemplate: `x=%{x:.5g} m<br>y=%{y:.5g} m<br>%{customdata:.5g} ${unit}<extra></extra>` }],
    layout: { ...axis("x (m)", "y (m)"), yaxis: { title: { text: "y (m)" }, scaleanchor: "x", scaleratio: 1 } } };
}

/** Presentation admission only. It never turns samples into a solver result. */
export function su2ResultPresentation(value: unknown): Presentation {
  const envelope = record(value), data = record(envelope.data);
  const raw = Object.keys(record(data.result)).length ? record(data.result) : Object.keys(data).length ? data : envelope;
  const isCht = raw.contract === "spike/su2-cht-result/v1";
  const result: Presentation = { title: isCht ? "SU2 conjugate heat transfer" : "SU2 reference case", status: String(raw.status ?? data.status ?? "No result"), error: "", plots: [], previews: [], details: [], residuals: [], metrics: [], provenance: [], limitations: [] };
  const limitations = raw.limitations ?? data.limitations;
  if (Array.isArray(limitations)) result.limitations = limitations.filter((item): item is string => typeof item === "string").slice(0, 20);
  if (typeof data.limitation === "string") result.limitations.push(data.limitation);
  for (const [name, runtime] of [["Runtime", record(raw.runtime)], ["CFD runtime", record(raw.cfd)], ["CHT runtime", record(raw.cht)]] as const) {
    if (typeof runtime.available === "boolean") {
      result.details.push([name, runtime.available ? "Available" : "Unavailable; configure a trusted SU2 installation"]);
      if (typeof runtime.executable === "string") result.details.push([`${name} executable`, runtime.executable]);
    }
  }
  const provenance = record(raw.provenance);
  for (const key of ["version", "elapsed_s", "run_directory", "executable_sha256", "mesh_sha256", "config_sha256", "solution_sha256", "history_sha256"])
    if (typeof provenance[key] === "string" || finite(provenance[key])) result.provenance.push([key.replace(/_/g, " "), String(provenance[key])]);
  for (const kind of ["input_sha256","output_sha256"]) for (const [name, hash] of Object.entries(record(provenance[kind])).slice(0,20))
    if(typeof hash === "string") result.provenance.push([`${kind.replace(/_/g," ")} - ${name}`,hash]);
  for(const [key,value] of Object.entries(record(raw.request)).slice(0,20))
    if(finite(value)||typeof value === "string") result.details.push([key.replace(/_/g," "),String(value)]);
  const convergence = record(raw.convergence), residuals = record(convergence.final_log10_residuals);
  for (const [name, residual] of Object.entries(residuals).slice(0, 30)) if (finite(residual)) result.residuals.push([name, residual]);
  const diagnostics = record(raw.diagnostics);
  for (const [key, label] of Object.entries({ interface_temperature_jump_k: "Hot interface temperature jump (K)", interface_flux_relative_error: "Hot interface flux relative error", cold_interface_temperature_jump_k: "Cold interface temperature jump (K)", cold_interface_flux_relative_error: "Cold interface flux relative error", global_energy_relative_error: "Global energy relative error", heat_input_w_per_m: "Heat input per depth (W/m)", heat_output_w_per_m: "Heat output per depth (W/m)", cold_boundary_max_error_k: "Cold boundary maximum error (K)", temperature_min_k: "Minimum temperature (K)", temperature_max_k: "Maximum temperature (K)" }))
    if (finite(diagnostics[key])) result.metrics.push([label, diagnostics[key]]);
  if(typeof diagnostics.flux_estimator === "string") result.details.push(["Flux diagnostic method",diagnostics.flux_estimator]);
  if (!raw.contract) {
    if (raw.geometry !== undefined) {
      result.status = "Prepared case - not solved";
      if (typeof raw.geometry === "string") result.details.push(["Geometry", raw.geometry]);
      const geometry = record(raw.geometry), traces: PlotTrace[] = [];
      for (const [key, label] of [["fluid_bounds_m", "Fluid"], ["solid_bounds_m", "Hot solid"], ["cold_solid_bounds_m", "Cold solid"]]) {
        const bounds = geometry[key];
        if (bounds === undefined) continue;
        if (!Array.isArray(bounds) || bounds.length !== 2 || !bounds.every(point => Array.isArray(point) && point.length === 2 && point.every(finite))) { result.error = "Prepared geometry has invalid bounds."; return result; }
        const [[x0, y0], [x1, y1]] = bounds as number[][];
        if (x0 >= x1 || y0 >= y1) { result.error = "Prepared geometry bounds must have positive extent."; return result; }
        result.details.push([`${label} bounds (m)`, `(${x0}, ${y0}) to (${x1}, ${y1})`]);
        traces.push({ type: "scatter", mode: "lines", name: label, x: [x0,x1,x1,x0,x0], y: [y0,y0,y1,y1,y0], fill: "toself" });
      }
      if (traces.length) result.previews.push({ title: "Prepared reference geometry - unsolved", data: traces, layout: { ...axis("x (m)","y (m)"), yaxis: { title: { text: "y (m)" }, scaleanchor:"x", scaleratio:1 } } });
      for (const source of [record(raw.case),record(raw.settings),record(raw.boundaries)]) for (const [key, value] of Object.entries(source).slice(0,30))
        if (finite(value) || typeof value === "string") result.details.push([key.replace(/_/g," "),String(value)]);
    } else if (raw.cfd !== undefined || raw.cht !== undefined || raw.runtime !== undefined) result.status = "Runtime check - no solve performed";
    return result;
  }
  if (!["spike/su2-cavity-result/v1", "spike/su2-cht-result/v1"].includes(String(raw.contract))) { result.error = "Unsupported SU2 result contract; no solved fields displayed."; return result; }
  const validation = record(raw.validation);
  if (raw.status === "failed_validation" || validation.passed === false) {
    const violations = Array.isArray(validation.violations) ? validation.violations.filter((item): item is string => typeof item === "string").slice(0,20) : [];
    result.error = `Physical validation failed. ${violations.join(" ") || "Review the returned validation diagnostics."} No accepted thermal fields are displayed.`;
    return result;
  }
  if (raw.status !== "completed" || convergence.converged !== true) { result.error = "No converged solution is available for plotting."; return result; }
  if (isCht && validation.passed !== true) { result.error = "CHT physical validation evidence is missing; no accepted thermal fields are displayed."; return result; }
  try {
    if (isCht) {
      const zones = record(raw.zones);
      if ((zones.cold_solid !== undefined) !== (raw.cold_interface !== undefined)) throw new Error("Cold solid and cold interface must be returned together.");
      const zoneData = [["fluid","Fluid"],["solid","Hot solid"],...(zones.cold_solid === undefined ? [] : [["cold_solid","Cold solid"]])].map(([key,name]) => {
        const zone = record(zones[key]), x=numbers(zone.x_m), y=numbers(zone.y_m), t=numbers(zone.temperature_k);
        if (t.some(value=>value<=0)) throw new Error("Returned absolute temperatures must be positive kelvin.");
        if (key === "fluid" && (numbers(zone.u_m_s).length!==x.length || numbers(zone.v_m_s).length!==x.length)) throw new Error("Returned CHT velocity component lengths differ from fluid nodes.");
        return { name, x, y, t, map:field(`${name} temperature`,x,y,t,"K") };
      });
      let low = Infinity, high = -Infinity;
      for (const zone of zoneData) for (const value of zone.t) { low=Math.min(low,value); high=Math.max(high,value); }
      zoneData.forEach((zone,index)=>{zone.map.data[0].marker={...record(zone.map.data[0].marker),cmin:low,cmax:high,symbol:index?"square":"circle",showscale:index===0};});
      const centre = (x: number[], y: number[], t: number[], name: string): PlotTrace => {
        const indexes = x.map((value, index) => Math.abs(value-.5)<1e-10 ? index : -1).filter(index => index >= 0);
        if (indexes.length < 2) throw new Error("Returned CHT field does not include the reference centreline.");
        return { type: "scatter", mode: "lines+markers", name, x: indexes.map(index => y[index]), y: indexes.map(index => t[index]) };
      };
      const interfaces:Figure[]=[];
      for(const [key,name] of [["interface","Hot interface"],...(raw.cold_interface===undefined?[]:[["cold_interface","Cold interface"]])]) {
        const join=record(raw[key]), ix=numbers(join.x_m,2,129);
        const joinTemp=line(`${name} temperature`,ix,numbers(join.fluid_temperature_k,2,129),"x (m)","Temperature (K)");
        joinTemp.data[0].name="Fluid interface";
        joinTemp.data.push({...line("Solid interface",ix,numbers(join.solid_temperature_k,2,129),"x (m)","Temperature (K)").data[0],name:"Solid interface"});
        const joinFlux=line(`${name} conductive flux`,ix,numbers(join.fluid_flux_w_m2,2,129),"x (m)","Heat flux (W/m^2)");
        joinFlux.data[0].name="Fluid interface";
        joinFlux.data.push({...line("Solid interface",ix,numbers(join.solid_flux_w_m2,2,129),"x (m)","Heat flux (W/m^2)").data[0],name:"Solid interface"});
        interfaces.push(joinTemp,joinFlux);
      }
      result.plots = [{ title: "Returned fluid and solid temperature", data: zoneData.flatMap(zone=>zone.map.data), layout: zoneData[0].map.layout },
        { title: "Vertical temperature profile at x = 0.5 m", data: zoneData.map(zone=>centre(zone.x,zone.y,zone.t,zone.name)), layout: axis("y (m)", "Temperature (K)") }, ...interfaces];
    } else {
      const units = record(raw.units);
      for (const [name, expected] of Object.entries({ x: "m", y: "m", u: "m/s", v: "m/s", p: "Pa" }))
        if (units[name] !== expected) throw new Error("Returned CFD field units do not match the SI result contract.");
      const fields = record(raw.fields), centerlines = record(raw.centerlines);
      const x = numbers(fields.x), y = numbers(fields.y), u = numbers(fields.u), v = numbers(fields.v), p = numbers(fields.p);
      if (u.length !== v.length) throw new Error("Returned velocity component lengths differ.");
      const speed = u.map((component, index) => Math.hypot(component, v[index]));
      if (!speed.every(finite)) throw new Error("Returned velocity magnitudes overflow.");
      const coordinates = numbers(centerlines.coordinate, 2, 129), cu = numbers(centerlines.u, 2, 129), cv = numbers(centerlines.v, 2, 129);
      result.title = "SU2 lid-driven cavity";
      result.plots = [field("Returned nodal speed", x, y, speed, "m/s"), field("Returned nodal pressure", x, y, p, "Pa"),
        line("Vertical centreline: u at x = 0.5 m", coordinates, cu, "y (m)", "u (m/s)"),
        line("Horizontal centreline: v at y = 0.5 m", coordinates, cv, "x (m)", "v (m/s)")];
    }
  } catch (error) { result.error = error instanceof Error ? error.message : "Invalid returned samples."; result.plots = []; }
  return result;
}

function ResultContents({ view, showPlots = true }: { view: Presentation; showPlots?: boolean }) {
  return <>
    <p><strong>{view.status}</strong> · Experimental · Not production qualified</p>
    <p>Generated reference geometry. These fields do not represent the loaded PCB or assembly.</p>
    {view.error && <p role="alert">{view.error}</p>}
    {view.details.length > 0 && <dl>{view.details.map(([name, value],index)=><div key={`${name}:${index}`}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>}
    {showPlots && view.previews.length > 0 && <div className="su2-result-plots">{view.previews.map(plot=><article key={plot.title}><h4>{plot.title}</h4><InteractivePlot title={plot.title} revision={plot.title} data={plot.data} layout={plot.layout}/></article>)}</div>}
    {showPlots && view.plots.length > 0 && <><p>Plots show returned nodal samples and centreline data in SI units. Field markers do not imply interpolation between nodes.</p>
      <div className="su2-result-plots">{view.plots.map(plot => <article key={plot.title}><h4>{plot.title}</h4><InteractivePlot title={plot.title} revision={plot.title} data={plot.data} layout={plot.layout} /></article>)}</div></>}
    {view.residuals.length > 0 && <details open><summary>Final log10 residuals</summary><dl>{view.residuals.map(([name, residual]) => <div key={name}><dt>{name}</dt><dd>{residual.toPrecision(6)}</dd></div>)}</dl></details>}
    {view.metrics.length > 0 && <details open><summary>Thermal balance diagnostics</summary><dl>{view.metrics.map(([name, metric]) => <div key={name}><dt>{name}</dt><dd>{metric.toPrecision(6)}</dd></div>)}</dl></details>}
    {view.limitations.length > 0 && <ul>{view.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>}
    {view.provenance.length > 0 && <details><summary>Run provenance</summary><dl>{view.provenance.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl></details>}
  </>;
}

export function Su2ResultPanel({ result }: { result: unknown }) {
  const view = useMemo(() => su2ResultPresentation(result), [result]);
  const [expanded, setExpanded] = useState(false);
  const hasPlots = view.plots.length > 0 || view.previews.length > 0;
  return <section className="su2-result-panel" aria-label="SU2 reference case results">
    <header className="su2-result-heading"><h3>{view.title}</h3>{hasPlots && <button type="button" className="spike-control--primary" aria-haspopup="dialog" onClick={() => setExpanded(true)}>Expand results</button>}</header>
    <ResultContents view={view} showPlots={!expanded} />
    {expanded && hasPlots && <Su2ResultsDialog title={view.title} onClose={() => setExpanded(false)}><section className="su2-result-panel" aria-label="Expanded SU2 reference case results"><ResultContents view={view} /></section></Su2ResultsDialog>}
  </section>;
}
