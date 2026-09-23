import { invoke } from "@tauri-apps/api/core";
import { normalizeProcessResources } from "./resourceMonitorModel";
import type { ProcessResources } from "./resourceMonitorModel";
export { emptyProcessResources, systemMemoryPercent } from "./resourceMonitorModel";
export type { ProcessResources } from "./resourceMonitorModel";


type ChromiumPerformance = Performance & {
  memory?: {
    usedJSHeapSize: number;
    jsHeapSizeLimit: number;
  };
};

export async function sampleProcessResources(): Promise<ProcessResources> {
  if ("__TAURI_INTERNALS__" in window) {
    return normalizeProcessResources(await invoke<ProcessResources>("resource_snapshot"));
  }
  const memory = (performance as ChromiumPerformance).memory;
  return normalizeProcessResources({
    source: "browser",
    cpuPercent: null,
    capacityCpuPercent: null,
    memoryBytes: memory?.usedJSHeapSize ?? null,
    hostMemoryBytes: memory?.usedJSHeapSize ?? null,
    totalMemoryBytes: memory?.jsHeapSizeLimit ?? null,
    logicalCpus: navigator.hardwareConcurrency || null,
    processCount: null,
    workerActive: false,
  });
}
