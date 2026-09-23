export const SI_PROTOCOL_SUITE_CONTRACT = "spike/si-protocol-suite/v1" as const;

export type SiProtocolFamily =
  | "DDR" | "GDDR" | "SERDES" | "LVDS" | "PCI" | "PCIE" | "PXI"
  | "DISPLAYPORT" | "HDMI" | "USB" | "ETHERNET" | "MIPI" | "SATA"
  | "CXL" | "JESD204" | "HBM" | "CUSTOM";

export type SiAnalysisId =
  | "topology" | "impedance" | "rlgc" | "s_parameters" | "tdr_tdt"
  | "insertion_return_loss" | "next_fext" | "mode_conversion" | "skew_delay"
  | "eye" | "jitter" | "pam4" | "power_aware" | "compliance_review";

export type SiProtocolAnalysis = {
  id: SiAnalysisId;
  name: string;
  requiredCapabilities: string[];
  status: "available_input_review" | "solver_gated";
};

export type SiProtocolRule = {
  id: string;
  metric: string;
  operator: "minimum" | "maximum" | "range" | "informational";
  value?: number;
  maximum?: number;
  unit: string;
  source: "user" | "licensed_standard" | "measurement" | "public_reference";
  note: string;
};

export type SiProtocolSuite = {
  contract: typeof SI_PROTOCOL_SUITE_CONTRACT;
  id: string;
  name: string;
  family: SiProtocolFamily;
  revision: string;
  description: string;
  signaling: "single_ended" | "differential" | "parallel_bus" | "mixed";
  encoding: "NRZ" | "PAM4" | "mixed" | "user_defined";
  topology: string[];
  requiredInputs: string[];
  analyses: SiProtocolAnalysis[];
  rules: SiProtocolRule[];
  provenance: {
    title: string;
    locator: string;
    access: "public_overview" | "licensed_standard_required" | "user_defined";
    reviewedOn: string;
  };
  qualification: "setup_only" | "experimental" | "validated";
  custom: boolean;
};

const runnable = (id: SiAnalysisId, name: string, ...requiredCapabilities: string[]): SiProtocolAnalysis => ({
  id, name, requiredCapabilities, status: "available_input_review",
});

const blocked = (id: SiAnalysisId, name: string, ...requiredCapabilities: string[]): SiProtocolAnalysis => ({
  id, name, requiredCapabilities, status: "solver_gated",
});

// These matrices describe the executable bounded channel workflow, not protocol
// certification.  A runnable item opens the board-derived channel workbench;
// model-, solver-, and limit-dependent work remains explicitly blocked.
const CHANNEL = [
  runnable("topology", "Topology and lane mapping", "design_ir", "ports"),
  runnable("impedance", "Single-ended / differential impedance screening", "board_geometry", "bounded_rlgc"),
  runnable("rlgc", "Frequency-swept RLGC extraction", "board_geometry", "bounded_rlgc"),
  runnable("s_parameters", "Single-ended and mixed-mode S-parameters", "board_geometry", "bounded_sparameters"),
  runnable("tdr_tdt", "TDR / TDT impedance and transmission", "bounded_sparameters", "bounded_tdr_tdt"),
  runnable("insertion_return_loss", "Insertion and return loss", "bounded_sparameters"),
  runnable("next_fext", "NEXT / FEXT crosstalk", "coupled_planar_pair", "bounded_coupled_channel"),
  runnable("mode_conversion", "Differential mode conversion", "differential_pair", "bounded_mixed_mode"),
  runnable("skew_delay", "Lane skew and propagation delay", "board_geometry", "bounded_delay"),
  runnable("eye", "Normalized NRZ eye screening", "bounded_nrz_eye", "ideal_source_receiver"),
  blocked("jitter", "Statistical/deterministic jitter decomposition", "measured_or_ibis_ami_models", "validated_jitter_engine"),
  blocked("compliance_review", "Normative protocol compliance review", "licensed_limits", "validated_protocol_fixture"),
];

const MEMORY = [
  runnable("topology", "Controller, package and memory topology", "design_ir", "ports"),
  runnable("impedance", "DQ / DQS / CK / CA impedance screening", "board_geometry", "bounded_rlgc"),
  runnable("rlgc", "Frequency-swept DQ / DQS / CK / CA RLGC", "board_geometry", "bounded_rlgc"),
  runnable("s_parameters", "DQ and differential-strobe S-parameters", "board_geometry", "bounded_sparameters"),
  runnable("tdr_tdt", "DQ / DQS / CK TDR and TDT", "bounded_sparameters", "bounded_tdr_tdt"),
  runnable("insertion_return_loss", "DQ / DQS / CK insertion and return loss", "bounded_sparameters"),
  runnable("next_fext", "DQ / DQS / CK NEXT and FEXT", "coupled_planar_pair", "bounded_coupled_channel"),
  runnable("mode_conversion", "DQS / CK differential mode conversion", "differential_pair", "bounded_mixed_mode"),
  runnable("skew_delay", "Flight time and byte-lane skew", "board_geometry", "bounded_delay"),
  runnable("eye", "Normalized per-lane NRZ eye screening", "bounded_nrz_eye", "ideal_source_receiver"),
  blocked("jitter", "Read/write jitter decomposition", "ibis_or_measured_io_models", "validated_jitter_engine"),
  blocked("power_aware", "Simultaneous-switching and power-aware SI", "ibis_io_models", "package_power_model", "validated_power_aware_si"),
  blocked("compliance_review", "JEDEC mask and timing compliance", "licensed_limits", "validated_protocol_fixture"),
];

const source = (title: string, locator: string, access: SiProtocolSuite["provenance"]["access"] = "licensed_standard_required") => ({
  title, locator, access, reviewedOn: "2026-08-30",
});

const suite = (
  id: string,
  name: string,
  family: SiProtocolFamily,
  description: string,
  signaling: SiProtocolSuite["signaling"],
  encoding: SiProtocolSuite["encoding"],
  topology: string[],
  requiredInputs: string[],
  analyses: SiProtocolAnalysis[],
  provenance: SiProtocolSuite["provenance"],
): SiProtocolSuite => ({
  contract: SI_PROTOCOL_SUITE_CONTRACT,
  id, name, family, revision: "user-selectable", description, signaling, encoding,
  topology, requiredInputs, analyses, rules: [], provenance, qualification: "setup_only", custom: false,
});

export const builtinSiProtocolSuites: SiProtocolSuite[] = [
  suite("spike.si.ddr", "DDR / LPDDR", "DDR", "Parallel memory-channel setup for DQ, DQS, CK, command/address, package, termination and timing review.", "parallel_bus", "NRZ", ["controller", "package", "fly-by or point-to-point bus", "memory devices", "terminations"], ["stackup", "pin/lane map", "IBIS or measured models", "package models", "licensed limits"], MEMORY, source("JEDEC DDR and LPDDR family", "https://www.jedec.org/standards-documents")),
  suite("spike.si.gddr", "GDDR", "GDDR", "Graphics-memory channel setup with per-lane package/board topology and simultaneous-switching review.", "parallel_bus", "NRZ", ["graphics controller", "package escapes", "point-to-point memory lanes", "memory devices"], ["stackup", "lane map", "package models", "I/O models", "licensed limits"], MEMORY, source("JEDEC GDDR family", "https://www.jedec.org/standards-documents")),
  suite("spike.si.hbm", "HBM", "HBM", "Interposer/package-aware wide-memory interface setup; 2.5D/3D package extraction remains solver-gated.", "parallel_bus", "NRZ", ["logic die", "interposer", "stacked memory", "micro-bump ports"], ["interposer geometry", "package stack", "port map", "I/O models", "licensed limits"], MEMORY, source("JEDEC HBM family", "https://www.jedec.org/standards-documents")),
  suite("spike.si.serdes", "Generic SerDes", "SERDES", "Technology-neutral serial-channel workspace for user-owned baud rate, encoding, channel, equalization, jitter and mask inputs.", "differential", "user_defined", ["transmitter", "package", "channel", "connector", "receiver"], ["stackup", "differential pairs", "ports", "Tx/Rx models", "stimulus", "user limits"], [...CHANNEL, blocked("pam4", "PAM4 levels, eyes, and bathtub curves", "pam4_source_receiver_models", "validated_pam4_engine")], source("User-defined SerDes engineering inputs", "spike://user-protocol", "user_defined")),
  suite("spike.si.lvds", "LVDS", "LVDS", "Differential LVDS topology, termination, skew, crosstalk, waveform and eye setup.", "differential", "NRZ", ["driver", "differential channel", "termination", "receiver"], ["stackup", "pair mapping", "driver/receiver models", "termination", "applicable standard limits"], CHANNEL, source("ANSI/TIA/EIA-644 family", "https://www.tiaonline.org/")),
  suite("spike.si.pci", "PCI / PCI-X", "PCI", "Legacy parallel PCI-family bus topology, loading, timing, reflections and crosstalk workspace.", "parallel_bus", "NRZ", ["host", "shared bus", "connectors or loads", "terminations"], ["stackup", "bus map", "device models", "loading order", "licensed limits"], MEMORY, source("PCI-SIG PCI family", "https://pcisig.com/specifications")),
  suite("spike.si.pcie", "PCI Express", "PCIE", "PCIe lane, package, connector, loss, mode-conversion, crosstalk, TDR and eye setup across user-selected generations.", "differential", "mixed", ["root complex", "package", "lane channel", "connector", "endpoint"], ["generation/revision", "stackup", "lane/port map", "Tx/Rx or measured models", "licensed compliance limits"], [...CHANNEL, blocked("pam4", "PAM4 link review where applicable", "pam4_source_receiver_models", "validated_pam4_engine")], source("PCI-SIG PCI Express overview", "https://pcisig.com/specification-overview/pci-express-base")),
  suite("spike.si.pxi", "PXI", "PXI", "Classic PXI parallel backplane, module loading, clock/trigger, reflections and crosstalk setup layered on applicable PCI electrical requirements.", "parallel_bus", "NRZ", ["system controller", "parallel backplane", "slot connector", "module endpoint", "clock/trigger network"], ["PXI revision", "backplane geometry", "slot map", "PCI device models", "licensed limits"], MEMORY, source("PXI Systems Alliance specifications", "https://www.pxisa.org/")),
  suite("spike.si.pxie", "PXI Express", "PXI", "PXI Express serial backplane and module-channel setup with chassis clock and trigger topology treated explicitly.", "mixed", "mixed", ["system controller", "PCIe backplane lanes", "slot connector", "module endpoint", "clock/trigger network"], ["PXIe/PCIe revision", "backplane geometry", "lane/slot map", "Tx/Rx models", "licensed limits"], CHANNEL, source("PXI Systems Alliance specifications", "https://www.pxisa.org/")),
  suite("spike.si.displayport", "DisplayPort", "DISPLAYPORT", "DisplayPort main-link and auxiliary-channel topology, loss, skew, crosstalk and eye setup.", "differential", "mixed", ["source", "package", "main-link lanes", "connector/cable", "sink", "AUX channel"], ["revision/link mode", "lane map", "channel models", "source/sink models", "licensed limits"], [...CHANNEL, blocked("pam4", "Multilevel signaling review where applicable", "pam4_source_receiver_models", "validated_pam4_engine")], source("VESA DisplayPort compliance program", "https://vesa.org/displayport-developer/compliance/")),
  suite("spike.si.hdmi", "HDMI", "HDMI", "HDMI source, board, connector/cable and sink channel setup with licensed limits supplied by an authorized user.", "differential", "mixed", ["source", "package", "board channel", "connector/cable", "sink"], ["licensed specification/revision", "channel map", "source/sink models", "cable model", "licensed CTS limits"], CHANNEL, source("HDMI Licensing Administrator specification access", "https://www.hdmi.org/spec/index")),
  suite("spike.si.usb", "USB / USB4", "USB", "USB-family differential-channel setup for board, connector, cable and device links.", "differential", "mixed", ["host", "package", "board channel", "connector/cable", "device"], ["USB family/mode", "stackup", "port map", "channel/receiver models", "applicable limits"], CHANNEL, source("USB-IF specifications", "https://www.usb.org/documents")),
  suite("spike.si.ethernet", "Ethernet", "ETHERNET", "Board/backplane/cable Ethernet channel setup with user-selected PHY family and media.", "differential", "mixed", ["PHY", "magnetics/package", "board channel", "connector/media", "remote PHY"], ["PHY family", "media", "port map", "models", "applicable IEEE limits"], CHANNEL, source("IEEE 802.3 Ethernet overview", "https://standards.ieee.org/ieee/802.3/7071/")),
  suite("spike.si.mipi", "MIPI high-speed interfaces", "MIPI", "MIPI family workspace for user-selected D-PHY/C-PHY and protocol-owned topology inputs.", "mixed", "mixed", ["controller", "package", "lane channel", "connector if present", "device"], ["MIPI interface/revision", "lane map", "models", "licensed limits"], CHANNEL, source("MIPI Alliance specifications", "https://www.mipi.org/specifications")),
  suite("spike.si.sata", "SATA / SAS", "SATA", "Storage serial-link channel, connector, loss, reflection, crosstalk and eye setup.", "differential", "NRZ", ["host", "package", "board channel", "connector/cable", "device"], ["link family/revision", "stackup", "channel map", "models", "licensed limits"], CHANNEL, source("SATA-IO specifications", "https://sata-io.org/")),
  suite("spike.si.cxl", "CXL", "CXL", "CXL link setup layered on the applicable PCIe physical interface with CXL-owned topology and evidence.", "differential", "mixed", ["host", "package", "PCIe physical channel", "device"], ["CXL/PCIe revision", "lane map", "models", "licensed limits"], [...CHANNEL, blocked("pam4", "PAM4 link review where applicable", "pam4_source_receiver_models", "validated_pam4_engine")], source("CXL Consortium specifications", "https://www.computeexpresslink.org/download-the-specification")),
  suite("spike.si.jesd204", "JESD204", "JESD204", "Converter SerDes-link workspace for lanes, clocks, synchronization, channel loss and deterministic-latency evidence.", "differential", "mixed", ["logic device", "lane channel", "data converter", "clock/synchronization"], ["JESD204 revision", "lane map", "clock topology", "models", "licensed limits"], CHANNEL, source("JEDEC JESD204 family", "https://www.jedec.org/standards-documents")),
];

const ID_PATTERN = /^[a-z0-9][a-z0-9._-]{2,95}$/;
const ANALYSIS_IDS = new Set<SiAnalysisId>(["topology", "impedance", "rlgc", "s_parameters", "tdr_tdt", "insertion_return_loss", "next_fext", "mode_conversion", "skew_delay", "eye", "jitter", "pam4", "power_aware", "compliance_review"]);

export function validateSiProtocolSuite(value: unknown): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return ["Suite must be a JSON object."];
  const suite = value as Partial<SiProtocolSuite>;
  const errors: string[] = [];
  if (suite.contract !== SI_PROTOCOL_SUITE_CONTRACT) errors.push(`contract must be ${SI_PROTOCOL_SUITE_CONTRACT}.`);
  if (!suite.id || !ID_PATTERN.test(suite.id)) errors.push("id must contain 3-96 lowercase letters, numbers, dot, underscore, or dash.");
  if (!suite.name?.trim()) errors.push("name is required.");
  if (!suite.revision?.trim()) errors.push("revision is required.");
  if (!suite.description?.trim()) errors.push("description is required.");
  if (!Array.isArray(suite.topology) || !suite.topology.length || suite.topology.length > 64) errors.push("topology must contain 1-64 entries.");
  if (!Array.isArray(suite.requiredInputs) || !suite.requiredInputs.length || suite.requiredInputs.length > 64) errors.push("requiredInputs must contain 1-64 entries.");
  if (!Array.isArray(suite.analyses) || !suite.analyses.length || suite.analyses.length > 32) errors.push("analyses must contain 1-32 entries.");
  else {
    const seen = new Set<string>();
    suite.analyses.forEach((analysis, index) => {
      if (!analysis || !ANALYSIS_IDS.has(analysis.id)) errors.push(`analyses[${index}].id is unsupported.`);
      if (seen.has(analysis?.id)) errors.push(`Duplicate analysis ${analysis.id}.`);
      seen.add(analysis?.id);
      if (!analysis?.name?.trim()) errors.push(`analyses[${index}].name is required.`);
      if (!Array.isArray(analysis?.requiredCapabilities) || analysis.requiredCapabilities.length > 32) errors.push(`analyses[${index}].requiredCapabilities is invalid.`);
      if (analysis?.status !== "available_input_review" && analysis?.status !== "solver_gated") errors.push(`analyses[${index}].status is unsupported.`);
    });
  }
  if (!Array.isArray(suite.rules) || suite.rules.length > 256) errors.push("rules must be an array with at most 256 entries.");
  suite.rules?.forEach((rule, index) => {
    if (!rule?.id || !ID_PATTERN.test(rule.id)) errors.push(`rules[${index}].id is invalid.`);
    if (!rule?.metric?.trim() || !rule?.unit?.trim() || !rule?.note?.trim()) errors.push(`rules[${index}] requires metric, unit, and note.`);
    if (rule?.operator !== "informational" && !Number.isFinite(rule?.value)) errors.push(`rules[${index}].value must be finite.`);
    if (rule?.operator === "range" && (!Number.isFinite(rule?.maximum) || Number(rule.maximum) < Number(rule.value))) errors.push(`rules[${index}] range maximum is invalid.`);
  });
  if (!suite.provenance?.title?.trim() || !suite.provenance?.locator?.trim()) errors.push("provenance title and locator are required.");
  if (suite.qualification === "validated" && suite.custom) errors.push("A custom builder definition cannot self-assert validated qualification.");
  return errors;
}

export function createCustomSiProtocolSuite(): SiProtocolSuite {
  return {
    contract: SI_PROTOCOL_SUITE_CONTRACT,
    id: "user.si.custom-suite",
    name: "Custom high-speed protocol",
    family: "CUSTOM",
    revision: "0.1.0",
    description: "User-defined channel analysis suite.",
    signaling: "differential",
    encoding: "user_defined",
    topology: ["transmitter", "channel", "receiver"],
    requiredInputs: ["stackup", "port map", "source/receiver models", "user-owned limits"],
    analyses: CHANNEL.map(item => ({ ...item, requiredCapabilities: [...item.requiredCapabilities] })),
    rules: [],
    provenance: { title: "User-defined engineering requirements", locator: "spike://user-protocol", access: "user_defined", reviewedOn: new Date().toISOString().slice(0, 10) },
    qualification: "setup_only",
    custom: true,
  };
}

export function protocolSuiteExtensionBundle(suite: SiProtocolSuite) {
  const safeId = suite.id.startsWith("user.") ? suite.id : `user.${suite.id}`;
  return {
    contract: "spike/protocol-suite-extension-source/v1",
    execution: "declarative_only",
    code_state: "dormant_until_digest_bound_trust_and_os_sandbox",
    files: {
      "spike-extension.json": {
        contract: "spike/extension/v1", api_version: 1, id: safeId, name: suite.name,
        version: suite.revision, provider: "SPIKE user", description: suite.description,
        execution: "process", runtime: "python", entrypoint: "extension.py", state: "experimental",
        license: "proprietary", bundled: false, permissions: [],
        limits: { timeout_seconds: 30, max_result_bytes: 1048576 },
        contributes: { protocol_suites: [{ id: suite.id, name: suite.name, description: suite.description, definition: suite }] },
      },
      "suite.json": suite,
      "extension.py": "# Optional code-assisted augmentation. Dormant by default.\n# Do not execute until publisher identity, complete bundle digest, permissions, and OS sandbox are approved.\n",
      "README.md": "This bundle contains a declarative SPIKE SI protocol suite. The optional code file is intentionally dormant by default.\n",
    },
  };
}
