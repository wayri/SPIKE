// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { ArrowLeft, ChevronRight, Grid3X3, MousePointer2, type LucideIcon } from "./icons";
import CommandStrip from "./CommandStrip";
import type { FocusCommand } from "./focusCommands";
import "./buttonStandard.css";
import "./WorkspaceToolbar.css";

export type WorkspaceToolbarProps = { workspaces: readonly { name: string; icon: LucideIcon }[]; activeWorkspace: string; onWorkspace: (name: string) => void; actions: readonly FocusCommand[] };
function resolveCommands(commands: readonly FocusCommand[], path: readonly string[]) {
  let items = commands, active: FocusCommand | undefined;
  for (const id of path) { active = items.find(command => command.id === id && command.children !== undefined); if (!active) break; items = active.children ?? []; }
  return { active, items };
}

/** Compact workspace navigation that expands only while it is being used. */
export default function WorkspaceToolbar({ workspaces, activeWorkspace, onWorkspace, actions }: WorkspaceToolbarProps) {
  const [open, setOpen] = useState(false), [pinned, setPinned] = useState(false), [path, setPath] = useState<string[]>([]), [error, setError] = useState("");
  const root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null), workspaceButtons = useRef<Array<HTMLButtonElement | null>>([]), commandButtons = useRef(new Map<string, HTMLButtonElement>()), pendingCommandFocus = useRef<string | null>(null);
  const panelId = useId(), section = resolveCommands(actions, path);
  const close = (restoreFocus = false) => { setPath([]); setError(""); setPinned(false); setOpen(false); if (restoreFocus) requestAnimationFrame(() => trigger.current?.focus()); };
  useEffect(() => { setPath([]); setError(""); }, [activeWorkspace]);
  useEffect(() => {
    const requested = pendingCommandFocus.current;
    if (!open || requested === null) return;
    pendingCommandFocus.current = null;
    requestAnimationFrame(() => (requested ? commandButtons.current.get(requested) : root.current?.querySelector<HTMLButtonElement>(".workspace-toolbar-command:not(.workspace-toolbar-back):not(:disabled)"))?.focus());
  }, [open, path]);
  useEffect(() => {
    if (!pinned) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) close(); };
    const escape = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") close(true); };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [pinned]);
  const focusWorkspace = (index: number) => { if (workspaces.length) workspaceButtons.current[(index + workspaces.length) % workspaces.length]?.focus(); };
  const navigateWorkspaces = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "Escape"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Escape") { close(true); return; }
    focusWorkspace(event.key === "Home" ? 0 : event.key === "End" ? workspaces.length - 1 : index + (event.key === "ArrowLeft" ? -2 : event.key === "ArrowRight" ? 2 : event.key === "ArrowUp" ? -1 : 1));
  };
  const enter = async (command: FocusCommand) => {
    if (command.disabled || !command.children) return;
    try { await command.onEnter?.(); setError(""); pendingCommandFocus.current = ""; setPath(value => [...value, command.id]); }
    catch (cause) { setError(`Could not open ${command.label}: ${cause instanceof Error ? cause.message : String(cause)}`); }
  };
  const run = async (command: FocusCommand) => {
    if (command.disabled || !command.run) return;
    try { await command.run(); setError(""); }
    catch (cause) { setError(`Could not run ${command.label}: ${cause instanceof Error ? cause.message : String(cause)}`); }
  };
  const leaveSection = () => { const parentId = path[path.length - 1]; pendingCommandFocus.current = parentId ?? null; parentId ? setPath(value => value.slice(0, -1)) : close(true); };
  const commandKey = (event: KeyboardEvent<HTMLButtonElement>, command: FocusCommand) => {
    if (event.key === "Escape" || event.key === "ArrowLeft" && path.length) { event.preventDefault(); leaveSection(); return; }
    if (event.key === "ArrowRight" && command.children) { event.preventDefault(); void enter(command); return; }
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); const buttons = [...(root.current?.querySelectorAll<HTMLButtonElement>(".workspace-toolbar-command:not(:disabled)") ?? [])], at = buttons.indexOf(event.currentTarget);
    const target = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : at + (event.key === "ArrowLeft" ? -2 : event.key === "ArrowRight" ? 2 : event.key === "ArrowUp" ? -1 : 1); buttons[(target + buttons.length) % buttons.length]?.focus();
  };
  const openFromKeyboard = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!["ArrowRight", "ArrowDown"].includes(event.key)) return;
    event.preventDefault(); setOpen(true); setPinned(true); requestAnimationFrame(() => focusWorkspace(Math.max(0, workspaces.findIndex(item => item.name === activeWorkspace))));
  };
  return <div ref={root} className="workspace-toolbar" data-open={open || undefined} data-pinned={pinned || undefined} onMouseEnter={() => setOpen(true)} onMouseLeave={() => { if (!pinned) setOpen(false); }}>
    <button ref={trigger} type="button" className="spike-control--icon workspace-toolbar-trigger" title="Switch workspace" aria-label="Switch workspace" aria-haspopup="true" aria-expanded={open} aria-controls={open ? panelId : undefined} aria-pressed={pinned} onKeyDown={openFromKeyboard} onClick={() => { if (pinned) close(true); else { setOpen(true); setPinned(true); } }}><Grid3X3 size={15}/></button>
    {open && <div id={panelId} className="workspace-toolbar-flyout" role="group" aria-label="Workspace switcher"><div className="workspace-toolbar-row">
      <CommandStrip className="workspace-toolbar-workspaces" label="Workspaces">{workspaces.map((workspace, index) => <button type="button" key={workspace.name} ref={element => { workspaceButtons.current[index] = element; }} className="spike-control--compact workspace-toolbar-workspace" title={`${workspace.name} workspace`} aria-label={`${workspace.name} workspace`} aria-pressed={activeWorkspace === workspace.name} tabIndex={activeWorkspace === workspace.name || (!workspaces.some(item => item.name === activeWorkspace) && index === 0) ? 0 : -1} onKeyDown={event => navigateWorkspaces(event, index)} onClick={() => onWorkspace(workspace.name)}><workspace.icon size={15}/><span>{workspace.name}</span></button>)}</CommandStrip>
      {section.items.length > 0 && <><span className="workspace-toolbar-divider" aria-hidden="true"/><CommandStrip className="workspace-toolbar-actions" label={`${activeWorkspace} workspace actions`}>
        {path.length > 0 && <button type="button" className="spike-control--icon workspace-toolbar-command workspace-toolbar-back" title="Back to previous actions" aria-label="Back to previous actions" onKeyDown={event => commandKey(event, { id: "__back", label: "Back" })} onClick={leaveSection}><ArrowLeft size={14}/></button>}
        {section.items.map(command => { const Icon = command.icon, group = Boolean(command.children); return command.content ? null : <button ref={element => { if (element) commandButtons.current.set(command.id, element); else commandButtons.current.delete(command.id); }} type="button" key={command.id} className="spike-control--compact workspace-toolbar-command" title={command.disabled ? `${command.description ?? command.label} is unavailable` : command.description ?? command.label} aria-label={command.label} aria-pressed={command.checked} aria-haspopup={group ? "menu" : undefined} disabled={command.disabled} onKeyDown={event => commandKey(event, command)} onClick={() => group ? void enter(command) : void run(command)}><span aria-hidden="true">{Icon ? <Icon size={14}/> : command.iconNode ?? <MousePointer2 size={14}/>}</span><span>{command.label}</span>{group && <ChevronRight size={13} aria-hidden="true"/>}</button>; })}
      </CommandStrip></>}
    </div>{section.active?.content && <div className="workspace-toolbar-content" aria-label={section.active.label}>{section.active.content}</div>}{section.items.filter(command => command.content).map(command => <div key={command.id} className="workspace-toolbar-content" aria-label={command.label}>{command.content}</div>)}{error && <p className="workspace-toolbar-error" role="alert">{error}</p>}</div>}
  </div>;
}
