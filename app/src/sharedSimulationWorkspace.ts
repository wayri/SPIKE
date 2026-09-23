export type SimulationWorkspaceTab = "Mesh" | "Solve";
export type SimulationDomain = "pi" | "si";

export function workspaceForSimulationAction(action: "configure-mesh" | "extract" | "run"): SimulationWorkspaceTab {
  return action === "run" ? "Solve" : "Mesh";
}

export function simulationDomainLabel(domain: SimulationDomain): string {
  return domain === "pi" ? "Power integrity" : "Signal integrity";
}
