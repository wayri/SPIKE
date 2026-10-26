// SPDX-License-Identifier: Apache-2.0
export type ProjectBackupContext = { key: string; revision: number; dirty: boolean; hasWork: boolean; pausedReason?: string };
export type ProjectBackupRecord = { id: string; created_at: string; project_name: string; path: string; session_id: string; bytes: number };
export type ProjectBackupStatus = { phase: "idle" | "saving" | "saved" | "error" | "paused"; key?: string; record?: ProjectBackupRecord; message?: string };
/** One writer at a time; unchanged dirty revisions are not written repeatedly. */
export class ProjectBackupScheduler {
  private busy = false;
  private completed = new Map<string, number>();
  constructor(private current: () => ProjectBackupContext, private save: (context: ProjectBackupContext) => Promise<ProjectBackupRecord>, private publish: (status: ProjectBackupStatus) => void) {}
  async tick(force = false): Promise<boolean> {
    if (this.busy) return false;
    const context = { ...this.current() };
    if (!context.hasWork) return false;
    if (context.pausedReason) { this.publish({ phase: "paused", key: context.key, message: context.pausedReason }); return false; }
    if (!force && (!context.dirty || this.completed.get(context.key) === context.revision)) return false;
    this.busy = true; this.publish({ phase: "saving", key: context.key });
    try {
      const record = await this.save(context);
      this.completed.set(context.key, context.revision);
      // Old project completion never appears as the current project's recovery state.
      if (this.current().key === context.key) this.publish({ phase: "saved", key: context.key, record });
      return true;
    } catch (error) {
      if (this.current().key === context.key) this.publish({ phase: "error", key: context.key, message: error instanceof Error ? error.message : "Project backup failed." });
      return false;
    } finally { this.busy = false; }
  }
}
