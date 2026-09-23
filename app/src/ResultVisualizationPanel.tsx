import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Download, Eye, EyeOff, Grid3X3, Layers3, Pause, Play, RadioTower, SlidersHorizontal, Waves, X } from "lucide-react";
import type { ParsedBoard } from "./boardParser";
import { previewViewportTarget } from "./BoardViewport";
import {
  PdnCandidateRequest, PdnReview, ResultVisualization, ResultViewMode, SolverResultBundle, ViaModel, resultModeAvailable,
} from "./analysisResults";
import { buildResultEngineeringAnalytics } from "./resultAnalytics";
import { resultSolvedForPresentation } from "./resultAdmission";
import { buildDcReview } from "./dcReview";
import { sourceLoadReview } from "./sourceLoadReview";
import PiPdnReview from "./PiPdnReview";
import { viaStressMapSvg } from "./viaStressMap";
import { resultDatumLayers, resultLayerMatchesSelection } from "./resultLayerSelection";
import { numericExtent } from "./numericRange";

const modes: { id: ResultViewMode; label: string; icon: typeof Activity }[] = [
  { id: "geometry", label: "Geometry", icon: Eye },
  { id: "voltage", label: "Absolute voltage", icon: Activity },
  { id: "voltage_drop", label: "Relative drop", icon: Activity },
  { id: "current", label: "Current", icon: Waves },
  { id: "current_density", label: "Current density", icon: Waves },
  { id: "power_loss", label: "Copper loss", icon: Activity },
  { id: "via_stress", label: "Via stress", icon: Waves },
  { id: "impedance", label: "Impedance", icon: Activity },
  { id: "mesh", label: "Solver mesh", icon: Grid3X3 },
  { id: "electric_field", label: "Electric field", icon: RadioTower },
  { id: "magnetic_field", label: "Magnetic field", icon: Waves },
];

type Props = {
  domain: "pi" | "si";
  board: ParsedBoard | null;
  selectedNet: string | null;
  result: SolverResultBundle | null;
  sourceResult: SolverResultBundle | null;
  visualization: ResultVisualization;
  workerAvailable: boolean;
  parasiticsAvailable: boolean;
  riskAvailable: boolean;
  pdnReview: PdnReview | null;
  pdnReviewSourceId: string | null;
  densityLimitAMm2: number | null;
  dropLimitMv?: number | null;
  onVisualization: (value: ResultVisualization) => void;
  onConfigure: () => void;
  onRunParasitics: (viaModel: ViaModel) => void;
  onRunRisk: (victims: string[], aggressors: string[]) => void;
  onRunPdn: (targetOhm: number, candidate: PdnCandidateRequest) => void;
  onExportAnimation: () => void;
  onClose: () => void;
  onDetach?: () => void;
  onTracePlots?: () => void;
};

export default function ResultVisualizationPanel({
  domain, board, selectedNet, result: rawResult, sourceResult: rawSourceResult, visualization, workerAvailable, parasiticsAvailable, riskAvailable, pdnReview, pdnReviewSourceId, densityLimitAMm2, dropLimitMv,
  onVisualization, onConfigure, onRunParasitics, onRunRisk, onRunPdn, onExportAnimation, onClose, onDetach, onTracePlots,
}: Props) {
  const result = rawResult?.status === "preview" || resultSolvedForPresentation(rawResult) ? rawResult : null;
  const sourceResult = resultSolvedForPresentation(rawSourceResult) ? rawSourceResult : null;
  const [pdnTarget, setPdnTarget] = useState("0.05");
  const [candidateCuf, setCandidateCuf] = useState("100");
  const [candidateEsrMohm, setCandidateEsrMohm] = useState("10");
  const [candidateEslNh, setCandidateEslNh] = useState("1");
  const [candidateCount, setCandidateCount] = useState("1");
  const [candidateMountMohm, setCandidateMountMohm] = useState("0");
  const [candidateMountNh, setCandidateMountNh] = useState("0");
  const [candidatePortId, setCandidatePortId] = useState("");
  const nets = [...new Set(Object.values(board?.nets ?? {}).filter(Boolean))].sort();
  const visibleModes = modes.filter(mode => domain === "pi"
    ? !["electric_field", "magnetic_field"].includes(mode.id)
    : !["voltage", "voltage_drop", "current", "current_density", "power_loss", "via_stress"].includes(mode.id));
  const selected = selectedNet ?? nets[0] ?? "";
  const displayedNets = selected && !nets.slice(0, 20).includes(selected)
    ? [selected, ...nets.filter(net => net !== selected).slice(0, 19)]
    : nets.slice(0, 20);
  const update = (patch: Partial<ResultVisualization>) => onVisualization({ ...visualization, ...patch });
  useEffect(() => {
    if (visibleModes.some(mode => mode.id === visualization.mode)) return;
    update({ mode: result?.mesh.length ? "mesh" : "geometry" });
  }, [domain]);
  const selectedGeometry = selected ? {
    tracks: board?.tracks.filter(item => item.net === selected) ?? [],
    zones: board?.zones.filter(item => item.net === selected) ?? [],
    vias: board?.vias.filter(item => item.net === selected) ?? [],
    pads: board?.pads.filter(item => item.net === selected) ?? [],
  } : { tracks: [], zones: [], vias: [], pads: [] };
  const geometryCount = Object.values(selectedGeometry).reduce((sum, items) => sum + items.length, 0);
  const geometryLayers = [...new Set([
    ...selectedGeometry.tracks.map(item => item.layer),
    ...selectedGeometry.zones.map(item => item.layer),
    ...selectedGeometry.vias.flatMap(item => item.layers.some(layer => layer === "*.Cu" || layer === "F&B.Cu") ? board?.layers ?? [] : item.layers),
    ...selectedGeometry.pads.flatMap(item => item.layers.some(layer => layer === "*.Cu" || layer === "F&B.Cu") ? board?.layers ?? [] : item.layers),
  ].filter(layer => Boolean(layer) && Boolean(board?.layers.includes(layer))))];
  const toggleList = (selector: string) =>
    [...document.querySelectorAll<HTMLInputElement>(selector)].filter(input => input.checked).map(input => input.value);
  const selectedParasitic = result?.parasitics.find(item => item.net === selected) ?? result?.parasitics[0];
  const selectedLoopParasitic = result?.loop_parasitics.find(item =>
    item.forward_nets.includes(selected) || item.return_nets.includes(selected),
  ) ?? (!selectedParasitic ? result?.loop_parasitics[0] : undefined);
  const selectedImpedanceNetwork = selectedLoopParasitic?.impedance.length
    ? { kind: "loop" as const, name: selectedLoopParasitic.name, points: selectedLoopParasitic.impedance }
    : selectedParasitic?.impedance?.length
      ? { kind: "net" as const, name: selectedParasitic.net, points: selectedParasitic.impedance }
      : null;
  const piOperatingImpedance = result?.scalar_fields.operating_point_impedance_ohm ?? [];
  const siParasiticsAvailable = Boolean(selectedLoopParasitic || selectedParasitic);
  const impedanceAvailable = domain === "pi" ? piOperatingImpedance.length > 0 : siParasiticsAvailable;
  const siResistanceOhm = selectedLoopParasitic
    ? selectedLoopParasitic.geometry_resistance_ohm + selectedLoopParasitic.component_resistance_ohm
    : selectedParasitic?.resistance_ohm;
  const siInductanceH = selectedLoopParasitic?.total_loop_inductance_h ?? selectedParasitic?.inductance_h;
  const siCapacitanceF = selectedLoopParasitic?.estimated_net_capacitance_f ?? selectedParasitic?.capacitance_f;
  const siConductanceS = selectedParasitic?.conductance_s;
  const selectedMultiport = result?.pdn_multiports.find(item => item.net === selected) ?? result?.pdn_multiports[0];
  const candidatePorts = selectedMultiport?.candidates ?? [];
  const candidatePort = candidatePorts.find(item => item.id === candidatePortId);
  useEffect(() => {
    if (candidatePortId && candidatePorts.some(item => item.id === candidatePortId)) return;
    setCandidatePortId(candidatePorts[0]?.id ?? "");
  }, [selectedMultiport?.source_result_id, selected]);
  const rawScalarSamples = visualization.mode === "voltage"
    ? result?.scalar_fields.voltage_v ?? []
    : visualization.mode === "voltage_drop"
      ? result?.scalar_fields.voltage_drop_v ?? []
      : visualization.mode === "current"
        ? result?.scalar_fields.current_a ?? []
      : visualization.mode === "current_density"
        ? result?.scalar_fields.current_density_a_mm2 ?? []
      : visualization.mode === "power_loss"
        ? result?.scalar_fields.power_loss_w ?? []
      : visualization.mode === "via_stress"
        ? result?.scalar_fields.via_current_density_a_mm2 ?? []
      : visualization.mode === "impedance" && domain === "pi"
        ? piOperatingImpedance
        : [];
  const boardLayers = board?.layers ?? [];
  const resultLayers = [...new Set([
    ...rawScalarSamples.flatMap(sample => resultDatumLayers(sample.layer, boardLayers)),
    ...(result?.mesh ?? []).flatMap(cell => resultDatumLayers(cell.layer, boardLayers)),
    ...(result?.vector_fields.current_density ?? []).flatMap(sample => resultDatumLayers(sample.layer, boardLayers)),
    ...(result?.vector_fields.electric_field ?? []).flatMap(sample => resultDatumLayers(sample.layer, boardLayers)),
    ...(result?.vector_fields.magnetic_field ?? []).flatMap(sample => resultDatumLayers(sample.layer, boardLayers)),
  ].filter(layer => Boolean(layer) && layer !== "through"))]
    .sort((left, right) => (board?.layers.indexOf(left) ?? 999) - (board?.layers.indexOf(right) ?? 999));
  const layerSelected = (layer?: string) => resultLayerMatchesSelection(layer, visualization.visibleResultLayers, boardLayers);
  const scalarSamples = rawScalarSamples.filter(sample => layerSelected(sample.layer));
  const activeCount = visualization.mode === "geometry" ? geometryCount
    : visualization.mode === "mesh" ? result?.mesh.filter(cell => layerSelected(cell.layer)).length
    : visualization.mode === "impedance" ? (domain === "pi" ? scalarSamples.length : selectedImpedanceNetwork?.points.length ?? (siParasiticsAvailable ? 1 : 0))
    : visualization.mode === "electric_field" ? result?.vector_fields.electric_field.filter(sample => layerSelected(sample.layer)).length
      : visualization.mode === "magnetic_field" ? result?.vector_fields.magnetic_field.filter(sample => layerSelected(sample.layer)).length
        : scalarSamples.length;
  const toggleResultLayer = (layer: string) => {
    const selected = visualization.visibleResultLayers;
    const next = !selected.length
      ? resultLayers.filter(candidate => candidate !== layer)
      : selected.includes(layer)
        ? selected.filter(candidate => candidate !== layer)
        : [...selected, layer];
    update({ visibleResultLayers: next.length === resultLayers.length ? [] : next });
  };
  const values = scalarSamples.map(sample => sample.value).filter(Number.isFinite).sort((a, b) => a - b);
  const minimum = values[0];
  const maximum = values.length ? values[values.length - 1] : undefined;
  const mean = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : undefined;
  const p95 = values.length ? values[Math.min(values.length - 1, Math.floor(values.length * 0.95))] : undefined;
  const unit = visualization.mode === "current_density" || visualization.mode === "via_stress" ? "A/mm2"
    : visualization.mode === "current" ? "A"
      : visualization.mode === "power_loss" ? "W"
        : visualization.mode === "impedance" ? "ohm"
        : visualization.mode === "voltage_drop" ? "mV" : "V";
  const displayValue = (value: number | undefined) => value === undefined
    ? "-"
    : `${(visualization.mode === "voltage_drop" ? value * 1000 : value).toPrecision(6)} ${unit}`;
  const hotspots = [...scalarSamples].sort((a, b) => b.value - a.value).slice(0, 12);
  const impedancePoints = selectedImpedanceNetwork?.points ?? [];
  const selectedImpedanceIndex = impedancePoints.length
    ? impedancePoints.reduce((best, point, index) => {
      if (visualization.impedanceFrequencyHz === null) return best;
      return Math.abs(point.frequency_hz - visualization.impedanceFrequencyHz)
        < Math.abs(impedancePoints[best].frequency_hz - visualization.impedanceFrequencyHz) ? index : best;
    }, 0)
    : 0;
  const selectedImpedancePoint = impedancePoints[selectedImpedanceIndex];
  const impedanceMagnitudes = impedancePoints.map(point => point.magnitude_ohm).filter(value => Number.isFinite(value) && value >= 0);
  const impedanceExtent = numericExtent(impedanceMagnitudes);
  const impedanceMinimum = impedanceExtent.count ? impedanceExtent.minimum : undefined;
  const impedanceMaximum = impedanceExtent.count ? impedanceExtent.maximum : undefined;
  const impedancePlot = (() => {
    if (impedancePoints.length < 2) return "";
    const frequencies = impedancePoints.map(point => Math.log10(Math.max(point.frequency_hz, 1e-30)));
    const magnitudes = impedancePoints.map(point => Math.log10(Math.max(point.magnitude_ohm, 1e-30)));
    const frequencyExtent = numericExtent(frequencies);
    const magnitudeExtent = numericExtent(magnitudes);
    const minF = frequencyExtent.minimum; const maxF = frequencyExtent.maximum;
    const minZ = magnitudeExtent.minimum; const maxZ = magnitudeExtent.maximum;
    return impedancePoints.map((_, index) => {
      const x = 18 + (frequencies[index] - minF) / Math.max(maxF - minF, 1e-12) * 604;
      const y = 132 - (magnitudes[index] - minZ) / Math.max(maxZ - minZ, 1e-12) * 108;
      return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
  })();
  const resultLabel = !result ? rawResult ? `${rawResult.mode.toUpperCase()} / ${rawResult.status} / ${rawResult.model_status}` : "No solver result loaded"
    : result.status === "preview" ? `${result.mode.toUpperCase()} mesh preview / not solved`
      : `${result.mode.toUpperCase()} / ${result.model_status}`;
  const frameCount = sourceResult?.time_series.frames.length ?? 0;
  const activeTime = sourceResult?.time_series.frames[visualization.animationFrame]?.time_s;
  const transientSummary = sourceResult?.summary ?? {};
  const engineeringAnalytics = buildResultEngineeringAnalytics(result?.status === "preview" ? null : result, densityLimitAMm2, {
    ambientTemperatureC: visualization.fusingAmbientC,
    faultDurationS: visualization.fusingDurationS,
  });
  const dcReview = domain === "pi" ? buildDcReview(result, selected || null, visualization.visibleResultLayers, dropLimitMv ?? null, densityLimitAMm2) : null;
  const terminalReview = domain === "pi" ? sourceLoadReview(result, selected || null, dropLimitMv ?? null) : null;
  const vectorMode = ["current", "current_density", "electric_field", "magnetic_field"].includes(visualization.mode);
  const analyticsValue = (value: number | null, unit = "") => value === null ? "-" : `${value.toPrecision(6)}${unit ? ` ${unit}` : ""}`;
  const dcSampleIdentity = (sample: { element_id?: string; source_id?: string; source_kind?: string; net?: string; layer?: string } | null) =>
    sample ? `${sample.element_id || "sample"} / ${sample.net || "net unknown"} / ${sample.layer || "layer unknown"}${sample.source_id ? ` / geometry ${sample.source_kind || "object"} ${sample.source_id}` : " / geometry identity unavailable"}` : "No scoped sample returned";
  const reportedVias = engineeringAnalytics.stressedVias.some(via => via.status !== "ok")
    ? engineeringAnalytics.stressedVias.filter(via => via.status !== "ok").slice(0, 16)
    : engineeringAnalytics.stressedVias.slice(0, 8);
  const bytes = (value: unknown) => {
    const number = Number(value);
    if (!Number.isFinite(number) || number < 0) return "-";
    if (number >= 1024 ** 3) return `${(number / 1024 ** 3).toFixed(2)} GB`;
    if (number >= 1024 ** 2) return `${(number / 1024 ** 2).toFixed(1)} MB`;
    if (number >= 1024) return `${(number / 1024).toFixed(1)} KB`;
    return `${number.toFixed(0)} B`;
  };
  return <section className={`floating-panel result-visualizer domain-${domain}`}>
    <header className="floating-heading"><div><b>{domain === "pi" ? "PI RESULT VIEWER" : "SI / HF RESULT VIEWER"}</b><span>{resultLabel}</span></div>{onTracePlots && <button onClick={onTracePlots}>Trace plots</button>}{onDetach && <button onClick={onDetach} title="Move result controls and analytics to a separate desktop window">Detach</button>}<button onClick={onClose} aria-label="Close"><X size={17} /></button></header>
    <div className="result-visualizer-body">
      <nav className="result-mode-list">
        {visibleModes.map(({ id, label, icon: Icon }) => {
          const available = id === "impedance" ? impedanceAvailable : resultModeAvailable(result, id);
          const canRequestImpedance = domain === "si" && id === "impedance" && Boolean(selected) && workerAvailable && parasiticsAvailable;
          const displayedLabel = id === "impedance" ? domain === "pi" ? "Operating-point V/I" : "R/L/C and Z(f)" : label;
          return <button key={id} className={visualization.mode === id ? "selected" : ""} disabled={!available && !canRequestImpedance} onClick={() => {
            if (!available && id === "impedance") {
              if (domain === "si") onRunParasitics(visualization.viaModel);
              else onConfigure();
              return;
            }
            const revealSpatialField = id !== "geometry" && visualization.sceneMode === "opaque";
            update({
              mode: id,
              sceneMode: id === "geometry" && visualization.sceneMode === "results_only" ? "opaque"
                : revealSpatialField ? "translucent" : visualization.sceneMode,
              translucentScene: revealSpatialField ? true : visualization.translucentScene,
            });
          }}>
            <Icon size={15} /><span>{displayedLabel}</span><small>{available ? id === "geometry" ? "board" : id === "impedance" ? domain === "pi" ? "local V/I field" : "R/L/C/G + Z(f)" : "live overlay" : canRequestImpedance ? "run extraction" : result?.status === "preview" ? "run solver" : "solver required"}</small>
          </button>;
        })}
      </nav>
      <main>
        <div className="result-toolbar">
          <button className={visualization.visible ? "selected" : ""} disabled={domain === "si" && visualization.mode === "impedance"} onClick={() => update({ visible: !visualization.visible })}>
            {visualization.visible ? <Eye size={14} /> : <EyeOff size={14} />} {visualization.visible ? "Overlay shown" : "Overlay hidden"}
          </button>
          <button className={visualization.analysisOnly ? "selected" : ""} onClick={() => update({ analysisOnly: !visualization.analysisOnly })}>
            {visualization.analysisOnly ? <Eye size={14} /> : <EyeOff size={14} />} Analysis nets only
          </button>
          <label>Scene<select value={visualization.sceneMode} onChange={event => {
            const sceneMode = event.target.value as ResultVisualization["sceneMode"];
            update({ sceneMode, translucentScene: sceneMode === "translucent", visible: sceneMode === "results_only" ? true : visualization.visible });
          }}><option value="opaque">Board + analysis</option><option value="translucent">Translucent board</option><option value="analysis_only">Analyzed nets only</option><option value="results_only" disabled={!result || visualization.mode === "geometry"}>Analysis only</option></select></label>
          <button className={visualization.showComponentModels ? "selected" : ""} onClick={() => update({ showComponentModels: !visualization.showComponentModels })}>
            <Layers3 size={14} /> 3D models
          </button>
          <label>Board opacity <input type="range" min="0" max="0.8" step="0.02" disabled={visualization.sceneMode !== "translucent"} value={visualization.boardOpacity} onChange={event => update({ boardOpacity: Number(event.target.value) })} /></label>
          <button className={visualization.plotStyle === "height" ? "selected" : ""} disabled={domain === "si" && visualization.mode === "impedance"} onClick={() => update({ plotStyle: visualization.plotStyle === "height" ? "flat" : "height" })}>
            <Activity size={14} /> Raw height
          </button>
          <button className={visualization.plotStyle === "contour" ? "selected" : ""} disabled={!scalarSamples.length} onClick={() => update({ plotStyle: visualization.plotStyle === "contour" ? "flat" : "contour" })} title="Show an interpolated, layer-aware 3D scalar surface with contour lines">
            <Waves size={14} /> 3D contour
          </button>
          <label>Plot height <input type="range" min="0.1" max="8" step="0.1" disabled={visualization.plotStyle === "flat"} value={visualization.waveHeightScale} onChange={event => update({ waveHeightScale: Number(event.target.value) })} /></label>
          <button className={visualization.fieldStyle === "smooth" ? "selected" : ""} disabled={!scalarSamples.length || visualization.plotStyle === "contour"} onClick={() => update({ fieldStyle: visualization.fieldStyle === "smooth" ? "cells" : "smooth" })} title="Toggle between solver sample cells and a derived smooth display field">
            <Layers3 size={14} /> {visualization.fieldStyle === "smooth" ? "Smooth field" : "Raw cells"}
          </button>
          <button className={visualization.showVectors && vectorMode ? "selected" : ""} disabled={!vectorMode} onClick={() => update({ showVectors: !visualization.showVectors })} title="Show or hide solved direction vectors">
            {visualization.showVectors ? <Eye size={14} /> : <EyeOff size={14} />} Arrows
          </button>
          <label>Arrow scale <input type="range" min="0.2" max="5" step="0.2" disabled={!vectorMode || !visualization.showVectors} value={visualization.vectorScale} onChange={event => update({ vectorScale: Number(event.target.value) })} /></label>
        </div>
        {domain === "si" && visualization.mode === "impedance" && siParasiticsAvailable && <section className="rlcg-summary" aria-label="Extracted R L C G summary">
          <div><span>R</span><b>{siResistanceOhm == null ? "-" : `${(siResistanceOhm * 1000).toPrecision(6)} mOhm`}</b><small>series resistance</small></div>
          <div><span>L</span><b>{siInductanceH == null ? "-" : `${(siInductanceH * 1e9).toPrecision(6)} nH`}</b><small>{selectedLoopParasitic ? "loop inductance" : "partial inductance"}</small></div>
          <div><span>C</span><b>{siCapacitanceF == null ? "-" : `${(siCapacitanceF * 1e12).toPrecision(6)} pF`}</b><small>reference capacitance</small></div>
          <div><span>G</span><b>{siConductanceS == null ? "-" : `${siConductanceS.toPrecision(6)} S`}</b><small>dielectric conductance</small></div>
        </section>}
        {resultLayers.length > 1 && <div className="result-layer-filter" aria-label="Solved result layers">
          <span><Layers3 size={14} /> Result layers</span>
          <button className={!visualization.visibleResultLayers.length ? "selected" : ""} onClick={() => update({ visibleResultLayers: [] })}>All stitched</button>
          {resultLayers.map(layer => <button
            key={layer}
            className={!visualization.visibleResultLayers.length || visualization.visibleResultLayers.includes(layer) ? "selected" : ""}
            onClick={() => toggleResultLayer(layer)}
            title={`Toggle ${layer} solver samples while preserving physical layer height`}
          >{layer}</button>)}
        </div>}
        <div className="result-animation-bar">
          <button disabled={frameCount < 2} onClick={() => update({ animationPlaying: !visualization.animationPlaying })}>
            {visualization.animationPlaying ? <Pause size={14} /> : <Play size={14} />} {visualization.animationPlaying ? "Pause" : "Animate"}
          </button>
          <input aria-label="Animation frame" type="range" min="0" max={Math.max(0, frameCount - 1)} value={Math.min(visualization.animationFrame, Math.max(0, frameCount - 1))} disabled={frameCount < 2} onChange={event => update({ animationPlaying: false, animationFrame: Number(event.target.value) })} />
          <span>{frameCount ? `Frame ${visualization.animationFrame + 1}/${frameCount}${activeTime === undefined ? "" : ` / ${activeTime.toPrecision(6)} s`}` : "Static result"}</span>
          <label>FPS <input type="number" min="1" max="30" value={visualization.animationFps} onChange={event => update({ animationFps: Math.max(1, Math.min(30, Number(event.target.value) || 1)) })} /></label>
          <button disabled={frameCount < 2} onClick={onExportAnimation}><Download size={14} /> Export GIF</button>
          {frameCount > 0 && <span className="transient-resource-readout" title="Solver workspace is a deterministic allocation total; peak is a conservative pre-solve estimate.">
            Stored {bytes(transientSummary.stored_transient_numeric_bytes)} / arrays {bytes(transientSummary.actual_dense_array_bytes)} / peak estimate {bytes(transientSummary.estimated_peak_worker_bytes)} / {Number(transientSummary.solve_wall_time_s ?? 0).toPrecision(4)} s
          </span>}
        </div>
        <section className="result-overlay-notice">
          <Eye size={14} /><div><b>{visualization.mode === "impedance" ? domain === "pi" ? "OPERATING-POINT V/I OVERLAY" : "FREQUENCY-DOMAIN R/L/C/G NETWORK" : "LIVE BOARD OVERLAY"}</b><span>{visualization.mode === "impedance" ? domain === "pi" ? "Each solved conductor sample is |Vlocal / Ibranch| in ohms. This DC operating-point ratio is spatially rendered and is not broadband Z(f)." : "The SI/HF view reports extracted resistance, partial inductance, capacitance, conductance, and the port-defined Z(f) sweep. It is not inferred from DC color fields." : "The selected view is rendered in the 2D/3D board viewport beside this panel. Close this panel for the full canvas."}</span></div>
        </section>
        <section className="result-data-status">
          <b>{visualization.mode === "impedance" ? domain === "pi" ? "Operating-point V/I" : "R/L/C and Z(f)" : modes.find(item => item.id === visualization.mode)?.label}</b>
          <strong>{activeCount ?? 0} {visualization.mode === "impedance" && domain === "si" ? "network records" : "samples"}</strong>
          <span>{visualization.mode === "geometry" ? "Native design geometry" : visualization.mode === "impedance" && impedanceAvailable ? domain === "pi" ? "Spatial V/I from solved DC output" : "Extracted R/L/C/G and frequency sweep" : resultModeAvailable(result, visualization.mode) ? "Rendered from solver output" : "No compatible field dataset in the current result"}</span>
        </section>
        {rawResult && !result && <section className="result-workflow-state" role="alert"><AlertTriangle size={14} /><div><b>Result unavailable for review</b><span>{rawResult.status} / {rawResult.model_status}. Partial samples are diagnostic only and are hidden from engineering analytics.</span></div></section>}
        {dcReview && <section className="result-engineering-analytics" aria-label="DC source to board review">
          <header><div><b>DC SOURCE TO BOARD REVIEW</b><span>{selected || "All nets"} / {visualization.visibleResultLayers.length ? visualization.visibleResultLayers.join(", ") : "all layers"} / {result?.model_status} / {result?.analysis_id}</span></div></header>
          <dl className="probe-extrema">
            <dt>Maximum declared source voltage</dt><dd>{analyticsValue(dcReview.sourceVoltageV, "V")}{terminalReview ? " (terminal paths below)" : " (source terminal identity is not returned)"}</dd>
            <dt>Lowest returned board voltage</dt><dd>{analyticsValue(dcReview.lowestVoltage?.value ?? null, "V")}; {dcSampleIdentity(dcReview.lowestVoltage)}</dd>
            <dt>Highest returned board drop</dt><dd>{analyticsValue(dcReview.highestDrop === null ? null : dcReview.highestDrop.value * 1000, "mV")}; {dcSampleIdentity(dcReview.highestDrop)}</dd>
            <dt>Selected sample / current drop limit</dt><dd>{dcReview.drop.limit === null ? "No positive limit configured" : analyticsValue(dcReview.drop.limit * 1000, "mV")} / {dcReview.drop.state}</dd>
            <dt>Highest copper density</dt><dd>{analyticsValue(dcReview.highestDensity?.value ?? null, "A/mm2")}; {dcSampleIdentity(dcReview.highestDensity)}</dd>
            <dt>Selected sample / current density limit</dt><dd>{dcReview.density.limit === null ? "No positive limit configured" : analyticsValue(dcReview.density.limit, "A/mm2")} / {dcReview.density.state}</dd>
            <dt>Highest via density</dt><dd>{analyticsValue(dcReview.highestViaDensity?.value ?? null, "A/mm2")}; {dcSampleIdentity(dcReview.highestViaDensity)}</dd>
          </dl>
          {terminalReview && <div className="source-load-review" aria-label="Source to load terminal paths">
            <h4>Source to load terminals · {terminalReview.status}</h4>
            <p>Voltage reference: {terminalReview.voltageReference}. Source current balance: {terminalReview.sourceCurrentBalanceA === null ? "not returned" : analyticsValue(terminalReview.sourceCurrentBalanceA, "A")}.</p>
            <table><thead><tr><th>Source → load</th><th>Source</th><th>Load</th><th>Supply drop</th><th>Loop drop</th><th>Load current</th><th>Limit</th></tr></thead>
              <tbody>{terminalReview.paths.map((path, index) => <tr key={`${path.sourceId}-${path.loadId}-${index}`}>
                <td>{path.sourceId} → {path.loadId}<small>{path.supplyNet}{path.returnNet ? ` / return ${path.returnNet}` : ""}</small></td>
                <td>{analyticsValue(path.sourceVoltageV, "V")}</td><td>{analyticsValue(path.loadVoltageV, "V")}</td>
                <td>{analyticsValue(path.supplyDropV * 1000, "mV")}</td>
                <td>{path.loopDropV === null ? "No explicit return" : analyticsValue(path.loopDropV * 1000, "mV")}</td>
                <td>{analyticsValue(path.loadCurrentA, "A")}</td><td>{path.limitState}</td>
              </tr>)}</tbody></table>
          </div>}
          <p className="analytics-validity-note">These are original solver samples for the selected net and layers. {terminalReview ? "The terminal paths are separately anchored solver values; field extrema need not coincide with load pads." : "The worst board sample is not identified as a load terminal. A source-to-load voltage budget requires returned terminal identities and values."} {result?.model_status === "approximate" ? "This DC solve is approximate; check mesh convergence before engineering sign-off." : "Review model validity and mesh convergence before engineering sign-off."}</p>
        </section>}
        {!result && <section className="result-workflow-state">
          <div>
            <b>{selected || "No analysis net selected"}</b>
            <span>{geometryCount} copper objects on {geometryLayers.length} layer{geometryLayers.length === 1 ? "" : "s"}</span>
            <small>{selectedGeometry.tracks.length} tracks · {selectedGeometry.zones.length} zones · {selectedGeometry.vias.length} vias · {selectedGeometry.pads.length} pads</small>
          </div>
          <div className="result-layer-list">{geometryLayers.length ? geometryLayers.map(layer => <span key={layer}>{layer}</span>) : <span>No routed geometry</span>}</div>
          <button className="secondary-btn" onClick={onConfigure}><SlidersHorizontal size={14} /> Configure PI and preview mesh</button>
          {!workerAvailable && <p><AlertTriangle size={14} /> Solver execution is available in SPIKE Desktop. This browser view supports configuration and visualization only.</p>}
        </section>}
        {(scalarSamples.length > 0 || (visualization.mode === "impedance" && (selectedLoopParasitic || selectedParasitic))) && <section className="result-inspection-grid">
          <div className="field-statistics">
            {visualization.mode === "impedance" && domain === "si" && selectedImpedancePoint ? <>
              <div className="impedance-plot" aria-label="Log-frequency impedance magnitude plot">
                <svg viewBox="0 0 640 150" preserveAspectRatio="none"><path className="grid" d="M18 24H622M18 78H622M18 132H622" /><path className="trace" d={impedancePlot} /></svg>
              </div>
              <input className="impedance-frequency-slider" aria-label="Impedance frequency" type="range" min="0" max={Math.max(0, impedancePoints.length - 1)} value={selectedImpedanceIndex} onChange={event => update({ impedanceFrequencyHz: impedancePoints[Number(event.target.value)]?.frequency_hz ?? null })} />
              <dl>
                <dt>Selected frequency</dt><dd>{selectedImpedancePoint.frequency_hz.toPrecision(6)} Hz</dd>
                <dt>Magnitude</dt><dd>{selectedImpedancePoint.magnitude_ohm.toPrecision(6)} Ohm</dd>
                <dt>Resistance / reactance</dt><dd>{selectedImpedancePoint.resistance_ohm?.toPrecision(6) ?? "-"} / {selectedImpedancePoint.reactance_ohm?.toPrecision(6) ?? "-"} Ohm</dd>
                <dt>Phase</dt><dd>{selectedImpedancePoint.phase_deg.toPrecision(6)} deg</dd>
                <dt>Sweep minimum / maximum</dt><dd>{impedanceMinimum?.toPrecision(6) ?? "-"} / {impedanceMaximum?.toPrecision(6) ?? "-"} Ohm</dd>
              </dl>
            </> : <>
              <div className="field-scale"><span>LOW</span><i /><span>HIGH</span></div>
              <dl>
                <dt>Minimum</dt><dd>{displayValue(minimum)}</dd>
                <dt>Mean</dt><dd>{displayValue(mean)}</dd>
                <dt>95th percentile</dt><dd>{displayValue(p95)}</dd>
                <dt>Maximum</dt><dd>{displayValue(maximum)}</dd>
              </dl>
            </>}
          </div>
          <div className="result-sample-table">
            <header><b>{scalarSamples.length ? "Highest field samples" : selectedImpedanceNetwork?.kind === "loop" ? "Power-loop impedance" : "Impedance extraction"}</b><span>{selectedImpedanceNetwork?.name || selected || "Active port"}</span></header>
            {scalarSamples.length > 0 ? <div className="result-rows">
              {hotspots.map((sample, index) => <div key={`${sample.element_id ?? "sample"}-${index}`}>
                <b>{sample.element_id ?? `Sample ${index + 1}`}</b>
                <span>{sample.layer ?? "-"}</span>
                <strong>{displayValue(sample.value)}</strong>
              </div>)}
            </div> : (selectedLoopParasitic || selectedParasitic) && <>
              {selectedLoopParasitic ? <>
                <dl>
                  <dt>Loop name</dt><dd>{selectedLoopParasitic.name}</dd>
                  <dt>Forward / return</dt><dd>{selectedLoopParasitic.forward_nets.join(" + ")} / {selectedLoopParasitic.return_nets.join(" + ")}</dd>
                  <dt>Geometry resistance</dt><dd>{(selectedLoopParasitic.geometry_resistance_ohm * 1000).toPrecision(6)} mOhm</dd>
                  <dt>Geometry loop inductance</dt><dd>{(selectedLoopParasitic.geometry_loop_inductance_h * 1e9).toPrecision(6)} nH</dd>
                  <dt>Declared component R / L</dt><dd>{(selectedLoopParasitic.component_resistance_ohm * 1000).toPrecision(6)} mOhm / {(selectedLoopParasitic.component_inductance_h * 1e9).toPrecision(6)} nH</dd>
                  <dt>Declared series capacitance</dt><dd>{selectedLoopParasitic.component_series_capacitance_f == null ? "None" : `${(selectedLoopParasitic.component_series_capacitance_f * 1e12).toPrecision(6)} pF`}</dd>
                  <dt>Total loop inductance</dt><dd>{(selectedLoopParasitic.total_loop_inductance_h * 1e9).toPrecision(6)} nH</dd>
                  <dt>Estimated net capacitance</dt><dd>{selectedLoopParasitic.estimated_net_capacitance_f == null ? "Not reported" : `${(selectedLoopParasitic.estimated_net_capacitance_f * 1e12).toPrecision(6)} pF`} ({selectedLoopParasitic.capacitance_model_status})</dd>
                  <dt>Model status</dt><dd>{selectedLoopParasitic.model_status}</dd>
                  <dt>Sweep points</dt><dd>{impedancePoints.length}</dd>
                </dl>
                <p><AlertTriangle size={14} /> Loop L retains the solved forward/return coupling. Component R/L are declared model contributions; capacitance is an estimate, not a validated multiconductor capacitance matrix.</p>
              </> : selectedParasitic && <>
              <dl>
                <dt>Series resistance</dt><dd>{selectedParasitic.resistance_ohm === undefined ? "-" : `${(selectedParasitic.resistance_ohm * 1000).toPrecision(6)} mOhm`}</dd>
                <dt>Partial inductance</dt><dd>{selectedParasitic.inductance_h === undefined ? "-" : `${(selectedParasitic.inductance_h * 1e9).toPrecision(6)} nH`}</dd>
                <dt>Capacitance</dt><dd>{selectedParasitic.capacitance_f == null ? "Not solved" : `${(selectedParasitic.capacitance_f * 1e12).toPrecision(6)} pF`}</dd>
                <dt>Conductance</dt><dd>{selectedParasitic.conductance_s == null ? "Not solved" : `${selectedParasitic.conductance_s.toPrecision(6)} S`}</dd>
                <dt>C/G fidelity</dt><dd>{selectedParasitic.parameter_availability?.capacitance ?? "not reported"} / {selectedParasitic.parameter_availability?.conductance ?? "not reported"}</dd>
                <dt>Reference</dt><dd>{selectedParasitic.quality?.capacitance?.reference_net || selectedParasitic.quality?.capacitance?.reference_mode || "not resolved"}</dd>
                <dt>Capacitance coverage</dt><dd>{selectedParasitic.quality?.capacitance?.branch_coverage === undefined ? "-" : `${(selectedParasitic.quality.capacitance.branch_coverage * 100).toFixed(2)}%`}</dd>
                <dt>Solve residual</dt><dd>{selectedParasitic.quality?.maximum_relative_residual === undefined ? "-" : selectedParasitic.quality.maximum_relative_residual.toExponential(3)}</dd>
                <dt>Sampled condition</dt><dd>{selectedParasitic.quality?.maximum_sampled_condition_number == null ? "not sampled at this scale" : selectedParasitic.quality.maximum_sampled_condition_number.toExponential(3)}</dd>
                <dt>Passivity correction</dt><dd>{selectedParasitic.quality?.inductance_passivity?.frobenius_correction_ratio === undefined ? "-" : `${(selectedParasitic.quality.inductance_passivity.frobenius_correction_ratio * 100).toPrecision(5)}%`}</dd>
                <dt>Network contract</dt><dd>{selectedParasitic.contract ?? "legacy result"}</dd>
                <dt>Sweep points</dt><dd>{impedancePoints.length}</dd>
              </dl>
              {selectedParasitic.blocked_uses?.length && <p><AlertTriangle size={14} /> These outputs remain blocked because this is not a validated multiconductor propagation model: {selectedParasitic.blocked_uses.join(", ")}.</p>}
              </>}
              {impedancePoints.length > 0 && <div className="impedance-rows">
                <div><b>Frequency</b><b>R</b><b>X</b><b>|Z|</b><b>Phase</b></div>
                {impedancePoints.slice(0, 40).map((point, index) => <div key={`${point.frequency_hz}-${index}`} className={index === selectedImpedanceIndex ? "selected" : ""} onClick={() => update({ impedanceFrequencyHz: point.frequency_hz })}>
                  <span>{point.frequency_hz.toPrecision(5)} Hz</span>
                  <span>{point.resistance_ohm?.toPrecision(5) ?? "-"} Ohm</span>
                  <span>{point.reactance_ohm?.toPrecision(5) ?? "-"} Ohm</span>
                  <strong>{point.magnitude_ohm.toPrecision(5)} Ohm</strong>
                  <span>{point.phase_deg.toPrecision(5)} deg</span>
                </div>)}
              </div>}
            </>}
          </div>
        </section>}
        {result && result.status !== "preview" && <section className="result-engineering-analytics">
          <header><div><b>ENGINEERING ANALYTICS</b><span>Solver extrema, probes, via stress, and copper-fusing screening</span></div><span className="approximate-badge">APPROXIMATE FUSING MODEL</span></header>
          <div className="analytics-summary-grid">
            <div><span>Minimum voltage</span><strong>{analyticsValue(engineeringAnalytics.fields.find(field => field.key === "voltage_v")?.minimum ?? null, "V")}</strong></div>
            <div><span>Maximum voltage drop</span><strong>{analyticsValue((engineeringAnalytics.fields.find(field => field.key === "voltage_drop_v")?.maximum ?? null) === null ? null : Number(engineeringAnalytics.fields.find(field => field.key === "voltage_drop_v")?.maximum) * 1000, "mV")}</strong></div>
            <div><span>Peak current density</span><strong>{analyticsValue(engineeringAnalytics.fields.find(field => field.key === "current_density_a_mm2")?.maximum ?? null, "A/mm2")}</strong></div>
            <div><span>Peak via density</span><strong>{analyticsValue(engineeringAnalytics.fields.find(field => field.key === "via_current_density_a_mm2")?.maximum ?? null, "A/mm2")}</strong></div>
          </div>
          <div className="fusing-settings">
            <div><b>Copper fusing screen</b><span>Short-duration adiabatic estimate. It is not a continuous-current or temperature-rise rating.</span></div>
            <label>Ambient (C)<input type="number" min="-200" max="1000" step="1" value={visualization.fusingAmbientC} onChange={event => update({ fusingAmbientC: Number(event.target.value) })} /></label>
            <label>Fault duration (s)<input type="number" min="0.000001" step="0.001" value={visualization.fusingDurationS} onChange={event => update({ fusingDurationS: Number(event.target.value) })} /></label>
            <dl>
              <dt>Calculated threshold</dt><dd>{analyticsValue(engineeringAnalytics.fusing.currentDensityThresholdAMm2, "A/mm2")}</dd>
              <dt>Maximum utilization</dt><dd>{engineeringAnalytics.fusing.maximumUtilization === null ? "-" : `${(engineeringAnalytics.fusing.maximumUtilization * 100).toFixed(2)}%`}</dd>
            </dl>
          </div>
          <div className="analytics-tables">
            <div><h4>Probe extrema and values</h4><dl className="probe-extrema">
              <dt>Mapped probes</dt><dd>{engineeringAnalytics.probeSummary.mapped} / {engineeringAnalytics.probeSummary.total}</dd>
              <dt>Voltage range</dt><dd>{analyticsValue(engineeringAnalytics.probeSummary.minimumVoltageV, "V")} to {analyticsValue(engineeringAnalytics.probeSummary.maximumVoltageV, "V")}</dd>
              <dt>Maximum probe drop</dt><dd>{engineeringAnalytics.probeSummary.maximumDropV === null ? "-" : analyticsValue(engineeringAnalytics.probeSummary.maximumDropV * 1000, "mV")}</dd>
              <dt>Maximum probe density</dt><dd>{analyticsValue(engineeringAnalytics.probeSummary.maximumCurrentDensityAMm2, "A/mm2")}</dd>
            </dl><div className="engineering-result-rows">
              {result.probes.slice(0, 20).map(probe => <div key={probe.id}><b>{probe.name ?? probe.id}</b><span>{probe.net ?? "-"}</span><span>{analyticsValue(probe.voltage_v ?? null, "V")}</span><span>{analyticsValue(probe.peak_adjacent_current_a ?? null, "A")}</span><strong>{analyticsValue(probe.peak_adjacent_current_density_a_mm2 ?? null, "A/mm2")}</strong></div>)}
              {!result.probes.length && <p>No solved probes are available.</p>}
            </div></div>
            <div><h4>Via stress</h4><button onClick={() => update({ mode: "via_stress", visible: true })} disabled={!result.scalar_fields.via_current_density_a_mm2.length}>Show dedicated via stress overlay</button><div dangerouslySetInnerHTML={{ __html: viaStressMapSvg(result.scalar_fields.via_current_density_a_mm2) }} /><div className="engineering-result-rows via-stress-rows">
              {reportedVias.map(via => <div key={via.elementId} className={`via-status-${via.status}`}><b title={via.elementId}>{via.elementId}</b><span>{via.net}</span><span>{via.layer}</span><strong>{via.currentDensityAMm2.toPrecision(6)} A/mm2</strong><em>{via.status === "ok" ? "within screens" : via.status}</em></div>)}
              {!reportedVias.length && <p>No via-current-density samples were returned by the solver.</p>}
            </div></div>
          </div>
          <p className="analytics-validity-note">The fusing estimate uses Onderdonk's copper equation with user-defined initial ambient and fault duration. PCB heat spreading, solder mask, plating tolerance, neck-down geometry, convection, and continuous operating temperature require the thermal workflow and are not included here.</p>
        </section>}
        <div className={`analysis-tools-grid domain-${domain}`}>
          <section>
            <h3>{domain === "pi" ? "PI mesh, RL and impedance extraction" : "Channel RL and impedance extraction"}</h3>
            <label>Via representation<select value={visualization.viaModel} onChange={event => update({ viaModel: event.target.value as ViaModel })}>
              <option value="extracted">Extracted drill and plating geometry</option>
              <option value="plated_cylinder">Plated-cylinder approximation</option>
              <option value="lumped_rlc" disabled>Lumped RLC approximation - unavailable</option>
              <option value="ignore" disabled>Ignore vias - unavailable</option>
            </select></label>
            <div className="analysis-net-chip">{selected || "Select a net in the viewport"}</div>
            <button className="secondary-btn" disabled={!selected || !workerAvailable || !parasiticsAvailable} onClick={() => onRunParasitics(visualization.viaModel)}><Play size={14} /> Extract R/L/C/G and Z(f)</button>
            <p>{!workerAvailable ? "Open this project in SPIKE Desktop to execute the local PEEC worker." : !parasiticsAvailable ? "No installed solver provides partial inductance and frequency-dependent impedance." : "R/L use the conductor PEEC mesh. C/G are included only where a single-reference stackup estimate is valid; inspect quality metadata before use."}</p>
            <div className="pdn-screening">
              <b>PDN target and decoupling screening</b>
              <div>
                <label>Target (ohm)<input type="number" min="0" step="0.001" value={pdnTarget} onChange={event => setPdnTarget(event.target.value)} /></label>
                <label>C (uF)<input type="number" min="0" value={candidateCuf} onChange={event => setCandidateCuf(event.target.value)} /></label>
                <label>ESR (mohm)<input type="number" min="0" value={candidateEsrMohm} onChange={event => setCandidateEsrMohm(event.target.value)} /></label>
                <label>ESL (nH)<input type="number" min="0" value={candidateEslNh} onChange={event => setCandidateEslNh(event.target.value)} /></label>
                <label>Mount R (mohm)<input type="number" min="0" value={candidateMountMohm} onChange={event => setCandidateMountMohm(event.target.value)} /></label>
                <label>Mount L (nH)<input type="number" min="0" value={candidateMountNh} onChange={event => setCandidateMountNh(event.target.value)} /></label>
                <label>Count<input type="number" min="1" step="1" value={candidateCount} onChange={event => setCandidateCount(event.target.value)} /></label>
                <label>Placement port<select value={candidatePortId} onChange={event => setCandidatePortId(event.target.value)}>
                  <option value="">Load port only (lumped screen)</option>
                  {candidatePorts.map(port => <option key={port.id} value={port.id}>{port.id} · {port.location.layer ?? "connected layers"} @ {port.location.position_mm.map(value => value.toFixed(3)).join(", ")} mm</option>)}
                </select></label>
              </div>
              <button className="secondary-btn" disabled={!workerAvailable || !selectedParasitic?.impedance?.length || Number(pdnTarget) <= 0 || Number(candidateCuf) <= 0} onClick={() => onRunPdn(Number(pdnTarget), {
                id: candidatePort?.id ?? `${candidateCuf}uF-${candidateCount}x`,
                capacitance_f: Number(candidateCuf) * 1e-6,
                esr_ohm: Number(candidateEsrMohm) * 1e-3,
                esl_h: Number(candidateEslNh) * 1e-9,
                mounting_resistance_ohm: Number(candidateMountMohm) * 1e-3,
                mounting_inductance_h: Number(candidateMountNh) * 1e-9,
                count: Math.max(1, Number(candidateCount) || 1),
                ...(candidatePort ?? {}),
              })}><Activity size={14} /> Check target and candidate</button>
              {pdnReview && <PiPdnReview source={sourceResult} review={pdnReview} selectedNet={selected ?? ""} reviewSourceId={pdnReviewSourceId} />}
              <small>{candidatePorts.length ? `${candidatePorts.length} reviewed probe placement port(s) were extracted. Choose one to use local and transfer impedance; the model remains ${selectedMultiport?.model_status ?? "approximate"}.` : "Mount R/L screen an explicit lumped connection path. Place probes at candidate capacitor pads, then run AC from PI Setup to extract reviewed local and transfer-impedance sweeps."}</small>
            </div>
            <button className="secondary-btn" onClick={onConfigure}><Grid3X3 size={14} /> Configure and regenerate mesh</button>
          </section>
          {domain === "si" && <section>
            <h3>SI automatic risk analysis</h3>
            <div className="risk-columns">
              <div onMouseLeave={() => previewViewportTarget(null)}><b>Victims</b>{displayedNets.map(net => <label key={`v-${net}`} onMouseEnter={() => previewViewportTarget({ kind: "net", net, label: net })}><input className="risk-victim" type="checkbox" value={net} defaultChecked={net === selected} />{net}</label>)}</div>
              <div onMouseLeave={() => previewViewportTarget(null)}><b>Aggressors</b>{displayedNets.map(net => <label key={`a-${net}`} onMouseEnter={() => previewViewportTarget({ kind: "net", net, label: net })}><input className="risk-aggressor" type="checkbox" value={net} />{net}</label>)}</div>
            </div>
            <button className="secondary-btn" disabled={!workerAvailable || !riskAvailable} onClick={() => onRunRisk(toggleList(".risk-victim"), toggleList(".risk-aggressor"))}><Play size={14} /> Run coupling risk scan</button>
            <p>{!riskAvailable ? "No installed field/coupling solver provides this analysis yet." : "Requests coupled-line extraction plus electric and magnetic field coupling. Results are never inferred by the UI."}</p>
          </section>}
        </div>
      </main>
    </div>
  </section>;
}
