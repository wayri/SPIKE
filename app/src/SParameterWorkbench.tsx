import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Download, Play, Upload, X } from "lucide-react";
import { checkNetwork, parseTouchstone, TouchstoneData, trace } from "./sparameters";
import { numericExtent } from "./numericRange";
import type { AssemblyDesigns } from "./mcadAssembly";
import { cancelLocalWorker, isDesktopShell, runSiProtocolTestSuite, runSiUniformChannel } from "./workerBridge";
import SiChannelResultPanel from "./SiChannelResultPanel";
import SiWorkflowWorkbench from "./SiWorkflowWorkbench";
import type { SiProtocolSuite } from "./siProtocolSuites";

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

const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const records = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value.filter(item => item && typeof item === "object" && !Array.isArray(item)) as Record<string, unknown>[] : [];
const namedRecords = (value: unknown): NamedRecord[] => records(value).flatMap(item => {
  const id = typeof item.id === "string" ? item.id : "";
  if (!id) return [];
  return [{ ...item, id, name: typeof item.name === "string" && item.name ? item.name : id }];
});
const finite = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
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

const downloadJson = (name: string, value: unknown) => {
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  anchor.download = /\.s\d+p$/i.test(name) ? name.replace(/\.s\d+p$/i, "") + ".spike-sparams.json" : name;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
};

export default function SParameterWorkbench({ assemblyDesigns, canonicalDesign, onClose, onStatus, suite, selectedProfile, initialResult, initialView, initialFocus = "channel", intentToken, onResult }: Props) {
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
  const [siResult, setSiResult] = useState<SiResult | null>(() => initialResult?.contract === "spike/si-channel-result/v1" ? initialResult : null);
  const [suiteResult, setSuiteResult] = useState<Record<string, unknown> | null>(null);
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
    setSuiteResult(null);
    setSiError("");
  }, [activeDesign?.design_id, suite?.id, selectedProfile?.id, initialFocus]);
  useEffect(() => {
    setSiResult(initialResult?.contract === "spike/si-channel-result/v1" ? initialResult : null);
  }, [initialResult]);

  const runGeometryChannel = async () => {
    if (!activeDesign) return;
    const start = Number(frequencyStartHz);
    const stop = Number(frequencyStopHz);
    const count = Number(frequencyPoints);
    const bitRate = Number(bitRateHz);
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
    const step = (stop - start) / (count - 1);
    const frequencies = Array.from({ length: count }, (_, index) => start + step * index);
    const request: Record<string, unknown> = {
      contract: "spike/si-uniform-channel-request/v1",
      channel_id: `${activeDesign.design_id}:${signalNet}${coupledMate ? `:${coupledMate}` : ""}`,
      signal_net: signalNet,
      reference_net: referenceNet,
      reference_layer: referenceLayer,
      reference_impedance_ohm: 50,
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
      const response = suite
        ? await runSiProtocolTestSuite(activeDesign, {
          contract: "spike/si-protocol-test-suite-request/v1",
          suite,
          lanes: [{ lane_id: String(request.channel_id), channel_request: request }],
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

  const chart = useMemo(() => {
    if (points.length < 2) return "";
    const width = 720;
    const height = 220;
    const xValues = points.map(point => Math.log10(Math.max(point.frequencyHz, 1e-30)));
    const yValues = points.map(point => point.magnitudeDb);
    const xExtent = numericExtent(xValues);
    const yExtent = numericExtent(yValues);
    const minX = xExtent.minimum;
    const maxX = xExtent.maximum;
    const minY = yExtent.minimum;
    const maxY = yExtent.maximum;
    return points.map((point, index) => {
      const x = 12 + (xValues[index] - minX) / Math.max(maxX - minX, 1) * (width - 24);
      const y = 12 + (maxY - point.magnitudeDb) / Math.max(maxY - minY, 1) * (height - 24);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
  }, [points]);

  return <div className="modal-backdrop"><section className="modal sparam-workbench" role="dialog" aria-modal="true" aria-label="S-parameter workbench">
    <header><div><span className="eyebrow">HF / SI NETWORK ANALYSIS</span><h2>S-parameter workbench</h2></div><button className="icon-btn" onClick={onClose} title="Close"><X size={17} /></button></header>
    <div className="sparam-commandbar"><button className={workflowView ? "primary-btn" : "secondary-btn"} onClick={() => setWorkflowView(true)}>Source-to-receiver workflow</button><button className={!workflowView ? "primary-btn" : "secondary-btn"} onClick={() => setWorkflowView(false)}>Geometry / protocol / network inspection</button></div>
    <div hidden={!workflowView}><SiWorkflowWorkbench design={activeDesign} initialResult={initialResult} initialStep={initialFocus === "ports" ? "endpoints" : "channel"} intentToken={intentToken} onResult={onResult} onStatus={onStatus} /></div>
    {!workflowView && <>
    {!desktop && <p className="si-note">Geometry and protocol execution requires the SPIKE desktop app. Browser preview supports configuration and network inspection.</p>}
    <div className="sparam-commandbar"><b>{initialFocus === "crosstalk" ? "NEXT / FEXT · select an aggressor and separate victim net" : initialFocus === "pam4" ? "PAM4 channel and eye" : initialFocus === "eye" ? "NRZ channel and eye" : initialFocus === "impedance" ? "Channel impedance and TDR" : suite ? `${suite.name} preset · geometry channel` : "Geometry-derived channel"} · experimental, not signoff/compliance qualified</b></div>
    {!activeDesign ? <div className="sparam-error"><AlertTriangle size={16} /> Blocked: this project has no canonical active DesignIR v2 record. Save or reopen a canonical project design before running geometry-derived SI.</div> : <>
      <div className="sparam-body">
        <aside>
          <h3>Canonical geometry</h3>
          <label className="setup-sublabel">Signal net<select className="select-control" value={signalNet} onChange={event => { const next = event.target.value; setSignalNet(next); setDifferentialMateNet(suggestedDifferentialMate(designNets.find(net => net.id === next), designNets)); }}><option value="">Select signal</option>{designNets.map(net => <option key={net.id} value={net.id}>{net.name}</option>)}</select><small>{suite ? `${suite.name} candidates are prioritized; review the exact board net before running.` : "Select the exact board route to analyze."}</small></label>
          <label className="setup-sublabel">Signaling<select className="select-control" value={signaling} disabled={initialFocus === "crosstalk"} onChange={event => setSignaling(event.target.value as "single_ended" | "differential")}><option value="single_ended">Single-ended aggressor</option><option value="differential">Differential aggressor pair</option></select></label>
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
            <label><span>Modulation</span><select value={modulation} onChange={event => setModulation(event.target.value as "NRZ" | "PAM4")}><option>NRZ</option><option>PAM4</option></select></label>
            <label><span>{modulation === "PAM4" ? "Symbol rate (baud)" : "Bit rate (bit/s)"}</span><input value={bitRateHz} onChange={event => setBitRateHz(event.target.value)} inputMode="decimal" /></label>
          </div>
          {modulation === "PAM4" && <div className="sparam-readout">
            <label><span>Tx FFE taps</span><input value={txFfeTaps} onChange={event => setTxFfeTaps(event.target.value)} /></label>
            <label><span>Rx DFE taps</span><input value={rxDfeTaps} onChange={event => setRxDfeTaps(event.target.value)} /></label>
            <label><span>CTLE zero / pole (Hz)</span><input value={`${ctleZeroHz}, ${ctlePoleHz}`} onChange={event => { const [zero = "", pole = ""] = event.target.value.split(","); setCtleZeroHz(zero.trim()); setCtlePoleHz(pole.trim()); }} /></label>
            <label><span>Normalized voltage noise RMS</span><input value={voltageNoise} onChange={event => setVoltageNoise(event.target.value)} inputMode="decimal" /></label>
          </div>}
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
            <button className="secondary-btn" onClick={() => downloadJson("geometry-channel.experimental.json", { ...siResult, production_qualified: false, compliance_status: "not_evaluated" })}><Download size={15} /> Export experimental channel result</button>
            <div className="sparam-check warning"><AlertTriangle size={14} /><span>Piecewise planar routing length is included, but bend discontinuities, vias, launches, connectors, packages, skin/proximity/roughness and receiver nonlinearity require explicit models. NRZ and PAM4 BER values remain bounded numerical proxies, never protocol compliance evidence.</span></div>
            <SiChannelResultPanel result={siResult!} onStatus={onStatus} />
          </>}
        </main>
      </div>
    </>}
    <div className="sparam-commandbar">
      <button className="primary-btn" onClick={() => input.current?.click()}><Upload size={15} /> Import Touchstone</button>
      <input ref={input} className="hidden-input" type="file" accept=".s1p,.s2p,.s3p,.s4p,.s5p,.s6p,.s8p,.s12p,.s16p,.s32p" onChange={event => void load(event.target.files?.[0])} />
      <button className="secondary-btn" disabled={!data} onClick={() => data && downloadJson(data.name, { contract: "spike/touchstone-preview/v1", data, checks })}><Download size={15} /> Export normalized JSON</button>
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
          <svg className="sparam-chart" viewBox="0 0 720 220" preserveAspectRatio="none" aria-label={`S${destination + 1}${source + 1} magnitude plot`}>
            <line x1="12" y1="208" x2="708" y2="208" />
            <line x1="12" y1="12" x2="12" y2="208" />
            <polyline points={chart} />
          </svg>
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
