// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import { ShowControlIcon as PanelTopOpen, CloseControlIcon as X } from "./navigationIcons";
import {
  closeMinimizedTool,
  minimizedToolSnapshot,
  restoreMinimizedTool,
  subscribeMinimizedTools,
  type MinimizedToolItem,
} from "./minimizedTools";
import "./toolRestoreShelf.css";

export type ToolRestoreItem = MinimizedToolItem & { registered?: boolean };

/** Compact, scrollable home for minimized panels and restorable child windows. */
export default function ToolRestoreShelf({ items = [], onError }: { items?: readonly ToolRestoreItem[]; onError?: (message: string) => void }) {
  const [registered, setRegistered] = useState<readonly MinimizedToolItem[]>(minimizedToolSnapshot);
  const [error, setError] = useState("");
  useEffect(() => subscribeMinimizedTools(setRegistered), []);
  const visible = useMemo(() => {
    const merged = new Map<string, ToolRestoreItem>();
    registered.forEach(item => merged.set(item.id, { ...item, registered: true }));
    items.forEach(item => merged.set(item.id, item));
    return [...merged.values()];
  }, [registered, items]);
  if (!visible.length) return null;
  const invoke = async (item: ToolRestoreItem, action: "restore" | "close") => {
    try {
      if (item.registered) {
        if (action === "restore") await restoreMinimizedTool(item.id);
        else await closeMinimizedTool(item.id);
      } else if (action === "restore") await item.restore();
      else await item.close?.();
      setError("");
    } catch (cause) {
      const detail = cause instanceof Error ? cause.message : String(cause);
      const message = `[SPIKE-FE-APP-E-0001] Could not ${action} ${item.label}: ${detail}. Retry from the bottom bar; reopen the tool if its window was closed.`;
      setError(message);
      onError?.(message);
    }
  };
  return <div className="tool-restore-shelf" role="group" aria-label="Minimized tools">
    {error && <span className="tool-restore-error" role="alert" title={error}>{error}</span>}
    {visible.map(item => <span className="tool-restore-item" key={item.id}>
      <button type="button" className="tool-restore-button" title={`Restore ${item.label}`} aria-label={`Restore ${item.label}`}
        onClick={() => void invoke(item, "restore")}>
        <PanelTopOpen size={13} /><span>{item.label}</span>
      </button>
      {item.close && <button type="button" className="tool-restore-close" title={`Close ${item.label}`} aria-label={`Close ${item.label}`}
        onClick={() => void invoke(item, "close")}><X size={12} /></button>}
    </span>)}
  </div>;
}
