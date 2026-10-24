// SPDX-License-Identifier: Apache-2.0
/** Presentation-only run orchestration. Solver adapters own all admission rules. */
export type GuidedSimulationContext = { key: string; revision: string; workspace: string; title: string };
export type GuidedSimulationRequirement = { id: string; title: string; detail: string; severity: "blocker" | "warning"; route?: string };
export type GuidedSimulationStep = { id: string; title: string; detail: string; route?: string };
export type GuidedSimulationTutorStep = GuidedSimulationStep;
export type GuidedSimulationCheck = { requirements: GuidedSimulationRequirement[]; summary?: string };
export type GuidedSimulationAdapter = {
  check: (context: GuidedSimulationContext, signal: AbortSignal) => Promise<GuidedSimulationCheck>;
  run: (context: GuidedSimulationContext, signal: AbortSignal) => Promise<void>;
};
export type GuidedSimulationState = {
  phase: "idle" | "checking" | "blocked" | "ready" | "running" | "launched" | "error" | "cancelled";
  requirements: GuidedSimulationRequirement[];
  summary?: string;
  error?: string;
};
export const firstGuidedBlocker = (state: GuidedSimulationState) => state.requirements.find(row => row.severity === "blocker");
export const canLaunchGuidedRun = (state: GuidedSimulationState) => state.phase === "ready" && !firstGuidedBlocker(state);

/** Each instance belongs to one immutable project/workspace/revision snapshot. */
export class GuidedSimulationController {
  private state: GuidedSimulationState = { phase: "idle", requirements: [] };
  private listeners = new Set<(state: GuidedSimulationState) => void>();
  private active?: AbortController;
  private epoch = 0;
  private disposed = false;
  readonly context: GuidedSimulationContext;
  constructor(context: GuidedSimulationContext, private adapter: GuidedSimulationAdapter) { this.context = { ...context }; }
  snapshot = () => this.state;
  subscribe = (listener: (state: GuidedSimulationState) => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private set(state: GuidedSimulationState) { this.state = state; this.listeners.forEach(listener => listener(state)); }
  cancel = () => {
    this.epoch++; this.active?.abort(); this.active = undefined;
    if (!this.disposed) this.set({ phase: "cancelled", requirements: [] });
  };
  dispose = () => { this.cancel(); this.disposed = true; this.listeners.clear(); };
  private async execute(launch: boolean) {
    if (this.disposed || this.state.phase === "checking" || this.state.phase === "running" || this.state.phase === "launched") return;
    if (launch && !canLaunchGuidedRun(this.state)) return;
    const epoch = ++this.epoch;
    const operation = new AbortController(); this.active = operation;
    const current = () => !this.disposed && !operation.signal.aborted && this.epoch === epoch;
    this.set({ phase: "checking", requirements: [] });
    try {
      // Run always rechecks; a previous ready badge is never launch authority.
      const result = await this.adapter.check(this.context, operation.signal);
      if (!current()) return;
      if (!result || !Array.isArray(result.requirements) || result.requirements.some(row => !row || !row.id || !row.title || typeof row.detail !== "string" || !["blocker", "warning"].includes(row.severity)) || new Set(result.requirements.map(row => row.id)).size !== result.requirements.length) throw new Error("The setup check returned invalid requirements. Recheck or review the solver setup.");
      const requirements = result.requirements.map(row => ({ ...row }));
      const checked: GuidedSimulationState = { phase: requirements.some(row => row.severity === "blocker") ? "blocked" : "ready", requirements, summary: result.summary };
      this.set(checked);
      if (!launch || !canLaunchGuidedRun(checked) || !current()) return;
      this.set({ ...checked, phase: "running" });
      await this.adapter.run(this.context, operation.signal);
      if (current()) this.set({ ...checked, phase: "launched" });
    } catch (error) {
      if (current()) this.set({ phase: "error", requirements: [], error: error instanceof Error ? error.message : "Setup could not be checked. Review the setup and try again." });
    } finally { if (this.epoch === epoch) this.active = undefined; }
  }
  check = () => this.execute(false);
  launch = () => this.execute(true);
}
