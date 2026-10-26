// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { ChevronRight, ChevronDown, Eye, EyeOff, Layers3, Settings2, RotateCcw, Square, SquareDashed, Blend } from "./icons";
import type { ZoneDisplayMode } from "./zoneDisplay";
import { layerCssColor } from "./layerPalette";
import "./ViewportLayerSelector.css";

export type ViewportLayerScope = {
  id: string;
  name: string;
  layers: readonly string[];
  visibility: Record<string, boolean>;
  opacity?: Record<string, number>;
};

export function wheelLayerOpacity(value: number, deltaY: number): number {
  const current = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 1;
  return !Number.isFinite(deltaY) || deltaY === 0 ? current : Math.max(0, Math.min(1, Math.round(current * 100 + (deltaY < 0 ? 5 : -5)) / 100));
}

/** Selection must identify one occurrence, even when several occurrences share a design. */
export default function ViewportLayerSelector({ board, selectedBoardIds, disabled = false, showNetNames = false, onShowNetNames, onToggle, onShowAll, onOpacity, onAllOpacity, zoneDisplay = "filled", onZoneDisplay, onResetView, onManage }: {
  board: ViewportLayerScope | null;
  selectedBoardIds: readonly string[];
  disabled?: boolean;
  showNetNames?: boolean;
  onShowNetNames?: (boardId: string, visible: boolean) => void;
  onToggle: (boardId: string, layer: string) => void;
  onShowAll: (boardId: string) => void;
  onOpacity?: (boardId: string, layer: string, value: number) => void;
  onAllOpacity?: (boardId: string, value: number) => void;
  zoneDisplay?: ZoneDisplayMode;
  onZoneDisplay?: (boardId: string, mode: ZoneDisplayMode) => void;
  onResetView?: (boardId: string) => void;
  onManage: () => void;
}) {
  const manager = useRef<HTMLButtonElement>(null), choices = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const [feedback, setFeedback] = useState<Record<string, number>>({});
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const gesture = useRef<{ boardId: string | null; values: Record<string, number>; all: number | null }>({ boardId: null, values: {}, all: null });
  const live = useRef({ board, selectedBoardIds, disabled, onOpacity, onAllOpacity });
  live.current = { board, selectedBoardIds, disabled, onOpacity, onAllOpacity };
  const scopeId = board && selectedBoardIds.length === 1 && selectedBoardIds[0] === board.id && board.layers.length ? board.id : null;
  const choicesId = useId();
  useEffect(() => setExpanded(false), [board?.id]);
  useEffect(() => {
    gesture.current = { boardId: scopeId, values: {}, all: null };
    setFeedback({});
    return () => { for (const timer of timers.current.values()) clearTimeout(timer); timers.current.clear(); };
  }, [scopeId]);
  useEffect(() => {
    const element = root.current; if (!element) return;
    const wheel = (event: WheelEvent) => {
      const button = (event.target as Element | null)?.closest<HTMLButtonElement>("button[data-layer-opacity]");
      if (!button || !element.contains(button) || event.ctrlKey || event.metaKey || !Number.isFinite(event.deltaY) || event.deltaY === 0) return;
      const current = live.current, target = current.board;
      if (!target || current.disabled || button.disabled || current.selectedBoardIds.length !== 1 || current.selectedBoardIds[0] !== target.id || gesture.current.boardId !== target.id) return;
      const all = button.dataset.layerOpacity === "all", layer = button.dataset.layerName ?? "", key = all ? "all" : `layer:${layer}`;
      if (all ? !current.onAllOpacity : !current.onOpacity || !target.layers.includes(layer)) return;
      event.preventDefault(); event.stopPropagation();
      const stored = gesture.current;
      const opacities = target.layers.map(name => target.opacity?.[name] ?? 1);
      const initialAll = opacities.every(value => value === opacities[0]) ? opacities[0] : 1;
      const value = wheelLayerOpacity(all ? stored.all ?? initialAll : stored.values[layer] ?? target.opacity?.[layer] ?? 1, event.deltaY);
      if (all) {
        stored.all = value;
        stored.values = Object.fromEntries(target.layers.map(name => [name, value]));
        current.onAllOpacity?.(target.id, value);
      } else { stored.values[layer] = value; current.onOpacity?.(target.id, layer, value); }
      setFeedback(previous => ({ ...(all ? Object.fromEntries(Object.keys(previous).map(name => [name, Math.round(value * 100)])) : previous), [key]: Math.round(value * 100) }));
      clearTimeout(timers.current.get(key));
      const boardId = target.id;
      timers.current.set(key, setTimeout(() => {
        timers.current.delete(key);
        if (gesture.current.boardId !== boardId) return;
        // Read authoritative opacity again on the next gesture; All retains its master value.
        if (all) gesture.current.values = {}; else delete gesture.current.values[layer];
        setFeedback(previous => { const next = { ...previous }; delete next[key]; return next; });
      }, 1000));
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [scopeId]);
  const collapse = () => { manager.current?.focus(); setExpanded(false); };
  if (!board || selectedBoardIds.length !== 1 || selectedBoardIds[0] !== board.id || !board.layers.length) return null;
  const navigate = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); collapse(); return; }
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const buttons = [...(choices.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled):not(.command-strip-arrow)") ?? [])], at = buttons.indexOf(event.currentTarget);
    const target = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : at + (event.key === "ArrowLeft" ? -1 : 1);
    buttons[(target + buttons.length) % buttons.length]?.focus();
  };
  const label = (name: string, key: string) => <span className="viewport-layer-label"><span className="viewport-layer-name" data-adjusting={feedback[key] !== undefined || undefined}>{name}</span>{feedback[key] !== undefined && <span className="viewport-layer-percent" aria-hidden="true">{feedback[key]}</span>}</span>;
  return <div ref={root} className="viewport-layer-selector" role="group" aria-label={`Layers: ${board.name}`} data-board-id={board.id} data-expanded={expanded || undefined}
    onMouseEnter={() => setExpanded(true)} onMouseLeave={() => setExpanded(false)}
    onFocus={() => setExpanded(true)} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setExpanded(false); }}
    onPointerDown={event => event.stopPropagation()} onWheel={event => event.stopPropagation()}>
    <button ref={manager} type="button" className="spike-control--icon viewport-layer-pull" aria-label={`Show layers for ${board.name}`} title={`Layers · ${board.name}`} disabled={disabled}
      aria-expanded={expanded} aria-controls={expanded ? choicesId : undefined} onClick={() => setExpanded(true)}
      onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); collapse(); } else if (["ArrowRight", "ArrowDown"].includes(event.key)) { event.preventDefault(); setExpanded(true); requestAnimationFrame(() => choices.current?.querySelector<HTMLButtonElement>(".viewport-layer-choice")?.focus()); } }}>
      {expanded ? <Layers3 size={15}/> : <ChevronRight size={12}/>}</button>
    {expanded && <div id={choicesId} ref={choices} className="viewport-layer-choices" role="group" aria-label={`Layer visibility for ${board.name}`}>
      <div className="viewport-layer-caption" title={board.name}><b>{board.name}</b><small>{board.layers.length} layers</small>
        {onZoneDisplay && <button type="button" className="spike-control--icon viewport-layer-zone-mode" disabled={disabled} aria-label={`Copper zones: ${zoneDisplay}`} title={`Copper zones: ${zoneDisplay} · Click for ${zoneDisplay === "filled" ? "transparent" : zoneDisplay === "transparent" ? "outline" : "filled"}`} onClick={() => onZoneDisplay(board.id, zoneDisplay === "filled" ? "transparent" : zoneDisplay === "transparent" ? "outline" : "filled")}>
          {zoneDisplay === "outline" ? <SquareDashed size={14}/> : zoneDisplay === "transparent" ? <Blend size={14}/> : <Square size={14}/>}</button>}
        {onResetView && <button type="button" className="spike-control--icon" disabled={disabled} aria-label={`Reset view for ${board.name}`} title="Reset camera, layer visibility, layer opacity and zone display to defaults" onClick={() => { for (const timer of timers.current.values()) clearTimeout(timer); timers.current.clear(); gesture.current.values = {}; gesture.current.all = null; setFeedback({}); onResetView(board.id); }}><RotateCcw size={14}/></button>}
      </div>
      <div className="viewport-layer-grid" role="group" aria-label="Board layers">
      <button type="button" className="spike-control--compact viewport-layer-choice" disabled={disabled} aria-label={`All layers on ${board.name}`} data-layer-opacity="all" title={`Show all layers on ${board.name}`} aria-description="Scroll up to increase all layer opacities; down to decrease. Applies the All opacity to every layer." onKeyDown={navigate} onClick={() => onShowAll(board.id)}>{label("All", "all")}</button>
      {board.layers.map(layer => <button type="button" className="spike-control--compact viewport-layer-choice" key={layer} disabled={disabled}
        aria-label={`${layer} on ${board.name}`} aria-pressed={board.visibility[layer] !== false}
        data-layer-opacity="layer" data-layer-name={layer}
        title={`${board.visibility[layer] === false ? "Show" : "Hide"} ${layer} · ${board.name} · ${Math.round((board.opacity?.[layer] ?? 1) * 100)}% opacity · Scroll to adjust`}
        onKeyDown={navigate} onClick={() => onToggle(board.id, layer)}><i aria-hidden="true" style={{ background: layerCssColor(layer) }}/>{label(layer, `layer:${layer}`)}</button>)}
      <button type="button" className="spike-control--icon viewport-layer-choice" disabled={disabled} aria-label={`Manage layers for ${board.name}`} title="Layer settings and opacity" onKeyDown={navigate} onClick={onManage}><Settings2 size={15}/></button>
    </div>
      {onShowNetNames && <details className="viewport-layer-net-names" key={board.id}>
        <summary><ChevronDown size={12}/><Eye size={14}/><span>Net names</span><small>{showNetNames ? "Shown" : "Hidden"}</small></summary>
        <button type="button" className="spike-control--compact" disabled={disabled} aria-pressed={showNetNames}
          aria-label={`Net names on ${board.name}`} title={`${showNetNames ? "Hide" : "Show"} net names · ${board.name}`}
          onKeyDown={navigate} onClick={() => onShowNetNames(board.id, !showNetNames)}>
          {showNetNames ? <Eye size={14}/> : <EyeOff size={14}/>}{showNetNames ? "Hide net names" : "Show net names"}
        </button>
      </details>}
    </div>}
  </div>;
}
