// SPDX-License-Identifier: Apache-2.0
import { useId, useState } from "react";
import { ChevronDown, type LucideIcon } from "./icons";
import ActionContextMenu, { type ContextAction } from "./ActionContextMenu";

/** Secondary commands keep their existing handlers in a keyboard-accessible popup. */
export default function ToolbarMenu({ label, icon: Icon, actions }: { label: string; icon: LucideIcon; actions: ContextAction[] }) {
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);
  const id = useId();
  const open = (button: HTMLButtonElement) => {
    const bounds = button.getBoundingClientRect();
    setAnchor({ x: bounds.left, y: bounds.bottom + 4 });
  };
  return <>
    <button type="button" className="plain-btn toolbar-menu-trigger" aria-label={label} title={label}
      aria-haspopup="menu" aria-expanded={Boolean(anchor)} aria-controls={anchor ? id : undefined}
      onClick={event => anchor ? setAnchor(null) : open(event.currentTarget)}
      onKeyDown={event => { if (event.key === "ArrowDown") { event.preventDefault(); event.stopPropagation(); open(event.currentTarget); } }}>
      <Icon size={15} aria-hidden="true" /><span>{label}</span><ChevronDown size={12} aria-hidden="true" />
    </button>
    {anchor && <ActionContextMenu id={id} {...anchor} title={label} actions={actions} onClose={() => setAnchor(null)} />}
  </>;
}
