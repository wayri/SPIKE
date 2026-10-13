// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { cancelLocalWorker, runNativeProjectWorker, type WorkerResponse } from "./workerBridge";
import { runSerializedAutomaticWorker } from "./automaticWorkerQueue";
import type { FieldObject } from "./assemblyFieldStudyPresentation";
import "./buttonStandard.css";
import "./AssemblyAirflowPanel.css";

const format = (value: unknown) => JSON.stringify(value, null, 2);
function value(response: WorkerResponse): FieldObject {
  if (!response.ok || !response.result) throw new Error(response.error || "Airflow worker returned no result.");
  return response.result;
}
export function makeAirflowDraft(setup: FieldObject): FieldObject {
  return { contract: "spike/assembly-airflow-request/v1", geometry: { solids: setup.solids, mesh: setup.mesh,
    air_domain: { kind: "polygon_prism", outer_mm: [[null, null], [null, null], [null, null], [null, null]], holes_mm: [], z_min_mm: null, z_max_mm: null } },
    materials: [...setup.materials, { id: "air", phase: "fluid", conductivity_w_mk: 0.026, density_kg_m3: 1.2,
      specific_heat_j_kgk: 1006, dynamic_viscosity_pa_s: 1.8e-5 }],
    region_properties: Object.fromEntries(setup.solids.map((s: FieldObject) => [s.id, { role: "package", power_w: 0 }])),
    mode: "static", ambient_temperature_k: 298.15, perfect_solid_contact_acknowledged: false,
    numerics: { end_time_s: 1, delta_t_s: 0.01, write_interval_steps: 100, validation_interval_steps: 1 } };
}
export function airflowDraftError(request: FieldObject | null): string {
  if (!request) return "Load the current assembly sources first.";
  const positive = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v > 0;
  try {
    if (request.contract !== "spike/assembly-airflow-request/v1" || !["static", "natural", "forced"].includes(request.mode)
      || !Array.isArray(request.geometry.solids) || !request.geometry.solids.length || !Array.isArray(request.materials)) return "Unsupported or incomplete airflow request.";
    const domain = request.geometry.air_domain;
    if (domain.kind !== "polygon_prism" || domain.outer_mm.length !== 4 || domain.holes_mm.length) return "The guided editor requires a rectangular air domain without holes.";
    const [a, b, c] = domain.outer_mm;
    if (![...domain.outer_mm.flat(), domain.z_min_mm, domain.z_max_mm].every(v => typeof v === "number" && Number.isFinite(v))
      || !(b[0] > a[0] && c[1] > a[1] && domain.z_max_mm > domain.z_min_mm)) return "Enter increasing world-coordinate air bounds in mm.";
    if (!request.materials.every((m: FieldObject) => positive(m.density_kg_m3) && positive(m.specific_heat_j_kgk) && positive(m.conductivity_w_mk))) return "Every material needs positive density, heat capacity and conductivity.";
    if (!positive(request.ambient_temperature_k) || !positive(request.numerics.end_time_s) || !positive(request.numerics.delta_t_s)) return "Temperature and time settings must be positive.";
    if (!Object.values(request.region_properties).every((p: any) => typeof p.power_w === "number" && Number.isFinite(p.power_w) && p.power_w >= 0)) return "Every solid needs finite nonnegative watts.";
    if (request.mode === "forced" && (!positive(request.flow_rate_m3_s) || ![request.inlet?.coordinate_mm, request.outlet?.coordinate_mm].every(v => typeof v === "number" && Number.isFinite(v)) || format(request.inlet) === format(request.outlet))) return "Forced flow needs positive flow and distinct inlet/outlet planes.";
    if (request.mode === "natural" && !request.materials.find((m: FieldObject) => m.id === "air")?.density_model) return "Natural convection requires an explicit buoyancy density model.";
    return "";
  } catch { return "The request is incomplete. Restore the guided setup or correct the JSON."; }
}

/** Projects solver-provided cell centres only; no interpolation or invented fields. */
export function AirflowFieldView({ result }: { result: FieldObject }) {
  const [field, setField] = useState("temperature_k");
  const [plane, setPlane] = useState("xy");
  const [region, setRegion] = useState("all");
  const [slice, setSlice] = useState(false);
  const [position, setPosition] = useState(50);
  const [yaw, setYaw] = useState(35);
  const source = result.fields?.[field];
  const all = (source?.samples || []).filter((s: FieldObject) => Array.isArray(s.point_mm) && s.point_mm.length === 3
    && s.point_mm.every(Number.isFinite) && (Array.isArray(s.value) ? s.value.length === 3 && s.value.every(Number.isFinite) : Number.isFinite(s.value)));
  const selected = all.filter((s: FieldObject) => region === "all" || s.region === region);
  const axes = plane === "xz" ? [0, 2, 1] : plane === "yz" ? [1, 2, 0] : [0, 1, 2];
  const bounds = (axis: number) => selected.reduce((r: number[], s: FieldObject) => [Math.min(r[0], s.point_mm[axis]), Math.max(r[1], s.point_mm[axis])], [Infinity, -Infinity]);
  const normal = bounds(axes[2]);
  const centre = normal[0] + position / 100 * (normal[1] - normal[0]);
  const filtered = selected.filter((s: FieldObject) => !slice || plane === "3d" || Math.abs(s.point_mm[axes[2]] - centre) <= Math.max(1e-6, (normal[1] - normal[0]) * .05));
  const stride = Math.max(1, Math.ceil(filtered.length / 5000));
  const rows = filtered.filter((_: unknown, i: number) => i % stride === 0);
  const scalar = (s: FieldObject) => Array.isArray(s.value) ? Math.hypot(...s.value) : s.value;
  const range = selected.reduce((r: number[], s: FieldObject) => [Math.min(r[0], scalar(s)), Math.max(r[1], scalar(s))], [Infinity, -Infinity]);
  const angle = yaw * Math.PI / 180;
  const project = (s: FieldObject) => plane === "3d"
    ? [s.point_mm[0] * Math.cos(angle) - s.point_mm[1] * Math.sin(angle), s.point_mm[2] + .35 * (s.point_mm[0] * Math.sin(angle) + s.point_mm[1] * Math.cos(angle))]
    : [s.point_mm[axes[0]], s.point_mm[axes[1]]];
  const projected = rows.map(project);
  const extent = projected.reduce((r: number[], p: number[]) => [Math.min(r[0], p[0]), Math.max(r[1], p[0]), Math.min(r[2], p[1]), Math.max(r[3], p[1])], [Infinity, -Infinity, Infinity, -Infinity]);
  return <section className="assembly-airflow-fields" aria-label="Computed airflow fields">
    <div className="assembly-airflow-toolbar"><label>Field <select value={field} onChange={e => setField(e.target.value)}><option value="temperature_k">Temperature (K)</option><option value="velocity_m_s">Speed (m/s)</option></select></label>
      <label>View <select value={plane} onChange={e => setPlane(e.target.value)}>{["xy", "xz", "yz", "3d"].map(p => <option key={p}>{p}</option>)}</select></label>
      <label>Region <select value={region} onChange={e => setRegion(e.target.value)}><option value="all">All regions</option>{Array.from(new Set<string>(all.map((s: FieldObject) => s.region))).map(r => <option key={r}>{r}</option>)}</select></label>
      {plane === "3d" ? <label>Rotation <input type="range" min="0" max="360" value={yaw} onChange={e => setYaw(Number(e.target.value))}/></label> : <><label><input type="checkbox" checked={slice} onChange={e => setSlice(e.target.checked)}/> Slice (10% thickness)</label>{slice && <label>Slice position <input type="range" min="0" max="100" value={position} onChange={e => setPosition(Number(e.target.value))}/></label>}</>}
    </div>
    {rows.length ? <><svg viewBox="0 0 640 360" role="img" aria-label={`${field} computed cell centres; ${plane} projection; coordinates in mm`}>
      {rows.map((s: FieldObject, i: number) => { const p = projected[i]; const ratio = (scalar(s) - range[0]) / (range[1] - range[0] || 1); return <circle key={i} cx={35 + (p[0] - extent[0]) / (extent[1] - extent[0] || 1) * 565} cy={315 - (p[1] - extent[2]) / (extent[3] - extent[2] || 1) * 280} r="2.4" fill={`hsl(${240 * (1 - ratio)} 75% 55%)`}><title>{`${s.region}: ${scalar(s).toPrecision(5)} ${source.unit}; (${s.point_mm.join(", ")}) mm`}</title></circle>; })}
      <text x="30" y="340" fill="currentColor">{plane === "3d" ? "Rotated world coordinates (mm)" : `${"xyz"[axes[0]]}: ${extent[0].toFixed(2)} .. ${extent[1].toFixed(2)} mm; ${"xyz"[axes[1]]}: ${extent[2].toFixed(2)} .. ${extent[3].toFixed(2)} mm`}</text>
    </svg><p>Blue {range[0].toPrecision(5)} → red {range[1].toPrecision(5)} {source.unit}. {rows.length} displayed / {source.total_samples} saved samples. Cell-centre scatter; no interpolation.</p></> : <p>No computed samples in this field, region or slice.</p>}
  </section>;
}

export default function AssemblyAirflowPanel({ projectPath, manifestDigest, meshSetup, disabled, onUpdated, onDirtyChange }: {
  projectPath: string | null; manifestDigest: string | null; meshSetup: FieldObject | null; disabled: boolean;
  onUpdated: () => Promise<void>; onDirtyChange?: (dirty: boolean) => void;
}) {
  const [draft, setDraft] = useState<FieldObject | null>(null);
  const [owners, setOwners] = useState<FieldObject>({});
  const [result, setResult] = useState<FieldObject | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [advanced, setAdvanced] = useState("");
  const [dirty, setDirty] = useState(false);
  const generation = useRef(0), operation = useRef<string | null>(null);
  const identity = `${projectPath}\0${manifestDigest}`;
  const currentIdentity = useRef(identity); currentIdentity.current = identity;
  const locked = disabled || busy || !projectPath || !manifestDigest;
  const params = { project_path: projectPath, expected_manifest_payload_sha256: manifestDigest };
  useEffect(() => { onDirtyChange?.(dirty || busy); }, [dirty, busy, onDirtyChange]);
  useEffect(() => () => { onDirtyChange?.(false); }, [onDirtyChange]);
  useEffect(() => {
    const token = ++generation.current;
    setDraft(null); setResult(null); setDirty(false); setBusy(false); setError(""); setStatus(""); setAdvanced(""); setAcknowledged(false);
    if (operation.current) { void cancelLocalWorker(operation.current); operation.current = null; }
    if (projectPath && manifestDigest) void runSerializedAutomaticWorker(async () => value(await runNativeProjectWorker({ method: "read_assembly_airflow_study_in_project", params })), () => token === generation.current)
      .then(read => { if (token !== generation.current || !read) return; if (read.state === "current") { setDraft(read.record.request); setResult(read.record.result); setOwners(read.record.result.source_owners || {}); setAdvanced(format(read.record.request)); setStatus("Saved airflow study loaded."); } else if (read.state === "stale") setError(read.reason); })
      .catch(e => { if (token === generation.current) setError(String(e)); });
    return () => { generation.current++; if (operation.current) void cancelLocalWorker(operation.current); };
  }, [identity]);
  const change = (edit: (request: FieldObject) => void) => {
    if (!draft) return; const next = structuredClone(draft); edit(next); setDraft(next); setAdvanced(format(next)); setDirty(true); setResult(null); setAcknowledged(false);
  };
  const action = async (method: string, extra: FieldObject, accept: (read: FieldObject) => void) => {
    if (locked || operation.current) return;
    const token = generation.current, key = identity, id = `assembly-airflow-${crypto.randomUUID()}`;
    operation.current = id; setBusy(true); setError(""); setStatus("Working…");
    try { const read = value(await runNativeProjectWorker({ id, method, params: { ...params, ...extra } }));
      if (token === generation.current && key === currentIdentity.current) accept(read);
    } catch (e) { if (token === generation.current && key === currentIdentity.current) { setError(String(e)); setStatus(""); } }
    finally { if (token === generation.current && key === currentIdentity.current) { setBusy(false); operation.current = null; } }
  };
  const number = (label: string, v: unknown, update: (n: number | null) => void) => <label>{label}<input type="number" step="any" value={typeof v === "number" ? v : ""} disabled={locked} onChange={e => update(e.target.value === "" ? null : Number(e.target.value))}/></label>;
  const invalid = airflowDraftError(draft);
  return <details className="assembly-airflow-panel"><summary>Assembly air and temperature · OpenFOAM (experimental)</summary>
    <p>Build air around retained assembly solids and solve coupled fluid/solid temperatures. The installed Gmsh and OpenFOAM runtimes are required. Radiation and fan curves are not included.</p>
    <div className="assembly-airflow-toolbar"><button type="button" disabled={locked || !meshSetup} onClick={() => void action("read_assembly_airflow_setup_in_project", meshSetup!, read => { const next = makeAirflowDraft(read); setDraft(next); setAcknowledged(false); setOwners(read.owners); setAdvanced(format(next)); setResult(null); setDirty(true); setStatus("Assembly sources loaded. Enter material properties and world air bounds."); })}>Load current assembly sources</button>
      <button type="button" disabled={locked} onClick={() => void action("read_assembly_airflow_study_in_project", {}, read => { if (read.state === "current") { setDraft(read.record.request); setAcknowledged(false); setAdvanced(format(read.record.request)); setResult(read.record.result); setOwners(read.record.result.source_owners || {}); setDirty(false); setStatus("Saved airflow study loaded."); } else setStatus(read.reason || "No saved airflow result."); })}>Load saved airflow results</button>
      {busy && <button type="button" onClick={() => { const id = operation.current; generation.current++; operation.current = null; setBusy(false); setStatus("Cancelled."); if (id) void cancelLocalWorker(id); }}>Cancel airflow</button>}</div>
    {!meshSetup && <p>Choose material assignments in the assembly meshing setup above to load current sources.</p>}
    {draft && <><fieldset disabled={locked}><legend>Operating mode and air domain</legend><div className="assembly-airflow-grid">
      <label>Mode<select value={draft.mode} onChange={e => change(r => { r.mode = e.target.value; delete r.inlet; delete r.outlet; delete r.flow_rate_m3_s; const air = r.materials.find((m: FieldObject) => m.id === "air"); delete air.density_model; if (r.mode === "forced") Object.assign(r, { flow_rate_m3_s: null, inlet: { axis: 0, coordinate_mm: null }, outlet: { axis: 0, coordinate_mm: null } }); if (r.mode === "natural") air.density_model = { type: "Boussinesq", rho0_kg_m3: air.density_kg_m3, T0_k: r.ambient_temperature_k, beta_per_k: 1 / r.ambient_temperature_k, temperature_min_k: r.ambient_temperature_k - 20, temperature_max_k: r.ambient_temperature_k + 20 }; })}><option value="static">Static air conduction</option><option value="natural">Natural convection · gravity −Z</option><option value="forced">Prescribed inlet flow</option></select></label>
      {number("Ambient (K)", draft.ambient_temperature_k, n => change(r => { r.ambient_temperature_k = n; }))}
      {[0, 1, 2].flatMap(axis => [0, 1].map(side => { const d = draft.geometry.air_domain; const v = axis === 2 ? d[side ? "z_max_mm" : "z_min_mm"] : d.outer_mm[side ? 2 : 0][axis]; return <span key={`${axis}${side}`}>{number(`${"XYZ"[axis]} ${side ? "maximum" : "minimum"} (mm)`, v, n => change(r => { const a = r.geometry.air_domain; if (axis === 2) a[side ? "z_max_mm" : "z_min_mm"] = n; else for (const index of axis === 0 ? side ? [1, 2] : [0, 3] : side ? [2, 3] : [0, 1]) a.outer_mm[index][axis] = n; }))}</span>; }))}
    </div><p>Bounds must contain every solid. Exterior air walls use the ambient temperature. This is a user-defined surrounding domain; inlet/outlet planes select its exterior air faces.</p></fieldset>
    <fieldset disabled={locked}><legend>Material properties and heat</legend>{draft.materials.map((m: FieldObject, i: number) => <div className="assembly-airflow-material" key={m.id}><strong>{m.id}</strong><div className="assembly-airflow-grid">{[["Density (kg/m³)", "density_kg_m3"], ["Heat capacity (J/kg K)", "specific_heat_j_kgk"], ["Conductivity (W/m K)", "conductivity_w_mk"], ...(m.phase === "fluid" ? [["Dynamic viscosity (Pa s)", "dynamic_viscosity_pa_s"]] : [])].map(([label, key]) => <span key={key}>{number(label, m[key], n => change(r => { r.materials[i][key] = n; }))}</span>)}</div>
      {m.density_model && <div className="assembly-airflow-grid">{Object.keys(m.density_model).filter(k => k !== "type").map(key => <span key={key}>{number(key, m.density_model[key], n => change(r => { r.materials[i].density_model[key] = n; }))}</span>)}</div>}</div>)}
      {Object.entries(draft.region_properties).map(([id, p]: [string, any]) => <div className="assembly-airflow-grid" key={id}><span title={id}>{owners[id]?.occurrence_id || id}</span>{number("Heat load (W)", p.power_w, n => change(r => { r.region_properties[id].power_w = n; }))}<label>Solid role<select value={p.role} onChange={e => change(r => { r.region_properties[id].role = e.target.value; })}>{["board", "package", "heatsink", "enclosure", "potting", "coating"].map(role => <option key={role}>{role}</option>)}</select></label></div>)}</fieldset>
    {draft.mode === "forced" && <fieldset disabled={locked}><legend>Prescribed flow</legend><div className="assembly-airflow-grid">{number("Volumetric flow (m³/s)", draft.flow_rate_m3_s, n => change(r => { r.flow_rate_m3_s = n; }))}{["inlet", "outlet"].map(key => <div key={key}><label>{key} normal axis<select value={draft[key].axis} onChange={e => change(r => { r[key].axis = Number(e.target.value); })}>{["X", "Y", "Z"].map((axis, i) => <option value={i} key={axis}>{axis}</option>)}</select></label>{number(`${key} plane (mm)`, draft[key].coordinate_mm, n => change(r => { r[key].coordinate_mm = n; }))}</div>)}</div></fieldset>}
    <fieldset disabled={locked}><legend>Time integration</legend><div className="assembly-airflow-grid">{[["End time (s)", "end_time_s"], ["Time step (s)", "delta_t_s"], ["Write interval (steps)", "write_interval_steps"]].map(([label, key]) => <span key={key}>{number(label, draft.numerics[key], n => change(r => { r.numerics[key] = n; }))}</span>)}</div></fieldset>
    <label><input type="checkbox" disabled={locked} checked={draft.perfect_solid_contact_acknowledged === true} onChange={e => change(r => { r.perfect_solid_contact_acknowledged = e.target.checked; })}/> Use perfect thermal contact at touching solid interfaces. Finite contact resistance is not supported by this airflow adapter; do not use this assumption for a study requiring it.</label>
    <details><summary>Advanced request JSON</summary><textarea aria-label="Airflow request JSON" value={advanced} disabled={locked} onChange={e => { setAdvanced(e.target.value); setDirty(true); setAcknowledged(false); setResult(null); }}/><button type="button" disabled={locked} onClick={() => { try { const parsed = JSON.parse(advanced); const reason = airflowDraftError(parsed); if (reason) throw new Error(reason); setDraft(parsed); setResult(null); setError(""); } catch (e) { setError(String(e)); } }}>Apply JSON</button></details>
    <label><input type="checkbox" checked={acknowledged} disabled={locked} onChange={e => setAcknowledged(e.target.checked)}/> I reviewed the bounds, heat loads, material properties, boundary conditions and time settings. This experimental result needs convergence and physical validation.</label>
    {invalid && <p role="status">{invalid}</p>}<button type="button" className="spike-control--primary" disabled={locked || !meshSetup || !acknowledged || !!invalid || advanced !== format(draft)} onClick={() => void action("run_assembly_airflow_in_project", { ...meshSetup, request: draft }, read => { if (read.saved && read.result?.status === "completed") { setResult(read.result); setDirty(false); setStatus("Completed airflow result saved in this project."); void onUpdated(); } else { setResult(null); setError(read.result?.message || "Airflow did not complete; no result saved."); setStatus(read.result?.status || read.status); } })}>Run and save airflow</button></>}
    {status && <p role="status">{status}</p>}{error && <p role="alert">{error}</p>}{result?.status === "completed" && <AirflowFieldView result={result}/>}</details>;
}
