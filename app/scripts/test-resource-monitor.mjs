import assert from "node:assert/strict";
import { emptyProcessResources, normalizeProcessResources, systemMemoryPercent } from "../src/resourceMonitorModel.ts";

const base = { ...emptyProcessResources("desktop"), cpuPercent: 1600, capacityCpuPercent: 50,
  logicalCpus: 32, memoryBytes: 120, totalMemoryBytes: 100, systemUsedMemoryBytes: 75 };
const sample = normalizeProcessResources(base);
assert.equal(sample.cpuPercent, 50, "old core-unit host values must use normalized capacity");
assert.equal(systemMemoryPercent(sample), 75, "system RAM must never use aggregate process RSS");
assert.equal(normalizeProcessResources({ ...base, systemUsedMemoryBytes: 101 }).systemUsedMemoryBytes, null);
for (const value of [NaN, Infinity, -1]) {
  const bad = normalizeProcessResources({ ...base, cpuPercent: value, capacityCpuPercent: value, memoryBytes: value });
  assert.equal(bad.cpuPercent, null);
  assert.equal(bad.memoryBytes, null);
}
const gpu = normalizeProcessResources({ ...base, gpu: { source: "windows-pdh", status: "available",
  processPercent: 150, systemPercent: NaN, dedicatedMemoryBytes: -1, sharedMemoryBytes: 1024 } }).gpu;
assert.equal(gpu.processPercent, 100);
assert.equal(gpu.systemPercent, null);
assert.equal(gpu.dedicatedMemoryBytes, null);
assert.equal(gpu.sharedMemoryBytes, 1024);
assert.equal(systemMemoryPercent(emptyProcessResources("desktop")), null);
assert.equal(systemMemoryPercent({ ...base, source: "browser", memoryBytes: 30 }), 30);
assert.equal(systemMemoryPercent({ ...base, totalMemoryBytes: 0 }), null);
console.log("resource monitor: normalized CPU, system RAM, invalid samples and GPU checks passed");
