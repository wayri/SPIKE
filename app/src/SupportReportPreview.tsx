// SPDX-License-Identifier: Apache-2.0
import { useMemo, useRef, useState } from "react";
import { createDiagnosticReport, formatDiagnosticReport, reportWithNotes } from "./reportPrivacy";
import { openBugReport } from "./bugReport";
import "./buttonStandard.css";
import "./appRecovery.css";

export default function SupportReportPreview({ error, componentStack = "", workspace = "Other", onClose }: {
  error?: Error | null; componentStack?: string; workspace?: string; onClose?: () => void;
}) {
  const base = useMemo(() => createDiagnosticReport(error, componentStack), [error, componentStack]);
  const [notes, setNotes] = useState("");
  const [format, setFormat] = useState<"json" | "markdown">("json");
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const savePending = useRef(false);
  const report = reportWithNotes(base, notes);
  const preview = formatDiagnosticReport(report, format);
  async function copy() {
    try { await navigator.clipboard.writeText(preview); setStatus("Reviewed report copied."); }
    catch { setStatus("Copy failed. Select the preview text to copy manually, or retry Copy report."); }
  }
  async function save() {
    if (savePending.current) return;
    savePending.current = true;
    setSaving(true);
    setStatus("Preparing report save...");
    let url = "";
    try {
      const fileName = `${report.report_id}.${format === "json" ? "json" : "md"}`;
      if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
        const { saveNativeTextFile } = await import("./workerBridge");
        const savedPath = await saveNativeTextFile(fileName, preview, "support-report");
        setStatus(savedPath === null ? "Report save canceled. Nothing was saved." : "Reviewed report saved.");
        return;
      }
      url = URL.createObjectURL(new Blob([preview], { type: format === "json" ? "application/json" : "text/markdown" }));
      const link = document.createElement("a");
      link.href = url; link.download = fileName;
      document.body.appendChild(link);
      try { link.click(); } finally { link.remove(); }
      setStatus("Report download requested. Check your downloads; if unavailable, copy the preview or retry Save report.");
    } catch { setStatus("Save failed. Copy the preview or retry Save report."); }
    finally {
      if (url) setTimeout(() => URL.revokeObjectURL(url), 1000);
      savePending.current = false;
      setSaving(false);
    }
  }
  return <section className="support-report" aria-label="Review support report">
    <h2>Preview report</h2>
    <p>Report ID: <code>{report.report_id}</code>. Share this ID with the report to help group related failures.</p>
    <p>Private error text, paths, source names, URLs, timestamps and browser details are omitted. No project files, screenshots or logs are attached. Nothing is uploaded automatically.</p>
    <label>Optional steps to reproduce and expected behavior
      <textarea disabled={saving} value={notes} maxLength={12000} rows={3} onChange={event => { setNotes(event.target.value); setStatus(""); }} placeholder="Avoid names, project details and secrets."/>
    </label>
    <p>Notes are scrubbed for common private details. Automatic redaction cannot recognize every name or secret. Review the exact export below before sharing.</p>
    <label>Report format <select disabled={saving} value={format} onChange={event => { setFormat(event.target.value as "json" | "markdown"); setStatus(""); }}><option value="json">JSON</option><option value="markdown">Markdown</option></select></label>
    <label>Export preview<textarea readOnly value={preview} rows={12} spellCheck={false} onFocus={event => event.target.select()}/></label>
    <div className="support-report-actions">
      <button type="button" disabled={saving} onClick={() => void copy()}>Copy report</button>
      <button type="button" disabled={saving} onClick={save}>{saving ? "Saving report..." : "Save report"}</button>
      <button type="button" disabled={saving} onClick={() => { setNotes(""); setStatus("Notes cleared. Reports are kept only in this view until you copy or save them."); }}>Clear notes</button>
      <button type="button" disabled={saving} onClick={() => void openBugReport(workspace).then(() => setStatus("Issue form opened. Paste the reviewed report manually; opening the form sends only fixed application metadata.")).catch(() => setStatus("Could not open the issue form. Retry, or visit github.com/wayri/SPIKE/issues/new."))}>Open issue form</button>
      {onClose && <button type="button" disabled={saving} onClick={onClose}>Close report</button>}
    </div>
    {status && <p role="status">{status}</p>}
  </section>;
}
