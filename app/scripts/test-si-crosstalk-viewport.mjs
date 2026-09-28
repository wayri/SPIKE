// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(specifier, context, nextResolve) {
  if (specifier.startsWith(".") && !specifier.endsWith(".ts")) return nextResolve(`${specifier}.ts`, context);
  return nextResolve(specifier, context);
} });
const { admitSiCrosstalkViewport } = await import("../src/siCrosstalkViewport.ts");

const result = {
  binding: { sourceDesignId: "board-1", activeDesignId: "board-1", aggressorNetId: "net-a", victimNetId: "net-v", boardAggressorNetId: "net-a", boardVictimNetId: "net-v" },
  aggressorNet: "/network/ERXD0", victimNet: "/network/ERXD1",
  nextDb: -51.7, fextDb: -56.1, peakNextV: 0.002592, peakFextV: 0.001559,
  modelStatus: "experimental",
};
const names = new Set(["/network/ERXD0", "/network/ERXD1"]);
assert.deepEqual(admitSiCrosstalkViewport(result, names)?.metrics, { nextDb: -51.7, fextDb: -56.1, peakNextV: 0.002592, peakFextV: 0.001559 });
assert.equal(admitSiCrosstalkViewport({ ...result, binding: { ...result.binding, activeDesignId: "other" } }, names), null);
assert.equal(admitSiCrosstalkViewport({ ...result, binding: { ...result.binding, boardVictimNetId: "other" } }, names), null);
assert.equal(admitSiCrosstalkViewport({ ...result, victimNet: "missing" }, names), null);
assert.equal(admitSiCrosstalkViewport({ ...result, nextDb: Number.NaN }, names), null);
assert.equal(admitSiCrosstalkViewport({ ...result, nextDb: undefined, fextDb: undefined, peakNextV: undefined, peakFextV: undefined }, names), null);
console.log("SI board viewport: exact design/net binding and finite global metric admission passed");
