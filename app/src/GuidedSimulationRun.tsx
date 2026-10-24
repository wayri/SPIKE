// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import SectionHelpButton from "./SectionHelpButton";
import { GuidedSimulationController, canLaunchGuidedRun, firstGuidedBlocker } from "./guidedSimulationModel";
import type { GuidedSimulationAdapter, GuidedSimulationContext, GuidedSimulationRequirement, GuidedSimulationStep } from "./guidedSimulationModel";
import "./buttonStandard.css";
import "./GuidedSimulationRun.css";

export type GuidedSimulationRunProps = {
  context: GuidedSimulationContext;
  intent: "run" | "tutor";
  adapter: GuidedSimulationAdapter;
  steps?: GuidedSimulationStep[];
  onFix: (requirement: GuidedSimulationRequirement | GuidedSimulationStep) => void;
  onClose: () => void;
};

export default function GuidedSimulationRun({ context, intent, adapter, steps = [], onFix, onClose }: GuidedSimulationRunProps) {
  const adapterRef = useRef(adapter); adapterRef.current = adapter;
  const contextRef = useRef(context); contextRef.current = context;
  const requireCurrent = (snapshot: GuidedSimulationContext) => {
    const live = contextRef.current;
    if (snapshot.key !== live.key || snapshot.revision !== live.revision || snapshot.workspace !== live.workspace) throw new Error("Setup changed. Recheck the current project and workspace before running.");
  };
  const controller = useMemo(() => new GuidedSimulationController(context, {
    check: (snapshot, signal) => { requireCurrent(snapshot); return adapterRef.current.check(snapshot, signal); },
    run: (snapshot, signal) => { requireCurrent(snapshot); return adapterRef.current.run(snapshot, signal); },
  }), [context.key, context.revision, context.workspace]);
  const [observation, setObservation] = useState(() => ({ controller, state: controller.snapshot() }));
  const [stepIndex, setStepIndex] = useState(0);
  // A changed snapshot renders idle immediately; never expose old readiness for one frame.
  const state = observation.controller === controller ? observation.state : controller.snapshot();
  useEffect(() => { setStepIndex(0); }, [context.key, context.workspace]);
  const firstCheck = useRef<{key:string;controller:GuidedSimulationController}|null>(null);
  useEffect(() => {
    const unsubscribe = controller.subscribe(next => setObservation({ controller, state: next }));
    const key=`${context.key}:${context.workspace}`;
    if(firstCheck.current?.key!==key||firstCheck.current?.controller===controller){firstCheck.current={key,controller};void controller.check();}
    return () => { unsubscribe(); controller.cancel(); };
  }, [controller]);
  const blocker = firstGuidedBlocker(state);
  const blockers = state.requirements.filter(row => row.severity === "blocker");
  const warnings = state.requirements.filter(row => row.severity === "warning");
  const busy = state.phase === "checking" || state.phase === "running";
  const step = steps[Math.min(stepIndex, Math.max(0, steps.length - 1))];
  const close = () => { controller.cancel(); onClose(); };
  return <aside className="guided-simulation-run" aria-label="Simulation guide" onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); close(); } }}>
    <header className="guided-simulation-run__header">
      <div><span className="guided-simulation-run__eyebrow">{context.workspace}</span><h2>{intent === "tutor" ? "Simulation tutor" : "Prepare to run"}</h2></div>
      <SectionHelpButton topic="doc:docs/GUIDED_SIMULATION_RUN.md" label="Guided simulation" />
      <button type="button" className="spike-control--icon" aria-label="Close simulation guide" title="Close simulation guide" onClick={close}>×</button>
    </header>
    <div className="guided-simulation-run__body">
      <p className="guided-simulation-run__context" title={context.title}>{context.title}</p>
      <p className="guided-simulation-run__status" role="status" aria-live="polite">{state.phase === "checking" ? "Checking current setup…" : state.phase === "blocked" ? `${blockers.length} required ${blockers.length === 1 ? "item" : "items"} remaining` : state.phase === "ready" ? "Setup ready for this revision" : state.phase === "running" ? "Starting simulation…" : state.phase === "launched" ? "Run request submitted. Follow the simulation progress." : state.phase === "cancelled" ? "Guide paused. Recheck before running." : state.phase === "error" ? "Setup check or run request failed" : "Setup changed. Checking is required."}</p>
      {state.error && <p role="alert">{state.error}</p>}
      {intent === "tutor" && step && <section className="guided-simulation-run__section" aria-label="Tutor step">
        <span className="guided-simulation-run__eyebrow">Step {stepIndex + 1} of {steps.length}</span><h3>{step.title}</h3><p>{step.detail}</p>
        {step.route && <button type="button" disabled={busy} onClick={() => onFix(step)}>Open this step</button>}
        <div className="guided-simulation-run__actions"><button type="button" disabled={busy || stepIndex === 0} onClick={() => setStepIndex(value => Math.max(0, value - 1))}>Back</button><button type="button" disabled={busy || stepIndex >= steps.length - 1} onClick={() => setStepIndex(value => Math.min(steps.length - 1, value + 1))}>Next</button></div>
      </section>}
      {blocker && <section className="guided-simulation-run__section" aria-label="Next required item"><span className="guided-simulation-run__eyebrow">Next required item</span><h3>{blocker.title}</h3><p>{blocker.detail}</p>{blocker.route && <button type="button" className="spike-control--primary" disabled={busy} onClick={() => onFix(blocker)}>Resolve this item</button>}<p className="guided-simulation-run__hint">Save or apply the change, then recheck. The next requirement appears after this one is resolved.</p></section>}
      {warnings.length > 0 && <section className="guided-simulation-run__section" aria-label="Setup warnings"><h3>Review before running</h3>{warnings.map(warning => <div key={warning.id}><strong>{warning.title}</strong><p>{warning.detail}</p>{warning.route && <button type="button" disabled={busy} onClick={() => onFix(warning)}>Review warning</button>}</div>)}</section>}
      {state.summary && <p>{state.summary}</p>}
      <p className="guided-simulation-run__hint">Setup readiness checks required inputs. It does not establish numerical accuracy or validate the solver.</p>
    </div>
    <footer className="guided-simulation-run__actions"><button type="button" disabled={busy || state.phase === "launched"} onClick={() => void controller.check()}>Recheck setup</button><button type="button" className="spike-control--primary" disabled={!canLaunchGuidedRun(state)} onClick={() => void controller.launch()}>Run simulation</button></footer>
  </aside>;
}
