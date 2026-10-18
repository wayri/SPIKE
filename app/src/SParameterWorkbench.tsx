import "./sparameterResponsive.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Download, Play, Upload, X } from "./icons";
import { checkNetwork, parseTouchstone, TouchstoneData, trace } from "./sparameters";
import { numericExtent } from "./numericRange";
import type { AssemblyDesigns } from "./mcadAssembly";
import { cancelLocalWorker, isDesktopShell, runSiProtocolTestSuite, runSiUniformChannel } from "./workerBridge";
import SiChannelResultPanel from "./SiChannelResultPanel";
import SiWorkflowWorkbench from "./SiWorkflowWorkbench";
import PlotlyChart from "./PlotlyChart";
import type { SiProtocolSuite } from "./siProtocolSuites";
import { usePanelPresentation } from "./panelPresentation";
import { siSearchDraftError, type SiSearchDraft } from "./siSearchDraft";

type Props = {
  assemblyDesigns: AssemblyDesigns | null;
  canonicalDesign: Record<string, unknown> | null;
  onClose: () => void;
  onStatus: (message: string) => void;
  /** Optional App-owned context. It configures defaults only; it never asserts solver qualification. */
  suite?: SiProtocolSuite | null;
  selectedProfile?: SiChannelProfile | null;
  initialResult?: Record<string, unknown> | null;
  initialView?: "workflow" | "geometry";
  initialFocus?: "channel" | "crosstalk" | "eye" | "pam4" | "impedance" | "ports";
  intentToken?: number;
  searchDraft?: SiSearchDraft;
  onResult?: (result: Record<string, unknown>) => void;
};

export type SiChannelProfile = {
  id: string;
  label: string;
  signaling?: "single_ended" | "differential";
  pathMode?: "piecewise_planar";
  bitRateHz?: number;
  frequencyStopHz?: number;
};

export const suggestedDifferentialMate = (signal: NamedRecord | undefined, nets: readonly NamedRecord[]) => {
  if (!signal) return "";
  const escaped = signal.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const candidates = [new RegExp(`^${escaped.replace(/([_.-]?)(p|plus)$/i, "$1n")}$`, "i"), new RegExp(`^${escaped.replace(/([_.-]?)(n|minus)$/i, "$1p")}$`, "i")];
  return nets.find(net => net.id !== signal.id && candidates.some(pattern => pattern.test(net.name)))?.id ?? "";
};

const suitePreset = (suite?: Props["suite"], profile?: SiChannelProfile | null) => {
  const ddr = suite?.family === "DDR" || suite?.family === "GDDR";
  const serdes = suite?.family === "SERDES" || suite?.family === "PCIE" || suite?.family === "CXL" || suite?.family === "JESD204";
  return {
    signaling: profile?.signaling ?? (suite?.signaling === "differential" || serdes ? "differential" : "single_ended") as "single_ended" | "differential",
    pathMode: profile?.pathMode ?? "piecewise_planar" as const,
    bitRateHz: profile?.bitRateHz ?? (ddr ? 3.2e9 : serdes ? 8e9 : 1e9),
    frequencyStopHz: profile?.frequencyStopHz ?? (ddr ? 12.8e9 : serdes ? 32e9 : 4e9),
  };
};

const suggestedSuiteSignal = (nets: readonly NamedRecord[], suite?: Props["suite"]) => {
  const family = suite?.family ?? "";
  const patterns = family === "DDR" || family === "GDDR"
    ? [/\bDQS(?:[_-]?[PN])?\b/i, /\b(?:DQ|CK|CLK|CA|ADDR|CMD)\d*(?:[_-]?[PN])?\b/i]
    : [/(?:TX|RX|LANE|SERDES|PCIE|USB|SATA|DP|HDMI).*(?:[_-][PN]|[+-])$/i];
  return nets.find(net => patterns.some(pattern => pattern.test(net.name))) ?? nets[0];
};

type NamedRecord = Record<string, unknown> & { id: string; name: string };
type SiResult = Record<string, unknown>;

type EyeMask = {
  schema: "spike/si-eye-mask/v1";
  id: string;
  name: string;
  protocol: string;
  revision: string;
  source: { locator: string; clause: string };
  voltage_unit: "V" | "normalized";
  polygons: number[][][];
};

const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const records = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value.filter(item => item && typeof item === "object" && !Array.isArray(item)) as Record<string, unknown>[] : [];
const namedRecords = (value: unknown): NamedRecord[] => records(value).flatMap(item => {
  const id = typeof item.id === "string" ? item.id : "";
  if (!id) return [];
  return [{ ...item, id, name: typeof item.name === "string" && item.name ? item.name : id }];
});
const finite = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const parseEyeMask = (source: string): EyeMask | null => {
  if (!source.trim()) return null;
  const value = JSON.parse(source) as Record<string, unknown>;
  const keys = Object.keys(value).sort().join("|");
  if (keys !== "id|name|polygons|protocol|revision|schema|source|voltage_unit" || value.schema !== "spike/si-eye-mask/v1") throw new Error("Eye mask must contain exactly the spike/si-eye-mask/v1 fields.");
  if (!["id", "name", "protocol", "revision"].every(key => typeof value[key] === "string" && String(value[key]).trim())) throw new Error("Eye mask id, name, protocol, and revision must be non-empty text.");
  const provenance = record(value.source);
  if (Object.keys(provenance).sort().join("|") !== "clause|locator" || typeof provenance.locator !== "string" || !provenance.locator.trim() || typeof provenance.clause !== "string" || !provenance.clause.trim()) throw new Error("Eye mask source requires non-empty locator and clause fields.");
  if (value.voltage_unit !== "V" && value.voltage_unit !== "normalized") throw new Error("Eye mask voltage_unit must be V or normalized.");
  if (!Array.isArray(value.polygons) || value.polygons.length < 1 || value.polygons.length > 16 || value.polygons.some(polygon => !Array.isArray(polygon) || polygon.length < 3 || polygon.length > 64 || polygon.some(point => !Array.isArray(point) || point.length !== 2 || point.some(coordinate => typeof coordinate !== "number" || !Number.isFinite(coordinate))))) throw new Error("Eye mask polygons require 1–16 polygons of 3–64 finite [time_ui, voltage] vertices.");
  return value as EyeMask;
};
const engineering = (value: unknown, unit = "") => {
  const number = finite(value);
  if (number === null) return "Not available";
  return `${number.toExponential(4)}${unit ? ` ${unit}` : ""}`;
};

function siSummary(result: SiResult | null) {
  if (!result) return null;
  const extraction = record(result.extraction);
  const derived = record(extraction.derived);
  const network = record(result.network);
  const frequency = record(network.frequency);
  const checks = record(network.checks);
  const time = record(result.time_domain);
  const processing = record(time.processing);
  const tdr = records(time.tdr);
  const tdt = records(time.tdt);
  const eye = record(result.eye);
  const pam4 = record(eye.pam4);
  const crosstalk = record(result.crosstalk);
  const next = record(crosstalk.next);
  const fext = record(crosstalk.fext);
  const finiteImpedances = tdr.map(point => finite(point.impedance_ohm)).filter((value): value is number => value !== null);
  const transmission = tdt.map(point => finite(point.normalized_step)).filter((value): value is number => value !== null);
  const impedanceExtent = numericExtent(finiteImpedances);
  const transmissionExtent = numericExtent(transmission.map(Math.abs));
  const pam4BerProxies = Array.isArray(pam4.ber_proxies)
    ? (pam4.ber_proxies as number[]).filter(Number.isFinite)
    : [];
  const pam4BerExtent = numericExtent(pam4BerProxies);
  return {
    sParameters: `${Number(network.port_count ?? 0)}-port / ${Number(frequency.count ?? 0)} points; passivity ${String(record(checks.passivity).status ?? "not evaluated")}; reciprocity ${String(record(checks.reciprocity).status ?? "not evaluated")}`,
    tdr: `${tdr.length} retained samples${finiteImpedances.length ? `; impedance ${impedanceExtent.minimum.toFixed(3)} to ${impedanceExtent.maximum.toFixed(3)} ohm` : ""}`,
    tdt: `${tdt.length} retained samples${transmission.length ? `; peak normalized step ${transmissionExtent.maximum.toFixed(5)}` : ""}`,
    crosstalk: crosstalk.contract ? `NEXT ${engineering(next.worst_transfer_db, "dB")}; FEXT ${engineering(fext.worst_transfer_db, "dB")}` : "Not requested; select a victim net for the bounded coupled-line model.",
    eye: pam4.contract
      ? `PAM4 eyes ${records(pam4.eye_heights_normalized).length ? "available" : (Array.isArray(pam4.eye_heights_normalized) ? (pam4.eye_heights_normalized as number[]).map(value => Number(value).toPrecision(4)).join(" / ") : "not available")}; worst BER proxy ${pam4BerProxies.length ? pam4BerExtent.maximum.toExponential(3) : "not available"}`
      : eye.contract ? `height ${engineering(eye.eye_height_normalized)}; deterministic-ISI BER proxy ${engineering(eye.deterministic_isi_ber_estimate)}; ${Number(eye.samples_per_ui ?? 0)} samples/UI` : "Not computed.",
    model: `Z0 ${engineering(derived.lossless_characteristic_impedance_ohm, "ohm")}; delay ${engineering(derived.lossless_delay_s, "s")}; time step ${engineering(processing.delta_t_s, "s")}`,
  };
}

const downloadJson = (ownerDocument: Document | undefined, name: string, value: unknown) => {
  if (!ownerDocument) return;
  const anchor = ownerDocument.createElement("a");
  anchor.href = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  anchor.download = /\.s\d+p$/i.test(name) ? name.replace(/\.s\d+p$/i, "") + ".spike-sparams.json" : name;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
};

export default function SParameterWorkbench({ assemblyDesigns, canonicalDesign, onClose, onStatus, suite, selectedProfile, initialResult, initialView, initialFocus = "channel", intentToken, searchDraft, onResult }: Props) {
  const { ownerDocument } = usePanelPresentation();
  const [workflowView, setWorkflowView] = useState(() => initialView ? initialView === "workflow" : !suite && !selectedProfile && initialResult?.contract !== "spike/si-channel-result/v1");
  useEffect(() => { if ((suite || selectedProfile) && !initialView) setWorkflowView(false); }, [suite?.id, selectedProfile?.id, initialView]);
  useEffect(() => { if (initialView && intentToken) setWorkflowView(initialView === "workflow"); }, [initialView, intentToken]);
  const desktop = isDesktopShell();
  const input = useRef<HTMLInputElement>(null);
  const [data, setData] = useState<TouchstoneData | null>(null);
  const [error, setError] = useState("");
  const [destination, setDestination] = useState(0);
  const [source, setSource] = useState(0);
  const [sample, setSample] = useState(0);
  const [signalNet, setSignalNet] = useState("");
  const [victimNet, setVictimNet] = useState("");
  const [differentialMateNet, setDifferentialMateNet] = useState("");
  const [signaling, setSignaling] = useState<"single_ended" | "differential">("single_ended");
  const [referenceNet, setReferenceNet] = useState("");
  const [referenceLayer, setReferenceLayer] = useState("");
  const [frequencyStartHz, setFrequencyStartHz] = useState("0");
  const [frequencyStopHz, setFrequencyStopHz] = useState("4e9");
  const [frequencyPoints, setFrequencyPoints] = useState("1025");
  const [bitRateHz, setBitRateHz] = useState("1e9");
  const [referenceImpedanceOhm, setReferenceImpedanceOhm] = useState("50");
  const [modulation, setModulation] = useState<"NRZ" | "PAM4">("NRZ");
  const [txFfeTaps, setTxFfeTaps] = useState("1.0");
  const [rxDfeTaps, setRxDfeTaps] = useState("0.0");
  const [ctleZeroHz, setCtleZeroHz] = useState("0");
  const [ctlePoleHz, setCtlePoleHz] = useState("0");
  const [voltageNoise, setVoltageNoise] = useState("0.01");
  const [separationToleranceMm, setSeparationToleranceMm] = useState("0.15");
  const [skewToleranceMm, setSkewToleranceMm] = useState("2.0");
  const [loadedCrosstalk, setLoadedCrosstalk] = useState(false);
  const [crosstalkSourceV, setCrosstalkSourceV] = useState("1.0");
  const [crosstalkTerminations, setCrosstalkTerminations] = useState(["50", "50", "50", "50"]);
  const [siBusy, setSiBusy] = useState(false);
  const [siError, setSiError] = useState("");
  const [searchReview, setSearchReview] = useState("");
  const admittedSearchDraft = useRef<{ id: string; design: Record<string, unknown> } | null>(null);
  const [siResult, setSiResult] = useState<SiResult | null>(() => initialResult?.contract === "spike/si-channel-result/v1" ? initialResult : null);
  const [suiteResult, setSuiteResult] = useState<Record<string, unknown> | null>(null);
  const [eyeMaskJson, setEyeMaskJson] = useState("");
  const [eyeMaskProfileId, setEyeMaskProfileId] = useState("");
  const [eyeVoltageScale, setEyeVoltageScale] = useState("");
  const [eyeVoltageOffset, setEyeVoltageOffset] = useState("");
  const activeDesign = useMemo(() => {
    if (!assemblyDesigns || assemblyDesigns.contract !== "spike/assembly-designs/v1") return canonicalDesign?.contract === "spike/design-ir/v2" ? canonicalDesign : null;
    const design = assemblyDesigns.designs.find(item => item.design_id === assemblyDesigns.active_design_id);
    if (design?.contract === "spike/design-ir/v2") return design;
    return canonicalDesign?.contract === "spike/design-ir/v2" ? canonicalDesign : null;
  }, [assemblyDesigns, canonicalDesign]);
  const designNets = useMemo(() => namedRecords(activeDesign?.nets), [activeDesign]);
  const copperLayers = useMemo(() => namedRecords(activeDesign?.layers).filter(layer => layer.layer_type === "copper"), [activeDesign]);
  const summary = useMemo(() => siSummary(siResult), [siResult]);
  const checks = useMemo(() => data ? checkNetwork(data) : null, [data]);
  const points = useMemo(() => data ? trace(data, destination, source) : [], [data, destination, source]);
  const selected = points[Math.min(sample, Math.max(0, points.length - 1))];

  useEffect(() => {
    if (searchDraft && admittedSearchDraft.current?.id === searchDraft.id && admittedSearchDraft.current.design === activeDesign) return;
    const ground = designNets.find(net => /(^|[/_-])(gnd|vss|return|0v)([/_-]|$)/i.test(net.name));
    const signal = suggestedSuiteSignal(designNets.filter(net => net.id !== ground?.id), suite);
    setSignalNet(signal?.id ?? "");
    const preset = suitePreset(suite, selectedProfile);
    setVictimNet("");
    setSignaling(initialFocus === "crosstalk" ? "single_ended" : preset.signaling);
    setLoadedCrosstalk(initialFocus === "crosstalk");
    setDifferentialMateNet(suggestedDifferentialMate(signal, designNets));
    setReferenceNet(ground?.id ?? "");
    setReferenceLayer(copperLayers.find(layer => !/f\.cu|top/i.test(layer.name))?.id ?? copperLayers[0]?.id ?? "");
    setFrequencyStopHz(String(preset.frequencyStopHz)); setBitRateHz(String(preset.bitRateHz));
    setModulation(initialFocus === "pam4" || (initialFocus !== "eye" && suite?.encoding === "PAM4") ? "PAM4" : "NRZ");
    setEyeMaskProfileId("");
    setEyeMaskJson("");
    setSuiteResult(null);
    setSiError("");
  }, [activeDesign?.design_id, suite?.id, selectedProfile?.id, initialFocus]);
  useEffect(() => {
    setSiResult(initialResult?.contract === "spike/si-channel-result/v1" ? initialResult : null);
  }, [initialResult]);
  useEffect(() => {
    if (!searchDraft || !activeDesign || siBusy) return;
    const previous = admittedSearchDraft.current;
    if (previous?.id === searchDraft.id) {
      if (previous.design !== activeDesign) {
        setSignalNet(""); setReferenceNet(""); setReferenceLayer("");
        setSiResult(null); setSuiteResult(null);
        setSearchReview("Board context changed. Search the current board again before applying SI setup.");
      }
      return;
    }
    admittedSearchDraft.current = { id: searchDraft.id, design: activeDesign };
    setWorkflowView(false);
    setSiResult(null); setSuiteResult(null); setData(null);
    setSignalNet(""); setReferenceNet(""); setReferenceLayer("");
    setVictimNet(""); setDifferentialMateNet("");
    const problem = siSearchDraftError(searchDraft, designNets.map(net => net.id));
    if (problem) { setSiError(problem); setSearchReview(problem); return; }
    setSignalNet(searchDraft.signalNetId ?? "");
    setReferenceNet(searchDraft.referenceNetId ?? "");
    if (searchDraft.frequencyStartHz !== undefined) setFrequencyStartHz(String(searchDraft.frequencyStartHz));
    if (searchDraft.frequencyStopHz !== undefined) setFrequencyStopHz(String(searchDraft.frequencyStopHz));
    if (searchDraft.bitRateHz !== undefined) setBitRateHz(String(searchDraft.bitRateHz));
    if (searchDraft.impedanceOhm !== undefined) setReferenceImpedanceOhm(String(searchDraft.impedanceOhm));
    setSiError("");
    setSearchReview(`Reviewed search inputs applied. Select the reference copper layer and review signal, return, differential mate or victim, and frequency settings before running.${searchDraft.componentRefs?.length ? ` Component references ${searchDraft.componentRefs.join(", ")} do not define source/receiver pin endpoints; review explicit endpoints in the source-to-receiver workflow.` : " Source/receiver pin endpoints require separate review in the source-to-receiver workflow."}${searchDraft.riseTimeS !== undefined ? ` Requested rise time ${searchDraft.riseTimeS} s remains pending review: geometry channel setup has no source rise-time input. No waveform is inferred from this value; configure the source rise time in the source-to-receiver workflow.` : ""}`);
  }, [searchDraft, activeDesign, designNets, siBusy]);

  const runGeometryChannel = async () => {
    if (!activeDesign) return;
    const start = Number(frequencyStartHz);
    const stop = Number(frequencyStopHz);
    const count = Number(frequencyPoints);
    const bitRate = Number(bitRateHz);
    let eyeMask: EyeMask | null = null;
    try { eyeMask = parseEyeMask(eyeMaskJson); } catch (error) { setSiError(error instanceof Error ? error.message : String(error)); return; }
    if (eyeMaskProfileId && eyeMask) { setSiError("Choose either a built-in eye mask profile or supplied mask JSON."); return; }
    if (start !== 0) { setSiError("TDR/TDT and eye reconstruction require the frequency range to start at exactly 0 Hz (DC)."); return; }
    if (!Number.isFinite(stop) || stop <= 0) { setSiError("Frequency stop must be positive and finite."); return; }
    if (!Number.isInteger(count) || count < 3 || count > 32769) { setSiError("Frequency points must be an integer from 3 through 32769."); return; }
    if (loadedCrosstalk && count > 8193) { setSiError("Loaded NEXT/FEXT transient analysis admits at most 8,193 frequency points."); return; }
    if (!signalNet || !referenceNet || !referenceLayer) { setSiError("Select a signal net, reference net, and reference copper layer."); return; }
    if (initialFocus === "crosstalk" && !victimNet) { setSiError("Choose a separate victim net to calculate NEXT and FEXT."); return; }
    if (signalNet === referenceNet || (victimNet && [signalNet, referenceNet].includes(victimNet)) || (differentialMateNet && [signalNet, referenceNet, victimNet].includes(differentialMateNet))) { setSiError("Aggressor, differential mate, optional victim, and reference nets must be distinct."); return; }
    if (signaling === "differential" && !differentialMateNet) { setSiError("Differential signaling requires an explicitly selected P/N mate."); return; }
    const coupledMate = signaling === "differential" ? differentialMateNet : victimNet;
    const separationTolerance = Number(separationToleranceMm);
    const skewTolerance = Number(skewToleranceMm);
    if (coupledMate && (!Number.isFinite(separationTolerance) || separationTolerance < 0 || !Number.isFinite(skewTolerance) || skewTolerance < 0)) { setSiError("Coupled separation and skew tolerances must be finite, non-negative millimetre values."); return; }
    if (!Number.isFinite(bitRate) || bitRate <= 0) { setSiError(`${modulation === "PAM4" ? "Symbol" : "Bit"} rate must be positive and finite.`); return; }
    const referenceImpedance = Number(referenceImpedanceOhm);
    if (!Number.isFinite(referenceImpedance) || referenceImpedance <= 0) { setSiError("Reference impedance must be positive and finite."); return; }
    const step = (stop - start) / (count - 1);
    const frequencies = Array.from({ length: count }, (_, index) => start + step * index);
    const request: Record<string, unknown> = {
      contract: "spike/si-uniform-channel-request/v1",
      channel_id: `${activeDesign.design_id}:${signalNet}${coupledMate ? `:${coupledMate}` : ""}`,
      signal_net: signalNet,
      reference_net: referenceNet,
      reference_layer: referenceLayer,
      reference_impedance_ohm: referenceImpedance,
      frequencies_hz: frequencies,
      trace_limit: 512,
      path_mode: "piecewise_planar",
      signaling,
    };
    if (modulation === "PAM4") {
      const parseTaps = (value: string) => value.split(/[,\s]+/).filter(Boolean).map(Number);
      const ffe = parseTaps(txFfeTaps);
      const dfe = parseTaps(rxDfeTaps);
      const zero = Number(ctleZeroHz);
      const pole = Number(ctlePoleHz);
      const noise = Number(voltageNoise);
      if (!ffe.length || ffe.some(value => !Number.isFinite(value)) || !dfe.length || dfe.some(value => !Number.isFinite(value))) { setSiError("FFE and DFE taps must be comma-separated finite values."); return; }
      if (![zero, pole, noise].every(Number.isFinite)) { setSiError("CTLE and noise controls must be finite."); return; }
      request.symbol_rate_hz = bitRate;
      request.symbol_count = 512;
      request.pam4_model = {
        tx_ffe_taps: ffe,
        rx_ctle_dc_gain: 1.0,
        rx_ctle_zero_hz: zero,
        rx_ctle_pole_hz: pole,
        rx_dfe_taps: dfe,
        voltage_noise_rms_normalized: noise,
        phase_bins: 65,
        target_ber: 1e-12,
        cdr_mode: "ideal_phase_search",
      };
    } else {
      request.bit_rate_hz = bitRate;
      request.bit_count = 512;
    }
    if (coupledMate) {
      request.victim_net = coupledMate;
      request.cross_section_vertical_cells = 24;
      request.coupled_separation_tolerance_mm = separationTolerance;
      request.coupled_skew_tolerance_mm = skewTolerance;
    }
    if (victimNet && loadedCrosstalk) {
      const sourceVoltage = Number(crosstalkSourceV);
      const terminations = crosstalkTerminations.map(Number);
      if (!Number.isFinite(sourceVoltage) || Math.abs(sourceVoltage) > 1e6) { setSiError("The NEXT/FEXT Thevenin source must be finite and within +/-1e6 V."); return; }
      if (terminations.some(value => !Number.isFinite(value) || value < 1e-6 || value > 1e12)) { setSiError("Each NEXT/FEXT termination must be within 1e-6 through 1e12 ohm."); return; }
      const waveform = Array.from({ length: 512 }, (_, index) => index < 16 || index >= 272 ? 0 : sourceVoltage);
      request.crosstalk_model = {
        port_map: { aggressor_near: 0, victim_near: 1, aggressor_far: 2, victim_far: 3 },
        termination_ohm: terminations,
        waveform_v: waveform,
        trace_limit: 512,
      };
    }
    setSiBusy(true);
    setSiError("");
    onStatus(`Running bounded experimental ${signaling === "differential" ? "differential" : "single-ended"} aggressor ${signalNet}${differentialMateNet ? ` / mate ${differentialMateNet}` : ""}${victimNet ? ` with separate victim ${victimNet}` : ""}`);
    try {
      const lane: Record<string, unknown> = { lane_id: String(request.channel_id), channel_request: request };
      if (eyeMask || eyeMaskProfileId) {
        if (eyeMask) lane.eye_mask = eyeMask;
        if (eyeMaskProfileId) lane.eye_mask_id = eyeMaskProfileId;
        if (eyeMaskProfileId || eyeMask?.voltage_unit === "V") {
          if (!eyeVoltageScale.trim() || !eyeVoltageOffset.trim()) { setSiError("A volts mask requires explicit scale and offset values for normalized eye samples."); setSiBusy(false); return; }
          const scaleV = Number(eyeVoltageScale);
          const offsetV = Number(eyeVoltageOffset);
          if (!Number.isFinite(scaleV) || scaleV <= 0 || !Number.isFinite(offsetV)) { setSiError("A volts mask requires a finite positive scale and finite offset for normalized eye samples."); setSiBusy(false); return; }
          lane.eye_voltage_mapping = { scale_v: scaleV, offset_v: offsetV, bit_rate_hz: bitRate };
        }
      }
      const response = suite
        ? await runSiProtocolTestSuite(activeDesign, {
          contract: "spike/si-protocol-test-suite-request/v1",
          suite,
          lanes: [lane],
        })
        : await runSiUniformChannel(activeDesign, request);
      if (!response.ok || !response.result) {
        const message = response.error ?? "The SI worker returned no result.";
        setSiError(message);
        onStatus(`Experimental SI channel failed: ${message}`);
        return;
      }
      const channelResult = suite
        ? (response.result.lanes as { channel_result?: Record<string, unknown> }[] | undefined)?.[0]?.channel_result
        : response.result;
      if (!channelResult || channelResult.contract !== "spike/si-channel-result/v1") {
        setSiError("The SI worker returned no geometry-derived channel result.");
        return;
      }
      setSuiteResult(suite ? response.result : null);
      setSiResult(channelResult);
      onResult?.(channelResult);
      onStatus(suite
        ? `${suite.name} experimental test matrix completed; blocked tests and compliance limits remain explicit.`
        : "Experimental geometry-derived S/TDR/TDT channel run completed; signoff and compliance remain false.");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setSiError(message);
      onStatus(`Experimental SI channel failed: ${message}`);
    } finally { setSiBusy(false); }
  };

  const load = async (file?: File) => {
    if (!file) return;
    try {
      const parsed = parseTouchstone(file.name, await file.text());
      setData(parsed);
      setDestination(Math.min(1, parsed.portCount - 1));
      setSource(0);
      setSample(0);
      setError("");
      onStatus(`${file.name}: ${parsed.portCount} ports and ${parsed.frequenciesHz.length} frequency points loaded`);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason);
      setError(message);
      onStatus(`Touchstone import failed: ${message}`);
    }
  };

  const chartData: Record<string, unknown>[] = [{ type: "scatter", mode: "lines+markers", name: `S${destination + 1}${source + 1}`,
    x: points.map(point => point.frequencyHz), y: points.map(point => point.magnitudeDb), connectgaps: false,
    marker: { size: 4 }, line: { width: 1.7 }, hovertemplate: "%{x:.8g} Hz<br>%{y:.5f} dB<extra></extra>" }];
  const chartLayout: Record<string, unknown> = { margin: { t: 16, r: 20, b: 52, l: 64 }, showlegend: false,
    xaxis: { title: "Frequency (Hz)", type: "log" }, yaxis: { title: "Magnitude (dB)" },
    ...(selected ? { shapes: [{ type: "line", x0: selected.frequencyHz, x1: selected.frequencyHz, y0: 0, y1: 1, xref: "x", yref: "paper", line: { color: "#ffbd69", width: 1, dash: "dot" } }] } : {}) };
  const suiteLane = records(suiteResult?.lanes)[0];
  const eyeMaskResult = record(suiteLane?.eye_mask_result);

  return <div className="modal-backdrop"><section className="modal sparam-workbench" role="dialog" aria-modal="true" aria-label="S-parameter workbench">
    <header><div><span className="eyebrow">HF / SI NETWORK ANALYSIS</span><h2>S-parameter workbench</h2></div><button className="icon-btn" onClick={onClose} title="Close"><X size={17} /></button></header>
    <div className="sparam-commandbar"><button className={workflowView ? "primary-btn" : "secondary-btn"} onClick={() => setWorkflowView(true)}>Source-to-receiver workflow</button><button className={!workflowView ? "primary-btn" : "secondary-btn"} onClick={() => setWorkflowView(false)}>Geometry / protocol / network inspection</button></div>
    {searchReview && <div className="sparam-error" role="status"><AlertTriangle size={16} /> {searchReview}</div>}
    <div hidden={!workflowView}><SiWorkflowWorkbench key={searchDraft?.id ?? "saved-workflow"} design={activeDesign} initialResult={searchDraft ? null : initialResult} initialStep={initialFocus === "ports" ? "endpoints" : "channel"} intentToken={intentToken} onResult={onResult} onStatus={onStatus} /></div>
    {!workflowView && <>
    {!desktop && <p className="si-note">Geometry and protocol execution requires the SPIKE desktop app. Browser preview supports configuration and network inspection.</p>}
    <div className="sparam-commandbar"><b>{initialFocus === "crosstalk" ? "NEXT / FEXT · select an aggressor and separate victim net" : initialFocus === "pam4" ? "PAM4 channel and eye" : initialFocus === "eye" ? "NRZ channel and eye" : initialFocus === "impedance" ? "Channel impedance and TDR" : suite ? `${suite.name} preset · geometry channel` : "Geometry-derived channel"} · experimental, not signoff/compliance qualified</b></div>
    {!activeDesign ? <div className="sparam-error"><AlertTriangle size={16} /> Blocked: this project has no canonical active SpiDeR v2 record. Save or reopen a canonical project design before running geometry-derived SI.</div> : <>
      <div className="sparam-body">
        <aside>
          <h3>Canonical geometry</h3>
          <label className="setup-sublabel">Signal net<select className="select-control" value={signalNet} onChange={event => { const next = event.target.value; setSignalNet(next); setDifferentialMateNet(suggestedDifferentialMate(designNets.find(net => net.id === next), designNets)); }}><option value="">Select signal</option>{designNets.map(net => <option key={net.id} value={net.id}>{net.name}</option>)}</select><small>{suite ? `${suite.name} candidates are prioritized; review the exact board net before running.` : "Select the exact board route to analyze."}</small></label>
          <label className="setup-sublabel">Signaling<select className="select-control" value={signaling} disabled={initialFocus === "crosstalk" || Boolean(eyeMaskProfileId)} onChange={event => setSignaling(event.target.value as "single_ended" | "differential")}><option value="single_ended">Single-ended aggressor</option><option value="differential">Differential aggressor pair</option></select></label>
          {signaling === "differential" ? <label className="setup-sublabel">Differential mate<select className="select-control" value={differentialMateNet} onChange={event => setDifferentialMateNet(event.target.value)}><option value="">Select mate (P/N)</option>{designNets.filter(net => net.id !== signalNet).map(net => <option key={net.id} value={net.id}>{net.name}</option>)}</select><small>Explicit P/N mate for the bounded four-port and mixed-mode transform.</small></label> : <label className="setup-sublabel">{initialFocus === "crosstalk" ? "Victim net (required)" : "Victim net (optional)"}<select className="select-control" value={victimNet} onChange={event => setVictimNet(event.target.value)}><option value="">No separate victim</option>{designNets.filter(net => ![signalNet, referenceNet].includes(net.id)).map(net => <option key={net.id} value={net.id}>{net.name}</option>)}</select><small>Select the separate coupled-line victim for NEXT/FEXT.</small></label>}
          {(signaling === "differential" || victimNet) && <><label className="setup-sublabel">Separation variation tolerance (mm)<input value={separationToleranceMm} onChange={event => setSeparationToleranceMm(event.target.value)} inputMode="decimal" /></label><label className="setup-sublabel">Path skew tolerance (mm)<input value={skewToleranceMm} onChange={event => setSkewToleranceMm(event.target.value)} inputMode="decimal" /><small>Fail-closed bounds for the piecewise paired-route approximation.</small></label></>}
          {signaling === "single_ended" && victimNet && <fieldset className="setup-subgroup"><legend>Loaded NEXT / FEXT voltage</legend>
            <label className="setup-sublabel"><span><input type="checkbox" checked={loadedCrosstalk} onChange={event => setLoadedCrosstalk(event.target.checked)} /> Apply explicit source and terminations</span><small>Computes victim volts from a 512-sample Thevenin pulse. Other sources are suppressed.</small></label>
            {loadedCrosstalk && <><label className="setup-sublabel">Thevenin pulse amplitude (V)<input value={crosstalkSourceV} onChange={event => setCrosstalkSourceV(event.target.value)} inputMode="decimal" /></label>
              {crosstalkTerminations.map((value, index) => <label className="setup-sublabel" key={index}>{["Aggressor near source R (ohm)", "Victim near load R (ohm)", "Aggressor far load R (ohm)", "Victim far load R (ohm)"][index]}<input value={value} onChange={event => setCrosstalkTerminations(values => values.map((item, itemIndex) => itemIndex === index ? event.target.value : item))} inputMode="decimal" /></label>)}
              <small>Port order is explicit: aggressor near, victim near, aggressor far, victim far. Transient reconstruction requires DC, uniform spacing, and no more than 8,193 frequency points.</small></>}
          </fieldset>}
          <label className="setup-sublabel">Reference net<select className="select-control" value={referenceNet} onChange={event => setReferenceNet(event.target.value)}><option value="">Select reference</option>{designNets.map(net => <option key={net.id} value={net.id}>{net.name}</option>)}</select></label>
          <label className="setup-sublabel">Reference layer<select className="select-control" value={referenceLayer} onChange={event => setReferenceLayer(event.target.value)}><option value="">Select copper layer</option>{copperLayers.map(layer => <option key={layer.id} value={layer.id}>{layer.name}</option>)}</select></label>
        </aside>
        <main>
          <div className="sparam-plot-heading"><div><span className="eyebrow">BOUNDED REQUEST</span><h3>{String(activeDesign.name ?? activeDesign.design_id)}</h3></div><div><b>Qualification: false</b><span>Compliance: not evaluated</span></div></div>
          <div className="sparam-readout">
            <label><span>Start frequency (Hz)</span><input value={frequencyStartHz} onChange={event => setFrequencyStartHz(event.target.value)} inputMode="decimal" /></label>
            <label><span>Stop frequency (Hz)</span><input value={frequencyStopHz} onChange={event => setFrequencyStopHz(event.target.value)} inputMode="decimal" /></label>
            <label><span>Uniform points</span><input value={frequencyPoints} onChange={event => setFrequencyPoints(event.target.value)} inputMode="numeric" /></label>
            <label><span>Reference impedance (ohm)</span><input value={referenceImpedanceOhm} onChange={event => setReferenceImpedanceOhm(event.target.value)} inputMode="decimal" /></label>
            <label><span>Modulation</span><select value={modulation} disabled={Boolean(eyeMaskProfileId)} onChange={event => setModulation(event.target.value as "NRZ" | "PAM4")}><option>NRZ</option><option>PAM4</option></select></label>
            <label><span>{modulation === "PAM4" ? "Symbol rate (baud)" : "Bit rate (bit/s)"}</span><input value={bitRateHz} disabled={Boolean(eyeMaskProfileId)} onChange={event => setBitRateHz(event.target.value)} inputMode="decimal" /></label>
          </div>
          {modulation === "PAM4" && <div className="sparam-readout">
            <label><span>Tx FFE taps</span><input value={txFfeTaps} onChange={event => setTxFfeTaps(event.target.value)} /></label>
            <label><span>Rx DFE taps</span><input value={rxDfeTaps} onChange={event => setRxDfeTaps(event.target.value)} /></label>
            <label><span>CTLE zero / pole (Hz)</span><input value={`${ctleZeroHz}, ${ctlePoleHz}`} onChange={event => { const [zero = "", pole = ""] = event.target.value.split(","); setCtleZeroHz(zero.trim()); setCtlePoleHz(pole.trim()); }} /></label>
            <label><span>Normalized voltage noise RMS</span><input value={voltageNoise} onChange={event => setVoltageNoise(event.target.value)} inputMode="decimal" /></label>
          </div>}
          {suite && <fieldset className="si-eye-mask-input"><legend>Optional sourced eye mask</legend>
            {suite.family === "USB" && <label>USB 2.0 high-speed profile<select value={eyeMaskProfileId} onChange={event => { const id = event.target.value; setEyeMaskProfileId(id); if (id) { setEyeMaskJson(""); setSignaling("differential"); setBitRateHz("480e6"); setModulation("NRZ"); } }}><option value="">Unassigned / supplied JSON</option><option value="usb2.hs.template1.inner">Template 1 inner opening</option><option value="usb2.hs.template2.inner">Template 2 inner opening</option></select></label>}
            {eyeMaskProfileId && <div className="si-eye-mask-scope"><b>USB 2.0 high-speed inner opening screening</b><span>Uses a 480 Mbit/s differential NRZ channel. Transition-dependent 475/525 mV outer limits are not assessed, so this is not complete template compliance.</span></div>}
            <label>Mask JSON<textarea value={eyeMaskJson} disabled={Boolean(eyeMaskProfileId)} onChange={event => setEyeMaskJson(event.target.value)} spellCheck={false} placeholder={'Unassigned. Paste a sourced spike/si-eye-mask/v1 object; no protocol limits are built in.'} /></label>
            <small>Forbidden polygons use [time_ui, voltage] vertices with implicit closure. Source locator and clause are required. A mask pass applies only to the returned sampled polylines; overall protocol compliance remains not evaluated.</small>
            {(eyeMaskProfileId || eyeMaskJson.trim()) && (() => { try { const mask = parseEyeMask(eyeMaskJson); return eyeMaskProfileId || mask?.voltage_unit === "V" ? <div className="si-eye-voltage-mapping"><label>Normalized-to-volts scale (V)<input value={eyeVoltageScale} onChange={event => setEyeVoltageScale(event.target.value)} inputMode="decimal" /></label><label>Normalized zero offset (V)<input value={eyeVoltageOffset} onChange={event => setEyeVoltageOffset(event.target.value)} inputMode="decimal" /></label><small>Required evidence mapping: V = normalized × scale + offset at 480 Mbit/s for the built-in profiles. Values are never guessed.</small></div> : <span className="si-eye-mask-ready">Normalized mask assigned</span>; } catch { return <span className="si-eye-mask-invalid">Mask JSON is not ready to run.</span>; } })()}
          </fieldset>}
          {siBusy
            ? <button className="primary-btn" onClick={() => { void cancelLocalWorker().catch(error => setSiError(error instanceof Error ? error.message : String(error))); }}><X size={15} />Stop SI channel</button>
            : <button className="primary-btn" disabled={!desktop} onClick={() => void runGeometryChannel()}><Play size={15} />{initialFocus === "crosstalk" ? "Run NEXT / FEXT" : initialFocus === "pam4" ? "Run PAM4 channel" : "Run experimental SI channel"}</button>}
          {siError && <div className="sparam-error"><AlertTriangle size={16} /> {siError}</div>}
          {suiteResult && <div className="sparam-summary"><div><span>SUITE</span><b>{String(record(suiteResult.suite).family ?? suite?.family ?? "SI")}</b></div><div><span>COMPLETED TESTS</span><b>{String(record(suiteResult.summary).completed_tests ?? 0)}</b></div><div><span>BLOCKED TESTS</span><b>{String(record(suiteResult.summary).blocked_tests ?? 0)}</b></div><div><span>COMPLIANCE</span><b>{String(suiteResult.compliance_status ?? "not_evaluated")}</b></div></div>}
          {summary && <>
            <div className="sparam-summary">
              <div><span>S-PARAMETERS</span><b>{summary.sParameters}</b></div>
              <div><span>TDR</span><b>{summary.tdr}</b></div>
              <div><span>TDT</span><b>{summary.tdt}</b></div>
              <div><span>NEXT / FEXT</span><b>{summary.crosstalk}</b></div>
              <div><span>NORMALIZED EYE / BER</span><b>{summary.eye}</b></div>
              <div><span>EXTRACTED MODEL</span><b>{summary.model}</b></div>
            </div>
            <button className="secondary-btn" onClick={() => downloadJson(ownerDocument, "geometry-channel.experimental.json", { ...siResult, production_qualified: false, compliance_status: "not_evaluated" })}><Download size={15} /> Export experimental channel result</button>
            <div className="sparam-check warning"><AlertTriangle size={14} /><span>Piecewise planar routing length is included, but bend discontinuities, vias, launches, connectors, packages, skin/proximity/roughness and receiver nonlinearity require explicit models. NRZ and PAM4 BER values remain bounded numerical proxies, never protocol compliance evidence.</span></div>
            <SiChannelResultPanel result={siResult!} eyeMaskResult={Object.keys(eyeMaskResult).length ? eyeMaskResult : null} onStatus={onStatus} />
          </>}
        </main>
      </div>
    </>}
    <div className="sparam-commandbar">
      <button className="primary-btn" onClick={() => input.current?.click()}><Upload size={15} /> Import Touchstone</button>
      <input ref={input} className="hidden-input" type="file" accept=".s1p,.s2p,.s3p,.s4p,.s5p,.s6p,.s8p,.s12p,.s16p,.s32p" onChange={event => void load(event.target.files?.[0])} />
      <button className="secondary-btn" disabled={!data} onClick={() => data && downloadJson(ownerDocument, data.name, { contract: "spike/touchstone-preview/v1", data, checks })}><Download size={15} /> Export normalized JSON</button>
      {data && <span>{data.name}</span>}
    </div>
    {error && <div className="sparam-error"><AlertTriangle size={16} /> {error}</div>}
    {!data ? <div className="sparam-empty"><Upload size={28} /><b>Open a Touchstone network</b><span>Local parsing works offline. Full validation and renormalization are also available through the SPIKE CLI.</span></div> : <>
      <div className="sparam-summary">
        <div><span>PORTS</span><b>{data.portCount}</b></div>
        <div><span>FREQUENCY</span><b>{(data.frequenciesHz[0] / 1e6).toPrecision(4)} - {(data.frequenciesHz[data.frequenciesHz.length - 1] / 1e6).toPrecision(4)} MHz</b></div>
        <div><span>REFERENCE</span><b>{data.referenceOhm} ohm</b></div>
        <div className={checks?.passivity === "pass" ? "check-pass" : "check-fail"}><span>PASSIVITY</span><b>{checks?.passivity.toUpperCase()}</b><small>max sigma {checks?.worstSingularValue.toFixed(5)}</small></div>
        <div className={checks?.reciprocity === "pass" ? "check-pass" : "check-fail"}><span>RECIPROCITY</span><b>{checks?.reciprocity.toUpperCase()}</b><small>error {checks?.worstReciprocityError.toExponential(2)}</small></div>
      </div>
      <div className="sparam-body">
        <aside>
          <h3>Port matrix</h3>
          <div className="sparam-matrix" style={{ gridTemplateColumns: `36px repeat(${data.portCount}, minmax(46px, 1fr))` }}>
            <span />
            {Array.from({ length: data.portCount }, (_, index) => <b key={`source-${index}`}>P{index + 1}</b>)}
            {Array.from({ length: data.portCount }, (_, row) => [
              <b key={`destination-${row}`}>P{row + 1}</b>,
              ...Array.from({ length: data.portCount }, (_, column) =>
                <button key={`${row}-${column}`} className={destination === row && source === column ? "selected" : ""} onClick={() => { setDestination(row); setSource(column); }}>
                  S{row + 1}{column + 1}
                </button>,
              ),
            ])}
          </div>
          <h3>Checks and limits</h3>
          <div className="sparam-check"><CheckCircle2 size={14} /><span>File structure and frequency order checked</span></div>
          {data.warnings.map(warning => <div className="sparam-check warning" key={warning}><AlertTriangle size={14} /><span>{warning}</span></div>)}
          <div className="sparam-check warning"><AlertTriangle size={14} /><span>Causality is not inferred in preview. Use the CLI workflow when DC extrapolation, resampling, or delay removal is required.</span></div>
        </aside>
        <main>
          <div className="sparam-plot-heading"><div><span className="eyebrow">SELECTED TRACE</span><h3>S{destination + 1}{source + 1} magnitude</h3></div>{selected && <div><b>{selected.magnitudeDb.toFixed(3)} dB</b><span>{(selected.frequencyHz / 1e6).toPrecision(5)} MHz</span></div>}</div>
          <div className="sparam-chart"><PlotlyChart title={`S${destination + 1}${source + 1} magnitude plot`} data={chartData} layout={chartLayout} revision={`sparam:${destination}:${source}:${points.length}`} onPointClick={(point: { pointNumber: number; curveNumber: number }) => { if (point.curveNumber === 0) setSample(point.pointNumber); }} /></div>
          <input className="sparam-slider" type="range" min={0} max={Math.max(0, points.length - 1)} value={Math.min(sample, Math.max(0, points.length - 1))} onChange={event => setSample(Number(event.target.value))} />
          {selected && <div className="sparam-readout">
            <div><span>Magnitude</span><b>{selected.magnitude.toPrecision(7)}</b></div>
            <div><span>Phase</span><b>{selected.phaseDeg.toFixed(3)} deg</b></div>
            <div><span>Frequency</span><b>{selected.frequencyHz.toPrecision(8)} Hz</b></div>
            <div><span>Matched-port input Z</span><b>{selected.matchedInputImpedanceOhm ? `${selected.matchedInputImpedanceOhm.re.toFixed(4)} ${selected.matchedInputImpedanceOhm.im < 0 ? "-" : "+"} j${Math.abs(selected.matchedInputImpedanceOhm.im).toFixed(4)} ohm` : "Select a reflection term"}</b></div>
          </div>}
        </main>
      </div>
    </>}
    </>}
  </section></div>;
}
