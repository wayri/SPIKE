import assert from "node:assert/strict";
import { MAX_COPPER_LAYERS_PER_BOARD, MAX_PLANNED_BOARDS, planResourceCapacity } from "../src/resourceCapacity.ts";

const GiB = 1024 ** 3;
const typical = {
  availableMemoryBytes: 64 * GiB,
  userMemoryFraction: 0.75,
  boardCount: 1,
  copperLayers: 12,
  components: 4_000,
  tracks: 25_000,
  vias: 8_000,
  pads: 12_000,
  zones: 24,
  requestedMeshCells: 100_000,
};

const normal = planResourceCapacity(typical);
assert.equal(normal.status, "admissible");
assert.equal(normal.isAdmissible, true);
assert.ok(normal.budgets.admissibleMeshCells > normal.budgets.recommendedMeshCells);
assert.ok(normal.estimates.requestedWorkingSetBytes < normal.policy.effectiveMemoryBudgetBytes);
assert.match(normal.disclaimer, /not a guarantee/i);

const scaledAssembly = planResourceCapacity({
  ...typical,
  availableMemoryBytes: 256 * GiB,
  boardCount: MAX_PLANNED_BOARDS,
  copperLayers: MAX_COPPER_LAYERS_PER_BOARD,
  components: 80_000,
  tracks: 600_000,
  vias: 250_000,
  pads: 500_000,
  zones: 400,
  requestedMeshCells: 2_000_000,
});
assert.equal(scaledAssembly.isAdmissible, true);
assert.equal(scaledAssembly.requested.copperLayersPerBoard.length, MAX_PLANNED_BOARDS);
assert.ok(scaledAssembly.requested.copperLayersPerBoard.every(layers => layers === MAX_COPPER_LAYERS_PER_BOARD));

const overBoardLimit = planResourceCapacity({ ...typical, boardCount: MAX_PLANNED_BOARDS + 1 });
assert.equal(overBoardLimit.status, "inadmissible");
assert.ok(overBoardLimit.reasons.some(reason => reason.code === "CAPACITY_BOARD_LIMIT"));

const overLayerLimit = planResourceCapacity({ ...typical, copperLayers: MAX_COPPER_LAYERS_PER_BOARD + 1 });
assert.equal(overLayerLimit.status, "inadmissible");
assert.ok(overLayerLimit.reasons.some(reason => reason.code === "CAPACITY_LAYER_LIMIT"));

const userCap = planResourceCapacity({ ...typical, userMemoryFraction: 1, userMemoryLimitBytes: 4 * GiB });
assert.equal(userCap.policy.effectiveMemoryBudgetBytes, 4 * GiB);

const cautiousBaseline = planResourceCapacity({ ...typical, availableMemoryBytes: 8 * GiB, userMemoryFraction: 0.75, requestedMeshCells: 1 });
const cautious = planResourceCapacity({
  ...typical,
  availableMemoryBytes: 8 * GiB,
  userMemoryFraction: 0.75,
  requestedMeshCells: cautiousBaseline.budgets.recommendedMeshCells + 1,
});
assert.equal(cautious.status, "admissible_with_caution");
assert.equal(cautious.isAdmissible, true);

const tooLarge = planResourceCapacity({
  ...typical,
  availableMemoryBytes: 8 * GiB,
  requestedMeshCells: cautiousBaseline.budgets.admissibleMeshCells + 1,
});
assert.equal(tooLarge.status, "inadmissible");
assert.ok(tooLarge.reasons.some(reason => reason.code === "CAPACITY_REQUEST_EXCEEDS_BUDGET"));

const noMemoryProfile = planResourceCapacity({ ...typical, availableMemoryBytes: null, userMemoryLimitBytes: null });
assert.equal(noMemoryProfile.status, "needs_memory_profile");
assert.equal(noMemoryProfile.budgets.admissibleMeshCells, null);
assert.ok(noMemoryProfile.reasons.some(reason => reason.code === "CAPACITY_MEMORY_UNKNOWN"));

console.log("resource capacity: all assertions passed");
