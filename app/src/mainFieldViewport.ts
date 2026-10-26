// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useRef, useState } from "react";
import { type FieldViewOptions, type FieldVolumeData } from "./fieldVolumeModel";
import { fieldStreamAvailability } from "./fieldStreamPresentation";
import { admitFieldPresentation, type FieldComposite } from "./fieldCompositePresentation";
export type MainFieldView = { data: FieldVolumeData; options: FieldViewOptions; visible: boolean; secondary?: { data: FieldVolumeData; options: FieldViewOptions } };
export const MAIN_FIELD_EVENT = "spike-main-field-view";
export function defaultFieldOptions(data: FieldVolumeData): FieldViewOptions {
  const streams = fieldStreamAvailability(data, 0);
  const speed = data.frames[0].vectors && (streams.supplied || streams.grid) ? data.quantities.find(q => q.unit === "m/s") : undefined;
  return { frame: 0, quantity: speed?.id ?? data.quantities[0].id, mode: streams.supplied || speed ? "streamtubes" : data.cells.sizes ? "voxels" : "points", arrows: true, opacity: .7, budget: 2500, sliceAxis: "all", slicePercent: 100, celsius: true, seedAxis: "x", seedDensity: 4, streamWidth: 2, contextOpacity: .15, pointSize: 9 };
}
/** A local display request, never a solver run or project mutation. */
export function showFieldInMainViewport(data?: FieldVolumeData | FieldComposite) { window.dispatchEvent(new CustomEvent(MAIN_FIELD_EVENT, { detail: data ?? null })); }
export function useMainFieldViewport(scope: string, onPresent: (newData: boolean) => void, onError: (message: string) => void) {
  const [view, setView] = useState<MainFieldView | null>(null);
  const callbacks = useRef({ onPresent, onError }); callbacks.current = { onPresent, onError };
  const present = useCallback((value?: unknown) => { try {
    if (value) {
      const admitted = admitFieldPresentation(value);
      const composite = admitted.contract === "spike/field-composite-view/v1" ? admitted : null;
      const data = composite ? composite.primary : admitted as FieldVolumeData;
      setView({ data, options: { ...defaultFieldOptions(data), ...(composite ? { contextOpacity: .15, pointSize: 9 } : {}) }, visible: true, ...(composite ? { secondary: {
        data: composite.secondary, options: { ...defaultFieldOptions(composite.secondary),
          quantity: composite.secondary.quantities.find(q => q.unit === "K" || q.unit === "°C")!.id,
          mode: composite.secondary.cells.sizes ? "voxels" : "points", arrows: false, showSolids: false, opacity: 1, pointSize: 9 },
      } } : {}) });
    }
    callbacks.current.onPresent(Boolean(value));
  } catch (error) { callbacks.current.onError(`Field display rejected: ${error instanceof Error ? error.message : String(error)}`); } }, []);
  useEffect(() => { const receive = (event: Event) => present((event as CustomEvent).detail); window.addEventListener(MAIN_FIELD_EVENT, receive); return () => window.removeEventListener(MAIN_FIELD_EVENT, receive); }, [present]);
  useEffect(() => { setView(null); }, [scope]);
  const options = useCallback((patch: Partial<FieldViewOptions>) => setView(v => v && Object.entries(patch).some(([key, value]) => v.options[key as keyof FieldViewOptions] !== value) ? { ...v, options: { ...v.options, ...patch }, ...(v.secondary ? { secondary: { ...v.secondary, options: { ...v.secondary.options, ...(patch.frame !== undefined ? { frame: patch.frame } : {}), ...(patch.pointSize !== undefined ? { pointSize: patch.pointSize } : {}) } } } : {}) } : v), []);
  const visible = useCallback((visible: boolean) => setView(v => v ? { ...v, visible } : v), []);
  const clear = useCallback(() => setView(null), []);
  return { view, present, options, visible, clear };
}
