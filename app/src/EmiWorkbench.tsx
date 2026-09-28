import { validEmiFarField } from "./emiFieldData";
import { EmiFieldPlots } from "./EmiFieldPlots";
import WorkflowSchematic from "./WorkflowSchematic";
import { emiSchematic } from "./workflowSchematics";
import { defaultEmiChamber, normalizeEmiChamber, type EmiChamberSetup } from "./emiChamber";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, CheckCircle2, CircuitBoard, Gauge, Layers3, Network, Play, Plus,
  RadioTower, Search, ShieldAlert, SlidersHorizontal, Trash2, Waves, X,
} from "lucide-react";
import type { ParsedBoard } from "./boardParser";
import type { BoardObject } from "./BoardViewport";
import { previewViewportTarget } from "./BoardViewport";

export const EMI_SETUP_CONTRACT = "spike/emi-setup/v1";

export type EmiNetMetric = {
  net: string;
  source: string;
  dv_dt_v_per_s: number;
  di_dt_a_per_s: number;
  peak_current_a: number;
  loop_area_mm2: number;
  return_discontinuities: number;
};

export type EmiPort = {
  id: string;
  name: string;
  start: [number, number, number];
  stop: [number, number, number];
  direction: "x" | "y" | "z";
  impedance_ohm: number;
  excite: boolean;
};

export type EmiRadiatedEmissionsStandard = {
  id: string;
  classification?: string;
  platform?: string;
};

const RADIATED_EMISSIONS_STANDARDS = [
  { id: "cispr-32-2015-amd1-2019", label: "CISPR 32:2015+AMD1:2019", classificationLabel: "Class", classifications: ["A", "B"] },
  { id: "cispr-25-2021", label: "CISPR 25:2021", classificationLabel: "Class", classifications: ["1", "2", "3", "4", "5"] },
  { id: "mil-std-461h-2026-re102", label: "MIL-STD-461H:2026 RE102", requiresPlatform: true },
  { id: "mil-std-461g-2015-re102", label: "MIL-STD-461G:2015 RE102 (historical)", requiresPlatform: true },
] as const;

const MIL_RE102_PLATFORMS = ["ground", "surface_ship", "submarine", "aircraft", "space"] as const;

const radiatedEmissionsStandardFor = (id: string | undefined) =>
  RADIATED_EMISSIONS_STANDARDS.find(standard => standard.id === id);

const boundedProfileText = (value: unknown): string | undefined => {
  if (typeof value !== "string") return undefined;
  const text = value.trim();
  return text && text.length <= 128 ? text : undefined;
};

const normalizeRadiatedEmissionsStandard = (raw: unknown): EmiRadiatedEmissionsStandard | undefined => {
  if (raw == null) return undefined;
  const invalid = { id: "__invalid_saved_re_profile__" };
  if (typeof raw !== "object" || Array.isArray(raw)) return invalid;
  const value = raw as Partial<EmiRadiatedEmissionsStandard>;
  if (Object.keys(value).some(key => !["id", "classification", "platform"].includes(key))) return invalid;
  const id = boundedProfileText(value.id);
  if (!id) return invalid;
  if (value.classification != null && !boundedProfileText(value.classification)) return invalid;
  if (value.platform != null && !boundedProfileText(value.platform)) return invalid;
  const classification = boundedProfileText(value.classification);
  const platform = boundedProfileText(value.platform);
  return {
    id,
    ...(classification ? { classification } : {}),
    ...(platform ? { platform } : {}),
  };
};

export type EmiSetup = {
  contract: typeof EMI_SETUP_CONTRACT;
  chamber: EmiChamberSetup;
  selected_nets: string[];
  return_nets: string[];
  requested_analyses: Array<"conducted_screening" | "near_field" | "far_field">;
  frequency: { start_hz: number; stop_hz: number; points: number };
  environment: { kind: "free_space" | "bench_ground_plane" | "shielded_enclosure" };
  mesh: { resolution_mm: number; padding_cells: number };
  max_solver_time_s: number;
  excitation: { mode: "prepass_results" | "explicit_ports" | "spice"; ports: EmiPort[] };
  radiated_emissions_standard?: EmiRadiatedEmissionsStandard;
  net_metrics: EmiNetMetric[];
  viewport: { translucent_board: boolean; analysis_nets_only: boolean };
};

export type EmiIssue = {
  code: string;
  severity: "error" | "warning" | "info" | string;
  message: string;
  suggestion?: string;
};

export type EmiPreflight = {
  contract: string;
  status: string;
  can_screen: boolean;
  can_prepare: boolean;
  can_run: boolean;
  counts: { errors: number; warnings: number };
  issues: EmiIssue[];
  stages: Array<{ id: string; name: string; state: string; detail: string }>;
  geometry_coverage: Array<{ net: string; tracks: number; vias: number; pads: number; zones: number; layers: string[]; routed_length_mm: number; has_geometry: boolean }>;
  solver_recommendation: {
    status: string;
    recommended: { id: string; name: string; state: string; model_status: string; reason: string } | null;
    candidates: Array<{ id: string; name: string; state: string; eligible: boolean; missing: string[]; reason: string }>;
  };
};

export type EmiScreening = {
  contract: string;
  status: string;
  model_status: string;
  message?: string;
  preflight: EmiPreflight;
  screening: null | {
    status: string;
    warning: string;
    recommended_nets: Array<{
      net: string;
      score: number;
      reasons: string[];
      geometry: { tracks?: number; vias?: number; pads?: number; zones?: number; layers?: string[]; routed_length_mm?: number };
    }>;
  };
};

export type EmiFarFieldResult = {
  contract: "spike/openems-far-field-result/v1";
  status: string;
  validation_status: string;
  frequencies_hz: number[];
  theta_deg: number[];
  phi_deg: number[];
  radius_m: number;
  center_mm: [number, number, number];
  shape: [number, number, number];
  e_field_v_m: {
    magnitude: number[];
    theta?: { real: number[]; imag: number[] };
    phi?: { real: number[]; imag: number[] };
  };
  directivity: { linear: number[]; maximum_linear: number[] };
  radiated_power: { angular_w: number[]; total_w: number[] };
  validation: { status: string; established: string[]; required: string[] };
};

export type EmiFieldResult = {
  contract: string;
  engine_id: string;
  status: string;
  model_status: string;
  frequency_hz?: number[];
  message?: string;
  far_field?: EmiFarFieldResult;
};

export function normalizeEmiFieldResult(raw: unknown): EmiFieldResult | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Partial<EmiFieldResult>;
  const field = value.far_field;
  if (field && !validEmiFarField(field)) return null;
  return {
    contract: String(value.contract ?? ""),
    engine_id: String(value.engine_id ?? "external.openems"),
    status: String(value.status ?? "unknown"),
    model_status: String(value.model_status ?? "unvalidated"),
    frequency_hz: Array.isArray(value.frequency_hz) ? value.frequency_hz.map(Number).filter(Number.isFinite) : [],
    message: value.message ? String(value.message) : undefined,
    far_field: field,
  };
}

export type EmiSetupSection = "domain" | "prepass" | "excitation" | "solver";

const metricFor = (net: string): EmiNetMetric => ({
  net,
  source: "unassigned",
  dv_dt_v_per_s: 0,
  di_dt_a_per_s: 0,
  peak_current_a: 0,
  loop_area_mm2: 0,
  return_discontinuities: 0,
});

const dedupe = (values: unknown): string[] => Array.isArray(values)
  ? Array.from(new Set(values.map(String).map(value => value.trim()).filter(Boolean)))
  : [];

export function defaultEmiSetup(netNames: string[] = []): EmiSetup {
  const ground = netNames.find(net => /(^|[/_+-])(gnd|ground)([/_+-]|$)/i.test(net));
  const candidate = netNames.find(net => net !== ground && !/^unconnected/i.test(net));
  const selected = candidate ? [candidate] : [];
  return {
    contract: EMI_SETUP_CONTRACT,
    chamber: defaultEmiChamber(),
    selected_nets: selected,
    return_nets: ground ? [ground] : [],
    requested_analyses: ["conducted_screening", "near_field", "far_field"],
    frequency: { start_hz: 30e6, stop_hz: 1e9, points: 201 },
    environment: { kind: "free_space" },
    mesh: { resolution_mm: 0.5, padding_cells: 8 },
    max_solver_time_s: 3600,
    excitation: { mode: "prepass_results", ports: [] },
    radiated_emissions_standard: undefined,
    net_metrics: selected.map(metricFor),
    viewport: { translucent_board: true, analysis_nets_only: false },
  };
}

export function normalizeEmiSetup(raw: unknown, netNames: string[] = []): EmiSetup {
  const fallback = defaultEmiSetup(netNames);
  if (!raw || typeof raw !== "object") return fallback;
  const value = raw as Partial<EmiSetup>;
  const selected = dedupe(value.selected_nets);
  const returns = dedupe(value.return_nets).filter(net => !selected.includes(net));
  const metrics = Array.isArray(value.net_metrics) ? value.net_metrics : [];
  return {
    ...fallback,
    ...value,
    contract: EMI_SETUP_CONTRACT,
    selected_nets: selected,
    return_nets: returns,
    requested_analyses: Array.isArray(value.requested_analyses) && value.requested_analyses.length
      ? value.requested_analyses.filter(item => ["conducted_screening", "near_field", "far_field"].includes(item))
      : fallback.requested_analyses,
    frequency: { ...fallback.frequency, ...(value.frequency ?? {}) },
    environment: { ...fallback.environment, ...(value.environment ?? {}) },
    mesh: { ...fallback.mesh, ...(value.mesh ?? {}) },
    excitation: {
      ...fallback.excitation,
      ...(value.excitation ?? {}),
      ports: Array.isArray(value.excitation?.ports) ? value.excitation.ports : [],
    },
    radiated_emissions_standard: normalizeRadiatedEmissionsStandard(value.radiated_emissions_standard),
    net_metrics: selected.map(net => ({ ...metricFor(net), ...(metrics.find(item => item?.net === net) ?? {}), net })),
    viewport: { ...fallback.viewport, ...(value.viewport ?? {}) },
    chamber: normalizeEmiChamber(value.chamber),
  };
}

type Props = {
  board: ParsedBoard | null;
  selected: BoardObject | null;
  setup: EmiSetup;
  setSetup: React.Dispatch<React.SetStateAction<EmiSetup>>;
  preflight: EmiPreflight | null;
  screening: EmiScreening | null;
  section: EmiSetupSection;
  setSection: (section: EmiSetupSection) => void;
  busy: boolean;
  canExecutePreparedCase: boolean;
  onValidate: () => void;
  onScreen: () => void;
  onPrepare: () => void;
  onRun: () => void;
  onDashboard: () => void;
  onSolverManager: () => void;
  onStatus: (message: string) => void;
};

const stageTone = (state: string) => state === "complete" || state === "ready"
  ? "ready"
  : state === "blocked" || state === "capability_gated" ? "blocked" : "pending";

export function EmiSetupPanel({
  board, selected, setup, setSetup, preflight, screening, section, setSection, busy, canExecutePreparedCase,
  onValidate, onScreen, onPrepare, onRun, onDashboard, onSolverManager, onStatus,
}: Props) {
  const [filter, setFilter] = useState("");
  const nets = useMemo(() => Object.values(board?.nets ?? {}).filter(Boolean).sort((a, b) => a.localeCompare(b)), [board]);
  const visibleNets = useMemo(() => nets.filter(net => net.toLowerCase().includes(filter.toLowerCase())).slice(0, 160), [nets, filter]);

  useEffect(() => () => previewViewportTarget(null), []);

  const replace = (patch: Partial<EmiSetup>) => setSetup(current => ({ ...current, ...patch }));
  const toggleNet = (net: string, role: "candidate" | "return") => setSetup(current => {
    if (role === "candidate") {
      const selectedNets = current.selected_nets.includes(net)
        ? current.selected_nets.filter(item => item !== net)
        : [...current.selected_nets, net];
      return {
        ...current,
        selected_nets: selectedNets,
        return_nets: current.return_nets.filter(item => item !== net),
        net_metrics: selectedNets.map(name => current.net_metrics.find(item => item.net === name) ?? metricFor(name)),
      };
    }
    const returnNets = current.return_nets.includes(net)
      ? current.return_nets.filter(item => item !== net)
      : [...current.return_nets, net];
    return { ...current, return_nets: returnNets, selected_nets: current.selected_nets.filter(item => item !== net), net_metrics: current.net_metrics.filter(item => item.net !== net) };
  });
  const useSelectedNet = () => {
    if (!selected?.net || selected.net === "No net") { onStatus("Select a routed net, pad, via, or zone in the viewport first"); return; }
    if (!setup.selected_nets.includes(selected.net)) toggleNet(selected.net, "candidate");
    onStatus(`${selected.net} added to EMI candidate nets`);
  };
  const updateMetric = (net: string, key: keyof Omit<EmiNetMetric, "net">, value: string) => setSetup(current => ({
    ...current,
    net_metrics: current.net_metrics.map(metric => metric.net === net
      ? { ...metric, [key]: key === "source" ? value : Math.max(0, Number(value) || 0) }
      : metric),
  }));
  const addPort = () => setSetup(current => ({
    ...current,
    excitation: {
      ...current.excitation,
      ports: [...current.excitation.ports, {
        id: `port-${current.excitation.ports.length + 1}`,
        name: `Port ${current.excitation.ports.length + 1}`,
        start: [0, 0, 0], stop: [0, 0, -1], direction: "z", impedance_ohm: 50,
        excite: current.excitation.ports.length === 0,
      }],
    },
  }));
  const updatePort = (index: number, patch: Partial<EmiPort>) => setSetup(current => ({
    ...current,
    excitation: { ...current.excitation, ports: current.excitation.ports.map((port, itemIndex) => itemIndex === index ? { ...port, ...patch } : port) },
  }));
  const updateCoordinate = (index: number, endpoint: "start" | "stop", axis: number, value: string) => {
    const next = [...setup.excitation.ports[index][endpoint]] as [number, number, number];
    next[axis] = Number(value) || 0;
    updatePort(index, { [endpoint]: next });
  };
  const updateRadiatedEmissionsStandard = (id: string) => {
    const standard = radiatedEmissionsStandardFor(id);
    replace({ radiated_emissions_standard: standard ? { id: standard.id } : undefined });
  };
  const updateRadiatedEmissionsMetadata = (patch: Partial<EmiRadiatedEmissionsStandard>) => setSetup(current => {
    const standard = current.radiated_emissions_standard;
    return standard ? { ...current, radiated_emissions_standard: { ...standard, ...patch } } : current;
  });
  const stages = preflight?.stages ?? [
    { id: "setup", name: "Design and domain", state: board ? "pending" : "blocked", detail: "Choose candidate and return nets." },
    { id: "screen", name: "Electrical pre-pass", state: "pending", detail: "Supply PI, transient, SPICE, or measured metrics." },
    { id: "excitation", name: "Excitation and ports", state: "pending", detail: "Define field-solver excitation." },
    { id: "fields", name: "Full-wave fields", state: "capability_gated", detail: "Requires an eligible external solver." },
    { id: "far_field", name: "Far field and compliance", state: "capability_gated", detail: "A reference-validated openEMS adapter and an explicit NF2FF request are required." },
  ];

  return <div className="emi-setup-panel">
    <WorkflowSchematic title="EMI / EMC test schematic" diagram={emiSchematic(setup)} onSelect={target => setSection(target as EmiSetupSection)} />
    <div className="emi-readiness">
      <span className={`emi-state ${preflight?.status ?? "not-validated"}`}>{(preflight?.status ?? "NOT VALIDATED").replace(/_/g, " ")}</span>
      <b>{setup.selected_nets.length} candidate{setup.selected_nets.length === 1 ? "" : "s"}</b>
      <small>{preflight ? `${preflight.counts.errors} errors · ${preflight.counts.warnings} warnings` : "Run preflight before case preparation"}</small>
    </div>
    <div className="emi-process" aria-label="EM workflow stages">
      {stages.map((stage, index) => <button key={stage.id} className={`${stageTone(stage.state)} ${section === (["domain", "prepass", "excitation", "solver", "solver"] as const)[index] ? "selected" : ""}`} onClick={() => setSection((["domain", "prepass", "excitation", "solver", "solver"] as const)[index])} title={stage.detail}>
        <span>{index + 1}</span><b>{stage.name}</b><small>{stage.state.replace(/_/g, " ")}</small>
      </button>)}
    </div>

    {section === "domain" && <>
      <section className="emi-section">
        <label>NET DOMAIN</label>
        <div className="emi-inline-actions"><button onClick={useSelectedNet} disabled={!selected?.net}><Network size={13} /> Use selected net</button><span>{setup.return_nets.length} returns</span></div>
        <div className="emi-net-filter"><Search size={13} /><input value={filter} onChange={event => setFilter(event.target.value)} placeholder="Filter board nets" /></div>
        <div className="emi-net-head"><span>Net</span><b title="Candidate or aggressor">EMI</b><b title="Reference or return conductor">RET</b></div>
        <div className="emi-net-list" onMouseLeave={() => previewViewportTarget(null)}>
          {visibleNets.map(net => <label key={net} onMouseEnter={() => previewViewportTarget({ kind: "net", net, label: net })}>
            <span>{net}</span>
            <input type="checkbox" aria-label={`${net} candidate`} checked={setup.selected_nets.includes(net)} onChange={() => toggleNet(net, "candidate")} />
            <input type="checkbox" aria-label={`${net} return`} checked={setup.return_nets.includes(net)} onChange={() => toggleNet(net, "return")} />
          </label>)}
          {!visibleNets.length && <p>No matching nets.</p>}
        </div>
      </section>
      <section className="emi-section">
        <label>TEST DOMAIN</label>
        <div className="emi-checks">
          {(["conducted_screening", "near_field", "far_field"] as const).map(value => <label key={value}><input type="checkbox" checked={setup.requested_analyses.includes(value)} onChange={() => replace({ requested_analyses: setup.requested_analyses.includes(value) ? setup.requested_analyses.filter(item => item !== value) : [...setup.requested_analyses, value] })} />{value.replace(/_/g, " ")}</label>)}
        </div>
        <select value={setup.environment.kind} onChange={event => replace({ environment: { kind: event.target.value as EmiSetup["environment"]["kind"] } })}>
          <option value="free_space">Free space</option><option value="bench_ground_plane">Bench ground plane</option><option value="shielded_enclosure">Shielded enclosure</option>
        </select>
        <label>Radiated-emission reference profile
          <select value={setup.radiated_emissions_standard?.id ?? ""} onChange={event => updateRadiatedEmissionsStandard(event.target.value)}>
            <option value="">None</option>
            {setup.radiated_emissions_standard && !radiatedEmissionsStandardFor(setup.radiated_emissions_standard.id) && <option value={setup.radiated_emissions_standard.id}>Unknown / invalid saved profile: {setup.radiated_emissions_standard.id}</option>}
            {RADIATED_EMISSIONS_STANDARDS.map(standard => <option key={standard.id} value={standard.id}>{standard.label}</option>)}
          </select>
        </label>
        {(() => {
          const profile = setup.radiated_emissions_standard;
          const standard = radiatedEmissionsStandardFor(profile?.id);
          if (!profile) return null;
          if (!standard) return <div className="emi-gate"><AlertTriangle size={14} /><span><b>Unknown or invalid saved profile</b> This profile is preserved for preflight validation and is not treated as a valid standard selection. Select a supported profile or None to replace it.</span></div>;
          return <div className="emi-gate"><ShieldAlert size={14} /><span><b>Reference only</b> This profile records a versioned reference standard. No numeric limits, pass/fail assessment, or compliance determination is available.</span>
            {"classifications" in standard && <label>{standard.classificationLabel}<select value={profile.classification ?? ""} onChange={event => updateRadiatedEmissionsMetadata({ classification: event.target.value || undefined })}>{profile.classification && !standard.classifications.includes(profile.classification as never) && <option value={profile.classification}>Invalid saved class: {profile.classification}</option>}<option value="">Select {standard.classificationLabel.toLowerCase()}</option>{standard.classifications.map(classification => <option key={classification} value={classification}>{classification}</option>)}</select></label>}
            {"requiresPlatform" in standard && <label>Platform <select value={profile.platform ?? ""} onChange={event => updateRadiatedEmissionsMetadata({ platform: event.target.value || undefined })}>{profile.platform && !MIL_RE102_PLATFORMS.includes(profile.platform as typeof MIL_RE102_PLATFORMS[number]) && <option value={profile.platform}>Invalid saved platform: {profile.platform}</option>}<option value="">Select required platform</option>{MIL_RE102_PLATFORMS.map(platform => <option key={platform} value={platform}>{platform.replace(/_/g, " ")}</option>)}</select></label>}
          </div>;
        })()}
        <div className="emi-field-grid"><label>Start (Hz)<input type="number" min="1" value={setup.frequency.start_hz} onChange={event => replace({ frequency: { ...setup.frequency, start_hz: Number(event.target.value) } })} /></label><label>Stop (Hz)<input type="number" min="2" value={setup.frequency.stop_hz} onChange={event => replace({ frequency: { ...setup.frequency, stop_hz: Number(event.target.value) } })} /></label><label>Points<input type="number" min="2" max="100000" value={setup.frequency.points} onChange={event => replace({ frequency: { ...setup.frequency, points: Number(event.target.value) } })} /></label></div>
      </section>
    </>}

    {section === "prepass" && <section className="emi-section">
      <label>ELECTRICAL PRE-PASS METRICS</label>
      <p className="emi-note">Enter measured values or values exported from PI, transient, or SPICE analyses. Geometry alone is not treated as an emission prediction.</p>
      <div className="emi-metric-list">
        {setup.net_metrics.map(metric => <article key={metric.net} onMouseEnter={() => previewViewportTarget({ kind: "net", net: metric.net, label: metric.net })} onMouseLeave={() => previewViewportTarget(null)}>
          <b>{metric.net}</b>
          <label>Source<select value={metric.source} onChange={event => updateMetric(metric.net, "source", event.target.value)}><option value="unassigned">Unassigned</option><option value="pi_transient">PI transient</option><option value="spice">SPICE</option><option value="measured">Measured</option><option value="manual">Manual</option></select></label>
          <div className="emi-field-grid"><label>dV/dt (V/s)<input type="number" min="0" value={metric.dv_dt_v_per_s} onChange={event => updateMetric(metric.net, "dv_dt_v_per_s", event.target.value)} /></label><label>dI/dt (A/s)<input type="number" min="0" value={metric.di_dt_a_per_s} onChange={event => updateMetric(metric.net, "di_dt_a_per_s", event.target.value)} /></label><label>Peak I (A)<input type="number" min="0" value={metric.peak_current_a} onChange={event => updateMetric(metric.net, "peak_current_a", event.target.value)} /></label><label>Loop area (mm²)<input type="number" min="0" value={metric.loop_area_mm2} onChange={event => updateMetric(metric.net, "loop_area_mm2", event.target.value)} /></label><label>Return breaks<input type="number" min="0" step="1" value={metric.return_discontinuities} onChange={event => updateMetric(metric.net, "return_discontinuities", event.target.value)} /></label></div>
        </article>)}
        {!setup.net_metrics.length && <p>Select candidate nets in the Domain stage.</p>}
      </div>
      <button className="emi-primary" disabled={busy || !board} onClick={onScreen}><Gauge size={14} /> {busy ? "Working" : "Run screening"}</button>
    </section>}

    {section === "excitation" && <section className="emi-section">
      <label>FULL-WAVE EXCITATION</label>
      <select value={setup.excitation.mode} onChange={event => replace({ excitation: { ...setup.excitation, mode: event.target.value as EmiSetup["excitation"]["mode"] } })}>
        <option value="prepass_results">PI/transient result metrics (screening only)</option><option value="explicit_ports">Explicit lumped ports</option><option value="spice">Closed-loop SPICE (unavailable)</option>
      </select>
      {setup.excitation.mode === "explicit_ports" && <>
        <div className="emi-inline-actions"><button onClick={addPort}><Plus size={13} /> Add port</button><span>Exactly one excited</span></div>
        <div className="emi-port-list">{setup.excitation.ports.map((port, index) => <article key={port.id}>
          <header><input value={port.name} onChange={event => updatePort(index, { name: event.target.value })} /><label><input type="radio" name="emi-excited-port" checked={port.excite} onChange={() => setSetup(current => ({ ...current, excitation: { ...current.excitation, ports: current.excitation.ports.map((item, itemIndex) => ({ ...item, excite: itemIndex === index })) } }))} /> Excite</label><button onClick={() => setSetup(current => ({ ...current, excitation: { ...current.excitation, ports: current.excitation.ports.filter((_, itemIndex) => itemIndex !== index) } }))} title="Remove port"><Trash2 size={13} /></button></header>
          <div className="emi-coordinate"><b>Start XYZ</b>{port.start.map((value, axis) => <input key={`s-${axis}`} type="number" value={value} onChange={event => updateCoordinate(index, "start", axis, event.target.value)} />)}</div>
          <div className="emi-coordinate"><b>Stop XYZ</b>{port.stop.map((value, axis) => <input key={`e-${axis}`} type="number" value={value} onChange={event => updateCoordinate(index, "stop", axis, event.target.value)} />)}</div>
          <div className="emi-field-grid"><label>Direction<select value={port.direction} onChange={event => updatePort(index, { direction: event.target.value as EmiPort["direction"] })}><option>x</option><option>y</option><option>z</option></select></label><label>Impedance Ω<input type="number" min="0.001" value={port.impedance_ohm} onChange={event => updatePort(index, { impedance_ohm: Number(event.target.value) })} /></label></div>
        </article>)}</div>
      </>}
      <div className="emi-gate"><ShieldAlert size={14} /><span><b>Execution gate</b>Port coordinates are validated again against exported conductors. Closed-loop SPICE excitation remains unavailable.</span></div>
    </section>}

    {section === "solver" && <section className="emi-section">
      <label>FIELD SOLVER</label>
      <div className="emi-field-grid"><label>Resolution (mm)<input type="number" min="0.0001" step="0.05" value={setup.mesh.resolution_mm} onChange={event => replace({ mesh: { ...setup.mesh, resolution_mm: Number(event.target.value) } })} /></label><label>Boundary cells<input type="number" min="2" max="40" value={setup.mesh.padding_cells} onChange={event => replace({ mesh: { ...setup.mesh, padding_cells: Number(event.target.value) } })} /></label><label>Time limit (s)<input type="number" min="1" max="604800" value={setup.max_solver_time_s} onChange={event => replace({ max_solver_time_s: Number(event.target.value) })} /></label></div>
      <div className="emi-solver-card">
        <CircuitBoard size={16} />
        <span><b>{preflight?.solver_recommendation.recommended?.name ?? "No eligible EMI solver"}</b><small>{preflight?.solver_recommendation.recommended?.reason ?? "Register a compatible engine in Solver Manager. No full-wave or far-field result is inferred by the UI."}</small></span>
      </div>
      <button className="secondary-btn" onClick={onSolverManager}><SlidersHorizontal size={14} /> Solver Manager</button>
      <div className="emi-viewport-options"><label><input type="checkbox" checked={setup.viewport.translucent_board} onChange={event => replace({ viewport: { ...setup.viewport, translucent_board: event.target.checked } })} /> Translucent board</label><label><input type="checkbox" checked={setup.viewport.analysis_nets_only} onChange={event => replace({ viewport: { ...setup.viewport, analysis_nets_only: event.target.checked } })} /> Analysis nets only</label></div>
    </section>}

    {preflight?.issues.length ? <div className="emi-issues">{preflight.issues.slice(0, 6).map(issue => <div key={`${issue.code}:${issue.message}`} className={issue.severity}><span>{issue.severity === "error" ? <AlertTriangle size={13} /> : <ShieldAlert size={13} />}</span><p><b>{issue.code.replace(/^EMI_/, "").replace(/_/g, " ")}</b>{issue.message}</p></div>)}</div> : null}
    {screening?.screening && <button className="emi-screen-summary" onClick={onDashboard}><RadioTower size={14} /><span><b>Screening complete</b>{screening.screening.recommended_nets[0]?.net ?? "No ranked net"} is first for full-wave review</span></button>}
    <footer className="emi-actions">
      <button onClick={onValidate} disabled={busy || !board}><ShieldAlert size={13} /> Validate</button>
      <button onClick={onPrepare} disabled={busy || !board || preflight?.can_prepare === false}><Layers3 size={13} /> Prepare</button>
      <button onClick={onRun} disabled={busy || !preflight?.can_run || !canExecutePreparedCase}><Play size={13} /> Run</button>
      <button onClick={onDashboard} disabled={!preflight && !screening}><Waves size={13} /> Review</button>
    </footer>
  </div>;
}

export function EmiDashboard({ embedded = false, preflight, screening, fieldResult, onClose, onScreen, onPrepare, onSolverManager }: {
  embedded?: boolean;
  preflight: EmiPreflight | null;
  screening: EmiScreening | null;
  fieldResult: EmiFieldResult | null;
  onClose: () => void;
  onScreen: () => void;
  onPrepare: () => void;
  onSolverManager: () => void;
}) {
  const [frequencyIndex, setFrequencyIndex] = useState(0);
  const active = preflight ?? screening?.preflight;
  const ranking = screening?.screening?.recommended_nets ?? [];
  const farField = fieldResult?.far_field;
  const activeFrequencyIndex = Math.min(frequencyIndex, Math.max((farField?.frequencies_hz.length ?? 1) - 1, 0));
  const thetaCount = farField?.shape?.[1] ?? 0;
  const phiCount = farField?.shape?.[2] ?? 0;
  const nearestIndex = (values: number[], target: number) => values.length
    ? values.reduce((best, value, index) => Math.abs(value - target) < Math.abs(values[best] - target) ? index : best, 0)
    : 0;
  const phiZero = farField ? nearestIndex(farField.phi_deg, 0) : 0;
  const phiOpposite = farField ? nearestIndex(farField.phi_deg, 180) : 0;
  const directivity = farField?.directivity.linear ?? [];
  const cutSamples = farField && thetaCount > 1 && phiCount > 1 ? [
    ...farField.theta_deg.map((angle, thetaIndex) => ({
      angle,
      value: directivity[(activeFrequencyIndex * thetaCount + thetaIndex) * phiCount + phiZero] ?? 0,
    })),
    ...farField.theta_deg.slice(1, -1).reverse().map((angle, reverseIndex) => {
      const thetaIndex = thetaCount - reverseIndex - 2;
      return {
        angle: 360 - angle,
        value: directivity[(activeFrequencyIndex * thetaCount + thetaIndex) * phiCount + phiOpposite] ?? 0,
      };
    }),
  ] : [];
  const maximum = cutSamples.reduce((current, sample) => Math.max(current, sample.value), 0);
  const maximumDb = maximum > 0 ? 10 * Math.log10(maximum) : 0;
  const polarPoints = cutSamples.map(sample => {
    const sampleDb = sample.value > 0 ? 10 * Math.log10(sample.value) : maximumDb - 40;
    const radius = 16 + 76 * Math.max(0, Math.min(1, (sampleDb - (maximumDb - 40)) / 40));
    const angle = sample.angle * Math.PI / 180;
    return `${140 + radius * Math.sin(angle)},${108 - radius * Math.cos(angle)}`;
  }).join(" ");
  const maximumLinear = farField?.directivity.maximum_linear[activeFrequencyIndex] ?? maximum;
  const maximumDirectivityDb = maximumLinear > 0 ? 10 * Math.log10(maximumLinear) : null;
  const radiatedPower = farField?.radiated_power.total_w[activeFrequencyIndex] ?? null;
  return <div className={embedded ? "emi-dashboard-embedded" : "modal-shade"}><section className="emi-dashboard" role={embedded ? "region" : "dialog"} aria-modal={embedded ? undefined : true} aria-label="EM review dashboard">
    <header><span><RadioTower size={18} /><b>EM TESTER</b><small>Screening, solver readiness, and field-workflow review</small></span><button onClick={onClose} title="Close EM dashboard"><X size={16} /></button></header>
    <div className="emi-dashboard-summary">
      <article><small>Workflow status</small><b>{(active?.status ?? "not validated").replace(/_/g, " ")}</b></article>
      <article><small>Screening</small><b>{active?.can_screen ? "Ready" : "Needs input"}</b></article>
      <article><small>Case preparation</small><b>{active?.can_prepare ? "Ready" : "Blocked"}</b></article>
      <article><small>Full-wave solve</small><b>{farField ? "Computed" : active?.can_run ? "Ready" : "Capability gated"}</b></article>
    </div>
    <div className="emi-dashboard-body">
      <section><h3>Process readiness</h3><div className="emi-stage-grid">{(active?.stages ?? []).map((stage, index) => <article key={stage.id} className={stageTone(stage.state)}><span>{index + 1}</span><div><b>{stage.name}</b><small>{stage.detail}</small></div><em>{stage.state.replace(/_/g, " ")}</em></article>)}</div></section>
      <section><h3>Pre-pass ranking</h3>{ranking.length ? <div className="emi-ranking"><header><span>Priority</span><span>Net</span><span>Score</span><span>Evidence</span></header>{ranking.map((row, index) => <div key={row.net} onMouseEnter={() => previewViewportTarget({ kind: "net", net: row.net, label: row.net })} onMouseLeave={() => previewViewportTarget(null)}><b>{index + 1}</b><span>{row.net}</span><strong>{row.score.toFixed(1)}</strong><small>{row.reasons.join(", ") || "equal supplied metrics"}<br />{row.geometry.routed_length_mm?.toFixed(2) ?? "0"} mm · {row.geometry.vias ?? 0} vias · {row.geometry.layers?.length ?? 0} layers</small></div>)}</div> : <div className="emi-empty"><Gauge size={24} /><b>No screening record</b><p>Supply defensible electrical pre-pass metrics, then run screening. Geometry is not substituted for missing electrical behavior.</p><button onClick={onScreen}>Run screening</button></div>}</section>
      <section className="emi-field-review"><h3>NF2FF far-field result</h3>{farField ? <>
        <div className="emi-field-toolbar"><label>Frequency<select value={activeFrequencyIndex} onChange={event => setFrequencyIndex(Number(event.target.value))}>{farField.frequencies_hz.map((value, index) => <option key={`${value}-${index}`} value={index}>{value >= 1e9 ? `${(value / 1e9).toFixed(4)} GHz` : `${(value / 1e6).toFixed(3)} MHz`}</option>)}</select></label><span className={`emi-field-validity ${farField.validation_status}`}>{farField.validation_status.replace(/_/g, " ")}</span></div>
        <div className="emi-polar-result"><svg viewBox="0 0 280 216" role="img" aria-label="Directivity polar cut at phi zero and 180 degrees"><g className="polar-grid"><circle cx="140" cy="108" r="92" /><circle cx="140" cy="108" r="69" /><circle cx="140" cy="108" r="46" /><circle cx="140" cy="108" r="23" /><line x1="48" y1="108" x2="232" y2="108" /><line x1="140" y1="16" x2="140" y2="200" /></g>{polarPoints && <polyline className="polar-trace" points={polarPoints} />}</svg><div className="emi-field-metrics"><article><small>Peak directivity</small><b>{maximumDirectivityDb === null ? "-" : `${maximumDirectivityDb.toFixed(3)} dBi`}</b><span>{maximumLinear.toPrecision(6)} linear</span></article><article><small>Radiated power</small><b>{radiatedPower === null ? "-" : `${radiatedPower.toExponential(5)} W`}</b><span>NF2FF integration</span></article><article><small>Angular samples</small><b>{thetaCount * phiCount}</b><span>{thetaCount} theta x {phiCount} phi</span></article><article><small>Observation radius</small><b>{farField.radius_m.toPrecision(5)} m</b><span>phase center {farField.center_mm.map(value => value.toFixed(2)).join(", ")} mm</span></article></div></div>
        <EmiFieldPlots field={farField} frequencyIndex={activeFrequencyIndex} onFrequency={setFrequencyIndex} />
        <div className="emi-field-boundary"><ShieldAlert size={14} /><span><b>Validity boundary</b>This is a computed openEMS NF2FF result. The adapter has a reference-validated patch fixture, but this board result remains {farField.validation_status.replace(/_/g, " ")} until mesh convergence and independent correlation are attached.</span></div>
      </> : <div className="emi-empty"><RadioTower size={24} /><b>No NF2FF result loaded</b><p>Request far field, define a valid explicit port, prepare the case, and run openEMS. SPIKE will retain the structured field result here.</p></div>}</section>
      <section className="emi-validity-review"><h3>Validity and issues</h3><div className="emi-dashboard-issues">{(active?.issues ?? []).map(issue => <article key={`${issue.code}:${issue.message}`} className={issue.severity}>{issue.severity === "error" ? <AlertTriangle size={14} /> : issue.severity === "warning" ? <ShieldAlert size={14} /> : <CheckCircle2 size={14} />}<span><b>{issue.code}</b><p>{issue.message}</p>{issue.suggestion && <small>{issue.suggestion}</small>}</span></article>)}</div></section>
    </div>
    <footer><p><ShieldAlert size={14} /> {farField ? "NF2FF data is a solver result, not a compliance certification. Preserve convergence and correlation evidence." : "Screening prioritizes investigation only. It is not a radiated-emission or compliance result."}</p><button onClick={onSolverManager}>Solver Manager</button><button onClick={onPrepare} disabled={!active?.can_prepare}>Prepare openEMS case</button></footer>
  </section></div>;
}
