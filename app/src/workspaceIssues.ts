export type WorkspaceIssue = { kind: "info" | "warning" | "ok"; title: string; detail: string };

/** Empty workspaces are setup states, not failed analyses or successful imports. */
export function workspaceIssues(input: {
  hasBoard: boolean; workspace: string; mode: string; stackupComplete: boolean;
  components: number; nets: number; copperLayers: number; stackRows: number;
  convergence?: unknown; convergenceLevels?: unknown;
}): WorkspaceIssue[] {
  if (!input.hasBoard) return [{ kind: "info", title: "No design loaded",
    detail: "Import a board or open a SPIKE project to begin. The empty scene is a preview, not an analysis result." }];
  const issues: WorkspaceIssue[] = [];
  if (["Home", "PI", "Results"].includes(input.workspace) && input.mode === "DC IR Drop") {
    issues.push(input.convergence === "passed"
      ? { kind: "ok", title: "Mesh convergence passed", detail: `${typeof input.convergenceLevels === "number" && Number.isFinite(input.convergenceLevels) ? input.convergenceLevels : 0} mesh levels passed the configured numerical stability thresholds. This does not establish physical signoff.` }
      : { kind: "info", title: "DC convergence review", detail: "Run the configured DC solve and mesh-convergence review before relying on its numerical result." });
  }
  if (["Home", "PI", "HF / SI", "EM", "EMI"].includes(input.workspace)) {
    issues.push(input.stackupComplete
      ? { kind: "ok", title: "Stackup available", detail: `${input.stackRows} stack rows include copper thickness and dielectric properties.` }
      : { kind: "warning", title: "Stackup needs attention", detail: "Open Stackup to supply missing thickness or dielectric properties before high-frequency extraction." });
  }
  issues.push({ kind: "info", title: "Design loaded", detail: `${input.components} components, ${input.nets} nets, ${input.copperLayers} copper layers. Check import/model diagnostics separately; loading is not solver validation.` });
  return issues;
}
