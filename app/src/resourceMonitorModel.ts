export type GpuResources = {
  source: string; status: string;
  systemPercent: number | null; processPercent: number | null;
  dedicatedMemoryBytes: number | null; sharedMemoryBytes: number | null;
};
export type ProcessResources = {
  source: "desktop" | "browser";
  cpuPercent: number | null;
  capacityCpuPercent: number | null;
  coreCpuPercent?: number | null;
  systemCpuPercent?: number | null;
  memoryBytes: number | null;
  hostMemoryBytes: number | null;
  totalMemoryBytes: number | null;
  systemUsedMemoryBytes?: number | null;
  memoryKind?: string;
  logicalCpus: number | null;
  processCount: number | null;
  workerThreads?: number | null;
  workerActive: boolean;
  gpu?: GpuResources;
};
const nonnegative = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
const percent = (value: unknown) => { const number = nonnegative(value); return number === null ? null : Math.min(100, number); };
export function emptyProcessResources(source: ProcessResources["source"]): ProcessResources {
  return { source, cpuPercent: null, capacityCpuPercent: null, memoryBytes: null, hostMemoryBytes: null,
    totalMemoryBytes: null, logicalCpus: null, processCount: null, workerActive: false };
}
export function normalizeProcessResources(raw: ProcessResources): ProcessResources {
  // capacityCpuPercent also handles older hosts whose cpuPercent used core units.
  const cpu = percent(raw.capacityCpuPercent ?? raw.cpuPercent);
  const total = nonnegative(raw.totalMemoryBytes);
  const used = nonnegative(raw.systemUsedMemoryBytes);
  return { ...raw, cpuPercent: cpu, capacityCpuPercent: cpu,
    coreCpuPercent: nonnegative(raw.coreCpuPercent), systemCpuPercent: percent(raw.systemCpuPercent),
    memoryBytes: nonnegative(raw.memoryBytes), hostMemoryBytes: nonnegative(raw.hostMemoryBytes), totalMemoryBytes: total,
    systemUsedMemoryBytes: total !== null && used !== null && used <= total ? used : null,
    gpu: raw.gpu ? { ...raw.gpu, processPercent: percent(raw.gpu.processPercent), systemPercent: percent(raw.gpu.systemPercent),
      dedicatedMemoryBytes: nonnegative(raw.gpu.dedicatedMemoryBytes), sharedMemoryBytes: nonnegative(raw.gpu.sharedMemoryBytes) } : undefined };
}
export function systemMemoryPercent(resources: ProcessResources): number | null {
  const used = resources.source === "desktop" ? resources.systemUsedMemoryBytes : resources.memoryBytes;
  const total = resources.totalMemoryBytes;
  return used != null && total != null && total > 0 && used >= 0 && used <= total ? used / total * 100 : null;
}
