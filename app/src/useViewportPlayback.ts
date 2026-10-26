// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { createPlaybackTimeline } from "./transientPlayback";
import { reviewPlaybackSpeed } from "./viewportPlaybackModel";

export type ViewportPlaybackSource = {
  id: string; label: string; revision: unknown; times: readonly number[];
  flow?: boolean; onActivate: () => void; onFrame: (index: number) => void;
  onFlow?: (playing: boolean) => void;
};
export function useViewportPlayback(sources: ViewportPlaybackSource[], scope: string) {
  const [selected, setSelected] = useState(""), [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false), [rate, setRate] = useState(1), [loop, setLoop] = useState(false);
  const current = sources.find(source => source.id === selected) ?? null;
  const latest = useRef(current); latest.current = current;
  const previous = useRef(new Map<string, unknown>()), previousScope = useRef(scope);
  const activate = (source: ViewportPlaybackSource) => {
    latest.current?.onFlow?.(false); setPlaying(false); setSelected(source.id); setFrame(0); setRate(1);
    latest.current = source;
    source.onActivate(); source.onFrame(0);
  };
  useEffect(() => {
    const changed = sources.filter(source => !previous.current.has(source.id) || previous.current.get(source.id) !== source.revision);
    previous.current = new Map(sources.map(source => [source.id, source.revision]));
    const scopeChanged = previousScope.current !== scope;
    if (scopeChanged) { previousScope.current = scope; setPlaying(false); setSelected(""); setFrame(0); }
    const next = changed[changed.length - 1] ?? (scopeChanged || !current ? sources[sources.length - 1] : undefined);
    if (next) activate(next);
    else if (!current) { setPlaying(false); setSelected(""); }
  }, [sources, scope]);
  const times = current?.times;
  const timeline = useMemo(() => { try { return times ? createPlaybackTimeline(times) : null; } catch { return null; } }, [times]);
  const speed = times ? reviewPlaybackSpeed(times) * rate : 1;
  useEffect(() => {
    current?.onFlow?.(playing && Boolean(current.flow));
    if (!playing || !timeline) return () => current?.onFlow?.(false);
    let started = performance.now(), first = frame, request = 0;
    const tick = (now: number) => {
      const state = timeline.frameAtElapsed(first, now - started, speed);
      setFrame(state.frameIndex); latest.current?.onFrame(state.frameIndex);
      if (state.ended && !loop) { setPlaying(false); latest.current?.onFlow?.(false); return; }
      if (state.ended) { started = now; first = 0; setFrame(0); latest.current?.onFrame(0); }
      request = requestAnimationFrame(tick);
    };
    request = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(request); current?.onFlow?.(false); };
  }, [playing, timeline, speed, loop, selected]);
  useEffect(() => () => latest.current?.onFlow?.(false), []);
  const target = (id?: string) => id ? sources.find(source => source.id === id) ?? null : latest.current;
  const seek = (index: number, id?: string) => { const source = target(id); if (!source) return; if (source.id !== selected) activate(source); setPlaying(false); source.onFlow?.(false); const next = Math.max(0, Math.min(source.times.length - 1, Math.trunc(index))); setFrame(next); source.onFrame(next); };
  const changePlaying = (value: boolean, id?: string) => {
    const source = target(id);
    if (!source || (source.times.length < 2 && !source.flow)) return;
    if (source.id !== selected) activate(source);
    if (value) { source.onActivate(); if (source.id !== selected || frame >= source.times.length - 1) { setFrame(0); source.onFrame(0); } }
    else source.onFlow?.(false);
    setPlaying(value);
  };
  const toggle = (id?: string) => changePlaying(id && id !== selected ? true : !playing, id);
  return { sources, current, selected, frame, playing, rate, loop, speed, timeline, select: (id: string) => { const source = sources.find(item => item.id === id); if (source) activate(source); }, seek, toggle, changePlaying, setRate, setLoop };
}
