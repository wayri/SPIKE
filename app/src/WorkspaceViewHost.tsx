// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { closeWorkspaceViewWindow, openWorkspaceViewWindow, updateWorkspaceViewWindow } from "./workspaceViewWindows";
import type { WorkspaceViewAction, WorkspaceViewDescriptor, WorkspaceViewSnapshot, WorkspaceViewViewportData } from "./workspaceViewModel";

export default function WorkspaceViewHost({ descriptor, snapshot, viewportData, onAction, onDock, onError }: {
  descriptor: WorkspaceViewDescriptor;
  snapshot: WorkspaceViewSnapshot;
  viewportData?: WorkspaceViewViewportData;
  onAction: (action: WorkspaceViewAction) => unknown | Promise<unknown>;
  onDock: () => void;
  onError?: (message: string) => void;
}) {
  const latest = useRef({ snapshot, viewportData, onAction, onDock, onError }); latest.current = { snapshot, viewportData, onAction, onDock, onError };
  const [error, setError] = useState("");
  useEffect(() => {
    if (!descriptor.detached) { void closeWorkspaceViewWindow(descriptor.id); return; }
    let disposed = false;
    void openWorkspaceViewWindow(descriptor.id, latest.current.snapshot, action => {
      if (action.type === "closed" || action.type === "redock") { latest.current.onDock(); return; }
      return latest.current.onAction(action);
    }, latest.current.viewportData).catch(cause => {
      if (disposed) return; const message = cause instanceof Error ? cause.message : String(cause);
      setError(message); latest.current.onError?.(message); latest.current.onDock();
    });
    return () => { disposed = true; void closeWorkspaceViewWindow(descriptor.id); };
  }, [descriptor.id, descriptor.detached]);
  useEffect(() => { if (descriptor.detached) void updateWorkspaceViewWindow(descriptor.id, snapshot, viewportData).catch(cause => { const message = String(cause); setError(message); latest.current.onError?.(message); }); }, [descriptor.detached, descriptor.id, snapshot, viewportData]);
  return error ? <div className="workspace-view-host-error" role="alert">{error}</div> : null;
}
