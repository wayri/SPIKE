// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import { History, RotateCcw } from "lucide-react";
import { listPythonWorkspaceBackups, restorePythonBackupDocument, type PythonDocument } from "./pythonWorkspaceModel";

export default function PythonRecoveryPanel({ revision, disabled, onRestore }: { revision: number; disabled: boolean; onRestore: (document: PythonDocument) => void }) {
  const [selected, setSelected] = useState("");
  const backups = useMemo(() => listPythonWorkspaceBackups(), [revision]);
  const backup = backups.find(item => item.id === selected) ?? backups[0];
  return <div className="python-recovery-panel" data-revision={revision}>
    <div className="python-pane-heading"><History size={14} /><b>AUTOMATIC BACKUPS</b></div>
    <p className="python-pane-note">Local recovery snapshots keep recent edits across app restarts. Save writes your script file. Restore opens a separate unsaved copy.</p>
    {backup ? <><label className="python-backup-select">Snapshot<select aria-label="Recovery snapshot" value={backup.id} onChange={event => setSelected(event.target.value)}>{backups.map(item => <option key={item.id} value={item.id}>{new Date(item.timestamp).toLocaleString()}</option>)}</select></label>
      <div className="python-recovery-files">{backup.session.documents.map(document => <article key={document.id}><span title={document.path ?? document.name}>{document.name}</span><small>{document.code.length.toLocaleString()} characters</small><button type="button" disabled={disabled} onClick={() => { const copy = restorePythonBackupDocument(backup, document.id); if (copy) onRestore(copy); }} aria-label={`Restore copy of ${document.name}`}><RotateCcw size={12} /> Restore copy</button></article>)}</div></> : <p className="python-pane-note">No recovery snapshots yet. Edits are backed up automatically when local storage is available.</p>}
  </div>;
}
