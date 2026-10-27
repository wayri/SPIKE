// SPDX-License-Identifier: Apache-2.0
import type { WorkerResponse } from "./workerBridge";

/** Presentation handoff to the released PCB copper DC workflow. */
export type GeometryPiInput = {
  design: Record<string, unknown>;
  reviewedSpec: Record<string, unknown>;
  assemblyScope: Record<string, unknown> | null;
};

export type GeometryPiWorker = (request: Record<string, unknown>) => Promise<WorkerResponse>;

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function buildGeometryPiRequest(input: GeometryPiInput): Record<string, unknown> {
  const { design, reviewedSpec, assemblyScope } = input;
  if (!record(design) || !String(design.design_id ?? "").trim()) {
    throw new Error("Load a normalized PCB design before preparing geometry PI.");
  }
  if (!record(reviewedSpec) || reviewedSpec.mode !== "dc") {
    throw new Error("Geometry PI requires the reviewed DC setup.");
  }
  if (reviewedSpec.solver_id && !["auto", "spike.routed_dc"].includes(String(reviewedSpec.solver_id))) {
    throw new Error("Geometry PI uses the existing SPIKE Copper Geometry DC solver.");
  }
  if (reviewedSpec.formulation && !["auto", "resistive_network"].includes(String(reviewedSpec.formulation))) {
    throw new Error("Geometry PI requires the existing resistive-network formulation.");
  }
  return {
    method: "run_preflighted_analysis",
    params: {
      contract: "spike/analysis-request/v1",
      design,
      spec: { ...reviewedSpec, solver_id: "spike.routed_dc", formulation: "resistive_network" },
      assembly_scope: assemblyScope,
    },
  };
}

/** Keep preflight, numerical admission, trust and execution in their existing owners. */
export async function runGeometryPi(input: GeometryPiInput, executeWorker: GeometryPiWorker): Promise<WorkerResponse> {
  const response = await executeWorker(buildGeometryPiRequest(input));
  if (response.ok && response.result?.contract !== "spike/preflighted-analysis/v1") {
    throw new Error("The worker returned no preflighted geometry PI transaction.");
  }
  return response;
}

/** Return only retained solver geometry; unavailable fields remain unavailable. */
export function geometryPiVisualization(transaction: Record<string, unknown> | undefined): Record<string, unknown> | null {
  if (transaction?.contract !== "spike/preflighted-analysis/v1" || !record(transaction.analysis_result)) return null;
  const result = transaction.analysis_result;
  if (result.mode !== "dc" || result.status !== "completed" || !record(result.fields)) return null;
  const visualization = result.fields.visualization;
  return record(visualization) && visualization.schema === "spike/result-visualization/v1"
    && Array.isArray(visualization.mesh) && record(visualization.scalar_fields)
    ? visualization : null;
}
