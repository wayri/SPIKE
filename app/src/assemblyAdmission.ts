import type { AssemblyDesigns, AssemblyIr } from "./mcadAssembly";

export type AssemblyWorkload = "visualization" | "pi_dc" | "pi_ac" | "thermal" | "full_wave";

export type AssemblyAdmissionIssue = {
  code?: string;
  severity?: string;
  message?: string;
};

export type AssemblyAdmissionResult = {
  contract?: string;
  workload?: string;
  state?: string;
  can_admit?: boolean;
  issues?: AssemblyAdmissionIssue[];
  meaning?: string;
};

export type AssemblyAnalysisScope = {
  contract: "spike/assembly-analysis-scope/v1";
  mode: "active_board_only";
  assembly: AssemblyIr;
  active_board_id: string;
  active_design_id: string;
  project_manifest_digest?: string;
};

export function assemblyAnalysisScope(
  assembly: AssemblyIr | null,
  activeDesignId: string | null,
  projectManifestDigest?: string | null,
): AssemblyAnalysisScope | null {
  if (!assembly) return null;
  if (!activeDesignId) throw new Error("The verified active design identity is required for assembly-scoped analysis.");
  const boards = assembly.boards.filter(board => String(board.design_id ?? "").trim() === activeDesignId);
  if (boards.length !== 1) {
    throw new Error(`Assembly-scoped analysis requires exactly one active board instance for design ${activeDesignId}; found ${boards.length}.`);
  }
  const activeBoardId = String(boards[0].id ?? "").trim();
  if (!activeBoardId) throw new Error("The active AssemblyIR board instance has no stable identity.");
  return {
    contract: "spike/assembly-analysis-scope/v1",
    mode: "active_board_only",
    assembly,
    active_board_id: activeBoardId,
    active_design_id: activeDesignId,
    ...(projectManifestDigest ? { project_manifest_digest: projectManifestDigest } : {}),
  };
}

export function assemblyAdmissionParams(
  assembly: AssemblyIr | null,
  activeDesign: Record<string, unknown> | null,
  activeDesignId: string | null,
  workload: AssemblyWorkload,
  memoryLimitGb: number,
  retainedDesigns: AssemblyDesigns | null = null,
): Record<string, unknown> | null {
  if (!assembly) return null;
  const designs: Record<string, Record<string, unknown>> = {};
  for (const design of retainedDesigns?.designs ?? []) {
    if (assembly.boards.some(board => String(board.design_id ?? "").trim() === design.design_id)) {
      designs[design.design_id] = design;
    }
  }
  if (activeDesign && activeDesignId && assembly.boards.some(board => String(board.design_id ?? "").trim() === activeDesignId)) {
    designs[activeDesignId] = activeDesign;
  }
  return {
    assembly,
    designs,
    workload,
    memory_limit_gb: memoryLimitGb,
  };
}

export function requireAdmittedAssembly(result: unknown, workload: AssemblyWorkload): void {
  const value = result && typeof result === "object" && !Array.isArray(result)
    ? result as AssemblyAdmissionResult
    : null;
  if (value?.contract !== "spike/assembly-resource-admission/v1" || value.workload !== workload) {
    throw new Error("Assembly resource admission returned an invalid contract.");
  }
  if (value.can_admit) return;
  const issue = value.issues?.find(item => item.severity === "error" && item.message)?.message
    ?? value.issues?.find(item => item.message)?.message;
  throw new Error(issue ?? `Assembly ${workload.replace(/_/g, " ")} resource admission was blocked.`);
}

export function requireSupportedAssemblyPhysics(assembly: AssemblyIr | null, workload: AssemblyWorkload, activeDesignId: string | null): void {
  if (!assembly) return;
  assemblyAnalysisScope(assembly, activeDesignId);
  void workload;
}
