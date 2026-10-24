// SPDX-License-Identifier: Apache-2.0
import { useEffect, useReducer, useRef } from "react";
import { helpGuidedFlows, helpGuideReducer, initialHelpGuideState, type HelpGuideReference, type HelpGuideStep } from "./helpGuidedFlows";
import "./buttonStandard.css";
import "./HelpGuidedTours.css";

export interface HelpGuidedToursProps { onNavigate?: (topic: string, anchor?: string) => void; initialFlow?: string }

export function HelpGuideStepContent({ step, number, onNavigate }: { step: HelpGuideStep; number: number } & HelpGuidedToursProps) {
  const { image } = step;
  function referenceLink(item: HelpGuideReference) {
    return <a key={`${item.topic}:${item.anchor ?? ""}`} href={`#help/${item.topic}${item.anchor ? `#${item.anchor}` : ""}`} data-help-topic={item.topic} data-help-anchor={item.anchor}
      onClick={onNavigate ? event => { event.preventDefault(); event.stopPropagation(); onNavigate(item.topic, item.anchor); } : undefined}>{item.label}</a>;
  }
  return <div className="help-guide-step-content">
    <div className="help-guide-instructions">
      <section><h3>Do this</h3><p>{step.action}</p></section>
      <section><h3>What you should see</h3><p>{step.expected}</p></section>
    </div>
    <figure className="help-guide-figure">
      <button type="button" className="help-guide-image" data-help-image="true" aria-label={`Enlarge screenshot: ${image.alt}`}>
        <img src={image.src} alt={image.alt} loading="lazy" />
        <span className="help-guide-highlight" aria-hidden="true" style={{ left: `${image.highlight.x}%`, top: `${image.highlight.y}%`, width: `${image.highlight.width}%`, height: `${image.highlight.height}%` }}>
          <span>{number}</span>
        </span>
      </button>
      <figcaption><strong>Highlight {number}: {image.highlight.label}.</strong> {image.caption} Select the picture to enlarge.</figcaption>
    </figure>
    <section className="help-guide-recovery"><h3>If you get stuck</h3><p>{step.recovery}</p></section>
    <div className="help-guide-references"><span>Reference</span>{step.references.map(referenceLink)}</div>
  </div>;
}

export default function HelpGuidedTours({ onNavigate, initialFlow }: HelpGuidedToursProps) {
  const [state, dispatch] = useReducer(helpGuideReducer, initialFlow ? helpGuideReducer(initialHelpGuideState, { type: "choose", flowId: initialFlow }) : initialHelpGuideState);
  const flow = helpGuidedFlows.find(item => item.id === state.flowId);
  const heading = useRef<HTMLHeadingElement>(null);
  const initial = useRef(true);
  const previousFlow = useRef(state.flowId);
  useEffect(() => {
    if (initial.current) { initial.current = false; return; }
    heading.current?.focus({ preventScroll: true });
    const target = previousFlow.current === state.flowId ? heading.current : heading.current?.closest(".help-guided-tours");
    target?.scrollIntoView({ block: "start" });
    previousFlow.current = state.flowId;
  }, [state.flowId, state.step]);
  if (!flow) return <section className="help-guided-tours" aria-label="Guided tasks">
    <div className="help-guide-intro"><span className="help-guide-kicker">Start with a task</span><h2 ref={heading} tabIndex={-1}>What would you like to do?</h2><p>Choose a task, then follow one step at a time. Each picture shows the actual interface with the relevant control highlighted.</p></div>
    <div className="help-guide-task-grid">{helpGuidedFlows.map((item, index) => <button type="button" className="help-guide-task" data-help-topic={`guide:${item.id}`} key={item.id} onClick={() => dispatch({ type: "choose", flowId: item.id })}>
      <img className="help-guide-task-thumbnail" src={item.steps[0].image.src} alt="" loading="lazy" />
      <span className="help-guide-task-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
      <span className="help-guide-task-copy"><strong>{item.title}</strong><span>{item.summary}</span><small>{item.steps.length} guided steps</small></span>
      <span aria-hidden="true">&rarr;</span>
    </button>)}</div>
  </section>;
  const step = flow.steps[state.step];
  return <section className="help-guided-tours" aria-label={`${flow.title} guided task`}>
    <div className="help-guide-header"><button type="button" onClick={() => dispatch({ type: "home" })}>All tasks</button><span>{flow.steps.length} steps / {flow.title}</span></div>
    <h2 className="help-guide-title">{flow.title}</h2><p>{flow.outcome}</p>
    <details className="help-guide-prerequisites" open={state.step === 0}><summary>Before you start</summary><ul>{flow.prerequisites.map(item => <li key={item}>{item}</li>)}</ul></details>
    <nav className="help-guide-step-list" aria-label="Task steps"><ol>{flow.steps.map((item, index) => <li key={item.title}><button type="button" aria-current={index === state.step ? "step" : undefined} onClick={() => dispatch({ type: "step", index })}><span aria-hidden="true">{index + 1}</span><span>{item.title}</span></button></li>)}</ol></nav>
    <h3 className="help-guide-current-title" ref={heading} tabIndex={-1}>Step {state.step + 1} of {flow.steps.length}: {step.title}</h3>
    <HelpGuideStepContent step={step} number={state.step + 1} onNavigate={onNavigate} />
    <div className="help-guide-navigation"><button type="button" disabled={state.step === 0} onClick={() => dispatch({ type: "back" })}>Back</button><span aria-live="polite">Step {state.step + 1} of {flow.steps.length}</span>{state.step < flow.steps.length - 1
      ? <button type="button" className="spike-control--primary" onClick={() => dispatch({ type: "next" })}>Next step</button>
      : <button type="button" className="spike-control--primary" onClick={() => dispatch({ type: "home" })}>Choose another task</button>}</div>
  </section>;
}
