// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
import { useEffect, useRef, useState } from 'react';
import { loadDuration, loadEstimate, projectLoadView, type ProjectLoadState } from './projectLoadProgress';
import './projectLoadPanel.css';

export default function ProjectLoadPanel({ state, onCancel, onDismiss }: {
  state: ProjectLoadState | null; onCancel: () => void; onDismiss: () => void;
}) {
  const [now, setNow] = useState(performance.now());
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!state || state.status !== 'running') return;
    button.current?.focus();
    const timer = window.setInterval(() => setNow(performance.now()), 250);
    return () => window.clearInterval(timer);
  }, [state?.id, state?.status]);
  if (!state || state.status === 'ready') return null;
  const view = projectLoadView(state, now);
  const busy = state.status === 'running';
  return <div className="project-load-shade" role="presentation">
    <section className="project-load-panel" role="dialog" aria-modal="true" aria-labelledby="project-load-title"
      onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); busy ? onCancel() : onDismiss(); }
        if (event.key === 'Tab') { event.preventDefault(); button.current?.focus(); } }}>
      <h2 id="project-load-title">{busy ? 'Loading project' : state.status === 'cancelled' ? 'Loading cancelled' : 'Project loading failed'}</h2>
      <p className="project-load-file" title={state.fileName}>{state.fileName}</p>
      <div className="project-load-stage"><span className={busy ? 'project-load-spinner' : ''} aria-hidden="true" />
        <span>{view.stageLabel}</span><strong>{view.percent}%</strong></div>
      <progress max={100} value={view.percent} aria-label="Project loading progress" />
      <p className="project-load-basis">{view.basis}; 100% requires a usable scene.</p>
      <dl><div><dt>Elapsed</dt><dd>{loadDuration(view.elapsedMs)}</dd></div>
        <div><dt>{view.etaScope === 'stage' ? 'Estimated remaining in this stage' : 'Estimated remaining'}</dt>
          <dd>{view.etaMs === null ? busy ? 'Measuring...' : 'Stopped' : loadEstimate(view.etaMs)}</dd></div></dl>
      <p className="project-load-estimate-note">{view.etaNote}</p>
      {busy && state.stage === 'package' && state.previousDurationMs !== undefined &&
        <p className="project-load-estimate-note">Previous open of {state.fileName} took {loadDuration(state.previousDurationMs)}.
          {' '}Project identity is still being verified; this is a timing reference.</p>}
      {state.detail && <p role="status">{state.detail}</p>}
      {state.error && <p className="project-load-error" role="alert">{state.error}</p>}
      <footer><button ref={button} type="button" className="spike-control--compact" onClick={busy ? onCancel : onDismiss}>
        {busy ? 'Cancel loading' : 'Close'}</button></footer>
    </section>
  </div>;
}
