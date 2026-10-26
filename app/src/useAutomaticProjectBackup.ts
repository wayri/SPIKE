// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { ProjectBackupScheduler, type ProjectBackupContext, type ProjectBackupRecord, type ProjectBackupStatus } from "./projectBackupScheduler";
export default function useAutomaticProjectBackup(options: { enabled: boolean; minutes: number; context: () => ProjectBackupContext; save: (context: ProjectBackupContext) => Promise<ProjectBackupRecord> }) {
  const latest = useRef(options); latest.current = options;
  const [status, setStatus] = useState<ProjectBackupStatus>({phase:"idle"});
  const mounted = useRef(true);
  const [scheduler] = useState(() => new ProjectBackupScheduler(() => latest.current.context(), context => latest.current.save(context), value => { if (mounted.current) setStatus(value); }));
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!options.enabled || !Number.isFinite(options.minutes) || options.minutes < 1 || options.minutes > 120) return;
    const timer = window.setInterval(() => { if (latest.current.enabled) void scheduler.tick(); }, options.minutes * 60000);
    return () => window.clearInterval(timer);
  }, [scheduler, options.enabled, options.minutes]);
  return { status, backupNow: () => scheduler.tick(true) };
}
