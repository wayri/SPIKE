import { CloseControlIcon } from "./navigationIcons";
import { FloatingPanelControls, useFloatingPanel } from "./FloatingPanel";
import { usePanelPresentation } from "./panelPresentation";
import { ArrowLeft, ChevronRight, MousePointer2, SlidersHorizontal, Search } from "./icons";
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { searchFocusCommands, type FocusCommand, type FocusCommandMatch } from "./focusCommands";

export type FocusCommandPanelProps = {
  commands: readonly FocusCommand[];
  initialSection?: string | null;
  active?: boolean;
  onClose: () => void;
  onError?: (message: string) => void;
};

function commandPath(commands: readonly FocusCommand[], target: string): string[] {
  for (const command of commands) {
    if (command.id === target || command.label === target) return command.children?.length ? [command.id] : [];
    const child = command.children?.length ? commandPath(command.children, target) : [];
    if (child.length) return [command.id, ...child];
  }
  return [];
}

function resolveSection(commands: readonly FocusCommand[], ids: readonly string[]) {
  let items = commands, active: FocusCommand | undefined;
  for (const id of ids) {
    active = items.find(command => command.id === id && command.children !== undefined);
    if (!active) break;
    items = active.children ?? [];
  }
  return { active, items };
}

export default function FocusCommandPanel({ commands, initialSection = null, active = true, onClose, onError }: FocusCommandPanelProps) {
  const floating = useFloatingPanel();
  const ownerDocument = usePanelPresentation().ownerDocument ?? document;
  const panel = useRef<HTMLElement>(null), search = useRef<HTMLInputElement>(null), closeHandler = useRef(onClose);
  closeHandler.current = onClose;
  const lastFocus = useRef<HTMLElement | null>(null);
  const identity = useId();
  const [path, setPath] = useState<string[]>(() => initialSection ? commandPath(commands, initialSection) : []);
  const [query, setQuery] = useState(""), [error, setError] = useState("");
  const [allActions, setAllActions] = useState(false);
  const section = resolveSection(commands, path), term = query.trim();
  const matches = useMemo(() => searchFocusCommands(commands, term), [commands, term]);
  const restoreToggle = () => document.getElementById("focus-menu-toggle")?.focus();
  const close = () => { if(floating?.detached)floating.dock(); restoreToggle(); closeHandler.current(); };
  const rows = () => Array.from(panel.current?.querySelectorAll<HTMLElement>(
    "button.focus-command-row:not(:disabled), .focus-command-content input:not(:disabled), .focus-command-content select:not(:disabled), .focus-command-content textarea:not(:disabled), .focus-command-content button:not(:disabled)"
  ) ?? []);
  const focusAt = (index: number) => {
    const entries = rows(); if (!entries.length) return;
    const target = ((index % entries.length) + entries.length) % entries.length;
    entries[target].focus(); entries[target].scrollIntoView?.({ block: "nearest" });
  };
  const fail = (label: string, cause: unknown) => {
    const detail = cause instanceof Error ? cause.message : String(cause);
    const message = `Could not open ${label}: ${detail}. Retry from the Menu.`;
    setError(message); onError?.(message);
  };
  const enter = async (command: FocusCommand) => {
    if (command.disabled || !command.children) return;
    try { await command.onEnter?.(); setError(""); setPath(value => [...value, command.id]); }
    catch (cause) { fail(command.label, cause); }
  };
  const run = async (command: FocusCommand) => {
    if (command.disabled || !command.run) return;
    try { await command.run(); setError(""); close(); }
    catch (cause) { fail(command.label, cause); }
  };
  const back = () => setPath(value => value.slice(0, -1));

  useEffect(() => {
    const element = panel.current;
    return () => { if (element?.contains(ownerDocument.activeElement)) restoreToggle(); };
  }, [ownerDocument]);
  useEffect(() => {
    setPath(initialSection ? commandPath(commands, initialSection) : []);
    setQuery("");
  }, [initialSection]);
  useLayoutEffect(() => {
    if(active) { if(lastFocus.current?.isConnected) lastFocus.current.focus({preventScroll:true}); else focusAt(0); }
  }, [active]);
  useLayoutEffect(() => {
    if (!term) focusAt(0);
  }, [path.join("/"), term]);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.nativeEvent.isComposing || event.isDefaultPrevented()) return;
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); path.length && !term ? back() : close(); return; }
    const target = event.target as HTMLElement;
    if (target === search.current) {
      if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); focusAt(event.key === "ArrowDown" ? 0 : -1); }
      return;
    }
    if (["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) return;
    const entries = rows(), at = entries.indexOf(target);
    if (at >= 0 && ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      focusAt(event.key === "Home" ? 0 : event.key === "End" ? -1 : at + (event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "ArrowLeft" && path.length && !term) { event.preventDefault(); back(); }
    else if (event.key === "ArrowRight" && target.dataset.commandGroup) {
      const command = section.items.find(item => item.id === target.dataset.commandGroup);
      if (command) { event.preventDefault(); void enter(command); }
    } else if (event.key.length === 1 && event.key !== " " && !event.ctrlKey && !event.metaKey && !event.altKey) {
      search.current?.focus(); setQuery(value => value + event.key); event.preventDefault();
    }
  };

  const routeSearchMatch = async (match: FocusCommandMatch) => {
    try {
      for (const ancestor of match.ancestors) await ancestor.onEnter?.();
      setError(""); setQuery(""); setPath(match.ancestors.map(ancestor => ancestor.id));
    } catch (cause) { fail(match.path[match.path.length - 2] ?? match.command.label, cause); }
  };
  const row = (command: FocusCommand, match?: FocusCommandMatch) => {
    const Icon = command.icon;
    const icon = <span className="focus-command-icon" aria-hidden="true">{Icon ? <Icon size={16} /> : command.iconNode ?? <MousePointer2 size={16} />}</span>;
    const needsFreshSection = Boolean(match?.ancestors.some(ancestor => ancestor.onEnter));
    if (match && needsFreshSection) return <button key={command.id} type="button" role="menuitem" className="focus-command-row" disabled={command.disabled}
      title={`Open ${match.path.slice(0, -1).join(" / ")}`} onClick={() => void routeSearchMatch(match)}>
      {icon}<span className="focus-command-label">{command.label}</span>
      <small>{match.path.slice(0, -1).join(" / ")}</small><ChevronRight className="focus-command-submenu" size={16} aria-hidden="true" />
    </button>;
    if (command.content) return <div key={command.id} role="none" className="focus-command-row focus-command-content">
      <span className="focus-command-control-label"><SlidersHorizontal size={14} aria-hidden="true" />{command.label}</span>
      <div className="focus-command-control">{command.content}</div>{match && <small>{match.path.slice(0, -1).join(" / ")}</small>}
    </div>;
    const group = Boolean(command.children);
    return <button key={command.id} type="button" className="focus-command-row" disabled={command.disabled}
      role={group ? "menuitem" : command.checked === undefined ? "menuitem" : command.radio ? "menuitemradio" : "menuitemcheckbox"}
      aria-checked={!group && command.checked !== undefined ? command.checked : undefined}
      data-command-group={group ? command.id : undefined} aria-haspopup={group ? "menu" : undefined}
      title={command.disabled ? `${command.description ?? command.label} is unavailable` : command.description ?? command.label}
      onClick={() => group ? void enter(command) : void run(command)}>
      {icon}<span className="focus-command-label">{command.label}</span>
      {match && <small>{match.path.slice(0, -1).join(" / ")}</small>}
      {command.shortcut && <kbd className="focus-command-shortcut">{command.shortcut}</kbd>}
      {command.checked !== undefined && <span aria-hidden="true">{command.checked ? "✓" : ""}</span>}
      {group && <ChevronRight className="focus-command-submenu" size={16} aria-hidden="true" />}
    </button>;
  };

  return <section id="focus-command-panel" ref={panel} className="focus-command-panel" role="dialog" aria-labelledby={`${identity}-title`} onKeyDown={onKeyDown} onFocusCapture={event=>{lastFocus.current=event.target as HTMLElement;}}>
    <header className="focus-command-header" onPointerDown={floating?.onHeaderPointerDown} title="Drag this header outside the main window to detach">
      <strong id={`${identity}-title`}>Menu{section.active ? ` / ${section.active.label}` : ""}</strong>
      <FloatingPanelControls/><button type="button" className="spike-control--icon" title="Close menu; reopen with Menu or View" aria-label="Close Menu" onClick={close}><CloseControlIcon size={14}/></button>
    </header>
    <label>
      <span className="sr-only">Search all commands</span>
      <input ref={search} type="search" aria-label="Search all commands" placeholder="Search commands…" value={query} onChange={event => setQuery(event.target.value)} />
    </label>
    <button type="button" className="focus-command-back" aria-pressed={allActions} onClick={() => setAllActions(value=>!value)}><Search size={14}/>{allActions ? "Browse sections" : "All actions"}</button>
    {path.length > 0 && !term && <button type="button" className="focus-command-back" onClick={back}><ArrowLeft size={15} aria-hidden="true" /> Back</button>}
    {error && <p role="alert">{error}</p>}
    <div className="focus-command-content" role="menu" aria-label={term || allActions ? "Command search results" : section.active?.label ?? "Menu"}>
      {term || allActions ? matches.map(match => row(match.command, match)) : section.items.map(command => row(command))}
      {(term || allActions ? matches.length === 0 : section.items.length === 0) && <p>{term ? "No matching commands." : "No commands in this section."}</p>}
    </div>
  </section>;
}
