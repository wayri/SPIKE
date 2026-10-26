// SPDX-License-Identifier: Apache-2.0
import { useId, type ReactNode } from "react";
import "./SolverSetupSteps.css";

export type SolverSetupStep = { id: string; label: string; description: string; disabled?: boolean };

/** Navigation records editing position only. Solver admission remains with the existing run handlers. */
export default function SolverSetupSteps({ label, steps, current, onChange }: {
  label: string; steps: readonly SolverSetupStep[]; current: string; onChange: (id: string) => void;
}) {
  const descriptionId = useId();
  const index = steps.findIndex(step => step.id === current);
  const active = steps[index];
  const move = (target: SolverSetupStep | undefined) => { if (target && !target.disabled) onChange(target.id); };
  return <div className="solver-setup-steps">
    <nav aria-label={label}><ol>{steps.map((step, position) => <li key={step.id}>
      <button type="button" className={step.id === current ? "selected" : ""} aria-current={step.id === current ? "step" : undefined}
        aria-describedby={step.id === current ? descriptionId : undefined} disabled={step.disabled} onClick={() => move(step)} title={step.description}>
        <span className="solver-step-number" aria-hidden="true">{position + 1}</span><span>{step.label}</span>
      </button>
    </li>)}</ol></nav>
    <p id={descriptionId} className="solver-step-description">{active?.description ?? "Choose a setup step."}</p>
    <div className="solver-step-navigation"><button type="button" disabled={index <= 0 || Boolean(steps[index - 1]?.disabled)} onClick={() => move(steps[index - 1])}>Back</button>
      <span>{index < 0 ? "Choose step" : `Step ${index + 1} of ${steps.length}`}</span>
      <button type="button" disabled={index < 0 || index >= steps.length - 1 || Boolean(steps[index + 1]?.disabled)} onClick={() => move(steps[index + 1])}>Next</button></div>
  </div>;
}

/** Keep editors mounted so drafts, file inputs and local control state survive navigation. */
export function SolverSetupPanel({ active, label, children }: { active: boolean; label: string; children: ReactNode }) {
  return <section className="solver-setup-panel" hidden={!active} aria-label={label}>{children}</section>;
}
