// SPDX-License-Identifier: Apache-2.0
import { FileArchive, X } from "lucide-react";

export default function ProjectUpgradeDialog({ fileName, sourceFormat, onUpgrade, onLater }: {
  fileName: string;
  sourceFormat: string;
  onUpgrade: () => void;
  onLater: () => void;
}) {
  return <div className="modal-backdrop unsaved-project-backdrop" role="presentation">
    <section className="modal unsaved-project-dialog" role="dialog" aria-modal="true" aria-labelledby="project-upgrade-title" aria-describedby="project-upgrade-description">
      <header><div><small>OLDER PROJECT FORMAT</small><h2 id="project-upgrade-title">Upgrade this project to .spike v3?</h2></div><FileArchive size={22} /></header>
      <div className="unsaved-project-content">
        <p id="project-upgrade-description"><b>{fileName}</b> opened from {sourceFormat}. SPIKE has converted it in memory. Choose a new file location to save the current project in the latest v3 package format.</p>
        <small>Upgrade now preserves the original file. Later keeps this project open; its next save will use v3.</small>
      </div>
      <footer><button className="secondary-btn" onClick={onLater}><X size={14} /> Later</button><button className="run-btn" autoFocus onClick={onUpgrade}><FileArchive size={14} /> Upgrade now…</button></footer>
    </section>
  </div>;
}
