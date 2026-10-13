// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { APP_SETTINGS_STORAGE_KEY, loadAppSettings } from "./appSettings";
import ReportPreview from "./ReportPreview";
import { connectReportPreviewChild, type ReportPreviewAction, type ReportPreviewSnapshot } from "./reportPreviewWindow";

export default function ReportPreviewWindowRoot() {
  const [snapshot, setSnapshot] = useState<ReportPreviewSnapshot | null>(null);
  const [error, setError] = useState("");
  const actRef = useRef<(action: ReportPreviewAction) => Promise<void>>(async () => {});

  useEffect(() => {
    const sync = () => { document.documentElement.dataset.theme = loadAppSettings().theme; };
    const changed = (event: StorageEvent) => { if (!event.key || event.key === APP_SETTINGS_STORAGE_KEY) sync(); };
    sync();
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, []);
  useEffect(() => {
    let disposed = false;
    let stop: (() => void) | undefined;
    void connectReportPreviewChild(value => {
      if (!disposed) {
        setSnapshot(value);
        document.title = `SPIKE | Engineering report | ${value.fileName}`;
      }
    }).then(connection => {
      if (disposed) connection.stop();
      else { stop = connection.stop; actRef.current = connection.act; }
    }).catch(reason => { if (!disposed) setError(reason instanceof Error ? reason.message : String(reason)); });
    const pagehide = () => { void actRef.current({ type: "closed" }); };
    window.addEventListener("pagehide", pagehide);
    return () => { disposed = true; stop?.(); window.removeEventListener("pagehide", pagehide); };
  }, []);

  if (error) return <main className="report-preview-window"><p role="alert">{error}</p></main>;
  if (!snapshot) return <main className="report-preview-window"><p role="status">Connecting to SPIKE workspace...</p></main>;
  return <ReportPreview
    mode="window"
    nativeWindow={"__TAURI_INTERNALS__" in window}
    fileName={snapshot.fileName}
    html={snapshot.html}
    onExport={() => { void actRef.current({ type: "export" }); }}
    onClose={() => { void actRef.current({ type: "close" }); }}
  />;
}
