// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useSyncExternalStore } from "react";
import type { GuidedSimulationContext, GuidedSimulationRequirement, GuidedSimulationCheck, GuidedSimulationTutorStep } from "./guidedSimulationModel";
export type SimulationRunAdapter = {
  id: string; context: GuidedSimulationContext;
  check: (context: GuidedSimulationContext, signal: AbortSignal) => Promise<GuidedSimulationCheck>;
  fix: (requirement: GuidedSimulationRequirement) => void;
  run: (context: GuidedSimulationContext, signal: AbortSignal) => Promise<void>;
  tutorSteps?: GuidedSimulationTutorStep[];
};
const adapters = new Map<string, { owner: symbol; read: () => SimulationRunAdapter }>();
const listeners = new Set<() => void>(); let version = 0;
function notify() { version++; listeners.forEach(listener => listener()); }
export const GUIDED_SIMULATION_EVENT = "spike-guided-simulation-request";
export function requestGuidedSimulation(id: string, intent: "run" | "tutor" = "run") {
  window.dispatchEvent(new CustomEvent(GUIDED_SIMULATION_EVENT, { detail: { id, intent } }));
}
/** Editors retain drafts and supply the latest check/run closures rather than saved copies. */
export function useGuidedRunAdapter(adapter: SimulationRunAdapter) {
  const live = useRef(adapter); live.current = adapter;
  const owner = useRef(Symbol("simulation-adapter"));
  useEffect(() => { const entry = { owner: owner.current, read: () => live.current }; adapters.set(adapter.id, entry); notify();
    return () => { if (adapters.get(adapter.id) === entry) { adapters.delete(adapter.id); notify(); } };
  }, [adapter.id]);
  useEffect(() => { notify(); }, [adapter.context.key, adapter.context.revision]);
  return () => requestGuidedSimulation(adapter.id);
}
export function useGuidedRunAdapters(): SimulationRunAdapter[] {
  useSyncExternalStore(listener => { listeners.add(listener); return () => listeners.delete(listener); }, () => version);
  return [...adapters.values()].map(entry => entry.read());
}
