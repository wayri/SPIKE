// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useModalFocusScope } from "./modalFocusScope";
export function DesktopCloseDraftDialog({ owner, onReview, onCancel }: { owner: string; onReview: () => Promise<boolean>; onCancel: () => void }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const modal = useModalFocusScope(onCancel, busy);
  const review = async () => {
    setBusy(true); setError("");
    try {
      if (await onReview()) onCancel();
      else setError("The draft window is unavailable. Cancel closing and reopen the assembly tool to review its state.");
    } catch (cause) { setError(`Could not show the draft: ${cause instanceof Error ? cause.message : String(cause)}`); }
    finally { setBusy(false); }
  };
  return <div className="modal-backdrop unsaved-project-backdrop" role="presentation">
    <section ref={modal.scopeRef} onKeyDown={modal.onKeyDown} className="modal unsaved-project-dialog" role="alertdialog" aria-modal="true" aria-label="Assembly draft prevents closing">
      <header><h2>Review the assembly draft before closing</h2></header>
      <div className="unsaved-project-content"><p>The {owner} tool has unsaved edits. Open it, then save or discard those edits before closing SPIKE.</p><p>Minimized tools will be restored. Cancel keeps SPIKE and the draft open.</p>{error && <p role="alert">{error}</p>}</div>
      <footer><button type="button" className="secondary-btn" disabled={busy} data-modal-initial-focus onClick={onCancel}>Cancel closing</button><button type="button" className="run-btn" disabled={busy} onClick={() => void review()}>{busy ? "Opening draft" : "Review draft"}</button></footer>
    </section>
  </div>;
}
