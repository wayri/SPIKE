// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, CircleHelp, Focus, X } from "lucide-react";
import "./AnalysisGuide.css";

export type GuideDestination = "board-import" | "emerge" | "emerge-emi" | "emerge-em-result" | "pi" | "si" | "emi" | "thermal" | "circuit" | "results";
type GuideFlow = "emerge-si" | "emerge-radiation" | "pi" | "pi-peec" | "si" | "emi" | "thermal" | "thermal-board" | "circuit";
type GuideStep = {
  title: string;
  instruction: string;
  destination?: GuideDestination;
  selectors: string[];
  optional?: boolean;
};

const importStep: GuideStep = {
  title: "Import a board",
  instruction: "Use Import to load a KiCad board. Inspect the imported stackup and any validation issues before configuring an analysis.",
  destination: "board-import",
  selectors: ['[data-guide="board-import"]', '.ribbon-home .tool[title="Import"]', '.ribbon-tools .tool[title="Import"]'],
};

const resultStep: GuideStep = {
  title: "Inspect the result",
  instruction: "Open the result view and inspect plots, warnings, model status, and provenance. A visible curve alone does not establish solver validation.",
  destination: "results",
  selectors: ['[data-guide="emerge-result"]', '.result-visualizer', '[data-guide="results"]', '.extension-output'],
  optional: true,
};

const flows: Record<GuideFlow, { label: string; capability: string; next: string; steps: GuideStep[] }> = {
  "emerge-si": {
    label: "HF / SI EMerge S-parameters",
    capability: "EMerge is optional. SPIKE enables its S-parameter route only when the trusted runtime probe reports si_s_parameters; imported-board results remain unvalidated.",
    next: "Compare the selected frequency traces and port definitions with the setup; keep the reported model status and warnings with exports.",
    steps: [importStep, {
      title: "Open HF / SI",
      instruction: "Open HF / SI. The S-parameter solver selector controls only S-parameters and Ports; impedance, crosstalk, eye, PAM4, protocol suites, and Touchstone keep their internal paths.",
      destination: "si",
      selectors: ['[data-guide="si-setup"]'],
    }, {
      title: "Check and select EMerge",
      instruction: "Use Check Emerge when needed. Select EMerge only after the trusted runtime probe reports si_s_parameters. If EMerge remains unavailable, keep SPIKE internal selected and inspect the extension/runtime status.",
      destination: "si",
      selectors: ['[data-guide="si-sparameter-solver"]', '[data-guide="si-check-emerge"]'],
    }, {
      title: "Open the EMerge port setup",
      instruction: "Choose S-parameters or Ports. With EMerge selected and available, either opens the EMerge SI setup.",
      destination: "si",
      selectors: ['[data-guide="si-sparameters"]', '[data-guide="si-ports"]'],
    }, {
      title: "Set nets and ports",
      instruction: "Choose the signal and return nets, then aligned signal/return pads. Add the receive pair for a two-port solve.",
      destination: "si",
      selectors: ['[data-guide="emerge-emi-setup"]'],
    }, {
      title: "Set sweep and mesh",
      instruction: "Enter start/stop frequency, sample count, and mesh resolution. Check the board geometry limits shown in the EMerge setup.",
      destination: "si",
      selectors: ['[data-guide="emerge-frequency"]'],
    }, {
      title: "Run S-parameters",
      instruction: "Review the setup, then click Run beside EMerge SI/S-parameters. The guide highlights the button but will not start the solver for you.",
      destination: "si",
      selectors: ['[data-guide="emerge-si-run"]'],
    }, { ...resultStep, destination: "si", selectors: ['[data-guide="emerge-si-result"]'] }],
  },
  "emerge-radiation": {
    label: "EMerge radiation",
    capability: "External EMerge: the installed runtime must expose the radiation contribution. Relative patterns do not establish EMI compliance.",
    next: "Inspect the 3D pattern and angular cuts at the requested frequency, then review units, normalization and solver warnings.",
    steps: [importStep, {
      title: "Open EMerge in EM",
      instruction: "Open EM → EMerge. Check the runtime probe and the radiation capability before setup.",
      destination: "emerge-emi",
      selectors: ['[data-guide="emerge-emi-setup"]', '.tool[title="EMerge"]'],
    }, {
      title: "Set geometry and ports",
      instruction: "Select the board signal/return nets and aligned pads, then set the frequency sweep and mesh resolution.",
      destination: "emerge-emi",
      selectors: ['[data-guide="emerge-emi-setup"]'],
    }, {
      title: "Add a dielectric cover (optional)",
      instruction: "For a radome comparison, first solve the bare antenna. Then enable the dielectric cover, set its gap, dimensions and relative permittivity, and run the same sweep again.",
      destination: "emerge-emi",
      selectors: ['[data-guide="emerge-radome"]'],
      optional: true,
    }, {
      title: "Check runtime",
      instruction: "Click Check EMerge runtime and confirm the selected interpreter reports radiation_pattern. This does not start the solver.",
      destination: "emerge-emi",
      selectors: ['[data-guide="emerge-emi-probe"]'],
    }, {
      title: "Run radiation analysis",
      instruction: "Click Run beside EMerge radiation when ready. The guide will not click Run or change solver parameters.",
      destination: "emerge-emi",
      selectors: ['[data-guide="emerge-emi-run-radiation"]'],
    }, {
      ...resultStep,
      destination: "emerge-em-result",
      selectors: ['[data-guide="emerge-em-result"]'],
      instruction: "Inspect solved and display-interpolated 3D patterns, angular plots, and the chamber overlay. The bench visibility control changes only the view. Review units, model status, warnings and provenance; relative patterns are not an EMI compliance prediction.",
    }],
  },
  pi: {
    label: "SPIKE copper DC / PI",
    capability: "SPIKE Copper Geometry DC solves an approximate resistive network over tracks, vias, pads and copper zones. Zone results need mesh convergence review.",
    next: "Compare source-to-load voltage drop and current density against your limits; refine the copper-zone mesh where the result is sensitive.",
    steps: [importStep, {
      title: "Choose copper DC",
      instruction: "Open PI → DC drop. Check that SPIKE Copper Geometry DC is selected in the setup; this is the approximate board DC path.",
      destination: "pi",
      selectors: ['[data-guide="pi-analysis"]', '.tool[title="DC drop"]'],
    }, {
      title: "Configure sources and loads",
      instruction: "Select the nets, source and load terminals, stackup, and analysis limits. Review validation issues before running.",
      destination: "pi",
      selectors: ['[data-guide="pi-setup"]', '.pi-run-dialog'],
    }, {
      title: "Run PI",
      instruction: "Click Run PI once terminals, solver eligibility and warnings are reviewed. The guide never executes an analysis automatically.",
      destination: "pi",
      selectors: ['[data-guide="pi-run"]', '.tool[title="Run PI"]'],
    }, resultStep],
  },
  "pi-peec": {
    label: "SPIKE PEEC AC / transient",
    capability: "Native PEEC AC/RLCG and geometry transient are experimental and approximate; they are not calibrated SI S-parameters or full-wave radiation.",
    next: "Check passivity, energy or convergence diagnostics and compare a simpler DC result or an independent reference before using the waveform or impedance.",
    steps: [importStep, {
      title: "Choose the PEEC workflow",
      instruction: "Open PI → AC sweep or Transient. The selected native PEEC solver must be present in the packaged worker.",
      destination: "pi",
      selectors: ['.tool[title="AC sweep"]', '.tool[title="Transient"]'],
    }, {
      title: "Review model and limits",
      instruction: "Set terminals, excitation, frequency or time range, stackup, mesh and resource limits. Confirm the solver catalog marks this exact workflow eligible.",
      destination: "pi",
      selectors: ['[data-guide="pi-setup"]', '.pi-run-dialog'],
    }, {
      title: "Run experimental PEEC",
      instruction: "Run only after the setup accepts the selected native PEEC mode. Treat driving-point RLCG and transient fields as approximate.",
      destination: "pi",
      selectors: ['.tool[title="Run PI"]'],
    }, resultStep],
  },
  si: {
    label: "HF / SI SPIKE internal",
    capability: "Internal geometry-derived SI supports bounded simple channel and coupled-pair cases experimentally. Arbitrary PCB S-parameter extraction is not validated.",
    next: "Check reference path and geometry assumptions, then inspect passivity, port matching and convergence before comparing Touchstone or measured data.",
    steps: [importStep, {
      title: "Open HF / SI",
      instruction: "Open HF / SI and keep SPIKE internal selected for its bounded channel workflows.",
      destination: "si",
      selectors: ['[data-guide="si-setup"]'],
    }, {
      title: "Choose SPIKE internal",
      instruction: "The S-parameter solver selector affects only S-parameters and Ports. SPIKE internal is the default; EMerge becomes selectable only after a trusted probe reports si_s_parameters.",
      destination: "si",
      selectors: ['[data-guide="si-sparameter-solver"]'],
    }, {
      title: "Choose an SI analysis",
      instruction: "Select the impedance, S-parameter, coupling, or channel workflow you need. SPIKE internal S-parameters and Ports open the internal workbench.",
      destination: "si",
      selectors: ['[data-guide="si-sparameters"]'],
    }, {
      title: "Configure the channel",
      instruction: "Select nets, ports, stackup, and analysis settings. Check the workbench for capability and validity warnings.",
      destination: "si",
      selectors: ['[data-guide="si-setup"]', '.floating-panel:has([data-guide="si-run"])'],
      optional: true,
    }, {
      title: "Run the supported analysis",
      instruction: "Use the workbench Run button only when it reports a supported setup. No solve is started by this guide.",
      destination: "si",
      selectors: ['[data-guide="si-run"]'],
      optional: true,
    }, resultStep],
  },
  emi: {
    label: "SPIKE EMI screening",
    capability: "Built-in EMI screening is a risk estimate. SPIKE has no packaged general 3D full-wave solver or compliance prediction.",
    next: "Review the flagged nets and return paths; use a qualified external field workflow and measurements when an emission level matters.",
    steps: [importStep, {
      title: "Open EM setup",
      instruction: "Open EM and configure domains, nets, ports, excitation, and measurement settings.",
      destination: "emi",
      selectors: ['[data-guide="emi-setup"]', '.ribbon-emi'],
    }, {
      title: "Run preflight",
      instruction: "Check the preflight issues and solver capability before asking for a full-wave or screening run.",
      destination: "emi",
      selectors: ['[data-guide="emi-preflight"]'],
      optional: true,
    }, {
      title: "Run available analysis",
      instruction: "Run the available risk screen after reviewing its inputs and limitations. Full-wave Run solver requires a separately qualified external engine.",
      destination: "emi",
      selectors: ['[data-guide="emi-run"]', '.tool[title="Risk screen"]'],
      optional: true,
    }, resultStep],
  },
  thermal: {
    label: "SPIKE object thermal",
    capability: "Built-in steady/transient object thermal is an approximate lumped network with explicit power and heat paths; it is not a spatial board temperature field.",
    next: "Inspect each object peak and time history, then check heat balance and the assumed resistance and capacity values.",
    steps: [importStep, {
      title: "Open thermal setup",
      instruction: "Open Thermal and review stackup, components, heat sources, and ambient conditions.",
      destination: "thermal",
      selectors: ['[data-guide="thermal-setup"]', '.ribbon-thermal'],
    }, {
      title: "Review the thermal model",
      instruction: "Choose the supported steady or transient workflow and inspect its stated geometry and material assumptions.",
      destination: "thermal",
      selectors: ['[data-guide="thermal-run"]'],
      optional: true,
    }, {
      title: "Run thermal analysis",
      instruction: "Start the thermal run only after checking inputs and warnings. The guide does not start it automatically.",
      destination: "thermal",
      selectors: ['[data-guide="thermal-run"]'],
      optional: true,
    }, { ...resultStep, destination: "thermal", selectors: ['.thermal-native-results', '.thermal-validation.valid', '[data-guide="thermal-run"]'] }],
  },
  "thermal-board": {
    label: "SPIKE board thermal",
    capability: "Built-in board thermal uses an approximate 2D plate or layered stack grid. It does not resolve package blocks, airflow or CFD.",
    next: "Inspect layer maps and heat balance, then vary mesh and uncertain material or boundary inputs to see how the peak temperature changes.",
    steps: [importStep, {
      title: "Open board thermal",
      instruction: "Open Thermal and find the 2D/layered board thermal section. Layered mode needs a complete physical stackup.",
      destination: "thermal",
      selectors: ['[data-guide="thermal-board-setup"]', '.board-thermal-section'],
    }, {
      title: "Set board assumptions",
      instruction: "Choose plate or layered mode and enter power, conductivity and boundary conditions. Imported copper coverage does not supply missing thermal properties.",
      destination: "thermal",
      selectors: ['.board-thermal-section .board-thermal-settings'],
    }, {
      title: "Run board thermal",
      instruction: "Review the input warnings, then run the approximate board model.",
      destination: "thermal",
      selectors: ['[data-guide="thermal-board-run"]', '.board-thermal-section .run-btn'],
    }, { ...resultStep, destination: "thermal", selectors: ['.board-thermal-section .thermal-validation.valid'] }],
  },
  circuit: {
    label: "SPIKE native circuit MNA",
    capability: "The native MNA workspace accepts reviewed explicit linear R/L/C circuits and sources. PEEC coupling and the owned SPIKES route remain experimental.",
    next: "Review the composed netlist, model status and waveforms; verify element values and node mapping against a known circuit case.",
    steps: [importStep, {
      title: "Open the circuit workspace",
      instruction: "Open PI → SPICE models. The native MNA route needs an explicitly composed and validated circuit.",
      destination: "circuit",
      selectors: ['[data-guide="circuit-workspace"]', '.spice-workbench'],
    }, {
      title: "Compose and validate",
      instruction: "Assign models and nodes, open Run, select SPIKE native MNA (linear), then Compose & validate. Resolve blocking diagnostics.",
      destination: "circuit",
      selectors: ['[data-guide="circuit-compose"]', '.spice-run-controls'],
    }, {
      title: "Run the circuit",
      instruction: "Start the native circuit run only after the composed workspace passes validation. This does not infer a whole-board circuit automatically.",
      destination: "circuit",
      selectors: ['[data-guide="circuit-run"]', '.spice-workbench footer .run-btn'],
    }, resultStep],
  },
};

function visible(element: HTMLElement): boolean {
  if (!element.isConnected || element.closest('[aria-hidden="true"], [hidden]')) return false;
  const style = getComputedStyle(element);
  return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
}

function findTarget(selectors: string[]): HTMLElement | null {
  for (const selector of selectors) {
    try {
      const target = [...document.querySelectorAll<HTMLElement>(selector)].find(visible);
      if (target) return target;
    } catch { /* An unsupported fallback selector is ignored. */ }
  }
  return null;
}

export default function AnalysisGuide({ boardLoaded, resultAvailable, onNavigate, onClose }: {
  boardLoaded: boolean;
  resultAvailable: boolean;
  onNavigate: (destination: GuideDestination) => void;
  onClose: () => void;
}) {
  const [flow, setFlow] = useState<GuideFlow>("emerge-si");
  const [index, setIndex] = useState(0);
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [pulse, setPulse] = useState(0);
  const navigateRef = useRef(onNavigate);
  navigateRef.current = onNavigate;
  const step = flows[flow].steps[index];
  const workflow = flows[flow];
  const completed = useMemo(() => index === 0 && boardLoaded, [boardLoaded, index]);
  const recommendation = !boardLoaded
    ? "Import a board, then check its stackup and validation issues."
    : !target && !step.optional
      ? "Open the indicated workspace or setup panel, then use Find control. If the control remains absent, check runtime availability."
      : index < workflow.steps.length - 1
        ? `Continue with “${workflow.steps[index + 1].title}” after reviewing this step.`
        : `For this workflow's result: ${workflow.next}`;

  useEffect(() => {
    if (step.destination) navigateRef.current(step.destination);
    let highlighted: HTMLElement | null = null;
    let initialized = false;
    const update = () => {
      const next = findTarget(step.selectors);
      if (initialized && next === highlighted) return;
      initialized = true;
      highlighted?.classList.remove("analysis-guide-highlight");
      highlighted = next;
      next?.classList.add("analysis-guide-highlight");
      setTarget(next);
      next?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    };
    const frame = requestAnimationFrame(update);
    const observer = new MutationObserver(update);
    observer.observe(document.body, { childList: true, subtree: true });
    update();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      highlighted?.classList.remove("analysis-guide-highlight");
    };
  }, [flow, index, step]);

  const findControl = () => {
    if (step.destination) navigateRef.current(step.destination);
    const next = findTarget(step.selectors);
    if (!next) { setTarget(null); return; }
    next.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
    const focusable = next.matches("button, input, select, textarea, [tabindex]")
      ? next : next.querySelector<HTMLElement>("button, input, select, textarea, [tabindex]");
    focusable?.focus({ preventScroll: true });
    next.classList.remove("analysis-guide-highlight");
    void next.offsetWidth;
    next.classList.add("analysis-guide-highlight");
    setTarget(next);
    setPulse(value => value + 1);
  };

  return <aside className="analysis-guide floating-panel" aria-label="Analysis guide">
    <div className="floating-heading"><div><CircleHelp size={15} /><b>ANALYSIS GUIDE</b></div><button type="button" title="Close guide" aria-label="Close guide" onClick={onClose}><X size={15} /></button></div>
    <div className="analysis-guide-body">
      <label htmlFor="analysis-guide-flow">Analysis workflow</label>
      <select id="analysis-guide-flow" value={flow} onChange={event => { setFlow(event.target.value as GuideFlow); setIndex(0); }}>
        {Object.entries(flows).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}
      </select>
      <p className="analysis-guide-capability">{workflow.capability}</p>
      <div className="analysis-guide-progress" aria-label={`Step ${index + 1} of ${flows[flow].steps.length}`}>
        {flows[flow].steps.map((item, position) => <button key={position} type="button" className={position === index ? "active" : ""} title={`Step ${position + 1}: ${item.title}`} aria-label={`Go to step ${position + 1}: ${item.title}`} onClick={() => setIndex(position)} />)}
      </div>
      <small>Step {index + 1} of {flows[flow].steps.length}</small>
      <h3>{step.title}</h3>
      <p>{step.instruction}</p>
      <div className={target ? "analysis-guide-target found" : "analysis-guide-target missing"} role="status" aria-live="polite" data-pulse={pulse}>
        {target ? "Control highlighted in SPIKE" : completed ? "Board already loaded" : index === workflow.steps.length - 1 && resultAvailable ? "A saved result exists; confirm it belongs to this workflow" : step.optional ? "Control is not currently available in this workspace" : "Target unavailable. Open the relevant panel, then use Find control."}
      </div>
      <button type="button" className="analysis-guide-find" onClick={findControl}><Focus size={14} /> Find control</button>
      <section className="analysis-guide-next" aria-label="Recommended next step">
        <b>RECOMMENDED NEXT STEP</b>
        <p>{recommendation}</p>
        {index < workflow.steps.length - 1 && <button type="button" onClick={() => setIndex(position => position + 1)}>Go to next step <ArrowRight size={13} /></button>}
      </section>
    </div>
    <div className="analysis-guide-actions">
      <button type="button" onClick={() => setIndex(position => Math.max(0, position - 1))} disabled={index === 0}><ArrowLeft size={14} /> Back</button>
      <button type="button" onClick={() => index === flows[flow].steps.length - 1 ? onClose() : setIndex(position => position + 1)}>{index === flows[flow].steps.length - 1 ? "Finish" : "Next"}{index < flows[flow].steps.length - 1 && <ArrowRight size={14} />}</button>
    </div>
  </aside>;
}
