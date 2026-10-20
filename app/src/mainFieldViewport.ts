// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useRef, useState } from "react";
import { admitFieldVolume, type FieldViewOptions, type FieldVolumeData } from "./fieldVolumeModel";
export type MainFieldView = { data: FieldVolumeData; options: FieldViewOptions; visible: boolean };
export const MAIN_FIELD_EVENT = "spike-main-field-view";
export function defaultFieldOptions(data: FieldVolumeData): FieldViewOptions {
  return { frame: 0, quantity: data.quantities[0].id, mode: data.frames[0].streamlines?.length ? "streamtubes" : data.cells.sizes ? "voxels" : "points", arrows: true, opacity: .7, budget: 2500, sliceAxis: "all", slicePercent: 100, celsius: true, seedAxis: "x", seedDensity: 4, streamWidth: 2 };
}
/** A local display request, never a solver run or project mutation. */
export function showFieldInMainViewport(data?: FieldVolumeData) { window.dispatchEvent(new CustomEvent(MAIN_FIELD_EVENT, { detail: data ?? null })); }
export function useMainFieldViewport(scope: string, onPresent: (newData: boolean) => void, onError: (message: string) => void) {
  const [view, setView] = useState<MainFieldView | null>(null);
  const callbacks = useRef({ onPresent, onError }); callbacks.current = { onPresent, onError };
  const present = useCallback((value?: unknown) => { try {
    if (value) { const data = admitFieldVolume(value); setView({ data, options: defaultFieldOptions(data), visible: true }); }
    callbacks.current.onPresent(Boolean(value));
  } catch (error) { callbacks.current.onError(`Field display rejected: ${error instanceof Error ? error.message : String(error)}`); } }, []);
  useEffect(() => { const receive = (event: Event) => present((event as CustomEvent).detail); window.addEventListener(MAIN_FIELD_EVENT, receive); return () => window.removeEventListener(MAIN_FIELD_EVENT, receive); }, [present]);
  useEffect(() => { setView(null); }, [scope]);
  const options = useCallback((patch: Partial<FieldViewOptions>) => setView(v => v && Object.entries(patch).some(([key, value]) => v.options[key as keyof FieldViewOptions] !== value) ? { ...v, options: { ...v.options, ...patch } } : v), []);
  const visible = useCallback((visible: boolean) => setView(v => v ? { ...v, visible } : v), []);
  const clear = useCallback(() => setView(null), []);
  return { view, present, options, visible, clear };
}
