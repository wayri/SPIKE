/**
 * Deterministic planning estimate for local SPIKE workloads.
 *
 * This model is deliberately solver-agnostic. It does not predict numerical
 * convergence, external-engine behaviour, GPU memory use, or operating-system
 * pressure. It only turns a project-shape estimate and an explicit user memory
 * policy into conservative planning budgets.
 */

export const MAX_PLANNED_BOARDS = 20;
export const MAX_COPPER_LAYERS_PER_BOARD = 32;

const MEBIBYTE = 1024 * 1024;
const GIBIBYTE = 1024 * MEBIBYTE;

export type ResourceCapacityInput = {
  /** Physical RAM visible to the desktop worker. Null means it is unknown. */
  availableMemoryBytes: number | null;
  /** Fraction of available RAM SPIKE may plan to use, from 0 to 1. */
  userMemoryFraction?: number;
  /** Optional absolute cap. The lower of this and the fractional cap is used. */
  userMemoryLimitBytes?: number | null;
  boardCount: number;
  /** A single value applies to every board; an array permits mixed assemblies. */
  copperLayers: number | readonly number[];
  components: number;
  tracks: number;
  vias: number;
  pads: number;
  zones: number;
  requestedMeshCells: number;
};

export type CapacityReasonSeverity = "info" | "warning" | "error";

export type CapacityReason = {
  code:
    | "CAPACITY_MEMORY_UNKNOWN"
    | "CAPACITY_MEMORY_POLICY_INVALID"
    | "CAPACITY_PROJECT_INPUT_INVALID"
    | "CAPACITY_BOARD_LIMIT"
    | "CAPACITY_LAYER_LIMIT"
    | "CAPACITY_REQUEST_EXCEEDS_BUDGET"
    | "CAPACITY_REQUEST_ABOVE_RECOMMENDED"
    | "CAPACITY_PLAN_RECOMMENDED";
  severity: CapacityReasonSeverity;
  message: string;
};

export type CapacityStatus =
  | "admissible"
  | "admissible_with_caution"
  | "inadmissible"
  | "needs_memory_profile";

export type ResourceCapacityPlan = {
  status: CapacityStatus;
  isAdmissible: boolean;
  /** Always present so callers must communicate the model limits. */
  disclaimer: string;
  policy: {
    availableMemoryBytes: number | null;
    userMemoryFraction: number;
    userMemoryLimitBytes: number | null;
    effectiveMemoryBudgetBytes: number | null;
  };
  requested: {
    boardCount: number;
    copperLayersPerBoard: readonly number[];
    components: number;
    tracks: number;
    vias: number;
    pads: number;
    zones: number;
    meshCells: number;
  };
  estimates: {
    geometryBytes: number;
    viewportBytes: number;
    runtimeReserveBytes: number;
    meshBytesPerCell: number;
    solverBytesPerCell: number;
    resultBytesPerCell: number;
    totalBytesPerMeshCell: number;
    requestedWorkingSetBytes: number;
  };
  budgets: {
    fixedBytes: number;
    remainingBytes: number | null;
    admissibleMeshCells: number | null;
    recommendedMeshCells: number | null;
  };
  reasons: readonly CapacityReason[];
};

const nonNegativeFields = ["components", "tracks", "vias", "pads", "zones", "requestedMeshCells"] as const;

function isFiniteNonNegative(value: number): boolean {
  return Number.isFinite(value) && value >= 0;
}

function cleanCount(value: number): number {
  return isFiniteNonNegative(value) ? Math.floor(value) : 0;
}

function expandLayerCounts(copperLayers: ResourceCapacityInput["copperLayers"], boardCount: number): number[] {
  if (typeof copperLayers !== "number") return Array.from(copperLayers);
  return Array.from({ length: Math.max(0, boardCount) }, () => copperLayers);
}

/**
 * Estimate project capacity without invoking a solver. The constants reserve
 * memory for a connected-conductor mesh, sparse-system work buffers, result
 * samples and the viewport. They are intentionally not a solver contract.
 */
export function planResourceCapacity(input: ResourceCapacityInput): ResourceCapacityPlan {
  const reasons: CapacityReason[] = [];
  const boardCount = cleanCount(input.boardCount);
  const copperLayersPerBoard = expandLayerCounts(input.copperLayers, boardCount);
  const components = cleanCount(input.components);
  const tracks = cleanCount(input.tracks);
  const vias = cleanCount(input.vias);
  const pads = cleanCount(input.pads);
  const zones = cleanCount(input.zones);
  const meshCells = cleanCount(input.requestedMeshCells);
  const defaultFraction = 0.65;
  const userMemoryFraction = input.userMemoryFraction ?? defaultFraction;
  const userMemoryLimitBytes = input.userMemoryLimitBytes ?? null;
  const availableMemoryBytes = input.availableMemoryBytes;

  if (!Number.isInteger(input.boardCount) || input.boardCount < 1) {
    reasons.push({ code: "CAPACITY_PROJECT_INPUT_INVALID", severity: "error", message: "Board count must be a positive integer." });
  }
  for (const field of nonNegativeFields) {
    if (!isFiniteNonNegative(input[field])) {
      reasons.push({ code: "CAPACITY_PROJECT_INPUT_INVALID", severity: "error", message: `${field} must be a finite non-negative count.` });
    }
  }
  if (copperLayersPerBoard.length !== boardCount || copperLayersPerBoard.some(layerCount => !Number.isInteger(layerCount) || layerCount < 1)) {
    reasons.push({ code: "CAPACITY_PROJECT_INPUT_INVALID", severity: "error", message: "Copper layers must provide one positive integer count for every board." });
  }
  if (boardCount > MAX_PLANNED_BOARDS) {
    reasons.push({ code: "CAPACITY_BOARD_LIMIT", severity: "error", message: `The resource planner supports at most ${MAX_PLANNED_BOARDS} boards per assembly.` });
  }
  if (copperLayersPerBoard.some(layerCount => layerCount > MAX_COPPER_LAYERS_PER_BOARD)) {
    reasons.push({ code: "CAPACITY_LAYER_LIMIT", severity: "error", message: `Each board may contain at most ${MAX_COPPER_LAYERS_PER_BOARD} copper layers in this planner.` });
  }

  const validFraction = Number.isFinite(userMemoryFraction) && userMemoryFraction > 0 && userMemoryFraction <= 1;
  const validMemoryLimit = userMemoryLimitBytes === null || isFiniteNonNegative(userMemoryLimitBytes) && userMemoryLimitBytes > 0;
  const validAvailableMemory = availableMemoryBytes !== null && isFiniteNonNegative(availableMemoryBytes) && availableMemoryBytes > 0;
  if (!validFraction || !validMemoryLimit) {
    reasons.push({ code: "CAPACITY_MEMORY_POLICY_INVALID", severity: "error", message: "Memory fraction must be in (0, 1] and memory limit must be positive when supplied." });
  }

  const effectiveMemoryBudgetBytes = validFraction && validMemoryLimit
    ? validAvailableMemory
      ? Math.floor(Math.min(availableMemoryBytes * userMemoryFraction, userMemoryLimitBytes ?? Number.POSITIVE_INFINITY))
      : userMemoryLimitBytes
    : null;
  if (effectiveMemoryBudgetBytes === null) {
    reasons.push({ code: "CAPACITY_MEMORY_UNKNOWN", severity: "warning", message: "No usable memory budget is available. Supply detected RAM or an explicit user memory limit." });
  }

  const totalLayers = copperLayersPerBoard.reduce((sum, layerCount) => sum + cleanCount(layerCount), 0);
  // Geometry allocation includes indexed source geometry and derived viewport buffers.
  const geometryBytes = components * 2_048 + tracks * 640 + vias * 896 + pads * 640 + zones * 12_288 + totalLayers * 48_000;
  const viewportBytes = Math.max(96 * MEBIBYTE, Math.ceil(geometryBytes * 0.75));
  const runtimeReserveBytes = Math.max(256 * MEBIBYTE, Math.min(2 * GIBIBYTE, Math.ceil((effectiveMemoryBudgetBytes ?? 0) * 0.12)));
  const averageLayers = totalLayers / Math.max(1, boardCount);
  const meshBytesPerCell = 352;
  const solverBytesPerCell = Math.ceil(896 + averageLayers * 24);
  const resultBytesPerCell = 256;
  const totalBytesPerMeshCell = meshBytesPerCell + solverBytesPerCell + resultBytesPerCell;
  const fixedBytes = geometryBytes + viewportBytes + runtimeReserveBytes;
  const requestedWorkingSetBytes = fixedBytes + meshCells * totalBytesPerMeshCell;
  const remainingBytes = effectiveMemoryBudgetBytes === null ? null : effectiveMemoryBudgetBytes - fixedBytes;
  const admissibleMeshCells = remainingBytes === null ? null : Math.max(0, Math.floor(remainingBytes / totalBytesPerMeshCell));
  // Keep 30% headroom for sparse fill-in, imports, browser allocations and OS pressure.
  const recommendedMeshCells = admissibleMeshCells === null ? null : Math.floor(admissibleMeshCells * 0.7);

  if (effectiveMemoryBudgetBytes !== null && requestedWorkingSetBytes > effectiveMemoryBudgetBytes) {
    reasons.push({ code: "CAPACITY_REQUEST_EXCEEDS_BUDGET", severity: "error", message: `Requested mesh requires an estimated ${requestedWorkingSetBytes} bytes, above the configured ${effectiveMemoryBudgetBytes}-byte memory budget.` });
  } else if (recommendedMeshCells !== null && meshCells > recommendedMeshCells) {
    reasons.push({ code: "CAPACITY_REQUEST_ABOVE_RECOMMENDED", severity: "warning", message: `Requested mesh is within the hard estimate but above the recommended ${recommendedMeshCells}-cell budget.` });
  } else if (admissibleMeshCells !== null) {
    reasons.push({ code: "CAPACITY_PLAN_RECOMMENDED", severity: "info", message: `Requested mesh is within the recommended ${recommendedMeshCells}-cell planning budget.` });
  }

  const hasError = reasons.some(reason => reason.severity === "error");
  const hasMemoryProfile = effectiveMemoryBudgetBytes !== null;
  const status: CapacityStatus = hasError
    ? "inadmissible"
    : !hasMemoryProfile
      ? "needs_memory_profile"
      : reasons.some(reason => reason.code === "CAPACITY_REQUEST_ABOVE_RECOMMENDED")
        ? "admissible_with_caution"
        : "admissible";

  return {
    status,
    isAdmissible: status === "admissible" || status === "admissible_with_caution",
    disclaimer: "This is a conservative planning estimate, not a guarantee of solver convergence, numerical accuracy, external-engine availability, GPU capacity, or operating-system stability.",
    policy: { availableMemoryBytes, userMemoryFraction, userMemoryLimitBytes, effectiveMemoryBudgetBytes },
    requested: { boardCount, copperLayersPerBoard, components, tracks, vias, pads, zones, meshCells },
    estimates: {
      geometryBytes,
      viewportBytes,
      runtimeReserveBytes,
      meshBytesPerCell,
      solverBytesPerCell,
      resultBytesPerCell,
      totalBytesPerMeshCell,
      requestedWorkingSetBytes,
    },
    budgets: { fixedBytes, remainingBytes, admissibleMeshCells, recommendedMeshCells },
    reasons,
  };
}
