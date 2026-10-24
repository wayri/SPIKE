import { CloseControlIcon } from "./navigationIcons";
import { FloatingPanelControls, useFloatingPanel } from "./FloatingPanel";
import { usePanelHeaderMenu } from "./PanelHeaderMenu";
import { usePanelPresentation } from "./panelPresentation";
import { ArrowLeft, ArrowRight, ArrowUp, ChevronRight, Home, MousePointer2, SlidersHorizontal, Search } from "./icons";
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

export type MenuRouteHistory = { entries: readonly (readonly string[])[]; index: number };
export const MENU_ROUTE_HISTORY_LIMIT = 40;

export function normalizeMenuRoute(commands: readonly FocusCommand[], route: readonly string[]): string[] {
  const resolved: string[] = [];
  let items = commands;
  for (const id of route) {
    const command = items.find(item => item.id === id && !item.disabled && item.children !== undefined);
    if (!command) break;
    resolved.push(id);
    items = command.children ?? [];
  }
  return resolved;
}

function sameMenuRoute(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((id, index) => id === right[index]);
}

export function recordMenuRoute(history: MenuRouteHistory, route: readonly string[], limit = MENU_ROUTE_HISTORY_LIMIT): MenuRouteHistory {
  if (sameMenuRoute(history.entries[history.index] ?? [], route)) return history;
  const branched = [...history.entries.slice(0, history.index + 1), [...route]];
  const entries = branched.slice(-Math.max(1, Math.floor(limit)));
  return { entries, index: entries.length - 1 };
}

export function findMenuRouteTarget(history: MenuRouteHistory, commands: readonly FocusCommand[], direction: -1 | 1, current: readonly string[]) {
  for (let index = history.index + direction; index >= 0 && index < history.entries.length; index += direction) {
    const route = normalizeMenuRoute(commands, history.entries[index]);
    if (sameMenuRoute(route, current)) continue;
    return { history: { entries: history.entries, index }, route };
  }
  return null;
}

function menuCommandSignature(commands: readonly FocusCommand[]): string {
  return commands.map(command => `${command.id}:${command.disabled ? 0 : 1}[${menuCommandSignature(command.children ?? [])}]`).join("|");
}

export default function FocusCommandPanel({ commands, initialSection = null, active = true, onClose, onError }: FocusCommandPanelProps) {
  const floating = useFloatingPanel();
  const ownerDocument = usePanelPresentation().ownerDocument ?? document;
  const panel = useRef<HTMLElement>(null), search = useRef<HTMLInputElement>(null), closeHandler = useRef(onClose);
  closeHandler.current = onClose;
  const lastFocus = useRef<HTMLElement | null>(null);
  const identity = useId();
  const initialPath = initialSection ? commandPath(commands, initialSection) : [];
  const [path, setPath] = useState<string[]>(initialPath);
  const [routeHistory, setRouteHistory] = useState<MenuRouteHistory>({ entries: [initialPath], index: 0 });
  const [query, setQuery] = useState(""), [error, setError] = useState("");
  const [allActions, setAllActions] = useState(false);
  const section = resolveSection(commands, path), term = query.trim();
  const menuLocation = ["Menu", ...path.map((_, index) => resolveSection(commands, path.slice(0, index + 1)).active?.label).filter(Boolean)].join(" / ");
  const commandSignature = menuCommandSignature(commands);
  const matches = useMemo(() => active && (term || allActions) ? searchFocusCommands(commands, term) : [], [active, commands, term, allActions]);
  const restoreToggle = () => document.getElementById("focus-menu-toggle")?.focus();
  const close = () => { if(floating?.detached)floating.dock(); restoreToggle(); closeHandler.current(); };
  const headerMenu=usePanelHeaderMenu("Menu",[
    ...(floating?[{label:floating.detached?"Dock back":"Move to floating window",description:floating.detached?"Return to the workspace":"Detach into a movable native window",run:()=>floating.detached?floating.dock():floating.detach()}]:[]),
    {label:"Close",run:close},
  ]);
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
    try { await command.onEnter?.(); setError(""); visit([...path, command.id]); }
    catch (cause) { fail(command.label, cause); }
  };
  const run = async (command: FocusCommand) => {
    if (command.disabled || !command.run) return;
    try { await command.run(); setError(""); close(); }
    catch (cause) { fail(command.label, cause); }
  };
  const visit = (route: readonly string[]) => {
    const next = normalizeMenuRoute(commands, route);
    setPath(next);
    setRouteHistory(current => recordMenuRoute(current, next));
  };
  const up = () => { setQuery(""); setError(""); visit(path.slice(0, -1)); };
  const home = () => { setQuery(""); setError(""); visit([]); };
  const historyTarget = (direction: -1 | 1) => findMenuRouteTarget(routeHistory, commands, direction, path);
  const moveHistory = (direction: -1 | 1) => {
    const target = historyTarget(direction); if (!target) return;
    setRouteHistory(target.history); setPath(target.route); setQuery(""); setError("");
  };

  useEffect(() => {
    const element = panel.current;
    return () => { if (element?.contains(ownerDocument.activeElement)) restoreToggle(); };
  }, [ownerDocument]);
  useEffect(() => {
    const next = initialSection ? commandPath(commands, initialSection) : [];
    setPath(next); setRouteHistory({ entries: [next], index: 0 });
    setQuery("");
  }, [initialSection]);
  useEffect(() => {
    const next = normalizeMenuRoute(commands, path);
    if (!sameMenuRoute(next, path)) { setPath(next); setRouteHistory(current => recordMenuRoute(current, next)); }
  }, [commandSignature]);
  useLayoutEffect(() => {
    if(active) { if(lastFocus.current?.isConnected) lastFocus.current.focus({preventScroll:true}); else focusAt(0); }
  }, [active]);
  useLayoutEffect(() => {
    if (!term) focusAt(0);
  }, [path.join("/"), term]);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.nativeEvent.isComposing || event.isDefaultPrevented()) return;
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); path.length && !term ? up() : close(); return; }
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
    } else if (event.key === "ArrowLeft" && path.length && !term) { event.preventDefault(); up(); }
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
      setError(""); setQuery(""); visit(match.ancestors.map(ancestor => ancestor.id));
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
    <header className="focus-command-header" {...headerMenu.headerProps} onPointerDown={floating?.onHeaderPointerDown} title="Drag this header outside the main window to detach">
      <button type="button" className="spike-control--icon" disabled={!historyTarget(-1)} onClick={()=>moveHistory(-1)} aria-label="Go back to previous menu section" title="Back"><ArrowLeft size={14}/></button>
      <button type="button" className="spike-control--icon" disabled={!historyTarget(1)} onClick={()=>moveHistory(1)} aria-label="Go forward to next menu section" title="Forward"><ArrowRight size={14}/></button>
      <button type="button" className="spike-control--icon" disabled={!path.length} onClick={up} aria-label="Go up to parent menu section" title="Up"><ArrowUp size={14}/></button>
      <button type="button" className="spike-control--icon" disabled={!path.length} onClick={home} aria-label="Go home to Menu" title="Home"><Home size={14}/></button>
      <strong id={`${identity}-title`} title={menuLocation}>{menuLocation}</strong>
      <FloatingPanelControls/><button type="button" className="spike-control--icon" title="Close menu; reopen with Menu or View" aria-label="Close Menu" onClick={close}><CloseControlIcon size={14}/></button>
    </header>
    {headerMenu.menu}
    <label>
      <span className="sr-only">Search all commands</span>
      <input ref={search} type="search" aria-label="Search all commands" placeholder="Search commands…" value={query} onChange={event => setQuery(event.target.value)} />
    </label>
    <button type="button" className="focus-command-back" aria-pressed={allActions} onClick={() => setAllActions(value=>!value)}><Search size={14}/>{allActions ? "Browse sections" : "All actions"}</button>
    {error && <p role="alert">{error}</p>}
    <div className="focus-command-content" role="menu" aria-label={term || allActions ? "Command search results" : section.active?.label ?? "Menu"}>
      {term || allActions ? matches.map(match => row(match.command, match)) : section.items.map(command => row(command))}
      {(term || allActions ? matches.length === 0 : section.items.length === 0) && <p>{term ? "No matching commands." : "No commands in this section."}</p>}
    </div>
  </section>;
}
